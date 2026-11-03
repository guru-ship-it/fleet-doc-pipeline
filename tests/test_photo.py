"""The photo step: SAM's boxes are parsed, the paper is cropped and straightened in code, a SAM failure keeps the
original (logged), the record carries what happened, and the residency guard covers the photo model too."""
import io
import math

import pytest
from PIL import Image, ImageDraw

from conftest import A, C, FILES, consent, run, wa

from pipeline import photo as ph
from pipeline.errors import ModelCallError, ResidencyError
from pipeline.intake import handle_payload
from pipeline.photo import SamPhoto, parse_boxes, skew_angle

SAM_TEXT = "<0f>0<|box;x1=120;y1=80;x2=620;y2=780;w=1139;h=954|><|mask;abc|>,1<|box;x1=5;y1=5;x2=40;y2=40;w=1139;h=954|>"


def page_image(angle: float, on_desk: bool = True) -> bytes:
    """A white page with dark text lines, rotated by angle, on a dark desk (or filling the frame)."""
    page = Image.new("RGB", (600, 840), "white")
    d = ImageDraw.Draw(page)
    for y in range(80, 800, 36):
        d.rectangle((60, y, 540, y + 10), fill=(30, 30, 30))
    page = page.rotate(angle, expand=True, fillcolor=(90, 70, 50) if on_desk else "white", resample=Image.BICUBIC)
    if on_desk:
        desk = Image.new("RGB", (page.width + 400, page.height + 300), (90, 70, 50))
        desk.paste(page, (200, 150))
        page = desk
    buf = io.BytesIO()
    page.save(buf, "JPEG", quality=92)
    return buf.getvalue()


class FakeSam(SamPhoto):
    """SamPhoto with the network call replaced: returns a box around the bright paper, or raises."""
    def __init__(self, fail=False):
        super().__init__("https://example.invalid", "key", "sam-3.1")
        self.fail, self.calls = fail, 0

    def segment(self, im):
        self.calls += 1
        if self.fail:
            raise ModelCallError("Model returned HTTP 503")
        bbox = im.convert("L").point(lambda v: 255 if v > 200 else 0).getbbox()
        x1, y1, x2, y2 = bbox
        return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2, "w": x2 - x1, "h": y2 - y1, "img_w": im.width, "img_h": im.height}]


def test_sam_output_tokens_are_parsed_in_order():
    boxes = parse_boxes(SAM_TEXT)
    assert [(b["w"], b["h"], b["img_w"], b["img_h"]) for b in boxes] == [(500, 700, 1139, 954), (35, 35, 1139, 954)]
    assert parse_boxes("") == [] and parse_boxes("no boxes here") == []
    half = Image.new("RGB", (570, 477))       # SAM worked on 1139x954; our image is half that
    scaled = ph.scale_box(boxes[0], half)
    assert (round(scaled["x1"]), round(scaled["x2"]), round(scaled["w"])) == (60, 310, 250)
    assert ph.output_text({"output": [{"content": [{"type": "output_text", "text": "a"}, {"type": "other", "text": "x"}]},
                                      {"content": [{"type": "output_text", "text": "b"}]}]}) == "ab"


def test_tilted_photo_on_a_desk_is_cropped_and_straightened():
    sam = FakeSam()
    pages, info = sam.prepare([(page_image(7), "image/jpeg")], "f" * 64)
    assert sam.calls == 1 and info["cropped"] and 0.2 < info["cover"] < 0.9
    assert math.isclose(info["angle_deg"], -7, abs_tol=1.5)            # PIL rotates counter-clockwise; undoing +7 is -7
    out = Image.open(io.BytesIO(pages[0][0]))
    assert pages[0][1] == "image/jpeg" and out.width < 1000           # the desk is gone
    assert abs(skew_angle(out)) < 1.0                                 # a second pass finds nothing left to fix


def test_scan_with_paper_to_the_edges_skips_sam_and_keeps_the_bytes():
    sam = FakeSam()
    scan = page_image(0, on_desk=False)
    pages, info = sam.prepare([(scan, "image/jpeg")], "f" * 64)
    assert sam.calls == 0 and info["called"] is False and not info["cropped"]
    assert pages == [(scan, "image/jpeg")]                               # untouched, so nothing is re-encoded


def test_sam_failure_keeps_the_original_and_is_recorded():
    sam = FakeSam(fail=True)
    pages, info = sam.prepare([(page_image(7), "image/jpeg")], "f" * 64)
    assert not info["cropped"] and "error" in info and pages[0][1] == "image/jpeg"


def test_worker_records_the_photo_step(env):
    env.photo = FakeSam()
    FILES["INVOICE_A"] = page_image(5)      # the stand-in model still answers by file hash, so patch the reading too
    import hashlib
    env.model.readings[hashlib.sha256(FILES["INVOICE_A"]).hexdigest()] = env.model.readings[
        hashlib.sha256(b"jpeg-invoice-cab-A").hexdigest()]
    try:
        consent(env, A)
        handle_payload(wa(A, media="INVOICE_A"), env)
        rec, = run(env)
        assert rec["outcome"] == "accepted" and rec["photo"]["cropped"] is True and env.photo.calls == 1
    finally:
        FILES["INVOICE_A"] = b"jpeg-invoice-cab-A"


def test_residency_guard_covers_the_photo_model(env):
    env.photo = FakeSam()                    # in_india is False, like the real one
    consent(env, C, "हाँ")                   # a real driver
    handle_payload(wa(C, media="DOC_C"), env)
    with pytest.raises(ResidencyError):
        run(env)
    assert env.photo.calls == 0
