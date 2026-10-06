#!/usr/bin/env python3
"""Create the portable SHA-256/size inventory for this evidence directory."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


files = []
for path in sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name != "manifest.json"):
    files.append({"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha(path)})
(ROOT / "manifest.json").write_text(json.dumps({"format": "UDM_SURFRAD_EVIDENCE_SHA256_V1", "files": files}, indent=2) + "\n")
print(f"wrote {len(files)} artifact hashes")
