from __future__ import annotations

from pathlib import Path

import pytest

from snapims.interpreter import interpret_stream

from .conftest import BASE_TIME, record


def interpret(records):
    return interpret_stream(records, source_folder=Path("batch"), imported_at=BASE_TIME)


def test_one_and_multi_photo_items_use_next_only() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "shelf.jpg", "CVHS1:LOC:A1"),
        record(2, "front1.jpg"), record(3, "back1.jpg"), record(4, "next.jpg", "CVHS1:ITEM:NEXT"),
        record(50, "front2.jpg"), record(500, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert [[p.original_name for p in item.photos] for item in batch.items] == [
        ["front1.jpg", "back1.jpg"], ["front2.jpg"]
    ]


def test_photos_before_start_and_after_end_are_warned_and_excluded() -> None:
    batch = interpret([
        record(0, "before.jpg"), record(1, "start.jpg", "CVHS1:BATCH:START"),
        record(2, "shelf.jpg", "CVHS1:LOC:A1"), record(3, "front.jpg"),
        record(4, "end.jpg", "CVHS1:BATCH:END"), record(5, "after.jpg"),
    ])
    assert [p.original_name for p in batch.items[0].photos] == ["front.jpg"]
    assert any("before START" in warning for warning in batch.warnings)
    assert any("after END" in warning for warning in batch.warnings)


def test_duplicate_start_warns_without_resetting_state() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "shelf.jpg", "CVHS1:LOC:A1"),
        record(2, "front.jpg"), record(3, "start2.jpg", "CVHS1:BATCH:START"),
        record(4, "back.jpg"), record(5, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert len(batch.items) == 1 and len(batch.items[0].photos) == 2
    assert any("Duplicate START" in warning for warning in batch.warnings)


def test_duplicate_end_warns() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "shelf.jpg", "CVHS1:LOC:A1"),
        record(2, "front.jpg"), record(3, "end.jpg", "CVHS1:BATCH:END"),
        record(4, "end2.jpg", "CVHS1:BATCH:END"),
    ])
    assert len(batch.items) == 1
    assert any("after END" in warning for warning in batch.warnings)


def test_consecutive_and_trailing_next_never_create_empty_items() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "shelf.jpg", "CVHS1:LOC:A1"),
        record(2, "front.jpg"), record(3, "next1.jpg", "CVHS1:ITEM:NEXT"),
        record(4, "next2.jpg", "CVHS1:ITEM:NEXT"), record(5, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert len(batch.items) == 1
    assert any("no item was open" in warning for warning in batch.warnings)


def test_cont_is_logged_noop() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "shelf.jpg", "CVHS1:LOC:A1"),
        record(2, "front.jpg"), record(3, "cont.jpg", "CVHS1:ITEM:CONT"),
        record(4, "back.jpg"), record(5, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert len(batch.items[0].photos) == 2
    assert any("CONT" in warning for warning in batch.warnings)


@pytest.mark.parametrize(
    "commands,expected",
    [(["CVHS1:FLAG:RARE"], (True, False)), (["CVHS1:FLAG:REVIEW"], (False, True)),
     (["CVHS1:FLAG:RARE", "CVHS1:FLAG:REVIEW"], (True, True))],
)
def test_pending_flags_apply_once(commands, expected) -> None:
    stream = [record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "shelf.jpg", "CVHS1:LOC:A1")]
    stream.extend(record(2 + index, f"flag{index}.jpg", payload) for index, payload in enumerate(commands))
    offset = 2 + len(commands)
    stream.extend([
        record(offset, "front1.jpg"), record(offset + 1, "next.jpg", "CVHS1:ITEM:NEXT"),
        record(offset + 2, "front2.jpg"), record(offset + 3, "end.jpg", "CVHS1:BATCH:END"),
    ])
    batch = interpret(stream)
    assert (batch.items[0].rare, batch.items[0].review) == expected
    assert (batch.items[1].rare, batch.items[1].review) == (False, False)


def test_shelf_change_and_q1_apply_to_following_items() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "a1.jpg", "CVHS1:LOC:A1"),
        record(2, "front1.jpg"), record(3, "next.jpg", "CVHS1:ITEM:NEXT"),
        record(4, "q1.jpg", "CVHS1:LOC:Q1"), record(5, "front2.jpg"),
        record(6, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert [item.shelf for item in batch.items] == ["A1", "Q1"]


def test_mid_item_location_and_flags_warn_and_apply_safely_to_next_item() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "a1.jpg", "CVHS1:LOC:A1"),
        record(2, "front1.jpg"), record(3, "b2.jpg", "CVHS1:LOC:B2"),
        record(4, "rare.jpg", "CVHS1:FLAG:RARE"), record(5, "back1.jpg"),
        record(6, "next.jpg", "CVHS1:ITEM:NEXT"), record(7, "front2.jpg"),
        record(8, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert batch.items[0].shelf == "A1" and not batch.items[0].rare
    assert batch.items[1].shelf == "B2" and batch.items[1].rare
    assert sum("inside item" in warning for warning in batch.warnings) == 2


def test_unknown_cvhs1_command_before_start_is_quarantined_without_raising() -> None:
    batch = interpret([
        record(0, "unknown.jpg", "CVHS1:DO:MAGIC"), record(1, "start.jpg", "CVHS1:BATCH:START"),
        record(2, "shelf.jpg", "CVHS1:LOC:A1"), record(3, "front.jpg"),
        record(4, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert [p.original_name for p in batch.items[0].photos] == ["front.jpg"]
    assert [photo.original_name for photo in batch.unknown_commands] == ["unknown.jpg"]
    assert [photo.qr_payload for photo in batch.unknown_commands] == ["CVHS1:DO:MAGIC"]
    assert any("Unknown CVHS1 command quarantined" in warning for warning in batch.warnings)


def test_unknown_cvhs1_command_inside_open_item_is_quarantined_and_excluded_from_photos() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "shelf.jpg", "CVHS1:LOC:A1"),
        record(2, "front.jpg"), record(3, "unknown.jpg", "CVHS1:DO:MAGIC"),
        record(4, "back.jpg"), record(5, "end.jpg", "CVHS1:BATCH:END"),
    ])
    assert len(batch.items) == 1
    assert [p.original_name for p in batch.items[0].photos] == ["front.jpg", "back.jpg"]
    assert [photo.original_name for photo in batch.unknown_commands] == ["unknown.jpg"]
    assert any("Unknown CVHS1 command quarantined" in warning for warning in batch.warnings)


def test_unknown_cvhs1_command_after_end_is_quarantined_without_raising() -> None:
    batch = interpret([
        record(0, "start.jpg", "CVHS1:BATCH:START"), record(1, "shelf.jpg", "CVHS1:LOC:A1"),
        record(2, "front.jpg"), record(3, "end.jpg", "CVHS1:BATCH:END"),
        record(4, "unknown.jpg", "CVHS1:DO:MAGIC"),
    ])
    assert len(batch.items) == 1
    assert [photo.original_name for photo in batch.unknown_commands] == ["unknown.jpg"]
    assert any("Unknown CVHS1 command quarantined" in warning for warning in batch.warnings)
