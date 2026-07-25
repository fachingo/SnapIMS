from __future__ import annotations

from pathlib import Path

import cv2

from snapims.protocol import parse_command


class QRDecodeError(RuntimeError):
    pass


def decode_snapims_qr(path: Path) -> str | None:
    """Decode one allowlisted SnapIMS QR command.

    A same-stem ``.qr.txt`` sidecar is supported for deterministic fixtures and
    does not change production camera behavior.
    """
    sidecar = path.with_suffix(path.suffix + ".qr.txt")
    if sidecar.is_file():
        payload = sidecar.read_text(encoding="utf-8").strip()
        return payload if parse_command(payload) else None
    image = cv2.imread(str(path))
    if image is None:
        raise QRDecodeError(f"Could not read image: {path.name}")
    payload, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    payload = payload.strip()
    return payload if payload and parse_command(payload) else None
