from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


class FolderPickerUnavailable(RuntimeError):
    pass


def choose_folder(initial: str = "") -> str:
    """Open a native local directory chooser without blocking the ASGI event loop.

    FastAPI executes the normal synchronous route in a worker thread. The picker itself
    runs in a short-lived subprocess so Tk cannot interfere with the web process.
    """
    test_value = os.getenv("SNAPIMS_TEST_FOLDER_PICKER")
    if test_value is not None:
        return test_value
    if not os.getenv("DISPLAY") and sys.platform.startswith("linux"):
        raise FolderPickerUnavailable(
            "Native folder browsing is unavailable in this headless session. Use Advanced manual path."
        )
    script = r'''
import sys
from tkinter import Tk, filedialog
root = Tk()
root.withdraw()
root.attributes("-topmost", True)
selected = filedialog.askdirectory(title="Choose SnapIMS photo folder", initialdir=sys.argv[1] or None)
root.destroy()
print(selected)
'''
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, initial],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FolderPickerUnavailable(f"Could not open the native folder picker: {exc}") from exc
    selected = result.stdout.strip()
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
        raise FolderPickerUnavailable(f"Native folder picker failed: {detail}")
    if not selected:
        return ""
    return str(Path(selected).expanduser().resolve())
