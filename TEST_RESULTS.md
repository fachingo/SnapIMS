# SnapIMS 0.5.1 Test Results

## Passed locally

- `pytest -q`: **110 tests passed**.
- `python -m compileall -q snapims`: passed.
- Native Playwright/Chromium-through-uvicorn audit: passed.
- Wheel build: passed with `pip wheel . --no-deps --no-build-isolation`.
- Wheel filename: `snapims-0.5.1-py3-none-any.whl`.
- Isolated-target install and package-resource smoke: passed; templates and static assets were present.
- CLI help from installed wheel: passed.
- SQLite integrity after audit: ok; zero foreign-key violations.

## Not executable in this container

- `ruff check .`: Ruff was not installed and the restricted package index returned no package.
- `mypy snapims --ignore-missing-imports`: MyPy was not installed and the restricted package index returned no package.
- `python -m build`: the `build` frontend was not installed; the wheel was built successfully via pip/setuptools without build isolation.
- `pip check`: the shared container reports an unrelated pre-existing MoviePy/Pillow version conflict. SnapIMS packaging itself installed and imported successfully.

No unavailable gate is claimed as passed. The GitHub Actions workflow retains the required pytest, Ruff, MyPy, compile, and build commands for execution after the branch is pushed from an authorized environment.
