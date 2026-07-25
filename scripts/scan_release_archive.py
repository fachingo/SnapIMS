from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

FORBIDDEN_NAMES = (
    ".env",
    ".pem",
    ".key",
    ".p12",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".log",
    ".pyc",
)
FORBIDDEN_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "workspace", "backups"}
SECRET_PATTERNS = [
    re.compile(rb"OPENAI_API_KEY[ \t]*=[ \t]*[^\s#]+", re.I),
    re.compile(rb"SHOPIFY_ADMIN_ACCESS_TOKEN[ \t]*=[ \t]*[^\s#]+", re.I),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"shpat_[A-Za-z0-9]{20,}"),
]
ALLOWED_ENV_EXAMPLE = ".env.example"


def scan(path: Path) -> list[str]:
    issues: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            lowered = name.casefold()
            parts = {part.casefold() for part in Path(name).parts}
            basename = Path(name).name.casefold()
            if parts & FORBIDDEN_PARTS:
                issues.append(f"forbidden directory: {name}")
            if basename != ALLOWED_ENV_EXAMPLE and any(lowered.endswith(suffix) for suffix in FORBIDDEN_NAMES):
                issues.append(f"forbidden file type: {name}")
            if info.is_dir() or info.file_size > 5_000_000:
                continue
            try:
                payload = archive.read(info)
            except OSError as exc:
                issues.append(f"unreadable member: {name}: {exc}")
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(payload):
                    issues.append(f"possible secret in: {name}")
                    break
    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    issues = scan(args.archive)
    if issues:
        print("ARCHIVE SAFETY SCAN: FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("ARCHIVE SAFETY SCAN: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
