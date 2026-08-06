from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from snapims.protocol import parse_command


class QRDecodeError(RuntimeError):
    pass


UNREADABLE_PHOTO_PAYLOAD = "CVHS1:IMPORT:UNREADABLE_PHOTO"
_MAX_SNAPIMS_PAYLOAD_LENGTH = 256


def _recognized_payload(value: str) -> str | None:
    """Return valid commands and malformed SnapIMS commands for repair.

    Non-SnapIMS QR codes remain product photographs. A QR that identifies
    itself as CVHS1 is returned even when malformed so the interpreter can open
    the exact-photo repair menu instead of silently treating the card as a VHS.
    """
    payload = value.strip().upper()
    if not payload or len(payload) > _MAX_SNAPIMS_PAYLOAD_LENGTH:
        return None
    if parse_command(payload) is not None or payload.startswith("CVHS1:"):
        return payload
    return None


def decode_snapims_qr(path: Path) -> str | None:
    """Decode a SnapIMS QR command or surface a malformed CVHS1 card.

    A same-stem ``.qr.txt`` sidecar is supported for deterministic fixtures and
    does not change production camera behavior.
    """
    sidecar = path.with_suffix(path.suffix + ".qr.txt")
    if sidecar.is_file():
        return _recognized_payload(sidecar.read_text(encoding="utf-8"))
    try:
        image = cv2.imread(str(path))
    except cv2.error as exc:
        raise QRDecodeError(f"Could not read image: {path.name}") from exc
    if image is None:
        try:
            with Image.open(path) as opened:
                normalized = ImageOps.exif_transpose(opened).convert("RGB")
                image = cv2.cvtColor(np.asarray(normalized), cv2.COLOR_RGB2BGR)
        except (OSError, ValueError, cv2.error) as exc:
            raise QRDecodeError(f"Could not read image: {path.name}") from exc
    try:
        payload, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    except cv2.error as exc:
        raise QRDecodeError(f"Could not scan image for QR: {path.name}") from exc
    return _recognized_payload(payload)
