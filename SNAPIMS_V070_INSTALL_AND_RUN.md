# SnapIMS 0.7.0 — Extract, Install, Test, Run and Push

## Extract

```bash
cd ~/Projects
unzip ~/Downloads/SnapIMS-v0.7.0-complete-repo.zip
cd ~/Projects/SnapIMS-v0.7.0
```

## Optional native Linux folder picker

```bash
sudo apt update
sudo apt install -y python3-tk
```

Without Tkinter, SnapIMS automatically exposes the manual-path fallback.

## Create environment and install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Configure OpenAI

```bash
cp -n .env.example .env
nano .env
```

In `.env`, set the `OPENAI_API_KEY` variable to the real key. Do not commit or paste the key into logs, screenshots, documentation, or support messages.

## Run with the existing data directory

```bash
snapims --data-dir ~/SnapIMS-data serve
```

Open `http://127.0.0.1:8767`.

## Run tests

```bash
pytest -q
python -m compileall -q snapims tests scripts
node --check snapims/web/static/app.js
git diff --check
```

## Catalog administration

```bash
python scripts/catalog_admin.py --data-dir ~/SnapIMS-data verify
python scripts/catalog_admin.py --data-dir ~/SnapIMS-data backup
```

## Push

```bash
git status
git push -u origin feature/v0.7.0-keyboard-catalog
git push origin v0.7.0
```
