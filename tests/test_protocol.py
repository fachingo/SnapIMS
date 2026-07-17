from __future__ import annotations

import pytest

from snapims.protocol import FIXED_COMMANDS, CommandKind, all_location_payloads, parse_command


@pytest.mark.parametrize("payload,kind", list(FIXED_COMMANDS.items()))
def test_all_fixed_commands(payload: str, kind: CommandKind) -> None:
    command = parse_command(payload.lower())
    assert command is not None
    assert command.kind == kind
    assert command.payload == payload


@pytest.mark.parametrize("payload", all_location_payloads())
def test_complete_location_vocabulary(payload: str) -> None:
    command = parse_command(payload)
    assert command is not None
    assert command.kind == CommandKind.LOCATION
    assert command.value == payload.rsplit(":", 1)[-1]


@pytest.mark.parametrize(
    "payload", ["CVHS1:LOC:K1", "CVHS1:LOC:A0", "CVHS1:LOC:A11", "OTHER:START", "https://example.com"]
)
def test_unknown_qr_payloads_never_execute(payload: str) -> None:
    assert parse_command(payload) is None
