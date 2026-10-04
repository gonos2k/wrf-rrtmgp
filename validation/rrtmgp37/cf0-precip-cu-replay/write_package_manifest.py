#!/usr/bin/env python3
"""Regenerate deterministic SHA-256 manifest for files in this package."""
import hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
files={}
for p in sorted(HERE.rglob('*')):
    if not p.is_file() or p.name=='package-manifest.json' or '__pycache__' in p.parts:
        continue
    rel=p.relative_to(HERE).as_posix()
    files[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
(HERE/'package-manifest.json').write_text(json.dumps({'schema':'cf0-cu-eight-call-evidence-package-v1','files':files},indent=2,sort_keys=True)+'\n')
print(json.dumps({'files':len(files),'manifest':'package-manifest.json'},sort_keys=True))
