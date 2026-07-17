from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from snapims.recognition.base import BaseRecognizer, RecognitionResult

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
MAX_RECOGNITION_IMAGES = 3
ALLOWED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_EXTENSION_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_RECOGNITION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "edition": {"type": "string"},
        "distributor": {"type": "string"},
        "year": {"type": ["integer", "null"]},
        "barcode_candidates": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "uncertainty_reasons": {"type": "array", "items": {"type": "string"}},
        "requires_review": {"type": "boolean"},
    },
    "required": [
        "title",
        "edition",
        "distributor",
        "year",
        "barcode_candidates",
        "confidence",
        "uncertainty_reasons",
        "requires_review",
    ],
    "additionalProperties": False,
}
_ENV_LOADED = False


def _ensure_dotenv_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    load_dotenv()
    _ENV_LOADED = True


def _resolve_image_mime_type(path: Path) -> str:
    extension = path.suffix.casefold()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise ValueError(f"Unsupported image extension {path.suffix!r} for {path.name}; use {allowed}")
    mime_type = _EXTENSION_MIME_TYPES.get(extension) or mimetypes.guess_type(path.name)[0]
    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_MIME_TYPES))
        raise ValueError(f"Unsupported image MIME type {mime_type!r} for {path.name}; expected {allowed}")
    return mime_type


def _image_to_data_url(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Image path does not exist: {path}")
    mime_type = _resolve_image_mime_type(path)
    encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _build_vision_input(images: list[Path]) -> list[dict[str, Any]]:
    if not images:
        raise ValueError("At least one item image is required for OpenAI recognition")
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Identify this VHS tape from the provided cover photos (front, back, and/or spine). "
                "Return catalog metadata only. Use empty strings when text is unreadable. "
                "List any visible barcodes or UPC codes in barcode_candidates."
            ),
        }
    ]
    for path in images[:MAX_RECOGNITION_IMAGES]:
        content.append({"type": "input_image", "image_url": _image_to_data_url(path)})
    return [{"role": "user", "content": content}]


