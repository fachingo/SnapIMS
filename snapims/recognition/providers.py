from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from snapims.config import SnapIMSConfig
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.runtime import test_providers_enabled
from snapims.settings import ConfigurationService

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
MAX_IMAGES = 3
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "edition": {"type": "string"},
        "distributor": {"type": "string"},
        "year": {"type": ["integer", "null"]},
        "barcode_candidates": {"type": "array", "items": {"type": "string"}},
        "suggested_tag_ids": {"type": "array", "items": {"type": "string"}},
        "suggested_price_cents": {"type": ["integer", "null"]},
        "suggested_discount_percent": {"type": "number"},
        "confidence": {"type": "number"},
        "uncertainty_reasons": {"type": "array", "items": {"type": "string"}},
        "title_evidence": {"type": "array", "items": {"type": "string"}},
        "field_evidence": {
            "type": "object",
            "properties": {
                "year": {"type": "array", "items": {"type": "string"}},
                "edition": {"type": "array", "items": {"type": "string"}},
                "distributor": {"type": "array", "items": {"type": "string"}},
                "barcode": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["year", "edition", "distributor", "barcode"],
            "additionalProperties": False,
        },
        "contradiction_flags": {"type": "array", "items": {"type": "string"}},
        "requires_review": {"type": "boolean"},
    },
    "required": [
        "title", "edition", "distributor", "year", "barcode_candidates", "suggested_tag_ids",
        "suggested_price_cents", "suggested_discount_percent", "confidence",
        "uncertainty_reasons", "requires_review",
        "title_evidence", "field_evidence", "contradiction_flags",
    ],
    "additionalProperties": False,
}


class MockRecognizer(BaseRecognizer):
    name = "mock"

    def model_name(self) -> str:
        return "mock-v1"

    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        reference = hashlib.sha256("|".join(str(image) for image in images).encode()).hexdigest()[:16]
        sequence = int(item.get("sequence") or 0)
        return RecognitionResult(
            suggested_title=item.get("title") or f"Demo VHS {sequence:03d}",
            edition=item.get("edition") or "Standard VHS",
            distributor=item.get("distributor") or "Demo Distributor",
            year=item.get("release_year") or 1990 + (sequence % 10),
            suggested_price_cents=None,
            suggested_discount_percent=0.0,
            confidence=0.91,
            uncertainty_reasons=("Synthetic mock result; verify against the cover",),
            title_evidence=("Synthetic fixture label",),
            field_evidence={
                "year": ["Synthetic fixture"],
                "edition": ["Synthetic fixture"],
                "distributor": ["Synthetic fixture"],
                "barcode": [],
            },
            provider_name=self.name,
            raw_response_reference=f"mock:{reference}",
            pricing_source="NO_RECOGNITION_PRICING",
            requires_review=True,
        )


class GeminiRecognizer(BaseRecognizer):
    name = "gemini"

    def available(self) -> tuple[bool, str]:
        return False, "Live Gemini recognition is not implemented"

    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        raise NotImplementedError("Live Gemini recognition is intentionally disabled.")


class OpenAIRecognizer(BaseRecognizer):
    name = "openai"

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        self.client = client
        self.model = model

    def model_name(self) -> str:
        service = ConfigurationService.load_runtime()
        legacy_model = service.value("SNAPIMS_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        return self.model or service.value(
            "SNAPIMS_OPENAI_BASELINE_MODEL", legacy_model
        )

    def available(self) -> tuple[bool, str]:
        configured = bool(SnapIMSConfig.load().openai_api_key)
        return (
            (True, f"OpenAI available ({self.model_name()})")
            if configured
            else (False, "OPENAI_API_KEY is not configured")
        )

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        from openai import OpenAI
        return OpenAI(api_key=SnapIMSConfig.load().openai_api_key)

    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        available, reason = self.available()
        if not available:
            raise RuntimeError(reason)
        if not images:
            raise ValueError("At least one item image is required")
        content: list[dict[str, Any]] = [{
            "type": "input_text",
            "text": (
                "Identify this VHS tape from the cover photographs. Return only catalog metadata. "
                "Use the exact title printed on the evidence, never a slogan or tagline. "
                "Return title UNKNOWN when the evidence is insufficient. Record short evidence "
                "snippets by field and flag conflicts between front, spine, back, or barcode. "
                "Do not estimate or suggest a listing price. Set suggested_price_cents to null and "
                "suggested_discount_percent to 0. Pricing is a separate operator/database/eBay workflow. "
                "For suggested_tag_ids, return zero to three conservative IDs only from this approved AI-eligible list. "
                + json.dumps(item.get("approved_ai_tags") or [])
            ),
        }]
        for path in images[:MAX_IMAGES]:
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"})
        response = self._client().responses.create(
            model=self.model_name(),
            input=[{"role": "user", "content": content}],
            text={"format": {"type": "json_schema", "name": "vhs_recognition", "strict": True, "schema": SCHEMA}},
        )
        payload = json.loads(response.output_text)
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        approved_ids = {
            str(row.get("tag_id") or "")
            for row in (item.get("approved_ai_tags") or [])
            if isinstance(row, dict) and row.get("tag_id")
        }
        suggested_tag_ids = tuple(
            value for value in (str(raw).strip() for raw in payload["suggested_tag_ids"])
            if value in approved_ids
        )[:3]
        return RecognitionResult(
            suggested_title=str(payload["title"]),
            edition=str(payload["edition"]),
            distributor=str(payload["distributor"]),
            year=payload["year"],
            barcode_candidates=tuple(payload["barcode_candidates"]),
            suggested_tag_ids=suggested_tag_ids,
            suggested_price_cents=None,
            suggested_discount_percent=0.0,
            confidence=float(payload["confidence"]),
            uncertainty_reasons=tuple(payload["uncertainty_reasons"]),
            title_evidence=tuple(payload["title_evidence"]),
            field_evidence=dict(payload["field_evidence"]),
            contradiction_flags=tuple(payload["contradiction_flags"]),
            provider_name=self.name,
            raw_response_reference=str(response.id),
            pricing_source="NO_RECOGNITION_PRICING",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requires_review=True,
        )


def recognizer_registry(*, include_test: bool | None = None) -> dict[str, BaseRecognizer]:
    providers: list[BaseRecognizer] = [OpenAIRecognizer(), GeminiRecognizer()]
    if include_test if include_test is not None else test_providers_enabled():
        providers.insert(0, MockRecognizer())
    return {provider.name: provider for provider in providers}


def recognizer_for(
    provider_name: str,
    *,
    model_name: str = "",
    include_test: bool | None = None,
) -> BaseRecognizer:
    providers = recognizer_registry(include_test=include_test)
    if provider_name not in providers:
        raise KeyError(f"Unknown provider: {provider_name}")
    if provider_name == "openai":
        return OpenAIRecognizer(model=model_name or None)
    return providers[provider_name]
