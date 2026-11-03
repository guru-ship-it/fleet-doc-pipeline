"""Photo clean-up before reading. A driver's photo of a bill is rarely flat or framed: it sits on a car seat or a
counter, tilted, with the surroundings in frame. SAM 3.1 (Meta's segmentation model, through the Model API) finds
the paper; code crops to it and straightens it; Muse then reads a clean page. SAM only finds, it decides nothing,
and a failed SAM call falls back to the original photo, logged, never hidden.

Like Muse, SAM is hosted outside India, so the worker's residency guard covers it too: synthetic documents only."""
import base64
import io
import re
import time

from PIL import Image, ImageOps, ImageStat

from . import bridge, logs
from .errors import ModelCallError

PROMPT = "paper document"
BOX = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)\|>")
MAX_SIDE = 1600                  # long side sent to the models; phone photos are 3000 to 4000 px
MIN_COVER, MAX_COVER = 0.12, 0.92   # crop only when the paper is a clear part of the frame, not the whole frame
MARGIN = 0.02                    # kept around the box, as a share of the box size
MAX_SKEW = 12                    # degrees searched either way when straightening
MIN_SKEW = 0.6                   # below this the page is left alone
BRIGHT_BORDER = 170              # a border this bright on every side is paper to the edges: a scan, not a photo


def parse_boxes(text: str) -> list:
    """Every box in SAM's special-token output, in order. In the token, w and h are the size of the image SAM
    worked on, not the box; the box is x1, y1, x2, y2 in that image's pixels. No boxes means nothing found."""
    boxes = []
    for m in BOX.finditer(text or ""):
        x1, y1, x2, y2, img_w, img_h = (int(v) for v in m.groups())
        boxes.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "w": x2 - x1, "h": y2 - y1, "img_w": img_w, "img_h": img_h})
    return boxes


def scale_box(box: dict, im: Image.Image) -> dict:
    """SAM's pixels mapped onto our image, in case SAM worked at another size."""
    sx = im.width / box["img_w"] if box.get("img_w") else 1.0
    sy = im.height / box["img_h"] if box.get("img_h") else 1.0
    if abs(sx - 1) < 0.01 and abs(sy - 1) < 0.01:
        return box
    return dict(box, x1=box["x1"] * sx, y1=box["y1"] * sy, x2=box["x2"] * sx, y2=box["y2"] * sy,
                w=box["w"] * sx, h=box["h"] * sy)


def needs_finding(im: Image.Image) -> bool:
    """A scan or screenshot has paper out to the edges; a photo has the seat or the counter around it. Only the
    photo needs SAM, so a bright border on all four sides skips the call."""
    grey = im.convert("L")
    bw, bh = max(2, int(im.width * 0.06)), max(2, int(im.height * 0.06))
    strips = (grey.crop((0, 0, im.width, bh)), grey.crop((0, im.height - bh, im.width, im.height)),
              grey.crop((0, 0, bw, im.height)), grey.crop((im.width - bw, 0, im.width, im.height)))
    return min(ImageStat.Stat(s).mean[0] for s in strips) < BRIGHT_BORDER


def output_text(response: dict) -> str:
    """The text parts of a Responses API answer, joined (the SDK's output_text, without the SDK)."""
    parts = []
    for item in response.get("output") or []:
        for c in item.get("content") or []:
            if c.get("type") == "output_text" and c.get("text"):
                parts.append(c["text"])
    return "".join(parts)


def normalize(data: bytes) -> Image.Image:
    """Honour the camera's orientation tag, drop alpha, and cap the long side."""
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    longest = max(im.size)
    if longest > MAX_SIDE:
        scale = MAX_SIDE / longest
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    return im


