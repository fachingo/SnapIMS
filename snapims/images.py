from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

from snapims.pipeline import sha256_file


class ImageProcessingError(RuntimeError):
    pass


def copy_original(source: Path, destination: Path, expected_sha256: str | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if expected_sha256 and sha256_file(destination) == expected_sha256:
            return destination
        raise FileExistsError(f"Refusing to overwrite existing original: {destination}")
    shutil.copy2(source, destination)
    if expected_sha256 and sha256_file(destination) != expected_sha256:
        destination.unlink(missing_ok=True)
        raise ImageProcessingError(f"Hash mismatch while preserving original: {source.name}")
    return destination


def _rgb(source: Path) -> Image.Image:
    opened = Image.open(source)
    image = ImageOps.exif_transpose(opened)
    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, "white")
        background.paste(image.convert("RGB"), mask=image.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    return image


def create_safe_jpeg(
    source: Path,
    destination: Path,
    *,
    max_dimension: int | None = None,
    quality: int = 94,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        with Image.open(destination) as existing:
            existing.verify()
        return destination
    try:
        image = _rgb(source)
        try:
            if max_dimension:
                image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            image.save(
                destination,
                format="JPEG",
                quality=quality,
                optimize=False,
                progressive=False,
            )
        finally:
            image.close()
    except (OSError, ValueError) as exc:
        destination.unlink(missing_ok=True)
        raise ImageProcessingError(f"Could not process {source.name}: {exc}") from exc
    return destination


def create_preview(source: Path, destination: Path) -> Path:
    """Create the persistent browser derivative; originals remain untouched."""
    return create_safe_jpeg(source, destination, max_dimension=1080, quality=80)


def create_recognition_derivative(source: Path, destination: Path) -> Path:
    """Create a compact, text-readable derivative for vision providers."""
    return create_safe_jpeg(source, destination, max_dimension=1920, quality=82)


def is_nearly_blank(path: Path) -> bool:
    try:
        image = _rgb(path)
        try:
            image.thumbnail((128, 128), Image.Resampling.BILINEAR)
            grayscale = ImageOps.grayscale(image)
            stat = ImageStat.Stat(grayscale)
            mean = float(stat.mean[0])
            spread = float(stat.stddev[0])
            return mean < 8 or (mean < 18 and spread < 6)
        finally:
            image.close()
    except (OSError, ValueError):
        return True
