from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont


def _exif(captured_at: datetime) -> Image.Exif:
    exif = Image.Exif()
    exif[36867] = captured_at.strftime("%Y:%m:%d %H:%M:%S")
    exif[37521] = f"{captured_at.microsecond:06d}"
    return exif


def _command_image(payload: str, captured_at: datetime, destination: Path) -> None:
    qr = qrcode.make(payload).convert("RGB").resize((700, 700), Image.Resampling.NEAREST)
    image = Image.new("RGB", (1000, 1200), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 960, 1160), radius=28, outline="#187a69", width=12)
    image.paste(qr, (150, 220))
    draw.text((500, 110), payload, anchor="mm", fill="#12302b", font=ImageFont.load_default(size=28))
    draw.text((500, 1030), "SNAPIMS COMMAND - NOT A PRODUCT IMAGE", anchor="mm", fill="#187a69", font=ImageFont.load_default(size=24))
    image.save(destination, format="JPEG", quality=95, exif=_exif(captured_at))


def _product_image(
    title: str, view: str, color: str, captured_at: datetime, destination: Path
) -> None:
    image = Image.new("RGB", (1100, 1500), color)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((80, 80, 1020, 1420), radius=32, fill="#f7f2e8", outline="#1b2430", width=12)
    draw.text((550, 360), "CANADA VHS", anchor="mm", fill="#b23a48", font=ImageFont.load_default(size=54))
    draw.text((550, 680), title, anchor="mm", fill="#17213a", font=ImageFont.load_default(size=74))
    draw.text((550, 910), view, anchor="mm", fill="#5d6470", font=ImageFont.load_default(size=44))
    draw.rectangle((250, 1080, 850, 1280), outline="#17213a", width=16)
    draw.ellipse((350, 1110, 500, 1260), outline="#17213a", width=12)
    draw.ellipse((600, 1110, 750, 1260), outline="#17213a", width=12)
    image.save(destination, format="JPEG", quality=95, exif=_exif(captured_at))


def create_demo_batch(destination: Path, *, start_at: datetime | None = None) -> Path:
    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Demo destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    start = start_at or datetime(2026, 7, 16, 12, 0, 0)
    sequence = [
        ("command", "CVHS1:BATCH:START", ""),
        ("command", "CVHS1:LOC:B2", ""),
        ("product", "THE LAST SIGNAL", "FRONT"),
        ("product", "THE LAST SIGNAL", "BACK"),
        ("command", "CVHS1:ITEM:NEXT", ""),
        ("command", "CVHS1:FLAG:RARE", ""),
        ("command", "CVHS1:FLAG:REVIEW", ""),
        ("product", "MIDNIGHT REWIND", "FRONT"),
        ("product", "MIDNIGHT REWIND", "OPEN CASE"),
        ("command", "CVHS1:BATCH:END", ""),
    ]
    for index, (kind, value, view) in enumerate(sequence):
        captured = start + timedelta(seconds=index, microseconds=index * 1000)
        path = destination / f"PXL_20260716_1200{index:02d}{index:03d}.jpg"
        if kind == "command":
            _command_image(value, captured, path)
        else:
            color = "#9bc5c3" if "LAST" in value else "#c9a8d8"
            _product_image(value, view, color, captured, path)
    return destination
