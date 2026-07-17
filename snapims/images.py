from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageOps

from snapims.pipeline import sha256_file


class ImageProcessingError(RuntimeError):
    pass


def copy_original(source: Path, destination: Path, expected_sha256: str | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if expected_sha256 and sha256_file(destination) == expected_sha256:
            return destination
        raise FileExistsError(f"Refusing to overwrite an existing original: {destination}")
    shutil.copy2(source, destination)
    if expected_sha256 and sha256_file(destination) != expected_sha256:
        destination.unlink(missing_ok=True)
        raise ImageProcessingError(f"Hash mismatch while preserving original: {source.name}")
    return destination


def create_safe_jpeg(source: Path, destination: Path, *, max_dimension: int | None = None) -> Path:
    """Create an oriented RGB JPEG without carrying EXIF/GPS metadata forward."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        try:
            with Image.open(destination) as existing:
                existing.verify()
            return destination
        except OSError as exc:
            raise FileExistsError(f"Existing processed image is invalid: {destination}") from exc
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened)
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, "white")
                alpha = image.getchannel("A")
                background.paste(image.convert("RGB"), mask=alpha)
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            if max_dimension:
                image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            image.save(destination, format="JPEG", quality=94, optimize=True)
    except (OSError, ValueError) as exc:
        destination.unlink(missing_ok=True)
        raise ImageProcessingError(f"Could not process {source.name}: {exc}") from exc
    return destination
