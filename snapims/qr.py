from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from snapims.protocol import parse_command

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


class QRDecodeError(RuntimeError):
    """Raised when a photo cannot be interpreted safely as a command image."""


def _decode_with_opencv(path: Path) -> list[str]:
    try:
        import cv2
    except ImportError as exc:
        raise QRDecodeError(
            "No QR decoder is installed. Run: pip install opencv-python-headless"
        ) from exc

    image = cv2.imread(str(path))
    if image is None:
        try:
            with Image.open(path) as opened:
                rgb = ImageOps.exif_transpose(opened).convert("RGB")
                image = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
        except (OSError, ValueError, cv2.error) as exc:
            raise QRDecodeError(f"Could not open image for QR decoding: {path}") from exc
    detector = cv2.QRCodeDetector()
    values: list[str] = []
    try:
        found, decoded_info, _, _ = detector.detectAndDecodeMulti(image)
        if found:
            values.extend(value.strip() for value in decoded_info if value.strip())
    except (cv2.error, ValueError):
        pass
    if not values:
        value, _, _ = detector.detectAndDecode(image)
        if value.strip():
            values.append(value.strip())
    return values


def decode_snapims_qr(path: Path) -> str | None:
    """Return one recognized CVHS1 command, one unrecognized ``CVHS1:`` payload for the
    interpreter to quarantine, or None when the image carries no SnapIMS QR content at all.
    """
    decoded = [value.upper() for value in _decode_with_opencv(path)]
    recognized = [value for value in decoded if parse_command(value) is not None]
    unique_recognized = list(dict.fromkeys(recognized))
    if len(unique_recognized) > 1:
        raise QRDecodeError(
            f"Image contains multiple SnapIMS commands: {path.name}: {unique_recognized}"
        )
    if unique_recognized:
        return unique_recognized[0]

    unrecognized_cvhs1 = [value for value in decoded if value.startswith("CVHS1:")]
    unique_unrecognized = list(dict.fromkeys(unrecognized_cvhs1))
    if len(unique_unrecognized) > 1:
        raise QRDecodeError(
            f"Image contains multiple unrecognized SnapIMS commands: {path.name}: "
            f"{unique_unrecognized}"
        )
    if unique_unrecognized:
        return unique_unrecognized[0]
    return None
