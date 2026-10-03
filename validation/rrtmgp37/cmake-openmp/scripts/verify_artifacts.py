#!/usr/bin/env python3
"""Verify the SHA-256 index for this OpenMP evidence package."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'artifact-index.json'
data = json.loads(INDEX.read_text())
errors = []
for rel, expected in data['files'].items():
    p = ROOT / rel
    if not p.is_file():
        errors.append(f'missing: {rel}')
        continue
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    if actual != expected:
        errors.append(f'hash mismatch: {rel}: {actual} != {expected}')
if errors:
    raise SystemExit('\n'.join(errors))
print(f"ARTIFACT_VERIFY_PASS {len(data['files'])} files")
