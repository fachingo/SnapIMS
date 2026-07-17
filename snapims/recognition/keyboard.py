from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import streamlit.components.v1 as components

_COMPONENT_PATH = Path(__file__).with_name("keyboard_component")
_keyboard_component = components.declare_component(
    "snapims_keyboard_shortcuts",
    path=str(_COMPONENT_PATH),
)


def keyboard_shortcut_event(*, key: str) -> dict[str, Any] | None:
    value = _keyboard_component(key=key, default=None)
    if value is None:
        return None
    return cast(dict[str, Any], value)
