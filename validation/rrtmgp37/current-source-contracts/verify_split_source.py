#!/usr/bin/env python3
"""Authenticate an archived package with historical WRF blobs and current evidence files.

The immutable archive verifier is not edited. WRF source/data paths are checked
against the historical checkout; validation evidence sidecars are checked in
the present checkout where those later-added files live.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe_path(root: Path, rel: str) -> Path:
    p = Path(rel)
    require(rel and not p.is_absolute() and ".." not in p.parts, f"unsafe path: {rel!r}")
    path = root / p
    require(path.is_file() and not path.is_symlink(), f"missing/nonregular file: {rel}")
    require(path.resolve().is_relative_to(root.resolve()), f"path escaped root: {rel}")
    return path


def pin(path: Path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def check_rows(root: Path, rows, label: str):
    names = [row["path"] for row in rows]
    require(len(names) == len(set(names)), f"duplicate {label} paths")
    for row in rows:
        require(set(row) == {"path", "sha256", "size_bytes"}, f"bad {label} pin row")
        actual = pin(safe_path(root, row["path"]))
        require(actual == {"sha256": row["sha256"], "size_bytes": row["size_bytes"]},
                f"{label} pin mismatch: {row['path']}")
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", required=True, type=Path)
    ap.add_argument("--historical-source-root", required=True, type=Path)
    ap.add_argument("--current-repo-root", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    package = args.package.resolve()
    historical = args.historical_source_root.resolve()
    current = args.current_repo_root.resolve()
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    expected_schema = {
        "activation-density-contract": "UDM_ACTIVATION_DENSITY_EVIDENCE_V1",
        "nc-unit-radiative-sensitivity": "UDM_NC_CONDITIONAL_RTE_ARCHIVE_V1",
    }.get(package.name)
    require(expected_schema is not None and manifest.get("schema") == expected_schema,
            "unexpected archive schema")
    payload = manifest.get("payload", [])
    payload_count = check_rows(package, payload, "package payload")
    payload_names = {row["path"] for row in payload}
    expected_roster = payload_names | {"manifest.json"}
    actual_roster = {p.relative_to(package).as_posix() for p in package.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts}
    require(actual_roster == expected_roster, "archive payload roster mismatch")
    rows = manifest.get("sources", [])
    old_rows = [r for r in rows if r["path"].startswith("WRF/")]
    current_rows = [r for r in rows if not r["path"].startswith("WRF/")]
    old_count = check_rows(historical, old_rows, "historical source")
    current_count = check_rows(current, current_rows, "evidence sidecar")
    historical_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=historical,
                                     check=True, capture_output=True, text=True).stdout.strip()
    require(historical_head == "092b901bf40b5334c5497fbf75f630b255262fb2",
            f"wrong historical source checkout: {historical_head}")
    archive_count = 0
    archive_names = manifest.get("text_archives", [])
    require(len(archive_names) == len(set(archive_names))
            and set(archive_names) <= payload_names, "invalid text archive roster")
    for name in archive_names:
        archived = json.loads(gzip.decompress(safe_path(package, name).read_bytes()))
        require(archived.get("schema") == "UDM_CONTRACT_TEXT_ARTIFACT_ARCHIVE_V1",
                f"bad embedded text archive: {name}")
        seen = set()
        for row in archived.get("files", []):
            require(set(row) == {"path", "sha256", "size_bytes", "content_utf8"},
                    f"bad embedded row fields in {name}")
            row_path = row.get("path")
            require(isinstance(row_path, str) and row_path and not Path(row_path).is_absolute()
                    and ".." not in Path(row_path).parts, f"unsafe embedded path: {row_path!r}")
            require(row_path not in seen, f"duplicate embedded path: {row_path}")
            seen.add(row_path)
            data = row.get("content_utf8", "").encode("utf-8")
            require(len(data) == row.get("size_bytes")
                    and hashlib.sha256(data).hexdigest() == row.get("sha256"),
                    f"embedded text hash mismatch: {row.get('path')}")
            archive_count += 1
    current_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=current,
                                  check=True, capture_output=True, text=True).stdout.strip()
    current_tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=current,
                                  check=True, capture_output=True, text=True).stdout.strip()
    result = {
        "schema": "UDM_HISTORICAL_ARCHIVE_SPLIT_SOURCE_AUTH_V1",
        "status": "PASS_HISTORICAL_SOURCE_AND_CURRENT_EVIDENCE_AUTHENTICATION",
        "package_manifest_sha256": pin(manifest_path)["sha256"],
        "historical_source_commit": historical_head,
        "current_checkout_head": current_head,
        "current_checkout_tree": current_tree,
        "historical_source_rows": old_count,
        "current_evidence_sidecar_rows": current_count,
        "package_payload_rows": payload_count,
        "embedded_text_files": archive_count,
        "execution_counts": {"compiler": 0, "models": 0, "RTE": 0},
        "scope": "Original manifest and payload are authenticated unchanged. WRF source/data pins use the archived source checkout; later-added validation sidecars use the current repository tree.",
    }
    if args.output:
        out = args.output.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
