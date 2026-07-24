from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path

from PIL import Image, ImageDraw


def _image(path: Path, label: str, when: datetime) -> None:
    image = Image.new("RGB", (900, 1200), "#d7c7a3")
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 70, 830, 1130), outline="#241f18", width=12)
    draw.text((110, 130), label, fill="#241f18")
    image.save(path, quality=92)
    timestamp = when.timestamp()
    path.touch()
    os.utime(path, (timestamp, timestamp))


def create_demo_batch(folder: Path, *, item_count: int = 2, photos_per_item: int = 2, shelf: str = "B2") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    when = datetime(2026, 7, 23, 15, 26, 0)
    index = 0

    def command(payload: str) -> None:
        nonlocal index, when
        path = folder / f"PXL_{when:%Y%m%d_%H%M%S}{index:03d}.jpg"
        _image(path, payload, when)
        path.with_suffix(path.suffix + ".qr.txt").write_text(payload, encoding="utf-8")
        index += 1
        when += timedelta(seconds=1)

    def product(label: str) -> None:
        nonlocal index, when
        path = folder / f"PXL_{when:%Y%m%d_%H%M%S}{index:03d}.jpg"
        _image(path, label, when)
        index += 1
        when += timedelta(seconds=1)

    command("CVHS1:BATCH:START")
    command(f"CVHS1:LOC:{shelf}")
    for item_number in range(1, item_count + 1):
        if item_number == 2:
            command("CVHS1:FLAG:RARE")
            command("CVHS1:FLAG:REVIEW")
        for photo_number in range(1, photos_per_item + 1):
            product(f"VHS {item_number:03d} - {'FRONT' if photo_number == 1 else 'PHOTO ' + str(photo_number)}")
        if item_number != item_count:
            command("CVHS1:ITEM:NEXT")
    command("CVHS1:BATCH:END")
    return folder
