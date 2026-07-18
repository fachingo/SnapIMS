from __future__ import annotations

import argparse
import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class ReleaseSafetyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReleaseArchive:
    destination: Path
    members: tuple[str, ...]


FORBIDDEN_PARTS = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".git",
        ".venv",
        "backups",
        "exports",
        "logs",
        "originals",
        "processed",
    }
)
FORBIDDEN_SUFFIXES = frozenset(
    {".db", ".sqlite", ".sqlite3", ".log", ".bak", ".backup", ".pyc"}
)
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"})
SECRET_PATTERNS = (
    re.compile(rb"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(rb"\bshpat_(?!(?:replace_me|test_only)\b)[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        rb"(?im)^[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET|PASSWORD)[ \t]*=[ \t]*[^ \t\r\n#][^\r\n]*$"
    ),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def tracked_files(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return sorted(path for path in completed.stdout.decode("utf-8").split("\0") if path)


def _validate_path(relative: str) -> None:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ReleaseSafetyError("Release refused: unsafe archive path detected.")
    lowered_parts = {part.casefold() for part in path.parts}
    name = path.name.casefold()
    if lowered_parts & FORBIDDEN_PARTS:
        raise ReleaseSafetyError("Release refused: forbidden runtime artifact detected.")
    if name.startswith(".env") and relative != ".env.example":
        raise ReleaseSafetyError("Release refused: environment file detected.")
    if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
        raise ReleaseSafetyError("Release refused: database, log, backup, or cache detected.")
    if path.suffix.casefold() in IMAGE_SUFFIXES and not relative.startswith(
        "demo-data/camera-roll/"
    ):
        raise ReleaseSafetyError("Release refused: non-synthetic inventory image detected.")


def _validate_content(path: Path) -> None:
    content = path.read_bytes().replace(b"shpat_replace_me", b"")
    if any(pattern.search(content) for pattern in SECRET_PATTERNS):
        raise ReleaseSafetyError("Release refused: credential-like content detected and redacted.")


def build_release_archive(
    root: Path,
    destination: Path,
    *,
    members: list[str] | None = None,
) -> ReleaseArchive:
    root = root.resolve()
    selected = tracked_files(root) if members is None else sorted(set(members))
    if not selected:
        raise ReleaseSafetyError("Release refused: no tracked source artifacts were found.")
    for relative in selected:
        _validate_path(relative)
        source = root / relative
        if not source.is_file() or source.is_symlink():
            raise ReleaseSafetyError("Release refused: invalid tracked artifact detected.")
        _validate_content(source)

    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        for relative in selected:
            archive.add(root / relative, arcname=f"SnapIMS/{relative}", recursive=False)
    return ReleaseArchive(destination, tuple(selected))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a secret-safe SnapIMS source archive")
    parser.add_argument("--output", type=Path, required=True, help="Destination .tar.gz path")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    args = parser.parse_args()
    try:
        result = build_release_archive(args.root, args.output)
    except ReleaseSafetyError as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Created {result.destination} with {len(result.members)} tracked artifacts.")


if __name__ == "__main__":
    main()
