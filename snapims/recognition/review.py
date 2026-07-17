from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACTION_ACCEPT = "accept"
ACTION_SKIP = "skip"
ACTION_PREVIOUS = "previous"
ACTION_MANUAL_REVIEW = "manual_review"
ACTION_EDIT = "edit"
ACTION_CANCEL_EDIT = "cancel_edit"
ACTION_ACCEPT_EDITED = "accept_edited"
ACTION_RETRY = "retry"
ACTION_PHOTO_PREFIX = "photo:"

_KEY_ACTIONS = {
    "Enter": ACTION_ACCEPT,
    "ArrowRight": ACTION_SKIP,
    "ArrowLeft": ACTION_PREVIOUS,
    "r": ACTION_MANUAL_REVIEW,
    "R": ACTION_MANUAL_REVIEW,
    "e": ACTION_EDIT,
    "E": ACTION_EDIT,
    "Escape": ACTION_CANCEL_EDIT,
    "f": ACTION_RETRY,
    "F": ACTION_RETRY,
}


@dataclass(frozen=True, slots=True)
class KeyboardDecision:
    action: str | None
    event_id: str


def keyboard_decision(
    event: dict[str, Any] | None,
    *,
    last_event_id: str,
    edit_mode: bool,
) -> KeyboardDecision:
    if not event:
        return KeyboardDecision(None, last_event_id)
    event_id = str(event.get("id", ""))
    if not event_id or event_id == last_event_id:
        return KeyboardDecision(None, last_event_id)
    key = str(event.get("key", ""))
    ctrl = bool(event.get("ctrl") or event.get("meta"))
    typing = bool(event.get("typing"))
    if typing and not (key == "Enter" and ctrl):
        return KeyboardDecision(None, event_id)
    if key == "Enter" and ctrl:
        return KeyboardDecision(ACTION_ACCEPT_EDITED if edit_mode else None, event_id)
    if key.isdigit() and key != "0":
        return KeyboardDecision(f"{ACTION_PHOTO_PREFIX}{int(key) - 1}", event_id)
    action = _KEY_ACTIONS.get(key)
    if action == ACTION_ACCEPT and edit_mode:
        action = None
    if action == ACTION_CANCEL_EDIT and not edit_mode:
        action = None
    return KeyboardDecision(action, event_id)


def current_result_id(result_ids: list[int], preferred_id: int | None) -> int | None:
    if not result_ids:
        return None
    if preferred_id in result_ids:
        return preferred_id
    return result_ids[0]


def next_result_id(result_ids: list[int], current_id: int) -> int | None:
    if current_id not in result_ids:
        return result_ids[0] if result_ids else None
    index = result_ids.index(current_id)
    if index + 1 < len(result_ids):
        return result_ids[index + 1]
    return result_ids[0] if len(result_ids) > 1 else None


def previous_result_id(result_ids: list[int], current_id: int) -> int | None:
    if current_id not in result_ids:
        return result_ids[0] if result_ids else None
    index = result_ids.index(current_id)
    if index == 0:
        return current_id
    return result_ids[index - 1]
