from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    suggested_title: str = ""
    edition: str = ""
    distributor: str = ""
    year: int | None = None
    barcode_candidates: tuple[str, ...] = ()
    suggested_tag_ids: tuple[str, ...] = ()
    suggested_price_cents: int | None = None
    suggested_discount_percent: float = 0
    confidence: float = 0.0
    uncertainty_reasons: tuple[str, ...] = ()
    title_evidence: tuple[str, ...] = ()
    field_evidence: dict[str, Any] | None = None
    contradiction_flags: tuple[str, ...] = ()
    provider_name: str = "unknown"
    raw_response_reference: str = ""
    pricing_source: str = "AI_ESTIMATE_NO_LIVE_MARKET_DATA"
    input_tokens: int = 0
    output_tokens: int = 0
    requires_review: bool = True


class BaseRecognizer(ABC):
    name = "base"

    def available(self) -> tuple[bool, str]:
        return True, "Available"

    @abstractmethod
    def recognize(self, item: dict[str, Any], images: list[Path]) -> RecognitionResult:
        """Return suggestions only. Implementations must never mutate item records."""
        raise NotImplementedError