def to_jpeg(im: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def data_url(im: Image.Image) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(to_jpeg(im, 85)).decode("ascii")


def crop_to(im: Image.Image, box: dict) -> Image.Image:
    mx, my = box["w"] * MARGIN, box["h"] * MARGIN
    left, top = max(0, int(box["x1"] - mx)), max(0, int(box["y1"] - my))
    right, bottom = min(im.width, int(box["x2"] + mx)), min(im.height, int(box["y2"] + my))
    return im.crop((left, top, right, bottom))


def _line_score(small: Image.Image, angle: float) -> float:
    """How strongly text lines read as horizontal after rotating by angle: variance of the row means."""
    rows = list(small.rotate(angle, resample=Image.BILINEAR, fillcolor=0).resize((1, small.height), Image.BOX).getdata())
    mean = sum(rows) / len(rows)
    return sum((r - mean) ** 2 for r in rows) / len(rows)


def skew_angle(im: Image.Image) -> float:
    """The rotation (degrees, PIL's counter-clockwise sense) that makes the page's text lines horizontal. Measured
    on the central 60% of the image: after a crop to a tilted page, the corners still hold the seat or the counter."""
    w, h = im.size
    core = im.crop((int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8))).convert("L")
    small = ImageOps.autocontrast(core)
    scale = 400 / small.width
    small = small.resize((400, max(1, round(small.height * scale))), Image.BOX)
    small = small.point(lambda v: 255 if v < 128 else 0)    # ink becomes bright, paper dark
    best = max(range(-MAX_SKEW, MAX_SKEW + 1), key=lambda a: _line_score(small, a))
    fine = [best + d / 4 for d in range(-4, 5)]
    return max(fine, key=lambda a: _line_score(small, a))


def trim_to_paper(im: Image.Image) -> Image.Image:
    """Crop to the bright region (the page), dropping dark surroundings and the dark fill a rotation leaves."""
    bbox = im.convert("L").point(lambda v: 255 if v > 150 else 0).getbbox()
    if not bbox:
        return im
    if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < 0.3 * im.width * im.height:   # too small to be the page
        return im
    return im.crop(bbox)


def straighten(im: Image.Image) -> tuple:
    """(image, angle applied). Rotation fills with dark grey so the page can be trimmed out cleanly afterwards."""
    angle = skew_angle(im)
    if abs(angle) < MIN_SKEW:
        return im, 0.0
    rotated = im.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(40, 40, 40))
    return trim_to_paper(rotated), round(angle, 2)


class SamPhoto:
    """Find the paper with SAM 3.1, then crop and straighten in code."""
    in_india = False

    def __init__(self, base_url: str, api_key: str, model_id: str):
        if not (base_url and api_key and model_id):
            raise ModelCallError("Photo model settings are missing (base URL, key or model id)")
        self.base_url, self.api_key, self.model_id = base_url, api_key, model_id

    def segment(self, im: Image.Image) -> list:
        body = {"model": self.model_id, "input": [{"role": "user", "content": [
            {"type": "input_text", "text": PROMPT}, {"type": "input_image", "image_url": data_url(im)}]}]}
        out, _ = bridge.model_responses(self.base_url, self.api_key, body)
        return parse_boxes(output_text(out))

    def prepare(self, pages: list, file_hash: str) -> tuple:
        """([(bytes, mime)], info) for one photographed page. A scan is passed through untouched; a photo goes to
        SAM, then crop and straighten; a SAM failure keeps the original, logged."""
        t0 = time.monotonic()
        data, mime = pages[0]
        im = normalize(data)
        info = {"model": self.model_id, "called": False, "cropped": False, "cover": None, "angle_deg": 0.0}
        if not needs_finding(im):
            info["ms"] = round((time.monotonic() - t0) * 1000)
            logs.event("PHOTO_READ_AS_SENT", file=file_hash[:12], reason="paper fills the frame", ms=info["ms"])
            big = max(Image.open(io.BytesIO(data)).size) > MAX_SIDE
            return ([(to_jpeg(im), "image/jpeg")] if big else [(data, mime)]), info
        info["called"] = True
        try:
            boxes = self.segment(im)
        except ModelCallError as e:
            info["error"] = str(e)[:80]
            logs.event("PHOTO_STEP_FAILED", "error", file=file_hash[:12], error=type(e).__name__)
            return [(to_jpeg(im), "image/jpeg")], dict(info, ms=round((time.monotonic() - t0) * 1000))
        if boxes:
            box = scale_box(max(boxes, key=lambda b: b["w"] * b["h"]), im)
            info["cover"] = round(box["w"] * box["h"] / float(im.width * im.height), 3)
            if MIN_COVER <= info["cover"] <= MAX_COVER:
                im, info["cropped"] = crop_to(im, box), True
        im, info["angle_deg"] = straighten(im)
        info["ms"] = round((time.monotonic() - t0) * 1000)
        logs.event("PHOTO_PREPARED", file=file_hash[:12], model=self.model_id, boxes=len(boxes), cover=info["cover"],
                   cropped=info["cropped"], angle_deg=info["angle_deg"], ms=info["ms"])
        return [(to_jpeg(im), "image/jpeg")], info
