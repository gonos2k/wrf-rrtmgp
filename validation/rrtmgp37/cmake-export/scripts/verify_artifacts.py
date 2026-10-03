#!/usr/bin/env python3
"""Verify the SHA256 inventory in artifact-index.json using only Python stdlib."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "artifact-index.json"
index = json.loads(INDEX.read_text(encoding="utf-8"))
errors = []
for item in index.get("files", []):
    rel = Path(item["path"])
    target = (ROOT / rel).resolve()
    if not target.is_relative_to(ROOT):
        errors.append(f"path escapes package: {rel}")
        continue
    if not target.is_file():
        errors.append(f"missing file: {rel}")
        continue
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != item["sha256"]:
        errors.append(f"SHA256 mismatch: {rel}: {digest}")
if errors:
    print("ARTIFACT_VERIFY_FAIL")
    print("\n".join(errors))
    sys.exit(1)
print(f"ARTIFACT_VERIFY_PASS {len(index.get('files', []))} files")
