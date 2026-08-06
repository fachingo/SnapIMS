#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys, zipfile
from pathlib import Path
RELEASE='0.15.0'
def run(args,cwd):
    return subprocess.run(args,cwd=cwd,text=True,capture_output=True,check=True)
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('root',type=Path,nargs='?',default=Path(__file__).resolve().parents[1]); args=parser.parse_args()
    root=args.root.resolve()
    required=[root/'install_v0150.sh',root/f'dist/snapims-{RELEASE}-py3-none-any.whl',root/'tests',root/'docs',root/'browser-evidence/v0.15.0/browser-verification.json']
    missing=[str(p) for p in required if not p.exists()]
    if missing: raise SystemExit('missing: '+', '.join(missing))
    run([sys.executable,'-m','compileall','-q','snapims','tests','scripts'],root)
    run(['node','--check','snapims/web/static/app.js'],root)
    run(['bash','-n','install_v0150.sh'],root)
    import tomllib
    assert tomllib.loads((root/'pyproject.toml').read_text())['project']['version']==RELEASE
    browser=json.loads((root/'browser-evidence/v0.15.0/browser-verification.json').read_text())
    assert browser['passed'] is True
    print(json.dumps({'release':RELEASE,'required_files':'PASS','compile':'PASS','javascript':'PASS','installer_syntax':'PASS','browser':'PASS'},indent=2))
if __name__=='__main__': main()
