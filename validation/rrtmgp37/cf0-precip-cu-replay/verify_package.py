#!/usr/bin/env python3
"""Check exact closed file roster and hashes for this evidence package."""
import hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
manifest=json.loads((HERE/'package-manifest.json').read_text())
files=manifest.get('files')
if not isinstance(files,dict) or not files: raise SystemExit('FAIL: malformed/empty package manifest')
actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p.name!='package-manifest.json' and '__pycache__' not in p.parts}
if actual!=set(files):
    raise SystemExit(f'FAIL: closed roster mismatch; unlisted={sorted(actual-set(files))}; missing={sorted(set(files)-actual)}')
for rel,expected in sorted(files.items()):
    got=hashlib.sha256((HERE/rel).read_bytes()).hexdigest()
    if got!=expected: raise SystemExit(f'FAIL: hash mismatch {rel}: {got}')
print(json.dumps({'status':'PASS_CLOSED_PACKAGE_ROSTER','files':len(files),'manifest_sha256':hashlib.sha256((HERE/'package-manifest.json').read_bytes()).hexdigest()},sort_keys=True))
