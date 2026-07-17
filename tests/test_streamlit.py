from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_dashboard_renders_without_runtime_errors(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "ui-data"))
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    assert not app.exception
    assert any("SnapIMS dashboard" in title.value for title in app.title)
