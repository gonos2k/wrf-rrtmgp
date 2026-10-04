#!/usr/bin/env python3
"""Verify the self-contained RRTMG4 runtime evidence payload (stdlib only)."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from read_export import read_export
EXPECTED_ARMS = {"OLD_OFF", "NEW_OFF", "NEW_ON"}
EXPECTED_PHASES = {"LW", "SW"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    manifest_path = ROOT / "package-manifest.json"
    manifest = load_json(manifest_path)
    entries = manifest["files"]
    listed = [item["path"] for item in entries]
    require(len(listed) == len(set(listed)), "duplicate manifest path")
    require("package-manifest.json" not in listed, "manifest must not list itself")
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and p.name != "package-manifest.json"}
    require(actual == set(listed), f"package roster mismatch: extra={sorted(actual-set(listed))}, missing={sorted(set(listed)-actual)}")
    for item in entries:
        rel = Path(item["path"])
        require(not rel.is_absolute() and ".." not in rel.parts, f"unsafe path: {rel}")
        data = (ROOT / rel).read_bytes()
        require(len(data) == item["size_bytes"], f"size mismatch: {rel}")
        require(sha(data) == item["sha256"], f"SHA-256 mismatch: {rel}")

    idx = load_json(ROOT / "export-index.json")
    require(idx["schema"] == "rrtmg4-live-export-index-v1", "unexpected export index schema")
    require(len(idx["files"]) == 2, "expected exactly two phase exports")
    phases = set()
    for item in idx["files"]:
        phase = item["phase"]
        phases.add(phase)
        require(phase in EXPECTED_PHASES, f"unexpected phase {phase}")
        require(item["metadata"] == {"domain": 1, "i": 24, "j": 55, "phase": phase,
                                      "source_seconds": 129600.0, "step": 2161},
                f"wrong export context for {phase}")
        require(item["stages"] == ["INPUT", "CLOUD", "GAS", "RESULT"], f"wrong stages for {phase}")
        packed = (ROOT / item["stored_path"]).read_bytes()
        require(len(packed) == item["gzip_size_bytes"] and sha(packed) == item["gzip_sha256"],
                f"compressed export mismatch for {phase}")
        payload = gzip.decompress(packed)
        require(len(payload) == item["size_bytes"] and sha(payload) == item["sha256"],
                f"decompressed export mismatch for {phase}")
        with tempfile.NamedTemporaryFile(prefix="rrtmg4-export-", suffix=".txt") as stream:
            stream.write(payload)
            stream.flush()
            parsed = read_export(Path(stream.name), expected_phase=phase)
        require(parsed["metadata"] == item["metadata"], f"parsed context mismatch for {phase}")
        require(parsed["stage_order"] == ["INPUT", "CLOUD", "GAS", "RESULT"],
                f"parsed stage order mismatch for {phase}")
        require(len(parsed["fields"]) == item["field_count"], f"field count mismatch for {phase}")
    require(phases == EXPECTED_PHASES, "missing LW or SW export")

    run = load_json(ROOT / "receipts/runtime/execution.json")
    require(run["status"] == "PASS_EXACT_OUTPUTS_CAPTURE_AUDIT_EXPORT", "runtime status is not PASS")
    require(run["model_invocations"] == 3, "expected exactly three model invocations")
    require(set(run["arms"]) == EXPECTED_ARMS, "unexpected runtime arm roster")
    for name, arm in run["arms"].items():
        require(arm["returncode"] == 0 and arm["status"] == "PASS_ARM" and not arm["timed_out"],
                f"arm failed: {name}")
    comparisons = run["comparison"]["netcdf_comparisons"]
    require(len(comparisons) == 6 and all(x["status"] == "PASS_EXACT" and not x["mismatches"] for x in comparisons),
            "the six whole-file NetCDF comparisons are not all exact")
    capture_comparisons = run["comparison"]["production_capture_comparisons"]
    require(len(capture_comparisons) == 6 and {x["suffix"] for x in capture_comparisons} == {"raw", "input", "result"},
            "expected six retained capture comparisons across two phases and three records")
    require(run["comparison"]["first_call_vs_retained_capture"] == "PASS_EXACT",
            "first-call retained capture check failed")
    audit = run["arms"]["NEW_ON"]["audit_first_call_comparison"]
    require(audit["status"] == "PASS_EXACT_FIRST_CALL" and audit["rows_compared"] == 188 and audit["selected_and_aggregate"],
            "audit comparison did not cover the expected 188 rows")
    exports = run["arms"]["NEW_ON"]["exports"]
    require(len(exports) == 2 and {x["metadata"]["phase"].upper() for x in exports} == EXPECTED_PHASES,
            "runtime receipt export roster differs")
    for item in exports:
        listed_item = next(x for x in idx["files"] if x["phase"] == item["metadata"]["phase"].upper())
        require(item["sha256"] == listed_item["sha256"],
                f"runtime export pin differs for {item['metadata']['phase']}")

    build_plan = load_json(ROOT / "receipts/build/build-plan-v2.json")
    build_receipt = load_json(ROOT / "receipts/build/build-receipt.json")
    runtime_plan = load_json(ROOT / "receipts/runtime/plan.json")
    auth = load_json(ROOT / "receipts/runtime/root-authorization.json")
    require(build_plan["source"]["commit"] == "b7b5f6f9cd657408e3bde3018d7e882ab3e4bce3",
            "build source commit differs from reviewed observer source")
    require(build_plan["source"]["parent"] == "1cb6920a43d8ba10ecfa179487839f9df7022cb4",
            "build source parent differs")
    prov = runtime_plan["build_provenance"]
    require(prov["commit"] == build_plan["source"]["commit"], "runtime/build source commit mismatch")
    require(prov["build_receipt_sha256"] == sha((ROOT / "receipts/build/build-receipt.json").read_bytes()),
            "runtime plan does not pin packaged build receipt")
    require(runtime_plan["source_manifest"]["sha256"] == build_receipt["manifest_sha256"] == prov["source_manifest_sha256"],
            "source manifest pin mismatch")
    require(build_receipt["status"] == "BUILD_PASS", "build receipt is not PASS")
    require(run["plan_sha256"] == sha((ROOT / "receipts/runtime/plan.json").read_bytes()),
            "runtime receipt plan hash mismatch")
    require(run["authorization_sha256"] == sha((ROOT / "receipts/runtime/root-authorization.json").read_bytes()),
            "runtime receipt authorization hash mismatch")
    require(auth["plan_sha256"] == run["plan_sha256"] and auth["max_forecasts"] == 3,
            "authorization does not match runtime plan or invocation limit")
    require(run["runner"]["sha256"] == sha((ROOT / "receipts/runtime/run_export_once.py").read_bytes()),
            "runtime runner pin mismatch")
    require(run["reader"]["sha256"] == sha((ROOT.parent / "read_export.py").read_bytes()),
            "export reader pin mismatch")
    require(run["comparison"]["actual_roster"] == [
        {"phase": "LW", "source_seconds": 129600.0, "step": 2161},
        {"phase": "SW", "source_seconds": 129600.0, "step": 2161}],
        "actual capture roster differs")
    print("PASS: package roster/hashes, parsed exports, source/build/runtime links, and scoped comparisons")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
