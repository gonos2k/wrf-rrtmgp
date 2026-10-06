#!/usr/bin/env python3
"""Verify payload hashes in this evidence bundle; no build or model is run."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text())
errors = []
for name, expected in manifest["files"].items():
    path = root / name
    if not path.is_file():
        errors.append(f"missing: {name}")
        continue
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        errors.append(f"SHA256 mismatch: {name}: {actual} != {expected}")
if errors:
    print("FAIL")
    print("\n".join(errors))
    sys.exit(1)
print(f"PASS: {len(manifest['files'])} evidence payload files match SHA256")
