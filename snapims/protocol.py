from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class CommandKind(StrEnum):
    BATCH_START = "batch_start"
    BATCH_END = "batch_end"
    ITEM_NEXT = "item_next"
    ITEM_CONT = "item_cont"
    FLAG_RARE = "flag_rare"
    FLAG_REVIEW = "flag_review"
    LOCATION = "location"


@dataclass(frozen=True, slots=True)
class Command:
    payload: str
    kind: CommandKind
    value: str | None = None


LOCATION_RE = re.compile(r"^CVHS1:LOC:(Q1|[A-J](?:[1-9]|10))$")
FIXED_COMMANDS: dict[str, CommandKind] = {
    "CVHS1:BATCH:START": CommandKind.BATCH_START,
    "CVHS1:BATCH:END": CommandKind.BATCH_END,
    "CVHS1:ITEM:NEXT": CommandKind.ITEM_NEXT,
    "CVHS1:ITEM:CONT": CommandKind.ITEM_CONT,
    "CVHS1:FLAG:RARE": CommandKind.FLAG_RARE,
    "CVHS1:FLAG:REVIEW": CommandKind.FLAG_REVIEW,
}


def parse_command(payload: str) -> Command | None:
    normalized = payload.strip().upper()
    kind = FIXED_COMMANDS.get(normalized)
    if kind is not None:
        return Command(payload=normalized, kind=kind)
    match = LOCATION_RE.fullmatch(normalized)
    if match:
        return Command(payload=normalized, kind=CommandKind.LOCATION, value=match.group(1))
    return None


def all_location_payloads() -> tuple[str, ...]:
    return ("CVHS1:LOC:Q1",) + tuple(
        f"CVHS1:LOC:{letter}{number}" for letter in "ABCDEFGHIJ" for number in range(1, 11)
    )
