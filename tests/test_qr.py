from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import qrcode
from PIL import Image
from pillow_heif import from_pillow

from snapims.demo import create_demo_batch
from snapims.qr import QRDecodeError, decode_snapims_qr


def test_decodes_generated_approved_command(tmp_path) -> None:
    demo = create_demo_batch(tmp_path / "demo")
    assert decode_snapims_qr(sorted(demo.glob("*.jpg"))[0]) == "CVHS1:BATCH:START"


def test_unknown_qr_is_ignored(tmp_path) -> None:
    path = tmp_path / "unknown.png"
    qrcode.make("https://example.com/not-a-command").save(path)
    assert decode_snapims_qr(path) is None


def test_unrecognized_cvhs1_payload_is_surfaced_for_quarantine_not_dropped(tmp_path) -> None:
    path = tmp_path / "unknown-command.png"
    qrcode.make("CVHS1:DO:MAGIC").save(path)
    assert decode_snapims_qr(path) == "CVHS1:DO:MAGIC"


def test_heic_command_uses_safe_pillow_decoder_fallback(tmp_path) -> None:
    path = tmp_path / "command.heic"
    qr = qrcode.make("CVHS1:ITEM:NEXT").convert("RGB").resize((900, 900))
    from_pillow(qr).save(path)
    assert decode_snapims_qr(path) == "CVHS1:ITEM:NEXT"


def test_corrupted_image_fails_clearly(tmp_path) -> None:
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"not-an-image")
    with pytest.raises(QRDecodeError, match="Could not open"):
        decode_snapims_qr(path)


@pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="Poppler is not installed")
def test_supplied_qr_pdf_first_page_commands_decode(tmp_path) -> None:
    pdf = Path(__file__).parents[1] / "docs/reference/Canada_VHS_QR_Card_Set_v2.pdf"
    output = tmp_path / "page"
    subprocess.run(
        ["pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-png", "-r", "180", str(pdf), str(output)],
        check=True, capture_output=True,
    )
    with Image.open(output.with_suffix(".png")) as page:
        width, height = page.size
        payloads: list[str | None] = []
        for row in range(3):
            for column in range(2):
                crop = page.crop((column * width // 2, row * height // 3, (column + 1) * width // 2, (row + 1) * height // 3))
                crop_path = tmp_path / f"card-{row}-{column}.png"
                crop.save(crop_path)
                payloads.append(decode_snapims_qr(crop_path))
    assert payloads == [
        "CVHS1:BATCH:START", "CVHS1:BATCH:END", "CVHS1:ITEM:NEXT",
        "CVHS1:ITEM:CONT", "CVHS1:FLAG:RARE", "CVHS1:FLAG:REVIEW",
    ]
