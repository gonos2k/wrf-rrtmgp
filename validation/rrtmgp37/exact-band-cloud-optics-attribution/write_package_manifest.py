#!/usr/bin/env python3
"""Write a closed SHA256/size manifest for this evidence directory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def pin(path: Path) -> dict:
    h = hashlib.sha256(); size = 0
    with path.open("rb") as f:
        while block := f.read(1 << 20): h.update(block); size += len(block)
    return {"path": path.name, "sha256": h.hexdigest(), "size_bytes": size}


def main() -> None:
    root = Path(__file__).resolve().parent
    target = root / "package-manifest.json"
    files = [p for p in root.rglob("*") if p.is_file() and p != target and "__pycache__" not in p.parts]
    entries = []
    for path in sorted(files):
        h = hashlib.sha256(); size = 0
        with path.open("rb") as f:
            while block := f.read(1 << 20): h.update(block); size += len(block)
        entries.append({"path": path.relative_to(root).as_posix(), "sha256": h.hexdigest(), "size_bytes": size})
    manifest = {"schema": "udm37-exact-band-cloud-optics-package-manifest-v1",
                "status": "TWO_CALLS_TERMINAL_REVIEWED_SCOPED_EVIDENCE",
                "files": entries,
                "external_reuse": [
                    "../rrtmg4-same-call-attribution/ (export, traces, reader)",
                    "../cf0-precip-cu-replay/outputs/baseline-sw.result.txt.gz (baseline output)"]}
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": target.name, "file_count": len(entries)}, sort_keys=True))


if __name__ == "__main__": main()
