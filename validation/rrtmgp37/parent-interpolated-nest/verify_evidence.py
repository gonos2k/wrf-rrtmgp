#!/usr/bin/env python3
"""Portable verifier for the archived nested-runtime receipts (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load(path: Path):
    return json.loads(path.read_text())

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence-dir", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--case-dir", type=Path, help="optional original directory containing the 20 raw histories")
    args = ap.parse_args()
    root = args.evidence_dir.resolve()
    manifest = load(root / "artifact_sha256.json")
    bad = []
    for item in manifest["files"]:
        path = root / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            bad.append(item["path"])
    if bad:
        raise SystemExit(f"archived artifact hash mismatch/missing: {bad}")
    pre = load(root / "runner/preflight.json")
    exe = load(root / "runner/execution.json")
    nml = (root / "runner/namelist.input").read_text()
    readback = load(root / "results/root-independent-history-readback.json")
    inventory = load(root / "results/summary-v2/history_file_inventory.json")
    state = load(root / "results/summary-v2/state_presence.json")
    source_match = load(root / "results/source-pin-match.json")
    assert exe["status"] == "PASS_BOUNDED_NESTED_RUNTIME"
    assert exe["launcher_returncode"] == 0 and not exe["launcher_timed_out"]
    assert exe["rank_success_all"] and len(exe["rank_success"]) == 4 and all(exe["rank_success"].values())
    assert exe["parent_interpolation_logged"] and exe["child_input_absent"]
    assert exe["staged_namelist_unchanged"]
    assert exe["namelist_sha256"] == pre["namelist"]["sha256"] == exe["source_namelist_sha256"]
    assert exe["binary_sha256"] == pre["build"]["executable_sha256"]
    assert exe["frozen_table_sha256"] == pre["physics_and_static_data"]["frozen_table_sha256"]
    assert pre["domains"]["physics"]["rrtmgp_udm_frozen_optics"] == 1
    assert pre["domains"]["physics"]["rrtmgp_data_path"] == pre["physics_and_static_data"]["run_path"]
    assert sha256(root / "runner/run_nested.py") == pre["runner"]["sha256"]
    assert sha256(root / "runner/run_nested-v2-reviewed-64m.py") == pre["runner"]["pre_review_sha256"]
    assert sha256(root / "runner/run_nested-v2-pre-review.py") == pre["runner"]["original_v2_pre_review_sha256"]
    assert sha256(root / "runner/resource-adjustment.diff") == pre["runner"]["resource_adjustment"]["diff_sha256"]
    assert pre["runner"]["resource_adjustment"]["main_stack_soft_limit_bytes"] == 536870912
    assert pre["runner"]["resource_adjustment"]["omp_stacksize"] == "512M"
    assert len(exe["pinned_files_before"]) == len(exe["pinned_files_after"]) == 117
    assert exe["pinned_files_before"] == exe["pinned_files_after"]
    assert len(exe["staged_assets_before"]) == len(exe["staged_assets_after"]) == 95
    assert exe["staged_assets_before"] == exe["staged_assets_after"]
    d1 = exe["output_validation"]["domains"]["d01"]
    d2 = exe["output_validation"]["domains"]["d02"]
    assert len(d1["times"]) == 13 and d1["times"][0] == "2010-06-11_00:00:00" and d1["times"][-1] == "2010-06-11_02:00:00"
    assert len(d2["times"]) == 7 and d2["times"][0] == "2010-06-11_01:00:00" and d2["times"][-1] == "2010-06-11_02:00:00"
    assert d1["masked_numeric_value_count"] == d2["masked_numeric_value_count"] == 0
    assert d1["numeric_variable_file_checks"] + d2["numeric_variable_file_checks"] == 4080
    assert d1["dimensions"]["west_east"] == 289 and d1["dimensions"]["south_north"] == 189
    assert d2["dimensions"]["west_east"] == 60 and d2["dimensions"]["south_north"] == 60
    assert d1["dimensions"]["bottom_top"] == d2["dimensions"]["bottom_top"] == 39
    assert set(("SWDOWN", "GLW", "OLR", "QGRAUP", "QHAIL")).issubset(d1["required_radiation_fields"])
    assert set(("SWDOWN", "GLW", "OLR", "QGRAUP", "QHAIL")).issubset(d2["required_radiation_fields"])
    assert re.search(r"(?im)^\s*rrtmgp_udm_frozen_optics\s*=\s*1\s*,?", nml)
    assert re.search(r"(?im)^\s*mp_physics\s*=\s*27\s*,\s*27\s*,?", nml)
    assert re.search(r"(?im)^\s*ra_lw_physics\s*=\s*37\s*,\s*37\s*,?", nml)
    assert re.search(r"(?im)^\s*ra_sw_physics\s*=\s*37\s*,\s*37\s*,?", nml)
    for rank in range(4):
        log = (root / f"logs/rsl.error.{rank:04d}").read_text(errors="replace")
        assert "SUCCESS COMPLETE WRF" in log
    all_logs = "\n".join(p.read_text(errors="replace") for p in sorted((root / "logs").glob("rsl.*")))
    assert re.search(r"Initializing nest domain #\s*2 by horizontally interpolating parent domain #\s*1\.", all_logs)
    assert inventory["history_file_count"] == 20 and len(inventory["files"]) == 20
    assert source_match["matching_tracked_runtime_sources"] == source_match["tracked_runtime_source_hashes"] == 13
    assert all(x["matches"] for x in source_match["files"] if x["tracked_in_base"])
    assert readback["execution_sha256"] == sha256(root / "runner/execution.json")
    assert state["domains"]["d02"]["QGRAUP_domain_max_kg_kg"] == readback["domains"]["d02"]["maximums"]["QGRAUP"]
    assert state["domains"]["d02"]["QHAIL_domain_max_kg_kg"] == readback["domains"]["d02"]["maximums"]["QHAIL"]
    checked_histories = 0
    if args.case_dir:
        case = args.case_dir.resolve()
        for item in inventory["files"]:
            path = case / item["file"]
            if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
                raise SystemExit(f"raw history mismatch/missing: {path}")
            checked_histories += 1
    assert not any(item["path"].lower().endswith(".nc") for item in manifest["files"])
    assert not any(Path(item["path"]).name in {"wrf.exe", "real.exe"} for item in manifest["files"])
    print(json.dumps({"status": "ARCHIVED_EVIDENCE_PASS", "archived_files_checked": len(manifest["files"]),
                      "history_files_hashed_if_available": checked_histories,
                      "runner_pass": exe["status"], "parent_records": len(d1["times"]),
                      "child_records": len(d2["times"]), "numeric_variable_file_checks": 4080,
                      "rank_success_count": 4, "raw_history_files_archived": False}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
