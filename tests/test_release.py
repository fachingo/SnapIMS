from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from snapims.release import ReleaseSafetyError, build_release_archive


def test_release_archive_contains_only_selected_tracked_sources(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "snapims").mkdir(parents=True)
    (root / "snapims" / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "README.md").write_text("safe docs\n", encoding="utf-8")
    (root / ".env").write_text("OPENAI_API_KEY=not-in-archive\n", encoding="utf-8")
    destination = tmp_path / "snapims-release.tar.gz"

    result = build_release_archive(
        root,
        destination,
        members=["README.md", "snapims/safe.py"],
    )

    assert result.members == ("README.md", "snapims/safe.py")
    with tarfile.open(destination, "r:gz") as archive:
        names = sorted(archive.getnames())
    assert names == ["SnapIMS/README.md", "SnapIMS/snapims/safe.py"]
    assert not any(".env" in name for name in names)


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        "inventory.sqlite3",
        "logs/snapims.log",
        "backups/inventory.backup",
        "exports/inventory.csv",
        "originals/real-tape.jpg",
        "__pycache__/module.pyc",
    ],
)
def test_release_refuses_forbidden_artifacts_without_writing_archive(
    tmp_path: Path, relative: str
) -> None:
    root = tmp_path / "repo"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"fixture")
    destination = tmp_path / "unsafe.tar.gz"

    with pytest.raises(ReleaseSafetyError):
        build_release_archive(root, destination, members=[relative])

    assert not destination.exists()


def test_release_refuses_secret_without_echoing_it(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    secret = "shpat_" + "this_value_must_never_be_echoed"
    (root / "settings.txt").write_text(f"SHOPIFY_ADMIN_ACCESS_TOKEN={secret}\n")

    with pytest.raises(ReleaseSafetyError) as caught:
        build_release_archive(root, tmp_path / "unsafe.tar.gz", members=["settings.txt"])

    assert secret not in str(caught.value)
    assert "redacted" in str(caught.value)


def test_wheel_package_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    python = shutil.which("python3")
    assert python is not None
    completed = subprocess.run(
        [
            python,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    wheels = list(tmp_path.glob("snapims-*.whl"))
    assert len(wheels) == 1
