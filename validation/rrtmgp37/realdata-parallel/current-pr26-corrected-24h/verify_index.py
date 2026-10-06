#!/usr/bin/env python3
"""Verify curated artifact hashes and receipt/hash cross-references.

This verifier deliberately does not read or require the large NetCDF outputs.
Run from any working directory with the package path as its argument.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_TIMES = [f"2010-06-11_{hour:02d}:00:00" for hour in range(24)] + ["2010-06-12_00:00:00"]


def load(path: Path):
    return json.loads(path.read_text())


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check(root: Path) -> dict:
    root = root.resolve()
    index = load(root / "artifact-index.json")
    entries = index.get("files", [])
    if index.get("file_count") != len(entries):
        raise ValueError("artifact-index file_count does not match entries")
    seen = set()
    for item in entries:
        rel = Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts or str(rel) in seen:
            raise ValueError(f"unsafe or repeated index path: {rel}")
        seen.add(str(rel))
        path = root / rel
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha(path) != item["sha256"]:
            raise ValueError(f"curated file hash/size mismatch: {rel}")
        if not SHA256.fullmatch(item["sha256"]):
            raise ValueError(f"malformed SHA256 in index: {rel}")

    v1 = load(root / "analysis/V1-analysis.json")
    v2 = load(root / "analysis/V2-analysis.json")
    run = load(root / "run/execution.json")
    preflight = load(root / "run/preflight.json")
    review = load(root / "run/root-review.json")
    if run.get("status") != "BOTH_VALIDATED" or set(run.get("returncodes", {})) != {"ra4", "ra37"}:
        raise ValueError("paired-run execution is not BOTH_VALIDATED")
    if any(run["returncodes"].get(arm) != 0 for arm in ("ra4", "ra37")):
        raise ValueError("paired-run arm has nonzero return code")
    executable = review["executable_sha256"]
    if run.get("hash_checks", {}).get("ra4", {}).get("before", {}).get("executable") != executable:
        raise ValueError("execution and root review executable hashes differ")
    for analysis in (v1, v2):
        if analysis.get("case_status") != "BOTH_VALIDATED":
            raise ValueError("analysis does not describe validated paired runs")
        src = analysis["source_and_inputs"]
        if src.get("executable_sha256") != executable:
            raise ValueError("analysis executable hash differs from execution receipt")
        if src.get("runner_sha256") != review.get("runner_sha256"):
            raise ValueError("analysis runner hash differs from approved runner")
        if src.get("preflight_sha256") != review.get("preflight_sha256"):
            raise ValueError("analysis preflight hash differs from approved preflight")
        if len(src.get("history_file_sha256", {}).get("ra4", [])) != 25 or len(src.get("history_file_sha256", {}).get("ra37", [])) != 25:
            raise ValueError("analysis is missing a 25-file history hash series")
    if v1.get("analysis_script_sha256") != sha(root / "analysis/analyze_pair_v1.py"):
        raise ValueError("V1 analyzer script hash mismatch")
    if v2.get("analysis_script_sha256") != sha(root / "analysis/analyze_pair_v2.py"):
        raise ValueError("V2 analyzer script hash mismatch")
    if v2.get("field_math_contracts", {}).get("status") != "INCOMPLETE_REQUIRED_FIELDS":
        raise ValueError("V2 identity contract status changed unexpectedly")

    nc_index = load(root / "netcdf-sha-index.json")
    for arm in ("ra4", "ra37"):
        history = nc_index["arms"][arm]["continuous_histories"]
        expected_sha = v2["source_and_inputs"]["history_file_sha256"][arm]
        if [entry["time"] for entry in history] != EXPECTED_TIMES or len(history) != 25:
            raise ValueError(f"{arm} history manifest lacks exact 25-hour timeline")
        if [entry["sha256"] for entry in history] != expected_sha:
            raise ValueError(f"{arm} NetCDF history hashes differ from analysis provenance")
        for item in history:
            if not SHA256.fullmatch(item["sha256"]) or item["bytes"] <= 0:
                raise ValueError(f"invalid history hash/size for {arm}: {item}")
        checkpoints = nc_index["arms"][arm]["continuous_restarts"]
        if [item["time"] for item in checkpoints] != ["2010-06-11_12:00:00", "2010-06-12_00:00:00"]:
            raise ValueError(f"{arm} checkpoint manifest lacks 12/24-hour restart hashes")
        if any(not SHA256.fullmatch(item["sha256"]) or item["bytes"] <= 0 for item in checkpoints):
            raise ValueError(f"invalid checkpoint hash/size for {arm}")

    restart = load(root / "restart/execution.json")
    restart_preflight = load(root / "restart/preflight.json")
    raw = load(root / "analysis/root-restart-bitwise-recheck.json")
    if restart.get("status") != "BOTH_ARMS_PASS":
        raise ValueError("same-executable restart execution did not pass")
    if raw.get("status") != "PASS_RAW_ARRAY_BYTES" or raw.get("overall_metadata") != "START_DATE_DIFFERENCE_RETAINED":
        raise ValueError("raw-byte restart check or explicit metadata caveat missing")
    for arm, numeric_count in (("ra4", 201), ("ra37", 204)):
        trial = nc_index["arms"][arm]["restart_trial"]
        detail = restart["arms"][arm]["comparison"]
        pin = restart_preflight["pins"]["checkpoints"][arm]
        if trial["checkpoint_sha256"] != pin or trial["checkpoint_sha256"] != nc_index["arms"][arm]["continuous_restarts"][0]["sha256"]:
            raise ValueError(f"{arm} restart checkpoint hash mismatch")
        if trial["continuous_13z_sha256"] != detail["reference_sha256"] or trial["restart_13z_sha256"] != detail["restart_sha256"]:
            raise ValueError(f"{arm} 13Z restart hashes differ from execution receipt")
        if trial["exact_numeric_variables"] != numeric_count or not trial["numeric_fields_exact"]:
            raise ValueError(f"{arm} exact numeric restart comparison mismatch")
        if raw["arms"][arm]["numeric_arrays_raw_bitwise_equal"] != numeric_count or raw["arms"][arm]["differences"]:
            raise ValueError(f"{arm} raw-byte checker result mismatch")
        if not raw["arms"][arm]["global_metadata_difference"].get("START_DATE"):
            raise ValueError(f"{arm} expected START_DATE difference not documented")

    logs = load(root / "completion-and-log-index.json")
    for arm in ("ra4", "ra37"):
        for phase in ("continuous", "restart12to13"):
            record = logs["arms"][arm][phase]
            if not record["all_four_ranks_complete"] or len(record["rank_logs"]) != 4:
                raise ValueError(f"{arm}/{phase} lacks four successful rank logs")
            if not all(log["success_marker"] and SHA256.fullmatch(log["sha256"])
                       for log in record["rank_logs"].values()):
                raise ValueError(f"{arm}/{phase} has missing success marker/log hash")
    payloads = [p for p in root.rglob("*") if p.is_file() and p.name.startswith(("wrfout", "wrfrst"))]
    if payloads:
        raise ValueError("large NetCDF payloads must remain outside compact evidence package")
    return {"status": "PASS", "curated_file_count": len(entries),
            "history_file_hashes": 50, "checkpoint_hashes": 4,
            "restart_outputs": 2, "raw_restart_numeric_arrays": {"ra4": 201, "ra37": 204},
            "netcdf_payloads_copied": 0,
            "analysis_field_math_status": v2["status"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, nargs="?", default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        result = check(args.package)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
