#!/usr/bin/env python3
"""Verify the copied evidence bytes and, optionally, original large artifacts."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evidence-manifest.json"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def fail(msg):
    raise RuntimeError(msg)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-external", action="store_true", help="also rehash original large files at recorded paths")
    ap.add_argument("--receipt", type=Path, help="write verification receipt to a new path")
    args = ap.parse_args()
    m = json.loads(MANIFEST.read_text())
    checked = []
    for row in m["bundle_artifacts"]:
        p = ROOT / row["bundle_path"]
        if not p.is_file():
            fail(f"missing bundled file: {row['bundle_path']}")
        raw_sha = sha(p)
        if raw_sha != row["bundle_sha256"] or p.stat().st_size != row["bundle_size_bytes"]:
            fail(f"bundled bytes differ: {row['bundle_path']}")
        if row["representation"] == "gzip":
            with gzip.open(p, "rb") as f:
                h = hashlib.sha256()
                size = 0
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    size += len(block)
                    h.update(block)
            if h.hexdigest() != row["original_sha256"] or size != row["original_size_bytes"]:
                fail(f"decompressed original differs: {row['bundle_path']}")
        elif row["representation"] == "identity":
            if raw_sha != row["original_sha256"] or p.stat().st_size != row["original_size_bytes"]:
                fail(f"identity mapping differs: {row['bundle_path']}")
        else:
            fail(f"unknown representation {row['representation']!r}")
        checked.append(row["bundle_path"])
    generated = []
    for row in m.get("generated_artifacts", []):
        p = ROOT / row["path"]
        if not p.is_file() or p.stat().st_size != row["size_bytes"] or sha(p) != row["sha256"]:
            fail(f"generated package artifact differs: {row['path']}")
        generated.append(row["path"])
    external = []
    if args.check_external:
        for row in m["external_large_artifacts_not_copied"]:
            p = Path(row["original_path"])
            if not p.is_file() or p.stat().st_size != row["size_bytes"] or sha(p) != row["sha256"]:
                fail(f"external source differs or missing: {p}")
            external.append(str(p))
    receipt = {
        "schema": "matthew-dt60-evidence-verification-v1",
        "status": "PASS",
        "manifest_sha256": sha(MANIFEST),
        "bundled_artifact_count": len(checked),
        "generated_artifact_count": len(generated),
        "external_artifact_count": len(external),
        "external_check_requested": args.check_external,
        "bundled_paths": checked,
        "generated_paths": generated,
        "external_paths": external,
    }
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        if args.receipt.exists():
            fail(f"refusing to overwrite receipt: {args.receipt}")
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(rendered)
    print(rendered, end="")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
