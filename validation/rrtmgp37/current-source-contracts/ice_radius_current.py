#!/usr/bin/env python3
"""Run the retained radius recipe against the checked-out current UDM source.

The source digest is recorded in the generated receipt, not pinned as an
acceptance constant. The historical recipe result remains authenticated by its
separate archive job.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    root = args.source_root.resolve()
    source = root / "WRF/phys/module_mp_udm.F"
    provenance = root / "validation/rrtmgp37/ice-radius-fit-contract/provenance.json"
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    spec = importlib.util.spec_from_file_location(
        "ice_radius_recipe_audit", root / "validation/rrtmgp37/ice-radius-fit-contract/audit.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load retained recipe audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Bind the audit's existing exact semantic checks to this checkout's source.
    module.EXPECTED_SOURCE_SHA256 = digest
    result = module.build_result(source, provenance)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()
    rel = "WRF/phys/module_mp_udm.F"
    blob = subprocess.run(["git", "rev-parse", f"HEAD:{rel}"], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=root, check=True,
                           capture_output=True, text=True).stdout
    git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    result["schema"] = "udm37-current-source-radius-recipe-audit-v1"
    result["status"] = "PASS_CURRENT_CHECKOUT_RADIUS_SOURCE_CONTRACT"
    result["current_checkout"] = {"head": head, "tree": tree,
                                   "udm_source_sha256": digest, "source_path": rel,
                                   "head_blob": blob, "working_file_git_blob": git_blob,
                                   "working_file_matches_head_blob": git_blob == blob,
                                   "dirty_source_status": dirty}
    result["scope"] += " The retained historical numerical artifact was not retagged; this is a fresh source-bound recipe execution."
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "head": head,
                      "udm_source_sha256": digest, "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
