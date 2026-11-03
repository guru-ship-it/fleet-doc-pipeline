"""Turn the clean synthetic bill into what a driver actually sends: a phone photo of the bill lying tilted on a
car seat, with the surroundings in frame. Synthetic in, synthetic out; this is the input for the SAM photo step.

    python demo/make_tilted_photo.py
"""
import pathlib
import random

from PIL import Image, ImageDraw, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "demo" / "synthetic" / "bill_TS09XY4521_service_demo.png"
OUT = ROOT / "demo" / "synthetic" / "photo_TS09XY4521_tilted_demo.jpg"


def main() -> None:
    random.seed(7)
    bill = Image.open(SRC).convert("RGB")
    bill = bill.resize((round(bill.width * 0.62), round(bill.height * 0.62)), Image.LANCZOS)
    # a faint paper shadow and a slight warm cast, as a phone camera would give
    paper = Image.new("RGB", (bill.width + 16, bill.height + 16), (236, 232, 222))
    paper.paste(bill, (8, 8))
    tilted = paper.rotate(7.5, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0))
    mask = Image.new("L", paper.size, 255).rotate(7.5, expand=True, resample=Image.BICUBIC, fillcolor=0)
    shadow = Image.new("L", mask.size, 0)
    shadow.paste(mask, (14, 18))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))

    w, h = tilted.width + 420, tilted.height + 360
    seat = Image.new("RGB", (w, h), (58, 54, 52))
    d = ImageDraw.Draw(seat)
    for i in range(0, w + h, 26):                      # stitched seat fabric
        d.line((i, 0, i - h, h), fill=(66, 62, 60), width=9)
    for _ in range(2200):                              # grain
        x, y = random.randrange(w), random.randrange(h)
        d.point((x, y), fill=(random.randrange(48, 78),) * 3)
    dark = Image.new("RGB", seat.size, (30, 28, 27))
    sh = Image.new("L", seat.size, 0)
    sh.paste(shadow, (210, 180))
    seat = Image.composite(dark, seat, sh.point(lambda v: int(v * 0.6)))
    seat.paste(tilted, (196, 162), mask)
    seat = seat.filter(ImageFilter.GaussianBlur(0.4))
    seat.save(OUT, "JPEG", quality=86)
    print("%s  %dx%d  %.0f KB" % (OUT.relative_to(ROOT), seat.width, seat.height, OUT.stat().st_size / 1024))


if __name__ == "__main__":
    main()
