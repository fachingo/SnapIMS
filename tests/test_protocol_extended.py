from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from snapims.interpreter import ProtocolError, interpret_stream, sanitize_batch_name
from snapims.models import PhotoRecord
from snapims.protocol import CommandKind, all_location_payloads, parse_command


def rec(index: int, payload: str | None = None, name: str | None = None) -> PhotoRecord:
    filename = name or f"{index:03d}.jpg"
    return PhotoRecord(
        Path(filename), filename, datetime(2026, 1, 1, 12, 0, min(index, 59)),
        "test", index, f"hash-{index}", payload,
    )


def run(records: list[PhotoRecord]):
    return interpret_stream(records, source_folder=Path("camera"), imported_at=datetime(2026, 1, 2, 3, 4, 5))


@pytest.mark.parametrize(
    ("payload", "kind", "value"),
    [
        ("CVHS1:BATCH:START", CommandKind.BATCH_START, None),
        (" cvhs1:batch:end ", CommandKind.BATCH_END, None),
        ("CVHS1:ITEM:NEXT", CommandKind.ITEM_NEXT, None),
        ("CVHS1:ITEM:CONT", CommandKind.ITEM_CONT, None),
        ("CVHS1:FLAG:RARE", CommandKind.FLAG_RARE, None),
        ("CVHS1:FLAG:REVIEW", CommandKind.FLAG_REVIEW, None),
        ("CVHS1:LOC:Q1", CommandKind.LOCATION, "Q1"),
        ("CVHS1:LOC:J10", CommandKind.LOCATION, "J10"),
    ],
)
def test_command_vocabulary(payload: str, kind: CommandKind, value: str | None) -> None:
    command = parse_command(payload)
    assert command is not None
    assert command.kind is kind
    assert command.value == value


@pytest.mark.parametrize("payload", ["", "CVHS1:LOC:A0", "CVHS1:LOC:K1", "CVHS1:ITEM:NEW", "QR:START"])
def test_invalid_commands_rejected(payload: str) -> None:
    assert parse_command(payload) is None


def test_all_locations_contains_q1_and_a1_to_j10() -> None:
    locations = all_location_payloads()
    assert len(locations) == 101
    assert locations[0] == "CVHS1:LOC:Q1"
    assert "CVHS1:LOC:A1" in locations
    assert "CVHS1:LOC:J10" in locations


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), ("", None), (" comedy tapes ", "COMEDY-TAPES"), ("a/b:c", "A-B-C")],
)
def test_batch_name_sanitization(raw: str | None, expected: str | None) -> None:
    assert sanitize_batch_name(raw) == expected


def test_pre_start_and_post_end_photos_are_excluded_with_warnings() -> None:
    batch = run([
        rec(0, name="before.jpg"),
        rec(1, "CVHS1:BATCH:START"),
        rec(2, "CVHS1:LOC:A1"),
        rec(3, name="front.jpg"),
        rec(4, "CVHS1:BATCH:END"),
        rec(5, name="after.jpg"),
    ])
    assert len(batch.items) == 1
    assert any("before START" in warning for warning in batch.warnings)
    assert any("after END" in warning for warning in batch.warnings)


def test_duplicate_start_is_ignored() -> None:
    batch = run([
        rec(0, "CVHS1:BATCH:START"), rec(1, "CVHS1:BATCH:START"),
        rec(2, "CVHS1:LOC:A1"), rec(3), rec(4, "CVHS1:BATCH:END"),
    ])
    assert len(batch.items) == 1
    assert any("Duplicate START" in warning for warning in batch.warnings)


def test_commands_before_start_are_rejected() -> None:
    with pytest.raises(ProtocolError, match="before START"):
        run([rec(0, "CVHS1:LOC:A1")])


def test_product_before_location_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="before a shelf"):
        run([rec(0, "CVHS1:BATCH:START"), rec(1)])


def test_consecutive_next_does_not_create_empty_item() -> None:
    batch = run([
        rec(0, "CVHS1:BATCH:START"), rec(1, "CVHS1:LOC:A1"), rec(2),
        rec(3, "CVHS1:ITEM:NEXT"), rec(4, "CVHS1:ITEM:NEXT"), rec(5),
        rec(6, "CVHS1:BATCH:END"),
    ])
    assert len(batch.items) == 2
    assert any("no item was open" in warning for warning in batch.warnings)


def test_mid_item_location_is_deferred() -> None:
    batch = run([
        rec(0, "CVHS1:BATCH:START"), rec(1, "CVHS1:LOC:A1"), rec(2),
        rec(3, "CVHS1:LOC:B2"), rec(4), rec(5, "CVHS1:ITEM:NEXT"), rec(6),
        rec(7, "CVHS1:BATCH:END"),
    ])
    assert [item.shelf for item in batch.items] == ["A1", "B2"]
    assert len(batch.items[0].photos) == 2


def test_flags_scanned_inside_item_apply_to_next_item_and_reset() -> None:
    batch = run([
        rec(0, "CVHS1:BATCH:START"), rec(1, "CVHS1:LOC:A1"), rec(2),
        rec(3, "CVHS1:FLAG:RARE"), rec(4, "CVHS1:FLAG:REVIEW"),
        rec(5, "CVHS1:ITEM:NEXT"), rec(6), rec(7, "CVHS1:ITEM:NEXT"), rec(8),
        rec(9, "CVHS1:BATCH:END"),
    ])
    assert not batch.items[0].rare
    assert batch.items[1].rare and batch.items[1].review
    assert not batch.items[2].rare and not batch.items[2].review


def test_cont_is_a_noop_with_warning() -> None:
    batch = run([
        rec(0, "CVHS1:BATCH:START"), rec(1, "CVHS1:LOC:A1"), rec(2),
        rec(3, "CVHS1:ITEM:CONT"), rec(4), rec(5, "CVHS1:BATCH:END"),
    ])
    assert len(batch.items) == 1
    assert len(batch.items[0].photos) == 2
    assert any("CONT compatibility no-op" in warning for warning in batch.warnings)


def test_unused_flags_warn_at_end() -> None:
    batch = run([
        rec(0, "CVHS1:BATCH:START"), rec(1, "CVHS1:LOC:A1"), rec(2),
        rec(3, "CVHS1:ITEM:NEXT"), rec(4, "CVHS1:FLAG:RARE"), rec(5, "CVHS1:BATCH:END"),
    ])
    assert any("Unused item flag" in warning for warning in batch.warnings)


def test_no_start_rejected() -> None:
    with pytest.raises(ProtocolError, match="START command"):
        run([rec(0)])


def test_no_product_items_rejected() -> None:
    with pytest.raises(ProtocolError, match="no product items"):
        run([rec(0, "CVHS1:BATCH:START"), rec(1, "CVHS1:BATCH:END")])
