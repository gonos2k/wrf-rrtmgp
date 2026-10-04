#!/usr/bin/env python3
"""Verify hashes of the copied evidence bundle; no access to source run dirs required."""
import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parent
m=json.loads((root/'bundle-manifest.json').read_text())
errors=[]
for rel,e in m['files'].items():
 p=root/rel
 if not p.is_file(): errors.append(f'missing: {rel}');continue
 h=hashlib.sha256(p.read_bytes()).hexdigest()
 if p.stat().st_size!=e['size_bytes'] or h!=e['sha256']:errors.append(f'hash/size mismatch: {rel}')
print(json.dumps({'status':'FAIL' if errors else 'PASS','file_count':len(m['files']),'errors':errors},indent=2))
sys.exit(bool(errors))
