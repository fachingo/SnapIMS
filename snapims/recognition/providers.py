from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from snapims.config import default_project_path
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.runtime import test_providers_enabled

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
        "suggested_price_cents": {"type": ["integer", "null"]},
        "suggested_discount_percent": {"type": "number"},
        "confidence": {"type": "number"},
        "uncertainty_reasons": {"type": "array", "items": {"type": "string"}},
        "requires_review": {"type": "boolean"},
    },
    "required": [
        "title", "edition", "distributor", "year", "barcode_candidates",
        "suggested_price_cents", "suggested_discount_percent", "confidence",
        "uncertainty_reasons", "requires_review",
    ],
    "additionalProperties": False,
}


def _load_environment() -> None:
    if os.getenv("SNAPIMS_SKIP_DOTENV"):
        return
    project = Path(os.getenv("SNAPIMS_PROJECT_PATH") or default_project_path()).expanduser().resolve()
    load_dotenv(project / ".env", override=False)


class MockRecognizer(BaseRecognizer):
    name = "mock"

    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        reference = hashlib.sha256("|".join(str(image) for image in images).encode()).hexdigest()[:16]
        sequence = int(item.get("sequence") or 0)
        return RecognitionResult(
            suggested_title=item.get("title") or f"Demo VHS {sequence:03d}",
            edition=item.get("edition") or "Standard VHS",
            distributor=item.get("distributor") or "Demo Distributor",
            year=item.get("release_year") or 1990 + (sequence % 10),
            suggested_price_cents=item.get("price_cents") or 999,
            suggested_discount_percent=float(item.get("discount_percent") or 0),
            confidence=0.91,
            uncertainty_reasons=("Synthetic mock result; verify against the cover",),
            provider_name=self.name,
            raw_response_reference=f"mock:{reference}",
            pricing_source="MOCK_ESTIMATE_NO_LIVE_MARKET_DATA",
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
        _load_environment()
        return self.model or os.getenv("SNAPIMS_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL

    def available(self) -> tuple[bool, str]:
        _load_environment()
        return (True, f"OpenAI available ({self.model_name()})") if os.getenv("OPENAI_API_KEY") else (False, "OPENAI_API_KEY is not configured")

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        from openai import OpenAI
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"])

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
                "Suggest a CAD listing price in cents only as an AI estimate. You do not have live sold-market data. "
                "Use 999 when uncertain and include the lack of live comparable sales in uncertainty_reasons."
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
        return RecognitionResult(
            suggested_title=str(payload["title"]),
            edition=str(payload["edition"]),
            distributor=str(payload["distributor"]),
            year=payload["year"],
            barcode_candidates=tuple(payload["barcode_candidates"]),
            suggested_price_cents=payload["suggested_price_cents"] or 999,
            suggested_discount_percent=float(payload["suggested_discount_percent"]),
            confidence=float(payload["confidence"]),
            uncertainty_reasons=tuple(payload["uncertainty_reasons"]),
            provider_name=self.name,
            raw_response_reference=str(response.id),
            pricing_source="AI_ESTIMATE_NO_LIVE_MARKET_DATA",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requires_review=True,
        )


def recognizer_registry(*, include_test: bool | None = None) -> dict[str, BaseRecognizer]:
    providers: list[BaseRecognizer] = [OpenAIRecognizer(), GeminiRecognizer()]
    if include_test if include_test is not None else test_providers_enabled():
        providers.insert(0, MockRecognizer())
    return {provider.name: provider for provider in providers}
