#!/usr/bin/env python3
"""Verify saved positive-N2 LW opacity evidence; never recompute opacity."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

HERE = Path(__file__).resolve().parent
# Package path is validation/rrtmgp37/<package>; the checkout root is two
# parent steps above the package directory in the isolated worktree or clone.
ROOT = HERE.parents[2]
MANIFEST = HERE / "manifest.json"
TABLE = ROOT / "WRF/run/rrtmgp-gas-lw-g128.nc"
TABLE_SHA = "70ad65d116531122660318e5da2a2af9db74b425916202860e9527ef2375b8f6"
N2_VMR = 0.7808


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_entry(path):
    b = (HERE / path).read_bytes()
    return gzip.decompress(b) if path.endswith(".gz") else b


def parse_packet(text, magic, header_check):
    lines = text.splitlines()
    need(len(lines) >= 3 and lines[0].strip() == magic, f"bad packet magic; expected {magic}")
    header = lines[1].split()
    need(header_check(header), f"unexpected packet dimensions/header: {header}")
    arrays = {}
    i = 2
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        h = lines[i].split()
        need(len(h) >= 2, f"invalid section at line {i+1}")
        name = h[0]
        shape = tuple(int(x) for x in h[1:])
        need(name not in arrays and shape and all(x > 0 for x in shape), f"duplicate/invalid section {name}")
        count = math.prod(shape)
        vals = []
        i += 1
        while i < len(lines) and len(vals) < count:
            if lines[i].strip():
                vals.extend(float(x.replace("D", "E").replace("d", "e")) for x in lines[i].split())
            i += 1
        need(len(vals) == count, f"truncated/overfull section {name}")
        need(all(math.isfinite(x) for x in vals), f"nonfinite section {name}")
        arrays[name] = (shape, vals)
    return arrays


def ordered_bits(x):
    bits = struct.unpack(">Q", struct.pack(">d", float(x)))[0]
    return (~bits & 0xffffffffffffffff) if bits >> 63 else (bits | 0x8000000000000000)


def same_list(a, b, label):
    need(len(a) == len(b), f"length mismatch: {label}")
    for i, (x, y) in enumerate(zip(a, b)):
        need(float(x) == float(y), f"value mismatch {label}[{i}]")


def flat_tau_target(vals, k, g):
    # RESULT payload shape (column, layer, g-point), serialized Fortran order.
    return vals[g * 45 + k]


def summary_check(record, candidate, target, label):
    n = len(candidate)
    diffs = [float(t) - float(c) for c, t in zip(candidate, target)]
    need(all(x == 0.0 for x in diffs), f"saved exact comparison changed: {label}")
    need(record["elements"] == n, f"comparison element count: {label}")
    need(record["absolute"]["max"] == 0.0 and record["absolute"]["rms"] == 0.0, f"absolute residual record: {label}")
    ulps = [abs(ordered_bits(t)-ordered_bits(c)) for c, t in zip(candidate, target)]
    need(record["ordered_binary64_ulp"]["max"] == max(ulps, default=0), f"max ULP record: {label}")
    need(record["ordered_binary64_ulp"]["nonzero_count"] == sum(x != 0 for x in ulps), f"ULP count record: {label}")
    sr = record["signed_target_minus_construction"]
    need(sr["min"] == 0.0 and sr["max"] == 0.0 and sr["mean"] == 0.0, f"signed residual record: {label}")
    rel = record["relative_to_construction"]
    zero = sum(float(c) == 0.0 for c in candidate)
    need(rel["zero_denominator_count"] == zero, f"relative zero-denominator count: {label}")
    need(rel["max_abs_nonzero_denominator"] == 0.0, f"relative residual record: {label}")


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    need(manifest["status"] == "READY_FOR_SAVED_EVIDENCE_VERIFICATION", "package is not terminal-audit-ready")
    entries = manifest["entries"]
    paths = [e["path"] for e in entries]
    need(len(paths) == len(set(paths)), "duplicate manifest path")
    expected = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and p != MANIFEST}
    need(set(paths) == expected, "manifest is not the closed package roster")
    blobs = {}
    for e in entries:
        rel = Path(e["path"])
        need(not rel.is_absolute() and ".." not in rel.parts, f"unsafe package path {rel}")
        p = HERE / rel
        need(p.is_file() and not p.is_symlink(), f"missing/nonregular payload {rel}")
        stored = p.read_bytes()
        need(len(stored) == e["size_bytes"] and sha_bytes(stored) == e["sha256"], f"stored payload pin {rel}")
        if e["encoding"] == "gzip":
            raw = gzip.decompress(stored)
            need(len(raw) == e["uncompressed_size_bytes"] and sha_bytes(raw) == e["uncompressed_sha256"], f"inflated payload pin {rel}")
            blobs[str(rel)] = raw
        else:
            need(e["encoding"] == "identity", f"unknown encoding {e['encoding']}")
            blobs[str(rel)] = stored
        origin = e.get("origin")
        if origin:
            mode = e.get("copy_mode")
            if mode == "verbatim":
                need(e["encoding"] == "identity" and e["sha256"] == origin["sha256"] and e["size_bytes"] == origin["size_bytes"], f"verbatim origin proof {rel}")
            elif mode == "lossless_gzip":
                need(e["encoding"] == "gzip" and e["uncompressed_sha256"] == origin["sha256"] and e["uncompressed_size_bytes"] == origin["size_bytes"], f"lossless gzip origin proof {rel}")
            elif mode == "verbatim_existing_gzip":
                need(e["encoding"] == "gzip" and e["sha256"] == origin["sha256"] and e["size_bytes"] == origin["size_bytes"], f"verbatim gzip origin proof {rel}")
            else:
                need(False, f"unknown/missing origin copy mode {rel}")

    ext = manifest["external_assets"]["lw_gas_coefficients"]
    need(ext["path"] == "WRF/run/rrtmgp-gas-lw-g128.nc" and ext["sha256"] == TABLE_SHA, "tracked coefficient table pin metadata")
    need(TABLE.is_file() and sha_file(TABLE) == TABLE_SHA, "tracked coefficient table bytes changed")

    # Root execution, construction and comparison ancestry.
    load = lambda p: json.loads(blobs[p].decode("utf-8"))
    exe = load("provenance/execution.json")
    auth = load("provenance/root-authorization.json")
    invocation = load("provenance/invocation.json")
    rc = load("provenance/process-return-code.json")
    construction_receipt = load("outputs/construction-receipt.json")
    comparison = load("outputs/comparison.json")
    state = load("outputs/execution-state.json")
    plan = load("provenance/point-plan-v3.json")
    input_gate = load("provenance/input-precondition-receipt.json")
    need(exe["actual_return_code"] == 0 and rc["actual_return_code"] == 0 and state["actual_return_code"] == 0, "actual point return code")
    need(exe["new_point_invocations_authorized"] == 1 and state["point_invocations"] == 1, "one point invocation")
    need(exe["new_model_RTE_compile_invocations"] == 0, "unexpected RTE/model/compile invocation")
    need(auth["authorized"] is True and auth["max_point_invocations"] == 1, "authorization status/scope")
    need(auth["plan_sha256"] == sha_bytes(blobs["provenance/point-plan-v3.json"]), "authorization plan pin")
    need(auth["runner_sha256"] == sha_bytes(blobs["provenance/point-runner-v3.py"]), "authorization runner pin")
    need(auth["point_source_sha256"] == sha_bytes(blobs["source/reconstruct_positive_locked_v1.py"]), "authorization point-source pin")
    need(auth["precondition_receipt_sha256"] == sha_bytes(blobs["provenance/input-precondition-receipt.json"]), "authorization precondition pin")
    need(auth["source_review_sha256"] == sha_bytes(blobs["provenance/source-review.json"]), "authorization source-review pin")
    need(auth["plan_runner_review"]["sha256"] == sha_bytes(blobs["provenance/runner-review-v3.json"]), "authorization runner-review pin")
    need(manifest["execution"]["execution_receipt_sha256"] == sha_bytes(blobs["provenance/execution.json"]), "manifest execution receipt pin")
    need(manifest["precondition_receipt_sha256"] == auth["precondition_receipt_sha256"], "manifest precondition pin")
    need(manifest["source_review_sha256"] == auth["source_review_sha256"], "manifest source-review pin")
    need(input_gate["status"] == "PASS_SCOPED_INPUT_SOURCE_PRECONDITIONS", "source/input precondition gate")
    need(input_gate["input"]["sha256"] == sha_bytes(blobs["inputs/lw-v13.input"]), "precondition input byte pin")
    need(input_gate["input"]["size_bytes"] == len(blobs["inputs/lw-v13.input"]), "precondition input size pin")
    plan_sha = sha_bytes(blobs["provenance/point-plan-v3.json"])
    runner_sha = sha_bytes(blobs["provenance/point-runner-v3.py"])
    point_sha = sha_bytes(blobs["source/reconstruct_positive_locked_v1.py"])
    need(state["plan_sha256"] == plan_sha == comparison["plan_sha256"] == construction_receipt["plan_sha256"], "plan ancestry")
    need(state["runner_sha256"] == runner_sha == construction_receipt["runner_sha256"], "runner ancestry")
    need(state["point_source_sha256"] == point_sha, "point source ancestry")
    need(state["authorization_sha256"] == sha_bytes(blobs["provenance/root-authorization.json"]), "authorization ancestry")
    # Bind the saved parent invocation to its exact plan, runner, review,
    # authorization, executor, and process-return-code files.
    for label, path, key in (
        ("plan", "provenance/point-plan-v3.json", "plan"),
        ("runner", "provenance/point-runner-v3.py", "runner"),
        ("authorization", "provenance/root-authorization.json", "authorization"),
        ("plan_runner_review", "provenance/runner-review-v3.json", "plan_runner_review"),
        ("parent_source", "provenance/root-execute-once.py", "parent_source"),
    ):
        pin = invocation[key]
        need(pin["sha256"] == sha_bytes(blobs[path]) and pin["size_bytes"] == len(blobs[path]), f"invocation {label} pin")
    need(invocation["allowed_point_invocations"] == 1 and invocation["new_RTE_invocations"] == 0 and invocation["new_WRF_invocations"] == 0 and invocation["new_REAL_invocations"] == 0 and invocation["new_compile_invocations"] == 0, "invocation scope/counters")
    need(auth["artifact_pin_count"] == invocation["verified_plan_pin_records"] == state["verified_pin_count"] == 108, "recursive artifact-pin counts")
    need(exe["invocation"]["sha256"] == sha_bytes(blobs["provenance/invocation.json"]), "execution receipt invocation pin")
    need(exe["authorization"]["sha256"] == sha_bytes(blobs["provenance/root-authorization.json"]), "execution receipt authorization pin")
    need(exe["return_code_receipt"]["sha256"] == sha_bytes(blobs["provenance/process-return-code.json"]), "execution receipt process-RC pin")
    need(exe["stdout"]["sha256"] == sha_bytes(blobs["provenance/stdout.log"]) and exe["stderr"]["sha256"] == sha_bytes(blobs["provenance/stderr.log"]), "execution receipt log pins")
    need(invocation["authorization"]["sha256"] == sha_bytes(blobs["provenance/root-authorization.json"]), "invocation authorization pin")
    need(invocation["parent_source"]["sha256"] == sha_bytes(blobs["provenance/root-execute-once.py"]), "invocation parent-executor pin")
    need(invocation["plan_runner_review"]["sha256"] == sha_bytes(blobs["provenance/runner-review-v3.json"]), "invocation runner-review pin")
    need(exe["output_dir"].endswith("/run-v1"), "execution output directory identity")
    need(rc["actual_return_code"] == 0, "durable process RC receipt")
    need(comparison["construction_receipt_sha256"] == sha_bytes(blobs["outputs/construction-receipt.json"]), "construction receipt ancestry")
    result_raw = blobs["targets/lw-v13.result.gz"]
    need(comparison["target_result_sha256"] == sha_bytes(result_raw), "target result ancestry")
    need(construction_receipt["status"] == "CONSTRUCTION_DURABLE_TARGET_NOT_YET_READ" and construction_receipt["point_invocations"] == 1, "durable construction receipt")
    construction_entry = next(e for e in entries if e["path"] == "outputs/construction.json.gz")
    need(construction_receipt["artifact"]["sha256"] == construction_entry["sha256"] and construction_receipt["artifact"]["size_bytes"] == construction_entry["size_bytes"], "construction artifact pin")
    need(construction_receipt["artifact"]["uncompressed_sha256"] == sha_bytes(blobs["outputs/construction.json.gz"]) and construction_receipt["artifact"]["uncompressed_size_bytes"] == len(blobs["outputs/construction.json.gz"]), "construction inflated artifact pin")
    need(state["status"] == "COMPLETE_DESCRIPTIVE_ONLY" and state["target_reads"] == 1, "execution state")
    need(comparison["status"] == "DESCRIPTIVE_COMPARISON_COMPLETE_NO_ACCEPTANCE_THRESHOLD", "comparison remains descriptive")
    audit2 = load("audits/terminal-audit-v2.json")
    audit3 = load("audits/terminal-audit-v3.json")
    supersession = load("audits/metadata-supersession.json")
    need(manifest["terminal_audit"]["status"] == "SOURCE_ORDER_LEDGER_VALIDATED_TARGET_RESIDUALS_DESCRIPTIVE_ONLY", "terminal audit status")
    need(audit3["status"] == manifest["terminal_audit"]["status"] and audit2["status"] == audit3["status"], "terminal audit lineage/status")
    need(audit3["target_reparse"] == audit2["target_reparse"] and audit3["dry_column"] == audit2["dry_column"] and audit3["major_terms"] == audit2["major_terms"] and audit3["minor_terms"] == audit2["minor_terms"], "v3 must preserve v2 numeric audit fields")
    need(supersession["changed_field"] == "Exactly one provenance_limits element is corrected. All remaining report fields and array/term findings are JSON-value-identical to v2.", "audit metadata supersession scope")
    need(audit3["execution"]["receipt_sha256"] == sha_bytes(blobs["provenance/execution.json"]), "terminal audit execution pin")
    need(audit2["pins"]["audit_script_sha256"] == sha_bytes(blobs["audits/audit-positive-saved-v2.py"]), "preserved v2 audit script pin")
    need(audit3["pins"]["audit_script_sha256"] == audit2["pins"]["audit_script_sha256"], "v3 numerical audit script lineage")
    need(supersession["corrector_script"]["sha256"] == sha_bytes(blobs["audits/audit-positive-saved-v3.py"]), "metadata correction script pin")
    need(supersession["corrected_report"]["sha256"] == sha_bytes(blobs["audits/terminal-audit-v3.json"]), "metadata corrected report pin")
    need(supersession["prior_report"]["sha256"] == sha_bytes(blobs["audits/terminal-audit-v2.json"]), "metadata prior report pin")

    inp = parse_packet(blobs["inputs/lw-v13.input"].decode("ascii"), "RRTMGP_REPLAY_V13",
                       lambda h: len(h) >= 3 and h[:3] == ["LW", "1", "45"])
    target = parse_packet(result_raw.decode("ascii"), "RRTMGP_RESULT_V1",
                          lambda h: h == ["LW", "1", "45"])
    need(inp["VMR_N2"][0] == (1,45) and all(x == N2_VMR for x in inp["VMR_N2"][1]), "captured positive N2 profile")
    need(inp["TRACE_GASES_PRESENT"][0] == (1,1) and inp["TRACE_GASES_PRESENT"][1] == [1.0], "CFC trace marker")
    for name in ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"):
        need(name in inp and inp[name][0] == (1,45) and all(x >= 0.0 for x in inp[name][1]), f"CFC profile {name}")

    cobj = json.loads(blobs["outputs/construction.json.gz"].decode("utf-8"))
    need(cobj["status"] == "POINT_ARRAYS_CONSTRUCTED_TARGETS_NOT_OPENED" and len(cobj["cases"]) == 1, "construction output")
    case = cobj["cases"][0]
    expected_gases = ["h2o", "co2", "o3", "n2o", "ch4", "o2", "n2", "ccl4", "cfc11", "cfc12", "cfc22"]
    expected_sections = {
        "h2o": "H2O", "co2": "CO2", "o3": "O3", "n2o": "N2O",
        "ch4": "CH4", "o2": "O2", "n2": "VMR_N2", "ccl4": "VMR_CCL4",
        "cfc11": "VMR_CFC11", "cfc12": "VMR_CFC12", "cfc22": "VMR_CFC22",
    }
    records = case["gas_column_records"]
    need(case["case_id"] == "normal-positive-n2-captured-input" and case["available_gases"] == expected_gases, "case gas roster")
    need([r["gas"] for r in records] == expected_gases and len({r["gas"] for r in records}) == 11, "unique canonical gas records")
    need({r["gas"]: r["input_section"] for r in records} == expected_sections, "canonical gas-to-input mapping")
    need(case["n2_source"].startswith("captured VMR_N2 input section") and case["n2_vmr_values"] == inp["VMR_N2"][1], "N2 source provenance")
    dry = case["dry_column_molecule_cm2"]
    need(len(dry) == 45 and all(math.isfinite(x) and x > 0 for x in dry), "45-layer dry column")
    need(inp["NATIVE_DRY_LAYER_MASS_KG_M2"][0] == (1,32) and inp["PLEV"][0] == (1,46) and inp["H2O"][0] == (1,45), "native mass / pressure / H2O input dimensions")
    need(inp["MOL_WEIGHT_DRY"][0] == (1,1) and inp["GRAVITY"][0] == (1,1), "host constants input dimensions")
    need(len(cobj["dry_column_source_order_terms"]) == 45, "dry source term roster")
    dry_terms = cobj["dry_column_source_order_terms"]
    need([r["source"] for r in dry_terms] == ["native_mass_prefix"]*32+["pressure_extension"]*13, "32+13 source split")
    constants = blobs["source/mo_gas_optics_constants.F90.gz"].decode("ascii")
    def const(name):
        match = re.search(rf"\b{name}\s*=\s*([0-9.]+(?:[Ee][+-]?\d+)?)_wp", constants, re.I)
        need(match is not None, f"source constant {name}")
        return float(match.group(1))
    avog = const("avogad")
    mh2o = const("m_h2o")
    mdry = inp["MOL_WEIGHT_DRY"][1][0]
    gravity = inp["GRAVITY"][1][0]
    masses = inp["NATIVE_DRY_LAYER_MASS_KG_M2"][1]
    h2o = inp["H2O"][1]
    plev = inp["PLEV"][1]
    for k, row in enumerate(dry_terms):
        need(row["layer_fortran"] == k+1, f"dry layer order {k+1}")
        if k < 32:
            expected = masses[k] * (avog / (mdry * 10000.0))
            need(row["native_mass_kg_m2"] == masses[k], f"native mass input {k+1}")
        else:
            edges = [x*100.0 for x in plev]
            delta = abs(edges[k]-edges[k+1])
            fact = 1.0 / (1.0 + h2o[k])
            mair = (mdry + mh2o*h2o[k]) * fact
            expected = 10.0 * delta * avog * fact / (1000.0 * mair * 100.0 * gravity)
        need(row["selected_molecule_cm2"] == expected == dry[k], f"source-order dry value {k+1}")
    for record in case["gas_column_records"]:
        gas, section = record["gas"], record["input_section"]
        need(section in inp and inp[section][0] == (1,45), f"input gas profile {gas}")
        vmr = inp[section][1]
        same_list(record["vmr_values"], vmr, f"{gas} VMR")
        same_list(record["column_molecule_cm2"], [v*d for v,d in zip(vmr,dry)], f"{gas} VMR×dry")
    need(len(case["tau_point"]) == 45 and all(len(r) == 128 for r in case["tau_point"]), "constructed tau dimensions")
    need(all(math.isfinite(x) for row in case["tau_point"] for x in row), "constructed tau finite")

    # Join all saved target arrays to construction, with exact 32/13 partitions.
    need(target["GAS_COL_DRY"][0] == (1,45,1), "target dry shape")
    target_dry = target["GAS_COL_DRY"][1]
    same_list(dry, target_dry, "GAS_COL_DRY all45")
    sections = (("GAS_TAU_RAW", "GAS_TAU_RAW"), ("GAS_TAU", "GAS_TAU"))
    for target_name, metric_name in sections:
        shape, vals = target[target_name]
        need(shape == (1,45,128), f"{target_name} shape")
        cand = case["tau_point"]
        linear = [cand[k][g] for g in range(128) for k in range(45)]
        same_list(linear, vals, target_name + " construction join")
        comp = comparison["comparisons"][metric_name]
        need(comp["all45"]["shape"] == [45,128] and comp["native32"]["shape"] == [32,128] and comp["pressure_extensions13"]["shape"] == [13,128], target_name + " comparison shape ledger")
        for scope, layers in (("all45", range(45)), ("native32", range(32)), ("pressure_extensions13", range(32,45))):
            cv = [cand[k][g] for g in range(128) for k in layers]
            tv = [flat_tau_target(vals,k,g) for g in range(128) for k in layers]
            summary_check(comp[scope], cv, tv, f"{target_name}/{scope}")
    need(target["VMR_N2"][0] == (1,45,1), "result N2 shape")
    same_list(target["VMR_N2"][1], inp["VMR_N2"][1], "result N2 echo")
    for scope, inds in (("all45", range(45)), ("native32", range(32)), ("pressure_extensions13", range(32,45))):
        cv = [dry[k] for k in inds]
        tv = [target_dry[k] for k in inds]
        summary_check(comparison["comparisons"]["GAS_COL_DRY"][scope], cv, tv, "GAS_COL_DRY/"+scope)

    print("PASS_SAVED_POSITIVE_N2_CONSTRUCTION_TARGET_AND_PROVENANCE_JOINS; diagnostic only")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
