from __future__ import annotations

from pathlib import Path

import pytest

from snapims.config import DataPaths


@pytest.fixture
def data_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DataPaths:
    root = tmp_path / "workspace"
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(root))
    return DataPaths.from_root(root).ensure()
