#!/usr/bin/env python3
"""Verify packaged saved opacity evidence; never rerun reconstruction."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import sys


HERE = Path(__file__).resolve().parent
EXPECTED_BASE = "bca70eaad093b6fa34b19c0d59928570471d8f35"
EXPECTED_PLAN_SHA = "21edb10d1af8cbc6b12f44e305572d49fa688d822644c49acb946246aa62d01e"
EXPECTED_CASES = ["n2-absent-baseline", "n2-explicit-zero", "n2-0p7808"]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_payload(path: Path, entry: dict) -> bytes:
    stored = path.read_bytes()
    if len(stored) != entry["size_bytes"] or digest(stored) != entry["sha256"]:
        raise ValueError(f"stored payload pin mismatch: {entry['path']}")
    if entry["encoding"] == "gzip":
        raw = gzip.decompress(stored)
        if len(raw) != entry["uncompressed_size_bytes"] or digest(raw) != entry["uncompressed_sha256"]:
            raise ValueError(f"inflated payload pin mismatch: {entry['path']}")
        return raw
    if entry["encoding"] != "identity":
        raise ValueError(f"unknown payload encoding for {entry['path']}")
    return stored


def load_payload(entries: dict, rel: str) -> bytes:
    if rel not in entries:
        raise ValueError(f"manifest lacks {rel}")
    return read_payload(HERE / rel, entries[rel])


def collect_plan_pins(obj, pointer=""):
    out = []
    if isinstance(obj, dict):
        if {"path", "sha256", "size_bytes"}.issubset(obj):
            out.append({"json_pointer": pointer or "/", "path": obj["path"],
                        "sha256": obj["sha256"], "size_bytes": int(obj["size_bytes"])})
        for key, value in obj.items():
            out.extend(collect_plan_pins(value, pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            out.extend(collect_plan_pins(value, pointer + "/" + str(i)))
    return sorted(out, key=lambda x: (x["json_pointer"], x["path"]))


def _skip_json_value(text: str, pos: int) -> int:
    """Lexically skip a large JSON value without materializing its term ledger."""
    n = len(text)
    while pos < n and text[pos].isspace():
        pos += 1
    if pos >= n:
        raise ValueError("unexpected EOF while scanning construction JSON")
    if text[pos] in "[{":
        stack = [text[pos]]
        pos += 1
        quoted = False
        escaped = False
        while pos < n and stack:
            ch = text[pos]
            if quoted:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    quoted = False
            elif ch == '"':
                quoted = True
            elif ch in "[{":
                stack.append(ch)
            elif ch in "]}":
                op = stack.pop()
                if (op, ch) not in {("[", "]"), ("{", "}")}:
                    raise ValueError("mismatched JSON brackets in construction")
            pos += 1
        if stack or quoted:
            raise ValueError("unterminated JSON value in construction")
        return pos
    if text[pos] == '"':
        _, end = json.JSONDecoder().raw_decode(text, pos)
        return end
    while pos < n and text[pos] not in ",]} \t\r\n":
        pos += 1
    return pos


def _case_member(text: str, start: int) -> tuple[dict, int]:
    decoder = json.JSONDecoder()
    pos = start
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if text[pos] != "{":
        raise ValueError("construction case is not a JSON object")
    pos += 1
    case = {}
    # The discrete frontend mapping is modest; retain it for the post-build
    # pfrac context join while lexically skipping the much larger term ledgers.
    wanted = {"case_id", "dry_column_molecule_cm2", "tau_point", "discrete_context", "available_gases"}
    while True:
        while pos < len(text) and (text[pos].isspace() or text[pos] == ","):
            pos += 1
        if text[pos] == "}":
            return case, pos + 1
        key, pos = decoder.raw_decode(text, pos)
        if not isinstance(key, str):
            raise ValueError("non-string key in construction case")
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if text[pos] != ":":
            raise ValueError("missing colon in construction case")
        pos += 1
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if key in wanted:
            case[key], pos = decoder.raw_decode(text, pos)
        else:
            pos = _skip_json_value(text, pos)
    raise ValueError("unterminated construction case")


def read_saved_construction(path: Path) -> dict:
    # 143 MB raw JSON is streamed through gzip then retained as text only; the
    # very large per-corner ledgers are skipped lexically, not parsed into dicts.
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        text = stream.read()
    marker = '"cases"'
    at = text.find(marker)
    if at < 0:
        raise ValueError("construction has no cases array")
    pos = at + len(marker)
    while text[pos].isspace():
        pos += 1
    if text[pos] != ":":
        raise ValueError("malformed cases member")
    pos += 1
    while text[pos].isspace():
        pos += 1
    if text[pos] != "[":
        raise ValueError("cases is not an array")
    pos += 1
    cases = []
    while True:
        while text[pos].isspace() or text[pos] == ",":
            pos += 1
        if text[pos] == "]":
            break
        case, pos = _case_member(text, pos)
        cases.append(case)
    if [x.get("case_id") for x in cases] != EXPECTED_CASES:
        raise ValueError("saved construction case roster/order mismatch")
    for case in cases:
        if len(case.get("dry_column_molecule_cm2", [])) != 45:
            raise ValueError(f"saved dry column must have 45 layers: {case.get('case_id')}")
        tau = case.get("tau_point")
        if len(tau) != 45 or any(len(row) != 128 for row in tau):
            raise ValueError(f"saved tau array must be 45x128: {case.get('case_id')}")
    return {x["case_id"]: x for x in cases}


def parse_result(raw: bytes) -> dict:
    lines = raw.decode("utf-8").splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RESULT_V1":
        raise ValueError("wrong replay result magic")
    head = lines[1].split()
    if len(head) != 3 or head[0].upper() != "LW" or tuple(map(int, head[1:])) != (1, 45):
        raise ValueError("unexpected saved result phase/dimensions")
    sections = {}
    i = 2
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        h = lines[i].split()
        i += 1
        if len(h) != 4:
            raise ValueError("invalid result section header")
        name = h[0].upper()
        shape = tuple(map(int, h[1:]))
        if name in sections or any(x <= 0 for x in shape):
            raise ValueError(f"duplicate or invalid section {name}")
        count = math.prod(shape)
        values = []
        while i < len(lines) and len(values) < count:
            if lines[i].strip():
                values.extend(float(x.replace("D", "E").replace("d", "e")) for x in lines[i].split())
            i += 1
        if len(values) != count or not all(math.isfinite(x) for x in values):
            raise ValueError(f"invalid value count/nonfinite data in {name}")
        sections[name] = (shape, values)
    return {"phase": "LW", "nc": 1, "nl": 45, "sections": sections}


def tau_matrix(parsed: dict, name: str) -> list[list[float]]:
    shape, values = parsed["sections"][name]
    if shape != (1, 45, 128):
        raise ValueError(f"{name} has unexpected shape {shape}")
    # The solver text is serialized in Fortran order for (column, layer, gpoint).
    return [[values[layer + 45 * gpoint] for gpoint in range(128)] for layer in range(45)]


def dry_vector(parsed: dict) -> list[float]:
    shape, values = parsed["sections"]["GAS_COL_DRY"]
    if shape != (1, 45, 1):
        raise ValueError(f"GAS_COL_DRY has unexpected shape {shape}")
    return values


def ordered_ulp(a: float, b: float) -> int:
    ai = struct.unpack(">Q", struct.pack(">d", a))[0]
    bi = struct.unpack(">Q", struct.pack(">d", b))[0]
    def order(bits):
        return ((~bits) & ((1 << 64) - 1)) if bits >> 63 else bits | (1 << 63)
    return order(ai) - order(bi)


def verify() -> dict:
    manifest_path = HERE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("base_commit") != EXPECTED_BASE:
        raise ValueError("unexpected package base commit")
    entries_list = manifest.get("entries")
    if not isinstance(entries_list, list):
        raise ValueError("manifest entries are not a list")
    entries = {x["path"]: x for x in entries_list}
    if len(entries) != len(entries_list):
        raise ValueError("duplicate package path in manifest")
    actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and p != manifest_path}
    if actual != set(entries):
        raise ValueError(f"closed-roster mismatch missing={sorted(set(entries)-actual)} extra={sorted(actual-set(entries))}")
    for rel, entry in entries.items():
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise ValueError(f"unsafe manifest path {rel}")
        read_payload(HERE / rel, entry)

    plan_raw = load_payload(entries, "plan/plan-v3.json")
    if digest(plan_raw) != EXPECTED_PLAN_SHA:
        raise ValueError("plan v3 frozen hash mismatch")
    plan = json.loads(plan_raw)
    auth = json.loads(load_payload(entries, "provenance/authorization.json"))
    receipt = json.loads(load_payload(entries, "provenance/execution.json"))
    if auth.get("status") != "AUTHORIZED_DIAGNOSTIC_ONLY" or auth.get("plan_sha256") != EXPECTED_PLAN_SHA:
        raise ValueError("authorization plan/status mismatch")
    expected_records = collect_plan_pins(plan)
    if auth.get("artifact_pins") != expected_records:
        raise ValueError("authorization does not bind all plan artifact records")
    if len(expected_records) != 51:
        raise ValueError("plan pin roster count changed")
    if receipt.get("actual_child_return_code") != 0 or receipt.get("timed_out") is not False:
        raise ValueError("parent execution receipt is not an actual successful bounded process")
    if receipt.get("point_source", {}).get("sha256") != auth.get("point_source", {}).get("sha256"):
        raise ValueError("execution source does not match authorization")
    if receipt.get("runner_source", {}).get("sha256") != auth.get("runner_source", {}).get("sha256"):
        raise ValueError("execution runner does not match authorization")
    if load_payload(entries, "provenance/stdout.log") or load_payload(entries, "provenance/stderr.log"):
        raise ValueError("captured parent stdout/stderr differ from the recorded empty logs")

    # Confirm the tracked external coefficient pin without duplicating its bytes.
    external = manifest.get("external_pins", [])
    if len(external) != 1:
        raise ValueError("expected exactly one external coefficient pin")
    repo = HERE.parents[2]
    ext = external[0]
    coeff_path = repo / ext["repository_path"]
    if not coeff_path.is_file() or coeff_path.is_symlink():
        raise ValueError("external coefficient table is not a regular tracked checkout file")
    if coeff_path.stat().st_size != ext["size_bytes"] or digest(coeff_path.read_bytes()) != ext["sha256"]:
        raise ValueError("external coefficient table hash/size mismatch")
    if ext["sha256"] != plan["pinned_artifacts"]["lw_coefficients"]["sha256"]:
        raise ValueError("external coefficient and frozen plan pins differ")

    source_checks = {
        "source/reconstruct_point_v5.py": auth["point_source"],
        "source/run_point_once_v2.py": auth["runner_source"],
        "reviews/point-v5-source-review.json": auth["source_review"],
        "reviews/runner-v2-review.json": auth["runner_review"],
    }
    for rel, pin in source_checks.items():
        raw = load_payload(entries, rel)
        if len(raw) != pin["size_bytes"] or digest(raw) != pin["sha256"]:
            raise ValueError(f"authorized source/review differs from bundled file: {rel}")
    source_pin_checks = {
        "source/gas_constants.F90.gz": "gas_constants",
        "source/gas_frontend.F90.gz": "gas_frontend",
        "source/gas_kernel.F90.gz": "gas_kernel",
        "source/coefficient_loader.F90.gz": "coefficient_loader",
        "source/reference_column.f90.gz": "gp_source",
        "inputs/matched-legacy-dry.input": "matched_input",
    }
    for rel, pin_name in source_pin_checks.items():
        raw = load_payload(entries, rel)
        pin = plan["pinned_artifacts"][pin_name]
        origin = entries[rel].get("origin", {})
        if (len(raw) != pin["size_bytes"] or digest(raw) != pin["sha256"] or
                origin.get("sha256") != pin["sha256"] or origin.get("size_bytes") != pin["size_bytes"]):
            raise ValueError(f"copied plan-pinned source/input identity differs: {rel}")
    review_doc = json.loads(load_payload(entries, "reviews/final-saved-evidence-review.json"))
    if review_doc.get("status") != "PASS_SCOPED_SAVED_EVIDENCE":
        raise ValueError("final saved-evidence review is not a scoped pass")
    erratum = json.loads(load_payload(entries, "reviews/reviewer-lookup-addendum.json"))
    if erratum.get("status") != "PASS_SCOPED_SAVED_EVIDENCE_UNCHANGED":
        raise ValueError("final review addendum is not a scoped pass")

    construction = read_saved_construction(HERE / "outputs/construction.json.gz")
    diagnostic = json.loads(load_payload(entries, "outputs/diagnostic.json.gz"))
    construction_raw = load_payload(entries, "outputs/construction.json.gz")
    if digest(construction_raw) != diagnostic.get("construction_sha256"):
        raise ValueError("diagnostic construction SHA does not match saved construction")
    if diagnostic.get("status") != "DIAGNOSTIC_COMPLETE_NO_NUMERICAL_VERDICT":
        raise ValueError("diagnostic status unexpectedly claims a numerical verdict")
    comparisons = diagnostic.get("comparisons", [])
    if len(comparisons) != 6:
        raise ValueError("expected six saved tau comparisons")
    target_file = {
        "n2-absent-baseline": "targets/n2-absent-baseline.result.gz",
        "n2-explicit-zero": "targets/n2-explicit-zero.result.gz",
        "n2-0p7808": "targets/n2-0p7808.result.gz",
    }
    target_data = {case: parse_result(load_payload(entries, rel)) for case, rel in target_file.items()}
    result_targets = {
        "n2-absent-baseline": plan["pinned_artifacts"]["gp_absent_result"],
        "n2-explicit-zero": plan["pinned_artifacts"]["gp_zero_result"],
        "n2-0p7808": plan["pinned_artifacts"]["gp_n2_result"],
    }
    for case_id, rec in result_targets.items():
        rel = target_file[case_id]
        origin = entries[rel].get("origin")
        if not origin or origin["sha256"] != rec["sha256"] or origin["size_bytes"] != rec["size_bytes"]:
            raise ValueError(f"saved target origin pin mismatch: {case_id}")

    verified_comparisons = 0
    for item in comparisons:
        case_id, section = item["case_id"], item["target_section"]
        if case_id not in construction or case_id not in target_data or section not in ("GAS_TAU_RAW", "GAS_TAU"):
            raise ValueError("unexpected case/target-section comparison")
        candidate = construction[case_id]["tau_point"]
        target = tau_matrix(target_data[case_id], section)
        if candidate != target:
            raise ValueError(f"saved reconstructed tau differs from captured {case_id}/{section}")
        if item.get("candidate_tau") != candidate or item.get("target_tau") != target:
            raise ValueError(f"diagnostic array copy differs for {case_id}/{section}")
        zeros = sum(x == 0.0 for row in target for x in row)
        if (item.get("summary", {}).get("max_absolute_residual") != 0.0 or
                item["summary"].get("max_absolute_ordered_ulp_delta") != 0 or
                item["summary"].get("target_zero_cells") != zeros or
                any(x != 0.0 for row in item["signed_residual"] for x in row) or
                any(x != 0.0 for row in item["absolute_residual"] for x in row) or
                any(x != 0 for row in item["signed_ordered_binary64_ulp_delta"] for x in row)):
            raise ValueError(f"stored residual summary/arrays are inconsistent for {case_id}/{section}")
        for layer in range(45):
            for gpoint in range(128):
                if ordered_ulp(candidate[layer][gpoint], target[layer][gpoint]) != 0:
                    raise ValueError("saved exact tau match has nonzero ordered ULP delta")
        verified_comparisons += 1

    dry_checks = diagnostic.get("dry_column_crosschecks", [])
    if [x.get("case_id") for x in dry_checks] != EXPECTED_CASES:
        raise ValueError("dry-column case roster mismatch")
    for row in dry_checks:
        case_id = row["case_id"]
        constructed = construction[case_id]["dry_column_molecule_cm2"]
        saved = dry_vector(target_data[case_id])
        if constructed != saved or row.get("reconstructed_molecule_cm2") != constructed or row.get("saved_GAS_COL_DRY_molecule_cm2") != saved:
            raise ValueError(f"saved 45-layer dry columns differ: {case_id}")
        if row["summary"].get("max_absolute_residual") != 0.0 or any(x != 0.0 for x in row["signed_residual"]):
            raise ValueError(f"saved dry-column residual arrays inconsistent: {case_id}")

    pfrac = json.loads(load_payload(entries, "context/pfrac-result.json"))
    pfrac_check = json.loads(load_payload(entries, "outputs/pfrac-context-crosscheck.json"))
    positive = construction["n2-0p7808"]["discrete_context"]
    if (construction["n2-0p7808"]["available_gases"] != pfrac["reduced_gases"] or
            positive["key_species_reduced_ids"] != pfrac["key_species_rewritten"] or
            positive["flavors_reduced_ids"] != pfrac["flavors_Fortran_indices"] or
            positive["jtemp_fortran"] != pfrac["jtemp_Fortran"] or
            positive["jpress_fortran"] != pfrac["jpress_Fortran"] or
            [1 if x else 2 for x in positive["tropopause_lower"]] != pfrac["atmosphere_Fortran"]):
        raise ValueError("saved positive-N2 pfrac discrete context does not join")
    if len(pfrac_check.get("exact_discrete_checks", {})) != 6 or not all(
        x.get("exact_equal") is True for x in pfrac_check["exact_discrete_checks"].values()
    ):
        raise ValueError("saved post-construction pfrac cross-check is incomplete")

    return {
        "status": "PASS_SAVED_ARTIFACT_INTEGRITY_AND_EXACT_OBSERVED_ARRAY_JOINS",
        "scope": "Package bytes, saved construction, saved outputs and metadata joins only; no fresh reconstruction.",
        "payloads_checked": len(entries),
        "plan_historical_artifact_pin_records": len(expected_records),
        "tau_arrays_exactly_joined": verified_comparisons,
        "dry_columns_exactly_joined": len(dry_checks),
        "solver_calls": 0,
        "model_calls": 0,
        "numerical_verdict": "NONE; observed equality is not a strict arithmetic-bound or accuracy pass",
    }


def main() -> int:
    try:
        report = verify()
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
