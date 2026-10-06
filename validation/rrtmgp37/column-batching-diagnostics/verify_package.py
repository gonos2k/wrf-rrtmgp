#!/usr/bin/env python3
"""Check package payload pins; --external also verifies referenced receipts."""
import argparse,hashlib,json
from pathlib import Path
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('root',nargs='?',default='.');ap.add_argument('--external',action='store_true');a=ap.parse_args()
 root=Path(a.root).resolve(strict=True);m=json.loads((root/'manifest.json').read_text())
 for r in m['files']:
  rel=Path(r['path'])
  if rel.is_absolute() or '..' in rel.parts: raise ValueError(f'unsafe path: {rel}')
  p=(root/rel).resolve(strict=True);p.relative_to(root)
  if not p.is_file() or p.stat().st_size!=r['size_bytes'] or sha(p)!=r['sha256']: raise ValueError(f'payload mismatch: {rel}')
 count=len(m['files'])
 if a.external:
  refs=json.loads((root/'source_references.json').read_text())
  evidence_root=Path(refs['evidence_root']).resolve(strict=True)
  for rel,r in refs['files'].items():
   p=evidence_root/rel
   if not p.is_file() or p.stat().st_size!=r['size_bytes'] or sha(p)!=r['sha256']: raise ValueError(f'external pin mismatch: {rel}')
  print(f'PASS: {count} package payloads and {len(refs["files"])} external receipts')
 else: print(f'PASS: {count} package payloads')
 return 0
if __name__=='__main__': raise SystemExit(main())
