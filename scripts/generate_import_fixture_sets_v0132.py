#!/usr/bin/env python3
"""Generate deterministic, real-image Import fixtures for SnapIMS v0.13.2.

The fixture set contains actual decodable QR photographs. It never writes into the
operator Batch Home and is safe to delete and regenerate.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Iterable

import qrcode
from PIL import Image, ImageDraw

NEXT = "CVHS1:ITEM:NEXT"
LEGACY = {
    "start": "CVHS1:BATCH:START",
    "end": "CVHS1:BATCH:END",
    "location": "CVHS1:LOC:A6",
    "location_malformed": "CVHS1:LOC:",
    "rare": "CVHS1:FLAG:RARE",
    "review": "CVHS1:FLAG:REVIEW",
    "continue": "CVHS1:ITEM:CONT",
}


def product(path: Path, label: str) -> None:
    image = Image.new("RGB", (800, 600), (40, 68, 92))
    draw = ImageDraw.Draw(image)
    draw.rectangle((35, 35, 765, 565), outline=(235, 235, 235), width=8)
    draw.text((65, 70), label, fill=(255, 255, 255))
    draw.text((65, 520), path.name, fill=(255, 255, 255))
    image.save(path, format="JPEG", quality=88, optimize=True)


def qr_photo(path: Path, payload: str, label: str = "QR") -> None:
    code = qrcode.make(payload).convert("RGB").resize((420, 420))
    image = Image.new("RGB", (800, 600), "white")
    image.paste(code, (190, 70))
    draw = ImageDraw.Draw(image)
    draw.text((35, 25), label, fill="black")
    draw.text((35, 555), payload, fill="black")
    image.save(path, format="JPEG", quality=94, optimize=True)


def folder(root: Path, name: str) -> Path:
    destination = root / name
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def stream(destination: Path, layout: Iterable[str]) -> None:
    for index, kind in enumerate(layout):
        target = destination / f"PXL_20260803_120{index:05d}.jpg"
        if kind == "P":
            product(target, f"PRODUCT {index + 1}")
        elif kind == "N":
            qr_photo(target, NEXT, "NEXT ITEM")
        else:
            qr_photo(target, kind, "COMMAND")


def build(root: Path) -> dict[str, object]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    stream(folder(root, "01-one-item-no-next"), ["P"])
    stream(folder(root, "02-two-items-one-next"), ["P", "N", "P"])

    twenty = folder(root, "03-twenty-items-normal-next")
    index = 0
    for item in range(20):
        product(twenty / f"{index:04d}.jpg", f"TAPE {item + 1}")
        index += 1
        if item < 19:
            qr_photo(twenty / f"{index:04d}.jpg", NEXT, "NEXT ITEM")
            index += 1

    stream(folder(root, "04-leading-next"), ["N", "P"])
    stream(folder(root, "05-trailing-next"), ["P", "N"])
    stream(folder(root, "06-consecutive-next"), ["P", "N", "N", "P"])
    folder(root, "07-empty-folder")
    stream(folder(root, "08-only-next-cards"), ["N", "N"])

    corrupt = folder(root, "09-corrupt-jpeg-among-valid")
    product(corrupt / "001.jpg", "VALID BEFORE")
    (corrupt / "002.jpg").write_bytes(b"not-a-jpeg\x00\x01")
    product(corrupt / "003.jpg", "VALID AFTER")

    heic = folder(root, "10-heic-if-supported")
    heic_status = "not generated: pillow-heif unavailable"
    try:
        import pillow_heif  # type: ignore[import-not-found]

        pillow_heif.register_heif_opener()
        Image.new("RGB", (800, 600), (40, 68, 92)).save(heic / "001.heic", format="HEIF")
        heic_status = "generated"
    except (ImportError, KeyError, OSError):
        (heic / "HEIC_RUNTIME_NOT_AVAILABLE.txt").write_text(heic_status, encoding="utf-8")

    mixed = folder(root, "11-unsupported-files-mixed")
    product(mixed / "001.jpg", "PRODUCT")
    (mixed / "notes.txt").write_text("ignored", encoding="utf-8")
    (mixed / "archive.zip").write_bytes(b"not a real archive")

    consumer = folder(root, "12-unrelated-consumer-qr")
    qr_photo(consumer / "001.jpg", "https://example.com/product/123", "CONSUMER QR")
    product(consumer / "002.jpg", "PRODUCT")

    legacy = folder(root, "13-legacy-mixed-with-next")
    qr_photo(legacy / "001.jpg", LEGACY["start"], "LEGACY START")
    product(legacy / "002.jpg", "TAPE 1")
    qr_photo(legacy / "003.jpg", LEGACY["location"], "LEGACY LOCATION")
    qr_photo(legacy / "004.jpg", NEXT, "NEXT ITEM")
    product(legacy / "005.jpg", "TAPE 2")
    qr_photo(legacy / "006.jpg", LEGACY["end"], "LEGACY END")

    malformed = folder(root, "14-legacy-malformed-location")
    product(malformed / "001.jpg", "PRODUCT")
    qr_photo(malformed / "002.jpg", LEGACY["location_malformed"], "MALFORMED LEGACY")

    for name in (
        "15-blank-location",
        "16-none-location",
        "17-processing-table-location",
        "20-duplicate-reused-folder",
        "21-source-change-after-preview",
        "22-stop-during-scan",
        "23-stop-after-preview-before-commit",
        "24-browser-refresh-during-scan",
        "25-manual-split-merge",
        "26-one-changed-photo",
        "29-v0123-upgrade-source",
        "30-clean-install-source",
    ):
        destination = folder(root, name)
        product(destination / "001.jpg", name)
        product(destination / "002.jpg", f"{name} second photo")

    spaced = folder(root, "18-Folder Name With Spaces")
    product(spaced / "001.jpg", "SPACES")
    unicode_folder = folder(root, "19-Horreur été ünicode")
    product(unicode_folder / "001.jpg", "UNICODE")

    large = folder(root, "27-100-items-202-photos")
    index = 0
    for item in range(100):
        product(large / f"{index:04d}.jpg", f"TAPE {item + 1}")
        index += 1
        if item < 99:
            qr_photo(large / f"{index:04d}.jpg", NEXT, "NEXT ITEM")
            index += 1
    for payload in (LEGACY["start"], LEGACY["end"], LEGACY["review"]):
        qr_photo(large / f"{index:04d}.jpg", payload, "LEGACY")
        index += 1
    assert index == 202

    multiple = folder(root, "28-multiple-batch-home")
    for child_name in ("AUGUST-HORROR-01", "Comedy Batch", "Été VHS"):
        child = folder(multiple, child_name)
        product(child / "001.jpg", child_name)

    manifest = {
        "release": "0.13.2",
        "root": str(root.resolve()),
        "fixture_folders": sorted(path.name for path in root.iterdir() if path.is_dir()),
        "image_files": sum(
            1
            for path in root.rglob("*")
            if path.suffix.casefold() in {".jpg", ".jpeg", ".heic", ".heif"}
        ),
        "heic": heic_status,
        "note": (
            "Scenarios 15-17 are differentiated by operator-entered metadata. "
            "Scenarios 20-26 and 29-30 are completed by the automated tests/scripts."
        ),
    }
    (root / "fixture-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/import_v0130"),
        help="Fixture output directory",
    )
    args = parser.parse_args()
    result = build(args.output.resolve())
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
