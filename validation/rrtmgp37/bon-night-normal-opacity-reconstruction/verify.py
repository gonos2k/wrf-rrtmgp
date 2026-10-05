#!/usr/bin/env python3
"""Verify the saved normal-carrier opacity evidence without numerical replay."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MANIFEST_PATH = HERE / "manifest.json"


def need(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("FAIL: " + message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_entry(entry: dict) -> bytes:
    p = HERE / entry["path"]
    data = p.read_bytes()
    need(len(data) == entry["size_bytes"], f"stored size: {entry['path']}")
    need(sha(data) == entry["sha256"], f"stored SHA256: {entry['path']}")
    if entry["encoding"] == "gzip":
        raw = gzip.decompress(data)
        need(len(raw) == entry["uncompressed_size_bytes"], f"inflated size: {entry['path']}")
        need(sha(raw) == entry["uncompressed_sha256"], f"inflated SHA256: {entry['path']}")
        return raw
    need(entry["encoding"] == "identity", f"unknown encoding: {entry['path']}")
    return data


def jentry(entries: dict, path: str) -> dict:
    return json.loads(read_entry(entries[path]))


HEADER = re.compile(r"^([A-Z][A-Z0-9_]*)\s+((?:\d+\s+){1,3}\d+)\s*$")
FLOAT = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?")


def packet(text: str, result: bool) -> tuple[dict, dict]:
    lines = text.splitlines()
    need(lines and lines[0].strip() == ("RRTMGP_RESULT_V1" if result else "RRTMGP_REPLAY_V10"), "packet magic")
    start = 1
    if result:
        need(len(lines) > 1 and lines[1].split()[:1] == ["LW"], "result phase header")
        phase = lines[1].split()
        need(phase == ["LW", "1", "45"], "result phase dimensions")
        start = 2
    else:
        head = lines[1].split()
        need(len(head) == 6 and head[:3] == ["LW", "1", "45"], "input phase dimensions")
        start = 2
    sections: dict[str, tuple[tuple[int, ...], list[float]]] = {}
    current = None
    for line in lines[start:]:
        m = HEADER.match(line)
        if m:
            dims = tuple(map(int, m.group(2).split()))
            current = (m.group(1), dims, [])
            need(current[0] not in sections, f"duplicate packet section {current[0]}")
            sections[current[0]] = (dims, current[2])
        elif current is not None:
            sections[current[0]][1].extend(float(x.replace("D", "E").replace("d", "e")) for x in FLOAT.findall(line))
        elif line.strip():
            raise SystemExit("FAIL: unparsed packet content")
    for name, (dims, vals) in sections.items():
        count = math.prod(dims)
        need(len(vals) == count, f"{name} payload count {len(vals)} != {count}")
    return {k: v[0] for k, v in sections.items()}, {k: v[1] for k, v in sections.items()}


def nested_layer_gpt(values: list[float], nlay: int, ngpt: int) -> list[list[float]]:
    # V10/result storage is Fortran ordered, with column as the unit dimension.
    return [[values[g * nlay + k] for g in range(ngpt)] for k in range(nlay)]


def close_json_numbers(a, b) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close_json_numbers(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    need(manifest.get("schema") == "udm37-bon-night-normal-opacity-reconstruction-manifest-v1", "manifest schema")
    entries_list = manifest["entries"]
    entries = {e["path"]: e for e in entries_list}
    need(len(entries) == len(entries_list), "duplicate manifest paths")
    actual = {str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file() and p != MANIFEST_PATH}
    need(actual == set(entries), f"closed roster mismatch: missing={sorted(set(entries)-actual)} extra={sorted(actual-set(entries))}")
    payload_count = 0
    decoded = {}
    for path, entry in entries.items():
        decoded[path] = read_entry(entry)
        payload_count += 1
    need(payload_count == manifest["payload_count"], "payload count")

    # These dependencies are already tracked evidence in the base branch.
    for ext in manifest["external_pins"]:
        p = REPO / ext["repository_path"]
        data = p.read_bytes()
        need(len(data) == ext["size_bytes"] and sha(data) == ext["sha256"], f"external tracked pin {ext['name']}")
    ext = {e["name"]: e for e in manifest["external_pins"]}
    pfrac_plan = json.loads((REPO / ext["pfrac plan from earlier tracked PR110 evidence"]["repository_path"]).read_text())
    pfrac_result = json.loads((REPO / ext["pfrac result from earlier tracked PR110 evidence"]["repository_path"]).read_text())
    matched_gz = (REPO / ext["matched pfrac input gzip from earlier tracked PR110 evidence"]["repository_path"]).read_bytes()
    matched = gzip.decompress(matched_gz)
    matched_pin = ext["matched pfrac input gzip from earlier tracked PR110 evidence"]
    need(len(matched) == matched_pin["uncompressed_size_bytes"] and sha(matched) == matched_pin["uncompressed_sha256"], "external matched-input inflated pin")

    plan = jentry(entries, "plan/normal-opacity-plan-v2.json")
    auth = jentry(entries, "provenance/authorization.json")
    parent = jentry(entries, "provenance/parent-execution.json")
    state = jentry(entries, "provenance/execution-state.json")
    receipt = jentry(entries, "provenance/construction-receipt.json")
    construction = json.loads(decoded["outputs/construction.json.gz"])
    comparison = json.loads(decoded["outputs/normal-target-comparison.json.gz"])
    crosscheck = jentry(entries, "outputs/pfrac-context-crosscheck.json")

    plan_bytes = decoded["plan/normal-opacity-plan-v2.json"]
    plan_hash = sha(plan_bytes)
    auth_bytes = decoded["provenance/authorization.json"]
    auth_hash = sha(auth_bytes)
    point_hash = sha(decoded["source/reconstruct_normal_locked_v1.py"])
    runner_hash = sha(decoded["source/run_normal_once_v3.py"])
    need(auth["plan_sha256"] == plan_hash == comparison["plan_sha256"], "plan ancestry")
    need(auth["point_source"]["sha256"] == point_hash == comparison["point_source_sha256"], "point source ancestry")
    need(auth["runner_source"]["sha256"] == runner_hash, "runner source ancestry")
    need(auth["status"] == "AUTHORIZED_DIAGNOSTIC_ONLY" and auth["source_review_status"] == "PASS_SCOPED_LOCKED_SOURCE_REVIEW", "authorization/source review status")
    need(parent["actual_child_return_code"] == 0 and parent["timed_out"] is False, "actual child terminal status")
    need(parent["bounded_python_invocations"] == 1 and all(parent[k] == 0 for k in ("new_WRF", "new_RTE", "new_REAL", "new_builds")), "execution scope")
    need(state["status"] == "POINT_RECONSTRUCTION_STARTED" and state["actual_process_return_code"] == "RECORDED_BY_PARENT", "saved execution-state placeholder is retained")
    need(receipt["status"] == "NORMAL_POINT_ARRAY_DURABLY_WRITTEN_BEFORE_TARGET_READ" and receipt["case_ids"] == ["normal-n2-absent"], "construction receipt")
    construction_raw = decoded["outputs/construction.json.gz"]
    need(receipt["construction_sha256"] == sha(construction_raw), "construction receipt SHA")
    cases = construction["cases"]
    need(construction["status"] == "POINT_ARRAYS_CONSTRUCTED_TARGETS_NOT_OPENED" and len(cases) == 1, "construction output status/count")
    case = cases[0]
    need(case["case_id"] == "normal-n2-absent" and case["n2_override"] is None, "case identity/N2 scope")
    need(case["available_gases"] == ["h2o", "co2", "o3", "n2o", "ch4", "o2", "ccl4", "cfc11", "cfc12", "cfc22"], "normal available-gas roster")
    need(len(case["dry_column_molecule_cm2"]) == 45 and len(case["tau_point"]) == 45 and all(len(row) == 128 for row in case["tau_point"]), "construction dimensions")

    dims_in, vals_in = packet(decoded["inputs/normal-lw-v10.input"].decode("ascii"), False)
    need(dims_in.get("NATIVE_DRY_LAYER_MASS_KG_M2") == (1, 32), "normal input native dry-mass dimensions")
    need(dims_in.get("PLEV") == (1, 46) and dims_in.get("H2O") == (1, 45), "normal input pressure/H2O dimensions")
    need(len(vals_in["NATIVE_DRY_LAYER_MASS_KG_M2"]) == 32, "native dry mass payload")
    dry_terms = construction["dry_column_source_order_terms"]
    need(len(dry_terms) == 45, "dry-column provenance ledger length")
    need([r["layer_fortran"] for r in dry_terms] == list(range(1, 46)), "dry-column ledger layer order")
    need(all(r.get("source") == "native_mass_prefix" for r in dry_terms[:32]), "native dry-column ledger scope")
    need(all(r.get("source") == "pressure_extension" for r in dry_terms[32:]), "pressure/H2O extension ledger scope")
    need(close_json_numbers([r["selected_molecule_cm2"] for r in dry_terms], case["dry_column_molecule_cm2"]), "dry-column ledger and saved construction")

    # The saved direct result is parsed as a packet; no opacity calculation is repeated.
    dims_res, vals_res = packet(decoded["targets/normal-n2-absent.result.gz"].decode("ascii"), True)
    need(dims_res.get("GAS_COL_DRY") == (1, 45, 1), "target dry-column shape")
    need(dims_res.get("GAS_TAU_RAW") == (1, 45, 128) and dims_res.get("GAS_TAU") == (1, 45, 128), "target tau shapes")
    target_dry = vals_res["GAS_COL_DRY"]
    need(close_json_numbers(target_dry, case["dry_column_molecule_cm2"]), "target GAS_COL_DRY vs constructed carrier")
    need(len(comparison["comparisons"]) == 2, "comparison arrays count")
    for cmp in comparison["comparisons"]:
        section = cmp["target_section"]
        need(section in ("GAS_TAU_RAW", "GAS_TAU"), "comparison target section")
        candidate = cmp["candidate_tau"]
        target = cmp["target_tau"]
        parsed = nested_layer_gpt(vals_res[section], 45, 128)
        need(len(candidate) == len(target) == 45 and all(len(row) == 128 for row in candidate + target), f"saved comparison dimensions {section}")
        need(close_json_numbers(candidate, case["tau_point"]), f"construction-to-comparison candidate join {section}")
        need(close_json_numbers(target, parsed), f"saved comparison target array matches packet {section}")
        need(close_json_numbers(candidate, target), f"saved candidate-target exact identity {section}")
        need(all(x == 0 for row in cmp["absolute_residual"] for x in row), f"saved residual zero {section}")
        need(all(x == 0 for row in cmp["signed_ordered_binary64_ulp_delta"] for x in row), f"saved ULP zero {section}")
        need(cmp["summary"]["numerical_gate"] == "NONE_DIAGNOSTIC_ONLY" and cmp["summary"]["cells"] == 45*128, f"diagnostic-only comparison {section}")

    # The independent pfrac artifact is only a shared-state/context cross-check.
    need(pfrac_result.get("status") == "PASS_SCOPED", "pfrac result scoped status")
    need(pfrac_result.get("plan_sha256") == ext["pfrac plan from earlier tracked PR110 evidence"]["sha256"], "pfrac result-plan ancestry")
    pfrac_held = pfrac_plan.get("pins", {}).get("held_input", {})
    need(pfrac_held.get("sha256") == matched_pin["uncompressed_sha256"] and pfrac_held.get("bytes") == matched_pin["uncompressed_size_bytes"], "pfrac plan held-input ancestry")
    pfrac_input_dims, pfrac_input_values = packet(matched.decode("ascii"), False)
    shared = ["PLAY", "PLEV", "TLAY", "GRAVITY", "MOL_WEIGHT_DRY", "H2O", "CO2", "O3", "N2O", "CH4", "O2", "VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"]
    normal_text = decoded["inputs/normal-lw-v10.input"].decode("ascii")
    normal_dims, normal_values = packet(normal_text, False)
    for name in shared:
        need(normal_dims.get(name) == pfrac_input_dims.get(name), f"pfrac shared section dimensions {name}")
        need(normal_values.get(name) == pfrac_input_values.get(name), f"pfrac shared section exact values {name}")
    need(pfrac_result.get("reduced_gases", []).count("n2") == 1, "pfrac N2 roster context")
    need([g for g in pfrac_result["reduced_gases"] if g != "n2"] == case["available_gases"], "pfrac roster after N2 removal")
    discrete = case["discrete_context"]
    def semantic_species_ids(value, roster):
        if isinstance(value, list):
            return [semantic_species_ids(x, roster) for x in value]
        if isinstance(value, int):
            need(value == 0 or 1 <= value <= len(roster), "pfrac gas id range")
            return None if value == 0 else roster[value - 1]
        return value
    normal_keys = semantic_species_ids(discrete["key_species_reduced_ids"], case["available_gases"])
    pfrac_keys = semantic_species_ids(pfrac_result["key_species_rewritten"], pfrac_result["reduced_gases"])
    need(normal_keys == pfrac_keys, "pfrac semantic major key-species mapping")
    pfrac_flavors = semantic_species_ids(pfrac_result["flavors_Fortran_indices"], pfrac_result["reduced_gases"])
    need(len(discrete["layer_flavor_state"]) == 45, "layer flavor state count")
    for layer_no, layer in enumerate(discrete["layer_flavor_state"], 1):
        flavors = layer["flavors"]
        need([f["flavor_fortran"] for f in flavors] == list(range(1, len(pfrac_flavors) + 1)), f"layer {layer_no} flavor indices")
        need([semantic_species_ids(f["reduced_pair"], case["available_gases"]) for f in flavors] == pfrac_flavors, f"layer {layer_no} flavor semantic mapping")
        need(layer["tropopause_lower"] is discrete["tropopause_lower"][layer_no - 1], f"layer {layer_no} atmosphere state consistency")
    for key in ("jtemp_fortran", "jpress_fortran"):
        pk = {"jtemp_fortran":"jtemp_Fortran", "jpress_fortran":"jpress_Fortran", "atmosphere_fortran":"atmosphere_Fortran"}[key]
        need(discrete[key] == pfrac_result[pk], f"pfrac discrete mapping {key}")
    expected_atmosphere = [1 if is_lower else 2 for is_lower in discrete["tropopause_lower"]]
    need(expected_atmosphere == pfrac_result["atmosphere_Fortran"], "pfrac atmosphere index semantic mapping")
    need(crosscheck["pfrac_result_sha256"] == ext["pfrac result from earlier tracked PR110 evidence"]["sha256"], "saved pfrac crosscheck target")
    need(all(v.get("exact_equal") is True for v in crosscheck["exact_discrete_checks"].values()), "pfrac discrete context checks")
    need(crosscheck["exact_discrete_checks"]["atmosphere_fortran"]["exact_equal"] is True and crosscheck["exact_discrete_checks"]["flavor_semantic_names"]["exact_equal"] is True, "pfrac atmosphere/flavor semantic context")
    need(crosscheck["fraction_differences_diagnostic_only"]["tolerance_or_numerical_verdict"] == "NONE", "pfrac scope has no numeric verdict")
    need(crosscheck["scope"].find("no minor-roster equality or tau inputs") >= 0, "pfrac scope wording")

    compat = jentry(entries, "provenance/source-compatibility.json")
    call_context = compat.get("actual_call_context", {})
    need(call_context.get("sidecar_argument") == "" and call_context.get("returncode") == 0, "normal invocation sidecar absent and target call succeeded")
    need("not as conclusive proof" in compat.get("provenance_gap", {}).get("remaining_limit", ""), "no overclaim of full executable identity")
    production_result = jentry(entries, "production-join/result.json")
    production_execution = jentry(entries, "production-join/execution.json")
    production_summary = jentry(entries, "production-join/target-distinction.json")
    production_review = jentry(entries, "production-join/independent-review.json")
    terminal_review = jentry(entries, "reviews/direct-reference-terminal-review.json")
    source_manifest = jentry(entries, "production-join/serial-source-manifest.json")
    need(production_execution["actual_returncode"] == 0 and production_execution["new_opacity_point_RTE_model_compile"] == 0, "saved WRF-join analysis execution scope")
    need(production_result["status"] == "DIAGNOSTIC_COMPLETE_NO_NUMERICAL_VERDICT" and production_result["same_call_join_exact"] is True, "saved same-call WRF join status")
    need(terminal_review["status"] == "PASS_SCOPED_SAVED_ARTIFACTS_AND_SOURCE_ORDER_TERM_AUDIT_NO_NUMERICAL_VERDICT", "direct target independent terminal review")
    need(production_review["status"] == "PASS_SCOPED_SOURCE_GROUPING_AND_SAVED_STATISTICS_NO_NUMERICAL_VERDICT", "actual WRF join independent review")
    tracked_source = next(x for x in source_manifest["tracked_files"] if x["path"] == "WRF/phys/module_ra_rrtmgp.F")
    need(tracked_source["sha256"] == entries["production-join/actual-module-ra-rrtmgp.F.gz"]["uncompressed_sha256"], "actual WRF source identity pin")
    wrf_dims, wrf_values = packet(decoded["production-join/wrf-normal-n2-absent.result.gz"].decode("ascii"), True)
    need(wrf_dims.get("GAS_COL_DRY") == (1, 45, 1) and wrf_dims.get("GAS_TAU_RAW") == (1, 45, 128) and wrf_dims.get("GAS_TAU") == (1, 45, 128), "actual WRF target result shapes")
    for sec in ("GAS_TAU_RAW", "GAS_TAU"):
        parsed = nested_layer_gpt(wrf_values[sec], 45, 128)
        joined = production_result["tau"][sec]["all45"]["target_tau"]
        constructed = production_result["tau"][sec]["all45"]["candidate_tau"]
        need(close_json_numbers(constructed, case["tau_point"]), f"normal construction-to-production candidate join {sec}")
        need(close_json_numbers(parsed, joined), f"actual WRF packet/result join {sec}")
        native = production_result["tau"][sec]["native32"]["summary"]
        extension = production_result["tau"][sec]["extension13"]["summary"]
        need(native["max_absolute_ordered_ulp_delta"] == 6 and extension["max_absolute_ordered_ulp_delta"] == 0, f"actual WRF measured native/extension delta {sec}")
        need(native["numerical_gate"] == extension["numerical_gate"] == "NONE_DIAGNOSTIC_ONLY", f"actual WRF descriptive-only scope {sec}")
        summ = production_summary["actual_wrf"]["tau_raw" if sec.endswith("RAW") else "tau"][sec]
        need(summ["native_32"] == native and summ["pressure_extension_13"] == extension, f"actual WRF summary consistency {sec}")
    need(production_result["dry"]["summary"]["numerical_gate"] == "NONE_DIAGNOSTIC_ONLY", "actual WRF dry join descriptive-only scope")
    need(close_json_numbers(production_result["dry"]["reconstructed_molecule_cm2"], case["dry_column_molecule_cm2"]), "normal construction-to-production dry candidate join")
    need(close_json_numbers(production_result["dry"]["saved_GAS_COL_DRY_molecule_cm2"], wrf_values["GAS_COL_DRY"]), "actual WRF GAS_COL_DRY packet join")
    need(production_summary["actual_wrf"]["production_dry_mass_expression_audit"]["parenthesized_factored_binary64_vs_saved"]["exact_equal_cells"] == 32, "actual WRF factored dry-mass expression audit")
    print(f"PASS_SAVED_EVIDENCE_ONLY payloads={payload_count} cases=1 layers=45 gpoints=128; authenticated saved dry/tau relationships; no numerical replay")


if __name__ == "__main__":
    main()
