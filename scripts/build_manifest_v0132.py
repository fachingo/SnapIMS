#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'.git','.pytest_cache','.venv','__pycache__'}
entries=[]
for path in sorted(ROOT.rglob('*')):
    if not path.is_file() or any(part in EXCLUDE for part in path.parts) or path.suffix=='.pyc':
        continue
    rel=path.relative_to(ROOT).as_posix()
    if rel in {'PACKAGE_FILE_MANIFEST.sha256','MANIFEST_SHA256.json','SHA256SUMS'}:
        continue
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    entries.append({'path':rel,'sha256':digest,'bytes':path.stat().st_size})
(ROOT/'PACKAGE_FILE_MANIFEST.sha256').write_text(''.join(f"{e['sha256']}  {e['path']}\n" for e in entries),encoding='utf-8')
(ROOT/'MANIFEST_SHA256.json').write_text(json.dumps({'release':'0.13.2','files':entries},indent=2),encoding='utf-8')
required=['install_v0132.sh','dist/snapims-0.13.2-py3-none-any.whl','SnapIMS_Operator_Guide_v0.13.2.pdf','SnapIMS_Operator_Guide_v0.13.2.docx']
for rel in required:
    p=ROOT/rel
    if not p.exists(): raise SystemExit(f'missing required release file: {rel}')
(ROOT/'SHA256SUMS').write_text(''.join(f"{hashlib.sha256((ROOT/r).read_bytes()).hexdigest()}  {r}\n" for r in required),encoding='utf-8')
print(f'manifested {len(entries)} files')
