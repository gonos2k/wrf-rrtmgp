#!/usr/bin/env python3
"""Verify the immutable files listed by artifact-index.json (stdlib only)."""
import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
index = json.loads((root / "artifact-index.json").read_text(encoding="utf-8"))
errors = []
for rel, expected in index["files"].items():
    path = root / rel
    if not path.is_file():
        errors.append(f"missing: {rel}")
        continue
    data = path.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if len(data) != expected["bytes"] or got != expected["sha256"]:
        errors.append(f"mismatch: {rel}")
if errors:
    print("FAIL")
    print("\n".join(errors))
    sys.exit(1)
print(f"PASS: {len(index['files'])} indexed files verified")
