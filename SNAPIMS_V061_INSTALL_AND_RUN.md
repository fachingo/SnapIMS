# SnapIMS 0.6.1 - Extract, Install, Test, Run, and Push

## Extract the complete repository package

```bash
cd ~/Projects
unzip ~/Downloads/SnapIMS-v0.6.1-complete-repo.zip
cd ~/Projects/SnapIMS-v0.6.1
```

The complete package contains `.git` and the full branch history. If the extracted directory has a longer package name, rename it once:

```bash
mv SnapIMS-v0.6.1-complete-repo SnapIMS-v0.6.1
cd SnapIMS-v0.6.1
```

## Create a clean virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Verify the release

```bash
ruff check .
mypy snapims
pytest -q
python -m compileall -q snapims tests
git diff --check
```

## Run SnapIMS manually

```bash
snapims --data-dir ~/SnapIMS-data serve
```

Open:

```text
http://127.0.0.1:8767
```

Stop a foreground server with `Ctrl+C`.

## Git verification and push

```bash
git status
git branch -vv
git log -1 --oneline
git remote -v
git push -u origin fix/v0.6.1-mega-stabilization
```

Do not force-push. Do not merge to the production branch until CI and the release review pass.

## Existing data

Keep the data directory separate from the repository:

```text
~/SnapIMS-data/
```

Before first launch against an existing workspace, copy `~/SnapIMS-data` to separate storage. SnapIMS also creates a pre-migration SQLite backup before schema changes.
