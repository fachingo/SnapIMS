from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any

from snapims.models import PhotoRecord
from snapims.protocol import parse_command
from snapims.qr import UNREADABLE_PHOTO_PAYLOAD


PLAN_VERSION = 1
MAX_PLAN_ACTIONS = 1_000
ACTION_PAYLOADS = {
    "start": "CVHS1:BATCH:START",
    "end": "CVHS1:BATCH:END",
    "next": "CVHS1:ITEM:NEXT",
    "cont": "CVHS1:ITEM:CONT",
    "rare": "CVHS1:FLAG:RARE",
    "review": "CVHS1:FLAG:REVIEW",
}


class ImportRepairError(ValueError):
    pass


def _index(value: object) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ImportRepairError("Import repair contains an invalid photo position.") from exc
    if parsed < 0 or parsed > 1_000_000:
        raise ImportRepairError("Import repair photo position is out of range.")
    return parsed


def _command(value: object) -> str:
    payload = str(value or "").strip().upper()
    command = parse_command(payload)
    if command is None:
        raise ImportRepairError(f"Unsupported manual command: {payload or '(empty)'}")
    return command.payload


def normalize_repair_plan(value: str | Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None or value == "":
        return {"version": PLAN_VERSION, "overrides": {}, "insert_before": {}}
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ImportRepairError("Import repair data is invalid. Preview the folder again.") from exc
    else:
        raw = dict(value)
    if not isinstance(raw, dict):
        raise ImportRepairError("Import repair data must be an object.")
    overrides: dict[str, str] = {}
    for raw_index, raw_action in dict(raw.get("overrides") or {}).items():
        index = _index(raw_index)
        action = str(raw_action or "").strip().upper()
        if action in {"PRODUCT", "IGNORE"}:
            overrides[str(index)] = action
        else:
            overrides[str(index)] = _command(action)
    inserted: dict[str, list[str]] = {}
    for raw_index, raw_commands in dict(raw.get("insert_before") or {}).items():
        index = _index(raw_index)
        if not isinstance(raw_commands, list):
            raise ImportRepairError("Inserted import commands must be a list.")
        commands = [_command(command) for command in raw_commands if str(command).strip()]
        if commands:
            inserted[str(index)] = commands
    action_count = len(overrides) + sum(len(commands) for commands in inserted.values())
    if action_count > MAX_PLAN_ACTIONS:
        raise ImportRepairError("Import repair contains too many actions.")
    return {"version": PLAN_VERSION, "overrides": overrides, "insert_before": inserted}


def repair_plan_json(value: str | Mapping[str, Any] | None) -> str:
    return json.dumps(normalize_repair_plan(value), sort_keys=True, separators=(",", ":"))


def repair_action_count(value: str | Mapping[str, Any] | None) -> int:
    plan = normalize_repair_plan(value)
    return len(plan["overrides"]) + sum(
        len(commands) for commands in plan["insert_before"].values()
    )


def repair_source_manifest(records: list[PhotoRecord]) -> list[str]:
    """Return stable source identities used to keep index repairs attached.

    Repair actions are submitted by photo position. The manifest prevents a
    saved action from being silently applied to a different photograph when a
    folder changes between preview, restart, recheck, and commit.
    """
    return [
        f"{record.path.resolve()}\0{record.original_name}\0{record.sha256}"
        for record in records
    ]


def remap_repair_plan(
    value: str | Mapping[str, Any] | None,
    previous_manifest: list[str] | tuple[str, ...] | None,
    records: list[PhotoRecord],
) -> dict[str, Any]:
    plan = normalize_repair_plan(value)
    old = [str(entry) for entry in (previous_manifest or [])]
    current = repair_source_manifest(records)
    if not old or old == current or repair_action_count(plan) == 0:
        return plan

    current_positions: dict[str, list[int]] = {}
    for index, identity in enumerate(current):
        current_positions.setdefault(identity, []).append(index)

    def mapped_index(raw_index: str) -> str:
        index = _index(raw_index)
        if index >= len(old):
            raise ImportRepairError(
                "The source folder changed and a saved correction no longer matches a photo. "
                "The batch must be previewed again before importing."
            )
        matches = current_positions.get(old[index], [])
        if len(matches) != 1:
            raise ImportRepairError(
                "The source folder changed and a saved correction no longer matches exactly one "
                "photo. The batch must be previewed again before importing."
            )
        return str(matches[0])

    overrides = {
        mapped_index(raw_index): action
        for raw_index, action in plan["overrides"].items()
    }
    inserted = {
        mapped_index(raw_index): list(commands)
        for raw_index, commands in plan["insert_before"].items()
    }
    return normalize_repair_plan(
        {"version": PLAN_VERSION, "overrides": overrides, "insert_before": inserted}
    )


def _form_command(action: str, location: str) -> str | None:
    normalized = action.strip().casefold()
    if normalized in {"", "none", "auto"}:
        return None
    if normalized == "location":
        shelf = location.strip().upper()
        if not shelf:
            raise ImportRepairError("Enter a shelf location such as A6.")
        try:
            return _command(f"CVHS1:LOC:{shelf}")
        except ImportRepairError as exc:
            raise ImportRepairError(
                "Shelf location must be Q1 or A1 through J10 (for example, A6)."
            ) from exc
    payload = ACTION_PAYLOADS.get(normalized)
    if payload is None:
        raise ImportRepairError(f"Unsupported repair choice: {action}")
    return payload


def update_plan_from_form(
    existing: str | Mapping[str, Any] | None,
    form: Mapping[str, Any],
) -> dict[str, Any]:
    plan = normalize_repair_plan(existing)
    overrides = dict(plan["overrides"])
    inserted = {key: list(value) for key, value in plan["insert_before"].items()}
    indexes = sorted(
        {
            _index(key.removeprefix("override_"))
            for key in form
            if re.fullmatch(r"override_\d+", str(key))
        }
    )
    for index in indexes:
        key = str(index)
        action = str(form.get(f"override_{index}") or "auto").strip().casefold()
        if action in {"", "auto"}:
            overrides.pop(key, None)
        elif action == "product":
            overrides[key] = "PRODUCT"
        elif action == "ignore":
            overrides[key] = "IGNORE"
        else:
            command = _form_command(
                action, str(form.get(f"override_location_{index}") or "")
            )
            if command is None:
                overrides.pop(key, None)
            else:
                overrides[key] = command
        insert_action = str(form.get(f"insert_{index}") or "none")
        if insert_action.strip().casefold() == "clear":
            inserted.pop(key, None)
        else:
            command = _form_command(
                insert_action, str(form.get(f"insert_location_{index}") or "")
            )
            if command is not None:
                commands = inserted.setdefault(key, [])
                if command not in commands:
                    commands.append(command)
    return normalize_repair_plan(
        {"version": PLAN_VERSION, "overrides": overrides, "insert_before": inserted}
    )


def apply_repair_plan(
    records: list[PhotoRecord],
    value: str | Mapping[str, Any] | None,
) -> tuple[list[PhotoRecord], list[PhotoRecord], dict[str, Any]]:
    """Return effective interpreter records, preserved physical records, and plan.

    Physical source photographs are never edited. Expanded stream indices leave
    deterministic slots for virtual commands while keeping physical order stable.
    """
    plan = normalize_repair_plan(value)
    if not plan["overrides"] and not plan["insert_before"]:
        return list(records), list(records), plan
    effective: list[PhotoRecord] = []
    physical: list[PhotoRecord] = []
    for source_index, original in enumerate(records):
        expanded_index = source_index * 100 + 50
        action = plan["overrides"].get(str(source_index), "")
        if original.qr_payload == UNREADABLE_PHOTO_PAYLOAD and action not in {"", "IGNORE"}:
            raise ImportRepairError(
                f"{original.original_name} is unreadable. Ignore this photo or replace only this "
                "file, then preview again."
            )
        physical_record = replace(original, stream_index=expanded_index)
        if action == "PRODUCT":
            physical_record = replace(physical_record, qr_payload=None)
        elif action and action != "IGNORE":
            physical_record = replace(physical_record, qr_payload=_command(action))
        physical.append(physical_record)
        commands = plan["insert_before"].get(str(source_index), [])
        for offset, payload in enumerate(commands, start=1):
            normalized = _command(payload)
            effective.append(
                PhotoRecord(
                    path=original.path,
                    original_name=f"Manual {normalized} before {original.original_name}",
                    captured_at=original.captured_at - timedelta(microseconds=len(commands) - offset + 1),
                    timestamp_source="manual_repair",
                    stream_index=source_index * 100 + offset,
                    sha256=hashlib.sha256(
                        f"manual:{source_index}:{offset}:{normalized}".encode("utf-8")
                    ).hexdigest(),
                    qr_payload=normalized,
                )
            )
        if action != "IGNORE":
            effective.append(physical_record)
    return effective, physical, plan


def repaired_fingerprint(base_fingerprint: str, value: str | Mapping[str, Any] | None) -> str:
    plan = normalize_repair_plan(value)
    if not plan["overrides"] and not plan["insert_before"]:
        return base_fingerprint
    digest = hashlib.sha256()
    digest.update(base_fingerprint.encode("ascii"))
    digest.update(b"\0manual-import-repair\0")
    digest.update(repair_plan_json(plan).encode("utf-8"))
    return digest.hexdigest()


def record_source_index(record: PhotoRecord | None, source_records: list[PhotoRecord]) -> int:
    if record is not None:
        resolved = record.path.resolve()
        for index, source in enumerate(source_records):
            if source.path.resolve() == resolved and source.original_name == record.original_name:
                return index
        for index, source in enumerate(source_records):
            if source.path.resolve() == resolved:
                return index
    return 0


_SESSION_TTL_SECONDS = 60 * 60
_SESSIONS: dict[str, tuple[float, tuple[Path, ...]]] = {}
_SESSION_LOCK = threading.Lock()


def create_photo_session(records: list[PhotoRecord]) -> str:
    token = secrets.token_urlsafe(24)
    now_value = time.monotonic()
    with _SESSION_LOCK:
        expired = [key for key, (created, _) in _SESSIONS.items() if now_value - created > _SESSION_TTL_SECONDS]
        for key in expired:
            _SESSIONS.pop(key, None)
        _SESSIONS[token] = (now_value, tuple(record.path.resolve() for record in records))
    return token


def session_photo(token: str, index: int) -> Path | None:
    now_value = time.monotonic()
    with _SESSION_LOCK:
        session = _SESSIONS.get(token)
        if session is None or now_value - session[0] > _SESSION_TTL_SECONDS:
            _SESSIONS.pop(token, None)
            return None
        paths = session[1]
    if index < 0 or index >= len(paths):
        return None
    path = paths[index]
    return path if path.is_file() else None
