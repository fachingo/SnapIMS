#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence" / "v0.10.1" / "local-verification"
EVIDENCE.mkdir(parents=True, exist_ok=True)

COMMANDS: list[tuple[str, list[str]]] = [
    ("focused-tests", [sys.executable, "-m", "pytest", "-q", "tests/test_v0101_regressions.py"]),
    ("full-pytest", [sys.executable, "-m", "pytest", "-q"]),
    ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
    ("mypy", [sys.executable, "-m", "mypy", "snapims", "--ignore-missing-imports"]),
    ("compileall", [sys.executable, "-m", "compileall", "-q", "snapims", "tests", "scripts"]),
    ("node-check", ["node", "--check", "snapims/web/static/app.js"]),
    ("build", [sys.executable, "-m", "build", "--no-isolation"]),
    ("pip-check", [sys.executable, "-m", "pip", "check"]),
    ("git-diff-check", ["git", "diff", "--check"]),
]


def run(name: str, command: list[str]) -> dict[str, object]:
    if not shutil.which(command[0]) and command[0] != sys.executable:
        result = {"name": name, "command": command, "status": "SKIP", "reason": "executable missing"}
        (EVIDENCE / f"{name}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    output = completed.stdout + completed.stderr
    (EVIDENCE / f"{name}.txt").write_text(output, encoding="utf-8")
    (EVIDENCE / f"{name}.exit").write_text(str(completed.returncode), encoding="utf-8")
    return {
        "name": name,
        "command": command,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit": completed.returncode,
    }


def database_checks() -> dict[str, object]:
    try:
        from snapims.config import DataPaths
        from snapims import db

        paths = DataPaths.from_root().ensure()
        db.initialize(paths.db_file, paths=paths)
        with db.connect(paths.db_file) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
            schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
            manifest = db.schema_manifest_report(connection)
            counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("batches", "items", "photos", "recognition_results")
            }
        result = {
            "status": "PASS" if integrity == "ok" and not foreign and manifest["ok"] and schema == 13 else "FAIL",
            "schema": schema,
            "integrity": integrity,
            "foreign_key_failures": len(foreign),
            "manifest": manifest,
            "counts": counts,
            "database": str(paths.db_file),
        }
    except Exception as exc:
        result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
    (EVIDENCE / "database.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def hygiene() -> dict[str, object]:
    problems: list[str] = []
    if (ROOT / 'ion bump"').exists():
        problems.append('tracked terminal-help file ion bump" exists')
    allowed_binary_roots = {"release-evidence", ".git", ".venv", "dist", "build"}
    control_files: list[str] = []
    for path in ROOT.iterdir():
        if (
            path.name.startswith(".")
            or path.name in allowed_binary_roots
            or path.is_dir()
            or path.suffix.lower() in {".pdf", ".docx"}
        ):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"SUMMARY OF LESS COMMANDS" in data or b"\x08" in data:
            control_files.append(path.name)
    problems.extend(f"terminal/pager capture: {name}" for name in control_files)
    result = {"status": "PASS" if not problems else "FAIL", "problems": problems}
    (EVIDENCE / "hygiene.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    results = [run(name, command) for name, command in COMMANDS]
    results.append({"name": "database", **database_checks()})
    results.append({"name": "hygiene", **hygiene()})
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "version": "0.10.1",
        "results": results,
        "overall": "PASS" if all(result.get("status") in {"PASS", "SKIP"} for result in results) else "FAIL",
    }
    raw = json.dumps(summary, indent=2, default=str)
    (EVIDENCE / "summary.json").write_text(raw, encoding="utf-8")
    print(raw)
    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
