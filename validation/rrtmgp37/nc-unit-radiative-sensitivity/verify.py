#!/usr/bin/env python3
"""Authenticate this saved conditional sensitivity; no compiler or RTE call."""
import argparse
import hashlib
import json
from pathlib import Path


PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]


def pin(path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_path(root, rel):
    require(isinstance(rel, str) and rel and not Path(rel).is_absolute()
            and ".." not in Path(rel).parts, f"unsafe path: {rel!r}")
    path = root / rel
    require(not path.is_symlink() and path.is_file(), f"missing/nonregular file: {rel}")
    require(path.resolve().is_relative_to(root.resolve()), f"path escaped root: {rel}")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, default=REPO)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    require(manifest["schema"] == "UDM_NC_CONDITIONAL_RTE_ARCHIVE_V1", "schema")
    payload = manifest["payload"]
    names = [row["path"] for row in payload]
    require(len(names) == len(set(names)), "duplicate payload")
    roster = {p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*")
              if p.is_file() and p != PACKAGE / "manifest.json" and "__pycache__" not in p.parts}
    require(roster == set(names), "payload roster changed")
    for row in payload:
        require(set(row) == {"path", "sha256", "size_bytes"}, "payload pin format")
        require(pin(local_path(PACKAGE, row["path"])) ==
                {k: row[k] for k in ("sha256", "size_bytes")}, f"payload changed: {row['path']}")
    for row in manifest["sources"]:
        require(pin(local_path(args.source_root, row["path"])) ==
                {k: row[k] for k in ("sha256", "size_bytes")}, f"source changed: {row['path']}")
    result = {
        "schema": "UDM_NC_CONDITIONAL_RTE_ARCHIVE_RECEIPT_V1",
        "status": "PASS_SCOPED_ARCHIVE_AUTHENTICATION",
        "manifest_sha256": pin(PACKAGE / "manifest.json")["sha256"],
        "authenticated_payloads": len(payload),
        "authenticated_sources": len(manifest["sources"]),
        "execution_counts": {"builds": 0, "models": 0, "RTE": 0},
        "scope": "Saved evidence authentication only. Fresh RTE reproduction uses replay.py separately. Nc units and radiative accuracy remain unresolved.",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
