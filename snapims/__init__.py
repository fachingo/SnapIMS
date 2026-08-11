"""SnapIMS photo-first inventory system."""

try:
    from pillow_heif import register_heif_opener
except ImportError:  # HEIC remains optional when the native codec is unavailable.
    register_heif_opener = None

if register_heif_opener is not None:
    register_heif_opener()

__version__ = "0.16.0"
