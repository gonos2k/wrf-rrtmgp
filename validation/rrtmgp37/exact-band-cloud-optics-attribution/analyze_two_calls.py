#!/usr/bin/env python3
"""Verify and summarize the frozen exact-two-call SW optics experiment offline."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile

import numpy as np

EXPECTED_SECTIONS = {
    "CLOUD_G", "CLOUD_SSA", "CLOUD_TAU", "CU_CLOUD_G", "CU_CLOUD_SSA", "CU_CLOUD_TAU",
    "CU_DI_USED", "CU_RL_USED", "DIFFUSE", "DIRECT", "DIRECTC", "DIRECTC_PREDELTA",
    "DIRECT_PREDELTA", "DI_USED", "DN", "DNC", "DS_USED", "FROZEN_G", "FROZEN_SSA",
    "FROZEN_TAU", "GAS_COL_DRY", "GAS_G", "GAS_SSA", "GAS_TAU", "GRAUPEL_TAU_EXT",
    "GRAUPEL_TAU_SCA", "GRAUPEL_TAU_SCA_G", "HAIL_TAU_EXT", "HAIL_TAU_SCA", "HAIL_TAU_SCA_G",
    "HR", "HRC", "MASK", "NATIVE_CLOUD_G", "NATIVE_CLOUD_SSA", "NATIVE_CLOUD_TAU", "NIRDIF",
    "NIRDIR", "NIRDIR_PREDELTA", "PRECIP_G", "PRECIP_SSA", "PRECIP_TAU", "PREPARED_G",
    "PREPARED_SSA", "PREPARED_TAU", "RL_USED", "TOTAL_G", "TOTAL_SSA", "TOTAL_TAU", "UP",
    "UPC", "VISDIF", "VISDIR", "VISDIR_PREDELTA",
}
EXPECTED_CHANGED = {
    "DIFFUSE", "DIRECT", "DN", "HR", "NIRDIF", "NIRDIR", "PREPARED_G", "PREPARED_SSA",
    "PREPARED_TAU", "TOTAL_G", "TOTAL_SSA", "TOTAL_TAU", "UP", "VISDIF", "VISDIR",
}
HELD_DIAGNOSTICS = {
    "GAS_COL_DRY", "GAS_G", "GAS_SSA", "GAS_TAU", "CLOUD_G", "CLOUD_SSA", "CLOUD_TAU",
    "NATIVE_CLOUD_G", "NATIVE_CLOUD_SSA", "NATIVE_CLOUD_TAU", "CU_CLOUD_G", "CU_CLOUD_SSA",
    "CU_CLOUD_TAU", "PRECIP_G", "PRECIP_SSA", "PRECIP_TAU", "FROZEN_G", "FROZEN_SSA",
    "FROZEN_TAU", "GRAUPEL_TAU_EXT", "GRAUPEL_TAU_SCA", "GRAUPEL_TAU_SCA_G", "HAIL_TAU_EXT",
    "HAIL_TAU_SCA", "HAIL_TAU_SCA_G", "MASK", "RL_USED", "DI_USED", "DS_USED", "CU_RL_USED",
    "CU_DI_USED", "DIRECT_PREDELTA", "DIRECTC_PREDELTA", "VISDIR_PREDELTA", "NIRDIR_PREDELTA",
    "DIRECTC", "DNC", "UPC", "HRC",
}


def sha(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        while b := f.read(1 << 20):
            h.update(b); n += len(b)
    return h.hexdigest(), n


def bytes_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bits_equal(a: np.ndarray, b: np.ndarray) -> bool:
    aa = np.asarray(a, dtype=np.float64)
    bb = np.asarray(b, dtype=np.float64)
    return aa.shape == bb.shape and np.array_equal(aa.view(np.uint64), bb.view(np.uint64))


def read_override(path: Path) -> dict[str, np.ndarray]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0] != "WRF_SW_OPTICS_OVERRIDE_V1":
        raise ValueError(f"invalid override header: {path}")
    nc, nl, nb = map(int, lines[1].split())
    expected = {"BAND_LIMITS": (2, nb), "TAU": (nc, nl, nb),
                "SSA": (nc, nl, nb), "ASYM": (nc, nl, nb)}
    out: dict[str, np.ndarray] = {}
    idx = 2
    for name, shape in expected.items():
        if idx >= len(lines): raise ValueError(f"missing section {name}")
        header = lines[idx].split(); idx += 1
        if not header or header[0] != name or tuple(map(int, header[1:])) != shape:
            raise ValueError(f"bad {name} dimensions/header")
        count = math.prod(shape); vals: list[float] = []
        while len(vals) < count and idx < len(lines):
            vals.extend(float(x.replace("D", "E")) for x in lines[idx].split()); idx += 1
        if len(vals) != count: raise ValueError(f"bad {name} payload length")
        out[name] = np.asarray(vals, dtype=np.float64).reshape(shape, order="F")
    if idx != len(lines): raise ValueError("trailing data in override")
    return out


def load_result_reader(repo: Path):
    p = repo / "WRF/test/rrtmgp/compare_column_replay.py"
    spec = importlib.util.spec_from_file_location("comparison_reader", p)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load result reader: {p}")
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    return mod


def load_export_reader(path: Path):
    spec = importlib.util.spec_from_file_location("export_reader", path)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load export reader: {path}")
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    return mod


def result_record(path: Path, reader) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    return reader.read_result(path), raw


def float_metrics(delta: np.ndarray) -> dict:
    d = np.asarray(delta, dtype=np.float64)
    flat = np.abs(d).ravel()
    idx = np.unravel_index(int(np.argmax(np.abs(d))), d.shape)
    return {"max_abs": float(flat.max()), "max_abs_index_zero_based": list(map(int, idx)),
            "mean_signed": float(d.mean()), "rms": float(np.sqrt(np.mean(d * d)))}


def verify_package_manifest(root: Path) -> dict | None:
    path = root / "package-manifest.json"
    if not path.exists():
        return None
    manifest = json.loads(path.read_text())
    expected = {entry["path"]: entry for entry in manifest.get("files", [])}
    actual_paths = {p.relative_to(root).as_posix() for p in root.rglob("*")
                    if p.is_file() and p != path and "__pycache__" not in p.parts}
    if actual_paths != set(expected):
        raise SystemExit(f"package manifest roster mismatch; missing={sorted(set(expected)-actual_paths)} extra={sorted(actual_paths-set(expected))}")
    for rel, entry in expected.items():
        got_sha, got_size = sha(root / rel)
        if got_sha != entry.get("sha256") or got_size != entry.get("size_bytes"):
            raise SystemExit(f"package manifest pin mismatch: {rel}")
    return {"file_count": len(expected), "manifest_sha256": sha(path)[0]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--write", action="store_true", help="write report.json and profile CSVs")
    args = ap.parse_args()
    root = args.package.resolve()
    package_manifest = verify_package_manifest(root)
    worktree = root.parents[4]
    plan = json.loads((root / "runtime/receipts/pre-run-plan-not-run-snapshot.json").read_text())
    runtime_receipt = json.loads((root / "runtime/receipts/two-call-execution.json").read_text())
    if runtime_receipt.get("status") != "TWO_CALLS_VALIDATED":
        raise SystemExit("runtime receipt is not TWO_CALLS_VALIDATED")
    if runtime_receipt.get("solver_invocations") != 2 or runtime_receipt.get("model_invocations") != 0:
        raise SystemExit("expected two standalone solver calls and zero WRF model calls")
    runtime_plan = root / "runtime/receipts/runtime-plan.json"
    runtime_runner = root / "runtime/receipts/run_two.py"
    if bytes_sha(runtime_plan.read_bytes()) != runtime_receipt.get("plan_sha256"):
        raise SystemExit("runtime plan hash does not match the execution receipt")
    if bytes_sha(runtime_runner.read_bytes()) != runtime_receipt.get("runner_sha256"):
        raise SystemExit("runtime runner hash does not match the execution receipt")
    if runtime_receipt.get("final_pins_match_initial") is not True:
        raise SystemExit("runtime immutable pin check did not pass")
    review = json.loads((root / "frozen/runtime-terminal-independent-review.json").read_text())
    if review.get("status") != "PASS_SCOPED_EXACT_TWO_CALLS_HYBRID_ATTRIBUTION" or review.get("reviewer_numerical_invocations") != 0:
        raise SystemExit("independent terminal review is missing or has an unexpected status")
    tool_receipt = json.loads((root / "runtime/receipts/root-tool-terminal-receipt-v1.json").read_text())
    if tool_receipt.get("actual_terminal_returncode") != 0 or tool_receipt.get("solver_invocations") != 2 or tool_receipt.get("wrf_forecast_invocations") != 0:
        raise SystemExit("root terminal tool receipt does not attest exactly two standalone calls and zero WRF forecasts")
    calls = runtime_receipt.get("calls", [])
    if len(calls) != 2 or [c.get("case_id") for c in calls] != ["control-full-prepared", "legacy-exact-band-k30-32"]:
        raise SystemExit("unexpected runtime call roster/order")
    if any(c.get("returncode") != 0 or c.get("timed_out") for c in calls):
        raise SystemExit("runtime call did not complete successfully")
    if any(not c.get("pid") for c in calls):
        raise SystemExit("runtime call is missing its PID")

    # Recheck the package-relative input references and copied prepared assets.
    # External source/table/executable hashes remain provenance metadata and are
    # intentionally not required to exist in a consumer's checkout.
    preparation = json.loads((root / "preparation-v4/plan-inputs.json").read_text())
    for name, item in plan["reused_evidence"].items():
        asset = (root / item["path"]).resolve()
        if not asset.is_file(): raise SystemExit(f"missing reused package input {name}: {asset}")
        actual_hash, actual_size = sha(asset)
        if actual_hash != item["sha256"] or actual_size != item["size_bytes"]:
            raise SystemExit(f"reused package input changed: {name}")
    for name, item in plan["prepared_assets"].items():
        asset = root / item["path"]
        actual_hash, actual_size = sha(asset)
        if actual_hash != item["sha256"] or ("size_bytes" in item and actual_size != item["size_bytes"]):
            raise SystemExit(f"prepared package asset changed: {name}")

    # Revalidate copied outputs against terminal receipt pins and baseline identity.
    outputs = {}
    raw_outputs = {}
    for cid, filename in (("control-full-prepared", "control-full-prepared.result.gz"),
                           ("legacy-exact-band-k30-32", "legacy-exact-band-k30-32.result.gz")):
        p = root / "runtime/outputs" / filename
        gzbytes = p.read_bytes()
        raw = gzip.decompress(gzbytes)
        c = next(x for x in calls if x["case_id"] == cid)
        pin = c.get("output_pin", {})
        if bytes_sha(raw) != pin.get("sha256") or len(raw) != pin.get("size_bytes"):
            raise SystemExit(f"output does not match execution receipt: {cid}")
        outputs[cid] = raw; raw_outputs[cid] = gzipbytes_sha = bytes_sha(gzbytes)
        logname = f"{cid}.log.gz"
        log_gz = (root / "runtime/logs" / logname).read_bytes()
        log_raw = gzip.decompress(log_gz)
        log_pin = c.get("log_pin", {})
        if bytes_sha(log_raw) != log_pin.get("sha256") or len(log_raw) != log_pin.get("size_bytes"):
            raise SystemExit(f"log does not match execution receipt: {cid}")
    baseline_gz = (root / plan["reused_evidence"]["baseline_result_gzip"]["path"]).read_bytes()
    baseline = gzip.decompress(baseline_gz)
    if bytes_sha(baseline) != plan["reused_evidence"]["baseline_result_gzip"]["decompressed_sha256"]:
        raise SystemExit("reused baseline decompressed pin mismatch")
    if outputs["control-full-prepared"] != baseline:
        raise SystemExit("identity-control output is not byte-identical to retained baseline")

    result_reader = load_result_reader(worktree)
    with tempfile.TemporaryDirectory(prefix="exact-band-compare-") as tmp:
        tmp = Path(tmp)
        parsed = {}
        for cid, raw in outputs.items():
            p = tmp / f"{cid}.result"; p.write_bytes(raw)
            parsed[cid] = result_reader.read_result(p)
        baseline_path = tmp / "baseline.result"; baseline_path.write_bytes(baseline)
        baseline_parsed = result_reader.read_result(baseline_path)

        control = parsed["control-full-prepared"]; variant = parsed["legacy-exact-band-k30-32"]
        for name, result in (("baseline", baseline_parsed), ("control", control), ("variant", variant)):
            if (result.get("phase"), result.get("nc"), result.get("nl")) != ("SW", 1, 45):
                raise SystemExit(f"unexpected phase/dimensions in {name}")
            if set(result["sections"]) != EXPECTED_SECTIONS:
                raise SystemExit(f"SW result section roster mismatch in {name}")
            for key, arr in result["sections"].items():
                if not np.all(np.isfinite(np.asarray(arr, dtype=np.float64))):
                    raise SystemExit(f"nonfinite {name} section {key}")
        bsec = baseline_parsed["sections"]; csec = control["sections"]; vsec = variant["sections"]
        if any(not bits_equal(bsec[k], csec[k]) for k in EXPECTED_SECTIONS):
            raise SystemExit("identity-control section mismatch despite whole-file gate")
        changed = {k for k in EXPECTED_SECTIONS if not bits_equal(csec[k], vsec[k])}
        if changed != EXPECTED_CHANGED:
            raise SystemExit(f"unexpected changed result sections: {sorted(changed)}")
        if not HELD_DIAGNOSTICS <= (EXPECTED_SECTIONS - changed):
            raise SystemExit("expected held diagnostics are not in the held output set")

        # Verify PREPARED arrays match the serialized variant and are altered only in
        # the 36 approved band/layer cells. Band and g-point maps come from frozen v4.
        prep = preparation
        matches = prep["band_contract"]["exact_matches"]
        gp_bounds = prep["band_contract"]["gas_table_gpoint_bounds_1based_inclusive"]
        if len(matches) != 12 or len(prep["eligibility"]["metrics"]) != 36:
            raise SystemExit("frozen preparation plan does not declare 12×3 eligible cells")
        swap = read_override(root / "preparation-v4/inputs/sw-optics-legacy-exact-band-k30-32.optics")
        base_override = read_override(root / "preparation-v4/inputs/sw-optics-control-full-prepared.optics")
        for field, result_field in (("TAU", "PREPARED_TAU"), ("SSA", "PREPARED_SSA"), ("ASYM", "PREPARED_G")):
            if not bits_equal(vsec[result_field], swap[field]): raise SystemExit(f"variant {result_field} does not match override")
            if not bits_equal(csec[result_field], base_override[field]): raise SystemExit(f"control {result_field} does not match identity override")
            a = np.asarray(csec[result_field]); z = np.asarray(vsec[result_field])
            changed_coords = set(map(tuple, np.argwhere(a.view(np.uint64) != z.view(np.uint64))))
            allowed = {(0, layer - 1, int(m["gp_band_1based"]) - 1) for m in prep["eligibility"]["metrics"] for layer in [m["native_layer_1based"]]}
            if changed_coords != allowed:
                raise SystemExit(f"{result_field} changed support is not exactly the declared 36 cells")
        allowed_gpts = set()
        for m in prep["eligibility"]["metrics"]:
            lo, hi = m["gp_gpoint_bounds_1based_inclusive"][:2]
            layer = m["native_layer_1based"] - 1
            for gp in range(lo - 1, hi): allowed_gpts.add((0, layer, gp))
        for field in ("TOTAL_TAU", "TOTAL_SSA", "TOTAL_G"):
            a = np.asarray(csec[field]); z = np.asarray(vsec[field])
            support = set(map(tuple, np.argwhere(a.view(np.uint64) != z.view(np.uint64))))
            if not support <= allowed_gpts:
                raise SystemExit(f"{field} changed outside the targeted native band/gpoint support")

        # Parse legacy export and produce a layer profile that labels native44 vs engine extension.
        export_path = root / plan["reused_evidence"]["sw_export"]["path"]
        export_reader = load_export_reader(root.parent / "rrtmg4-same-call-attribution/parser/read_export.py")
        with tempfile.TemporaryDirectory(prefix="exact-band-export-") as td:
            txt = Path(td) / "export.txt"; txt.write_bytes(gzip.decompress(export_path.read_bytes()))
            export = export_reader.read_export(txt, expected_phase="SW")
        legacy_hr = np.asarray(export["fields"]["RESULT", "HEATING"].values, dtype=np.float64).reshape(-1)
        base_hr = np.asarray(csec["HR"], dtype=np.float64).reshape(-1)
        variant_hr = np.asarray(vsec["HR"], dtype=np.float64).reshape(-1)
        if legacy_hr.shape != (45,) or base_hr.shape != (45,) or variant_hr.shape != (45,):
            raise SystemExit("expected 45-layer engine/legacy heating profiles")

        # Build portable report and profile tables.
        hr_rows = []
        for idx in range(45):
            hr_rows.append({"layer_1based": idx + 1, "native44": idx < 44,
                            "legacy4_hr_k_day": float(legacy_hr[idx]),
                            "control_hr_k_day": float(base_hr[idx]),
                            "variant_hr_k_day": float(variant_hr[idx]),
                            "control_abs_gap_to_legacy": float(abs(base_hr[idx] - legacy_hr[idx])),
                            "variant_abs_gap_to_legacy": float(abs(variant_hr[idx] - legacy_hr[idx]))})
        flux_rows = []
        for idx in range(46):
            flux_rows.append({"interface_index_bottom_first_0based": idx,
                              "native_interface": idx <= 44,
                              **{f"{key}_{arm}": float((csec if arm == "control" else vsec)[key][0, idx, 0])
                                 for key in ("DN", "UP", "DIRECT", "DIFFUSE", "DNC", "UPC", "DIRECTC")
                                 for arm in ("control", "variant")}})
        optics_rows = []
        for metric in prep["eligibility"]["metrics"]:
            k = int(metric["native_layer_1based"]) - 1
            band = int(metric["gp_band_1based"]) - 1
            row = {"native_layer_1based": k + 1, "gp_band_1based": band + 1,
                   "legacy_band_1based": int(metric["legacy_band_1based"]),
                   "legacy_band_code": int(metric["legacy_band_code"]),
                   "wavenumber_lo_cm-1": float(metric["bounds_cm-1"][0]),
                   "wavenumber_hi_cm-1": float(metric["bounds_cm-1"][1]),
                   "legacy_gpoint_count": int(metric["legacy_gpoint_count"]),
                   "gp_gpoint_count": int(metric["gp_gpoint_count"])}
            for suffix, sec in (("tau", "PREPARED_TAU"), ("ssa", "PREPARED_SSA"), ("asym", "PREPARED_G")):
                row[f"legacy_{suffix}"] = float(metric["legacy_values"][{"tau":"TAU","ssa":"SSA","asym":"ASYM"}[suffix]])
                row[f"control_prepared_{suffix}"] = float(csec[sec][0, k, band])
                row[f"variant_prepared_{suffix}"] = float(vsec[sec][0, k, band])
            optics_rows.append(row)
        diffs = {key: (np.asarray(vsec[key], dtype=np.float64) - np.asarray(csec[key], dtype=np.float64))
                 for key in EXPECTED_CHANGED}
        max_moment = {}
        for label, get in (("total_extinction_tau", lambda t, s, g: t),
                           ("total_scattering_tau_times_ssa", lambda t, s, g: t * s),
                           ("total_first_angular_moment_tau_ssa_g", lambda t, s, g: t * s * g)):
            a = get(np.asarray(csec["TOTAL_TAU"]), np.asarray(csec["TOTAL_SSA"]), np.asarray(csec["TOTAL_G"]))
            b = get(np.asarray(vsec["TOTAL_TAU"]), np.asarray(vsec["TOTAL_SSA"]), np.asarray(vsec["TOTAL_G"]))
            max_moment[label] = float(np.max(np.abs(b - a)))
        k31 = 30
        base_gap = abs(float(base_hr[k31] - legacy_hr[k31])); variant_gap = abs(float(variant_hr[k31] - legacy_hr[k31]))
        native_base_gap = np.abs(base_hr[:44] - legacy_hr[:44]); native_var_gap = np.abs(variant_hr[:44] - legacy_hr[:44])
        report = {
            "schema": "udm37-exact-band-cloud-swap-two-call-analysis-v1",
            "status": "PASS_SCOPED_TWO_CALL_OFFLINE_REPLAY",
            "runtime_calls": 2,
            "wrf_model_calls": 0,
            "call_records": [{"case_id": c["case_id"], "pid": int(c["pid"]), "returncode": int(c["returncode"]),
                              "status": c["status"], "timed_out": bool(c["timed_out"])} for c in calls],
            "execution_receipt_sha256": sha(root / "runtime/receipts/two-call-execution.json")[0],
            "independent_terminal_review": {"status": review["status"],
                                             "receipt_sha256": sha(root / "frozen/runtime-terminal-independent-review.json")[0],
                                             "reviewer_numerical_invocations": review["reviewer_numerical_invocations"]},
            "result_hashes": {"control_raw_sha256": bytes_sha(outputs["control-full-prepared"]),
                              "variant_raw_sha256": bytes_sha(outputs["legacy-exact-band-k30-32"]),
                              "control_gzip_sha256": raw_outputs["control-full-prepared"],
                              "variant_gzip_sha256": raw_outputs["legacy-exact-band-k30-32"]},
            "whole_file_identity_control": {"equals_reused_baseline": True,
                                            "baseline_decompressed_sha256": bytes_sha(baseline)},
            "result_contract": {"phase": "SW", "nc": 1, "nl": 45, "section_count": len(EXPECTED_SECTIONS),
                                "changed_sections": sorted(changed), "held_section_count": len(EXPECTED_SECTIONS - changed),
                                "held_components_and_pre_delta_diagnostics_bitwise_equal": True,
                                "clear_flux_and_heating_sections_bitwise_equal": True},
            "prepared_cell_contract": {"exact_band_layer_cells": 36, "property_assignments": 108,
                                       "prepared_tau_ssa_g_changed_support_exact": True,
                                       "total_arrays_changes_confined_to_targeted_gpoints": True,
                                       "unmatched_gp_bands_1_and_2_held": True},
            "heating_comparison_to_legacy_radius4_export": {
                "units": "K day-1", "native_layer_count": 44,
                "layer31_1based": {"legacy4": float(legacy_hr[30]), "control": float(base_hr[30]),
                                   "variant": float(variant_hr[30]), "control_abs_gap": base_gap,
                                   "variant_abs_gap": variant_gap,
                                   "abs_gap_reduction_percent": 100.0 * (base_gap - variant_gap) / base_gap},
                "native44_max_abs_gap_control": float(native_base_gap.max()),
                "native44_max_abs_gap_control_layer_1based": int(native_base_gap.argmax()) + 1,
                "native44_max_abs_gap_variant": float(native_var_gap.max()),
                "native44_max_abs_gap_variant_layer_1based": int(native_var_gap.argmax()) + 1,
                "engine_extension_layer45_gap_variant": float(abs(variant_hr[44] - legacy_hr[44])),
                "profile_csv": "results/heating-profile-45-layers.csv"},
            "radiative_fluxes": {
                "surface_interface_index_bottom_first": 0,
                "toa_interface_index_bottom_first": 45,
                "surface_DN_variant_minus_control_W_m2": float(diffs["DN"][0, 0, 0]),
                "toa_UP_variant_minus_control_W_m2": float(diffs["UP"][0, 45, 0]),
                "max_abs_variant_minus_control_by_total_moment": max_moment,
                "profile_csv": "results/flux-profile-46-interfaces.csv"},
            "verified_by_independent_terminal_review": {
                "total_moment_max_abs_residuals": review["total_moment_residuals"],
                "heating_residual_K_day_minus1": review["flux_heating_residual_K_day_minus1"],
                "endpoint_fluxes": review["endpoints"]},
            "optics_profile_csv": "results/selected-optics-36-cells.csv",
            "interpretation": "This is a one-column combined prepared-optics sensitivity. It does not establish physical accuracy, a pure engine/PSD effect, a native-only effect, or a fully consistent direct-beam attribution. The legacy4 comparison is a native-radius observer/counterfactual, not default-RRTMG4 preservation."
        }
    if args.write:
        (root / "results/analysis.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        for filename, rows in (("heating-profile-45-layers.csv", hr_rows),
                               ("flux-profile-46-interfaces.csv", flux_rows),
                               ("selected-optics-36-cells.csv", optics_rows)):
            with (root / "results" / filename).open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
                writer.writeheader(); writer.writerows(rows)
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
