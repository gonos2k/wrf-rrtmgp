#!/usr/bin/env python3
"""Verify the closed, saved-only ON coupling-ablation evidence package.

Standard library only. It never starts LBLRTM, compiles source, opens an
external scientific input, or writes inside this package. The report path must
be outside the package and must not already exist.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import struct
import sys
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.json"
MAX_STORED = 20_000_000
MAX_EXPANDED = 20_000_000


def digest(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(message)


def load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        fail(f"expected JSON object: {path.name}")
    return obj


def safe_relative(raw: str) -> Path:
    rel = PurePosixPath(raw)
    if rel.is_absolute() or not rel.parts or any(x in ("", ".", "..") for x in rel.parts):
        fail(f"unsafe package path: {raw!r}")
    p = HERE.joinpath(*rel.parts)
    cur = HERE
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            fail(f"symlink is not allowed in the package roster: {raw}")
    try:
        p.resolve(strict=True).relative_to(HERE)
    except (OSError, ValueError):
        fail(f"package path escapes or is missing: {raw}")
    return p


def verify_roster(manifest: dict[str, Any]) -> dict[str, Path]:
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        fail("manifest files must be a nonempty list")
    listed: dict[str, Path] = {}
    for row in rows:
        if not isinstance(row, dict):
            fail("malformed manifest file row")
        rel = row.get("path")
        if not isinstance(rel, str) or rel in listed:
            fail(f"duplicate or invalid manifest path: {rel!r}")
        p = safe_relative(rel)
        if not p.is_file():
            fail(f"listed payload is not a regular file: {rel}")
        h, n = digest(p)
        if (h, n) != (row.get("sha256"), row.get("size_bytes")):
            fail(f"payload hash/size mismatch: {rel}")
        listed[rel] = p

    actual: set[str] = set()
    for root, dirs, files in os.walk(HERE, followlinks=False):
        rootp = Path(root)
        for name in list(dirs):
            d = rootp / name
            if d.is_symlink():
                fail(f"unexpected symlink directory: {d.relative_to(HERE)}")
        for name in files:
            f = rootp / name
            rel = f.relative_to(HERE).as_posix()
            if rel == "manifest.json":
                continue
            if f.is_symlink() or not f.is_file():
                fail(f"unexpected nonregular package item: {rel}")
            actual.add(rel)
    if actual != set(listed):
        fail(f"closed roster mismatch; missing={sorted(set(listed)-actual)}, extra={sorted(actual-set(listed))}")
    return listed


def verify_gzip_payloads(manifest: dict[str, Any], files: dict[str, Path], scratch: Path) -> dict[str, Path]:
    rows = manifest.get("decompressed_artifacts")
    if not isinstance(rows, list) or len(rows) != 6:
        fail("expected exactly six compressed raw artifacts")
    outputs: dict[str, Path] = {}
    total_expanded = 0
    for row in rows:
        if not isinstance(row, dict):
            fail("malformed decompressed artifact row")
        stored_rel, raw_rel = row.get("stored_path"), row.get("logical_name")
        if stored_rel not in files or not isinstance(raw_rel, str) or raw_rel in outputs:
            fail("compressed artifact must point to one listed, unique gzip payload")
        stored = files[stored_rel]
        if stored.stat().st_size > MAX_STORED:
            fail(f"stored payload exceeds bound: {stored_rel}")
        out = scratch / f"raw-{len(outputs):02d}"
        h = hashlib.sha256()
        n = 0
        try:
            with gzip.open(stored, "rb") as src, out.open("xb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    n += len(chunk)
                    total_expanded += len(chunk)
                    if n > MAX_EXPANDED or total_expanded > 40_000_000:
                        fail("gzip expansion exceeds fixed safety bound")
                    h.update(chunk)
                    dst.write(chunk)
        except (OSError, EOFError) as exc:
            fail(f"invalid gzip stream {stored_rel}: {exc}")
        if (h.hexdigest(), n) != (row.get("raw_sha256"), row.get("raw_size_bytes")):
            fail(f"decompressed hash/size mismatch: {stored_rel}")
        outputs[raw_rel] = out
    return outputs


def check_event_trace(raw: dict[str, Path], receipts: dict[str, Any]) -> dict[str, Any]:
    parser_path = HERE / "parser" / "parse_selected_events.py"
    provenance = load_json(HERE / "parser" / "provenance.json")
    if provenance.get("parser_sha256") != digest(parser_path)[0]:
        fail("event parser differs from its provenance receipt")
    if provenance.get("runner_cli_or_process_functions_included") is not False:
        fail("packaged R3 parser is not declared process-free")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("saved_r3_parser", parser_path)
    if spec is None or spec.loader is None:
        fail("cannot load R3 parser")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = raw["off-UDM37_R3_TERM_TRACE"]
    on = raw["on-UDM37_R3_TERM_TRACE"]
    result = module.validate_ablation_events(base, base, on)
    expected = receipts["on-event-analysis.json"]
    staged_recomputed = load_json(HERE / "parser" / "recomputed-event-analysis.json")
    if result != staged_recomputed:
        fail("recomputed R3 analysis differs from the archived recomputation")
    for key in ("status", "baseline_selected_counts", "on_selected_counts",
                "fixed_probe_baseline_coupling_counts", "fixed_probe_on_coupling_counts",
                "nonselected_operand_identity_multiset_equal", "numeric_acceptance"):
        if result.get(key) != expected.get(key):
            fail(f"recomputed event result differs from frozen receipt: {key}")
    if result.get("status") != "PASS_SCOPED_SELECTED_COUPLING_EVENTS_OMITTED_DESCRIPTIVE_ONLY":
        fail("selected R3 event omission did not meet its descriptive contract")
    if result.get("nonselected_operand_identity_multiset_equal") is not True:
        fail("nonselected event operands/identities changed")
    return result


def check_layer21(raw: dict[str, Path], receipts: dict[str, Any]) -> dict[str, Any]:
    old = raw["off-ODdeflt_021"]
    new = raw["on-ODdeflt_021"]
    old_bytes, new_bytes = old.read_bytes(), new.read_bytes()
    htime_start, htime_end = 1348, 1356
    if len(old_bytes) != len(new_bytes) or len(old_bytes) <= htime_end:
        fail("selected raw OD records have incompatible byte lengths")
    outside_diff = sum(a != b for a, b in zip(old_bytes[:htime_start] + old_bytes[htime_end:],
                                              new_bytes[:htime_start] + new_bytes[htime_end:]))
    full_file_equal = old_bytes == new_bytes
    saved = receipts["on-payload-comparison.json"].get("selected_layer_21", {})
    decoded = receipts["on-saved-decode-result.json"]["layer21"]
    if outside_diff != saved.get("unexpected_payload_byte_difference_count"):
        fail("selected-layer byte diff does not match ON comparison receipt")
    if outside_diff != decoded.get("changed_raw_sample_byte_count"):
        fail("selected-layer raw payload diff does not match independent decode receipt")
    if full_file_equal or saved.get("status") != "DESCRIPTIVE_CHANGED":
        fail("selected layer must remain descriptively changed with distinct full-file hashes")

    # Re-run only the fixed-width layer-21 decoder extracted from the independently
    # reviewed saved-output decoder. No file discovery or external input is used.
    decoder = HERE / "independent-decode" / "decode_layer21.py"
    prov = load_json(HERE / "independent-decode" / "provenance.json")
    if prov.get("new_script_sha256") != digest(decoder)[0]:
        fail("selected-layer decoder differs from provenance pin")
    spec = importlib.util.spec_from_file_location("saved_layer21_decoder", decoder)
    if spec is None or spec.loader is None:
        fail("cannot load layer-21 decoder")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    off = mod.parse_file(old, 21, values=True)
    on = mod.parse_file(new, 21, values=True)
    if (off["sample_count"], on["sample_count"]) != (464329, 464329):
        fail("layer-21 sample count differs from archived independent result")
    for arm, got in (("OFF", off), ("ON", on)):
        exp = decoded[arm]
        for key in ("sample_count", "negative_count", "negative_min", "value_min", "value_max", "pave", "tave"):
            if got[key] != exp[key]:
                fail(f"decoded selected-layer {arm} field differs from saved independent result: {key}")
        if len(got["panels"]) != decoded["panel_count"]:
            fail(f"decoded {arm} panel count differs from saved receipt")
    panel_grid_equal = True
    sample_diffs = 0
    byte_diffs = 0
    for a, b in zip(off["panels"], on["panels"]):
        if (a["v1"], a["v2"], a["dv"], a["n"]) != (b["v1"], b["v2"], b["dv"], b["n"]):
            panel_grid_equal = False
            fail("OFF/ON layer-21 panel grid changed")
        if len(a["values"]) != len(b["values"]):
            fail("OFF/ON layer-21 sample count differs within panel")
        sample_diffs += sum(x != y for x, y in zip(a["values"], b["values"]))
        ab = struct.pack("<" + "d" * len(a["values"]), *a["values"])
        bb = struct.pack("<" + "d" * len(b["values"]), *b["values"])
        byte_diffs += sum(x != y for x, y in zip(ab, bb))
    if sample_diffs != decoded["changed_sample_count"] or byte_diffs != decoded["changed_raw_sample_byte_count"]:
        fail("recomputed decoded layer-21 difference count differs from saved result")
    return {"full_file_equal": full_file_equal, "payload_byte_diff_outside_htime": outside_diff,
            "sample_count": 464329, "negative_counts": {"OFF": off["negative_count"], "ON": on["negative_count"]},
            "negative_minima": {"OFF": off["negative_min"], "ON": on["negative_min"]},
            "changed_sample_count": sample_diffs, "changed_raw_sample_byte_count": byte_diffs,
            "panel_grid_identical": panel_grid_equal,
            "physical_reference_accepted": False}


def verify(report_path: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    manifest_hash, _ = digest(MANIFEST)
    if manifest_hash != expected_manifest_sha256:
        fail("manifest digest does not match the externally pinned expected value")
    manifest = load_json(MANIFEST)
    if load_json(HERE / "external-references.json") != manifest.get("external_artifacts"):
        fail("external artifact inventory does not match the closed manifest")
    files = verify_roster(manifest)
    receipts = {p.name: load_json(p) for rel, p in files.items()
                if rel.startswith("receipts/") and p.suffix == ".json"}
    required = {"on-execution.json", "on-process.json", "on-stage.json", "on-postflight.json",
                "on-event-analysis.json", "on-payload-comparison.json", "on-terminal-context.json",
                "on-authorization.json", "on-plan.json", "pair-plan.json", "case-stage.json",
                "build-plan.json", "build-execution.json", "build-child.json", "build-postflight.json",
                "build-authorization.json", "off-stop-context.json", "off-execution.json",
                "off-process.json", "off-header-audit.json", "baseline-od-manifest.json",
                "baseline-trace-manifest.json", "on-saved-decode-result.json",
                "on-prelaunch-review-v3.json", "on-saved-decode-independent-review.json"}
    if not required <= receipts.keys():
        fail(f"missing required receipts: {sorted(required-receipts.keys())}")
    on_exec, on_proc = receipts["on-execution.json"], receipts["on-process.json"]
    if (on_exec.get("status") != "TERMINAL_ON_DESCRIPTIVE_ONLY"
        or on_exec.get("attempted_solver_arms") != 1
        or on_exec.get("physical_reference_accepted") is not False
        or on_exec.get("full_file_hash_gate") != "PRESERVED_OFF_FAILURE_NOT_WAIVED"):
        fail("ON execution receipt does not preserve one-arm descriptive-only status")
    if (on_proc.get("status") != "TERMINAL" or on_proc.get("actual_child_returncode") != 0
        or on_proc.get("reaped") is not True or on_proc.get("timed_out") is not False
        or not on_proc.get("process_group_cleanup", {}).get("process_group_clean", False)):
        fail("ON process receipt is not RC0/reaped/clean")
    completed = on_exec.get("completed_process_records", [])
    if (len(completed) != 1 or completed[0].get("actual_child_returncode") != 0
        or completed[0].get("pid") != on_proc.get("pid")
        or completed[0].get("sha256") != digest(HERE / "receipts/on-process.json")[0]):
        fail("ON execution does not join its unique process receipt")
    post = receipts["on-postflight.json"]
    if post.get("process_receipt_sha256") != digest(HERE / "receipts/on-process.json")[0]:
        fail("ON postflight does not join the actual process receipt")

    plan, auth = receipts["on-plan.json"], receipts["on-authorization.json"]
    if (auth.get("status") != "AUTHORIZED_ON_ONLY_ROOT_EXECUTION" or auth.get("max_solver_invocations") != 1
        or auth.get("mode") != "ON" or auth.get("physical_reference_accepted") is not False):
        fail("authorization does not prove one ON-only diagnostic invocation")
    if on_exec.get("plan_sha256") != digest(HERE / "receipts/on-plan.json")[0] or auth.get("plan_sha256") != on_exec.get("plan_sha256"):
        fail("ON plan / authorization / execution hash join failed")
    if auth.get("runner_sha256") != on_exec.get("runner_sha256"):
        fail("ON authorization and execution runner pins differ")
    plan_rows = {
        "pair_plan": "pair-plan.json", "case_stage_manifest": "case-stage.json",
        "baseline_od_manifest": "baseline-od-manifest.json", "baseline_trace_manifest": "baseline-trace-manifest.json",
        "candidate_build_plan": "build-plan.json", "candidate_build_execution": "build-execution.json",
        "candidate_build_child": "build-child.json", "candidate_build_postflight": "build-postflight.json",
    }
    for key, local in plan_rows.items():
        row = plan.get(key)
        if not isinstance(row, dict) or row.get("sha256") != digest(HERE / "receipts" / local)[0]:
            fail(f"ON plan does not join copied {local}")
    source_sha, source_size = digest(HERE / "source/oprop.f90")
    if source_sha != plan.get("candidate_source_sha256") or source_sha != receipts["build-postflight.json"].get("source_sha256"):
        fail("captured OPROP source does not join ON and build receipts")
    build_post = receipts["build-postflight.json"]
    build_exec, build_child = receipts["build-execution.json"], receipts["build-child.json"]
    if (build_post.get("status") != "BUILD_RC0_OPROP_ONLY_SCOPED" or build_post.get("actual_child_returncode") != 0
        or not build_post.get("terminal") or not build_post.get("reaped") or build_post.get("timed_out")
        or build_post.get("solver_invocations") != 0):
        fail("candidate build postflight is not a scoped successful no-solver build")
    if (build_exec.get("actual_child_returncode") != 0 or not build_exec.get("reaped")
        or build_exec.get("timed_out") or build_exec.get("solver_invocations") != 0
        or build_exec.get("plan_sha256") != digest(HERE / "receipts/build-plan.json")[0]):
        fail("candidate build execution receipt is inconsistent")
    if build_child.get("actual_child_returncode") != 0 or not build_child.get("reaped") or build_child.get("timed_out"):
        fail("candidate build child receipt is inconsistent")
    exe = build_post.get("executable", {})
    if (exe.get("sha256") != manifest.get("external_artifacts", {}).get("executable", {}).get("sha256")
        or exe.get("size_bytes") != manifest.get("external_artifacts", {}).get("executable", {}).get("size_bytes")):
        fail("external executable metadata differs from actual build receipt")
    if len(build_post.get("runtime_libraries_post", [])) != manifest.get("external_artifacts", {}).get("runtime_library_count"):
        fail("external runtime library count differs from build receipt")

    case = receipts["case-stage.json"]
    if case.get("status") != "EXACT_38_INPUTS_STAGED_NO_SOLVER" or case.get("input_count") != 38 or case.get("solver_invocations") != 0:
        fail("source case did not pin exactly 38 inputs without a solver invocation")
    inputs = {r.get("path"): r for r in case.get("inputs", [])}
    if len(inputs) != 38 or inputs.get("TAPE3", {}).get("source_sha256_receipt") != manifest.get("external_artifacts", {}).get("tape3", {}).get("sha256"):
        fail("case-stage 38-input roster or omitted TAPE3 external pin is inconsistent")

    off = receipts["off-stop-context.json"]
    off_exec = receipts["off-execution.json"]
    off_proc = receipts["off-process.json"]
    gate = off.get("strict_full_file_gate", {})
    if (off.get("status") != "FAIL_STOP_PRESERVED_OFF_FULL_FILE_GATE_ON_NOT_RUN"
        or off_exec.get("status") != "FAIL_STOP_PRESERVED"
        or off_proc.get("actual_child_returncode") != 0 or off_proc.get("reaped") is not True
        or gate.get("changed_count") != 45 or gate.get("missing_count") != 0 or gate.get("extra_count") != 0):
        fail("original OFF full-file failure is absent or altered")
    header = receipts["off-header-audit.json"]
    if header.get("status") != "OFF_SCIENTIFIC_BYTES_IDENTICAL_EXCEPT_SOURCE_DEFINED_DATE_TIME_HEADER":
        fail("OFF header audit status changed")
    header_rows = header.get("files", [])
    allowed = [1348, 1349, 1351, 1352, 1354, 1355]
    if (len(header_rows) != 45 or any(r.get("full_file_hash_equal") is not False
        or r.get("changed_file_offsets") != allowed or r.get("bytes_after_first_record_identical") is not True
        for r in header_rows)):
        fail("OFF timestamp-only header audit does not match its frozen 45-file receipt")

    payload = receipts["on-payload-comparison.json"]
    if (payload.get("status") != "PASS_NONSELECTED_44_EXACT" or payload.get("compared_files") != 45
        or payload.get("nonselected_file_count") != 44
        or payload.get("all_nonselected_44_raw_payload_bytes_equal_outside_htime") is not True
        or "NOT_WAIVED" not in payload.get("full_file_hash_gate_status", "")):
        fail("nonselected raw identity is not attested by the frozen receipt")
    payload_files = payload.get("files", [])
    if len(payload_files) != 45 or sum(r.get("path") != "ODdeflt_021" and r.get("raw_payload_equal_outside_htime") is True for r in payload_files) != 44:
        fail("payload receipt does not list 44 exact nonselected layers and the selected layer")
    if any(r.get("path") != "ODdeflt_021" and r.get("full_file_hash_equal") is not False for r in payload_files):
        fail("nonselected file hash claim differs from full-file failure contract")

    decode_review = receipts["on-saved-decode-independent-review.json"]
    decode_result = receipts["on-saved-decode-result.json"]
    if decode_review.get("status") != "PASS_SCOPED_SAVED_OUTPUT_DECODE" or decode_result.get("status") != "SAVED_DATA_DECODE_COMPLETE_DESCRIPTIVE_ONLY":
        fail("independent selected-layer decoder review is missing or not scoped-pass")
    if decode_result.get("execution_pins", {}).get("physical_reference_accepted") is not False:
        fail("saved decoder promoted physical acceptance")
    scope = load_json(HERE / "scope.json")
    if (scope.get("physical_reference_accepted") is not False
        or scope.get("criteria", {}).get("negative_optical_depth_reference_gate") != "NOT_PASS"
        or scope.get("criteria", {}).get("nonselected_44_raw_payload_identity", "").find("ATTESTED") < 0):
        fail("scope metadata weakens physical or omitted-payload limitations")
    with tempfile.TemporaryDirectory(prefix="lblrtm-on-only-verify-") as td:
        scratch = Path(td)
        raw = verify_gzip_payloads(manifest, files, scratch)
        events = check_event_trace(raw, receipts)
        layer = check_layer21(raw, receipts)

    if layer["negative_counts"]["ON"] <= 0 or layer["negative_minima"]["ON"] >= 0:
        fail("negative optical depth must remain visible in ON data")
    if layer["physical_reference_accepted"] is not False or manifest.get("physical_reference_accepted") is not False:
        fail("package must not claim physical reference acceptance")
    if manifest.get("negative_od_gate") != "NOT_PASS":
        fail("negative-OD whole gate is not explicitly NOT_PASS")

    if report_path.exists():
        fail("report path already exists; verifier never overwrites")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "lblrtm-on-only-saved-package-verification-v1",
        "status": "PASS_SCOPED_SAVED_ON_ONLY_DIAGNOSTIC",
        "manifest_sha256": manifest_hash,
        "payload_file_count": len(files),
        "raw_gzip_count": 6,
        "decompressed_payload_bytes": sum(x.get("raw_size_bytes", 0) for x in manifest["decompressed_artifacts"]),
        "on_process": {k: on_proc.get(k) for k in ("status", "actual_child_returncode", "reaped", "timed_out", "pid")},
        "build_status": build_post.get("status"),
        "selected_layer_recomputed": layer,
        "selected_events_recomputed": {
            "status": events["status"],
            "baseline_selected_counts": events["baseline_selected_counts"],
            "on_selected_counts": events["on_selected_counts"],
            "fixed_probe_baseline_coupling_counts": events["fixed_probe_baseline_coupling_counts"],
            "fixed_probe_on_coupling_counts": events["fixed_probe_on_coupling_counts"],
            "nonselected_operand_identity_multiset_equal": events["nonselected_operand_identity_multiset_equal"],
        },
        "nonselected_44_identity": "RECEIPT_ATTESTED_RAW_FILES_OMITTED",
        "off_full_file_gate": "FAILURE_PRESERVED_NOT_WAIVED",
        "negative_od_gate": "NOT_PASS",
        "physical_reference_accepted": False,
    }
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected-manifest-sha256", required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    report = args.report.absolute()
    try:
        report.relative_to(HERE)
    except ValueError:
        pass
    else:
        fail("verification report must be outside the closed package directory")
    try:
        result = verify(report, args.expected_manifest_sha256)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "manifest_sha256": result["manifest_sha256"],
                      "report": str(report), "physical_reference_accepted": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
