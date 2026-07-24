from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from snapims.interpreter import ProtocolError, interpret_stream
from snapims.models import PhotoRecord


def record(index: int, name: str, payload: str | None = None) -> PhotoRecord:
    return PhotoRecord(Path(name), name, datetime(2026, 1, 1, 12, 0, index), "test", index, "hash", payload)


def interpret(records: list[PhotoRecord]):
    return interpret_stream(records, source_folder=Path("camera"), imported_at=datetime(2026, 1, 1))


def test_next_is_only_item_boundary() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"),
        record(1, "loc.jpg", "CVHS1:LOC:A1"),
        record(2, "front1.jpg"), record(3, "back1.jpg"),
        record(4, "next.jpg", "CVHS1:ITEM:NEXT"),
        record(5, "front2.jpg"), record(6, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert [[photo.original_name for photo in item.photos] for item in batch.items] == [["front1.jpg", "back1.jpg"], ["front2.jpg"]]


def test_flags_stack_for_next_item() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "loc.jpg", "CVHS1:LOC:B2"),
        record(2, "rare.jpg", "CVHS1:FLAG:RARE"), record(3, "review.jpg", "CVHS1:FLAG:REVIEW"),
        record(4, "front.jpg"), record(5, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert batch.items[0].rare and batch.items[0].review


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="Unknown CVHS1"):
        interpret([record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "bad.jpg", "CVHS1:DO:MAGIC")])


def test_missing_end_finalizes_with_warning() -> None:
    batch = interpret([record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "loc.jpg", "CVHS1:LOC:Q1"), record(2, "front.jpg")])
    assert len(batch.items) == 1
    assert any("END command was not found" in warning for warning in batch.warnings)
