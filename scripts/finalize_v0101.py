#!/usr/bin/env python3
"""Finalize SnapIMS 0.10.1 only after code and targeted browser gates pass."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "release-evidence" / "v0.10.1" / "local-verification" / "summary.json"
BROWSER = ROOT / "release-evidence" / "v0.10.1" / "targeted-browser" / "results.json"


def load_pass(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"{label} evidence is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("overall") != "PASS":
        raise RuntimeError(f"{label} did not pass: {path}")
    return payload


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {old!r} in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> int:
    load_pass(LOCAL, "Local verification")
    load_pass(BROWSER, "Targeted browser verification")

    replace_once(ROOT / "pyproject.toml", 'version = "0.10.0"', 'version = "0.10.1"')
    replace_once(ROOT / "snapims" / "__init__.py", '__version__ = "0.10.0"', '__version__ = "0.10.1"')

    for name in (
        "README.md",
        "INSTALLATION_GUIDE.md",
        "DEPLOYMENT_GUIDE.md",
        "DEVELOPER_GUIDE.md",
    ):
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"^(#\s+SnapIMS\s+)0\.10\.0\b",
            r"\g<1>0.10.1",
            text,
            count=1,
            flags=re.M,
        )
        text = text.replace("## v0.10.1 Patch Candidate", "## v0.10.1 Patch Status")
        text = text.replace(
            "The v0.10.1 audit-remediation code is staged but the active package version must\n"
            "remain 0.10.0 until `scripts/verify_v0101.py` and targeted browser verification\n"
            "pass. Run `scripts/finalize_v0101.py` only after those gates succeed.",
            "Version 0.10.1 passed the recorded local and targeted browser verification gates.",
        )
        path.write_text(text, encoding="utf-8", newline="\n")

    # Re-run version-sensitive smoke after the controlled bump.
    checks = [
        [sys.executable, "-c", "import snapims; assert snapims.__version__ == '0.10.1'"],
        [sys.executable, "-m", "compileall", "-q", "snapims", "tests", "scripts"],
        [sys.executable, "-m", "build", "--no-isolation"],
    ]
    evidence_dir = ROOT / "release-evidence" / "v0.10.1" / "version-finalization"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for index, command in enumerate(checks, start=1):
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        (evidence_dir / f"check-{index}.txt").write_text(
            completed.stdout + completed.stderr, encoding="utf-8"
        )
        results.append({"command": command, "exit": completed.returncode})
        if completed.returncode:
            raise RuntimeError(f"Version finalization check failed: {' '.join(command)}")

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "version": "0.10.1",
        "local_verification": str(LOCAL),
        "browser_verification": str(BROWSER),
        "results": results,
        "status": "PASS",
    }
    (evidence_dir / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print("SnapIMS active version finalized at 0.10.1. Commit the synchronized source and documents together.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