def _parse_recognition_payload(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("OpenAI returned malformed JSON for recognition output") from exc
    if not isinstance(payload, dict):
        raise ValueError("OpenAI recognition output must be a JSON object")
    required_fields = _RECOGNITION_JSON_SCHEMA["required"]
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise ValueError(f"OpenAI recognition output missing fields: {', '.join(missing)}")
    return payload


def _payload_to_result(payload: dict[str, Any]) -> RecognitionResult:
    year = payload["year"]
    if year is not None and not isinstance(year, int):
        raise ValueError("OpenAI recognition output field 'year' must be an integer or null")
    confidence = payload["confidence"]
    if not isinstance(confidence, (int, float)):
        raise ValueError("OpenAI recognition output field 'confidence' must be a number")
    confidence_value = float(confidence)
    if not 0.0 <= confidence_value <= 1.0:
        raise ValueError("OpenAI recognition output field 'confidence' must be between 0 and 1")
    barcode_candidates = payload["barcode_candidates"]
    if not isinstance(barcode_candidates, list) or not all(
        isinstance(value, str) for value in barcode_candidates
    ):
        raise ValueError("OpenAI recognition output field 'barcode_candidates' must be a string array")
    uncertainty_reasons = payload["uncertainty_reasons"]
    if not isinstance(uncertainty_reasons, list) or not all(
        isinstance(value, str) for value in uncertainty_reasons
    ):
        raise ValueError("OpenAI recognition output field 'uncertainty_reasons' must be a string array")
    for field in ("title", "edition", "distributor"):
        if not isinstance(payload[field], str):
            raise ValueError(f"OpenAI recognition output field {field!r} must be a string")
    return RecognitionResult(
        suggested_title=payload["title"],
        edition=payload["edition"],
        distributor=payload["distributor"],
        year=year,
        barcode_candidates=tuple(barcode_candidates),
        confidence=confidence_value,
        uncertainty_reasons=tuple(uncertainty_reasons),
        provider_name="openai",
        requires_review=True,
    )


class MockRecognizer(BaseRecognizer):
    name = "mock"

    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        reference = hashlib.sha256(
            "|".join(str(image) for image in images).encode("utf-8")
        ).hexdigest()[:16]
        return RecognitionResult(
            suggested_title=item.get("title") or f"Demo VHS {int(item.get('sequence', 0)):03d}",
            edition=item.get("edition") or "Standard VHS",
            distributor=item.get("distributor") or "Demo Distributor",
            confidence=0.91,
            uncertainty_reasons=("Synthetic mock result; verify against the cover",),
            provider_name=self.name,
            raw_response_reference=f"mock:{reference}",
            requires_review=True,
        )


class OpenAIRecognizer(BaseRecognizer):
    name = "openai"

    def __init__(self, client: Any | None = None, *, model: str | None = None) -> None:
        self._client = client
        self._model = model

    def _model_name(self) -> str:
        if self._model is not None:
            return self._model
        _ensure_dotenv_loaded()
        return os.getenv("SNAPIMS_OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        _ensure_dotenv_loaded()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import OpenAI

        return OpenAI(api_key=api_key)

    def available(self) -> tuple[bool, str]:
        _ensure_dotenv_loaded()
        if not os.getenv("OPENAI_API_KEY", "").strip():
            return False, "OPENAI_API_KEY is not configured"
        return True, f"OpenAI vision recognition available ({self._model_name()})"

    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        available, reason = self.available()
        if not available:
            raise RuntimeError(reason)
        try:
            from openai import APIConnectionError, AuthenticationError, OpenAIError, RateLimitError
        except ImportError as exc:
            raise RuntimeError("Install the openai package to use OpenAI recognition") from exc

        request_input = _build_vision_input(images)
        try:
            response = self._get_client().responses.create(
                model=self._model_name(),
                input=request_input,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "vhs_recognition",
                        "strict": True,
                        "schema": _RECOGNITION_JSON_SCHEMA,
                    }
                },
            )
        except AuthenticationError as exc:
            raise RuntimeError("OpenAI authentication failed; check OPENAI_API_KEY") from exc
        except RateLimitError as exc:
            raise RuntimeError("OpenAI rate limit exceeded; retry later") from exc
        except APIConnectionError as exc:
            raise RuntimeError("OpenAI network request failed; check connectivity") from exc
        except OpenAIError as exc:
            raise RuntimeError(f"OpenAI recognition request failed: {exc}") from exc

        response_id = getattr(response, "id", None)
        if not isinstance(response_id, str) or not response_id:
            raise ValueError("OpenAI response did not include a response ID")
        raw_text = getattr(response, "output_text", None)
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ValueError("OpenAI returned an empty structured recognition response")

        result = _payload_to_result(_parse_recognition_payload(raw_text))
        return RecognitionResult(
            suggested_title=result.suggested_title,
            edition=result.edition,
            distributor=result.distributor,
            year=result.year,
            barcode_candidates=result.barcode_candidates,
            confidence=result.confidence,
            uncertainty_reasons=result.uncertainty_reasons,
            provider_name=result.provider_name,
            raw_response_reference=response_id,
            requires_review=True,
        )


class GeminiRecognizer(BaseRecognizer):
    name = "gemini"

    def available(self) -> tuple[bool, str]:
        _ensure_dotenv_loaded()
        if not os.getenv("GEMINI_API_KEY"):
            return False, "GEMINI_API_KEY is not configured"
        return True, "Configured adapter boundary (live recognition deferred)"

    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        raise NotImplementedError(
            "The Gemini adapter boundary is configured, but live recognition is intentionally disabled."
        )


class LocalOCRRecognizer(BaseRecognizer):
    name = "local-ocr"

    def available(self) -> tuple[bool, str]:
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return False, "Install pytesseract and the tesseract-ocr Linux package"
        return True, "Local OCR available"

    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        available, reason = self.available()
        if not available:
            raise RuntimeError(reason)
        import pytesseract
        from PIL import Image

        text_parts: list[str] = []
        for path in images[:3]:
            with Image.open(path) as image:
                text_parts.append(pytesseract.image_to_string(image).strip())
        text = "\n".join(part for part in text_parts if part)
        candidate = next((line.strip() for line in text.splitlines() if len(line.strip()) >= 3), "")
        return RecognitionResult(
            suggested_title=candidate,
            confidence=0.35 if candidate else 0.0,
            uncertainty_reasons=("Raw OCR requires human interpretation",),
            provider_name=self.name,
            raw_response_reference="local-ocr:inline",
            requires_review=True,
        )


def recognizer_registry() -> dict[str, BaseRecognizer]:
    _ensure_dotenv_loaded()
    providers: list[BaseRecognizer] = [
        MockRecognizer(), LocalOCRRecognizer(), OpenAIRecognizer(), GeminiRecognizer()
    ]
    return {provider.name: provider for provider in providers}
