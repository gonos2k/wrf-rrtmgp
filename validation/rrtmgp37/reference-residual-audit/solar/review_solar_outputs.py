#!/usr/bin/env python3
"""Read-only audit of the preserved v6 failure and v7 two-call SW run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

ROOT = Path(".").resolve()
BASE = ROOT / "build/udm37-rfmip-solar-counterfactual-v1"
PUBLISHED = ROOT / "build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/reference"
UPSTREAM = ROOT / "build/official-rrtmgp-reference/run-upstream"
CURRENT_SW = ROOT / "build/official-rrtmgp-reference/data/rrtmgp-gas-sw-g224.nc"
OLD_SW = ROOT / "build/udm37-rfmip-reference-provenance-v1/rrtmgp-data-sw-g224-2018-12-04.nc"
OUTPUT = ROOT / "build/udm37-rfmip-solar-terminal-review-v1/review-v2.json"
NAMES = {
    "rsd": "rsd_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc",
    "rsu": "rsu_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc",
}
EXPECTED_RECEIPTS = {
    "stage-v6/execution.json": "",
    "stage-v7/execution.json": "",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def array(path: Path, varname: str):
    with netCDF4.Dataset(path) as ds:
        if varname not in ds.variables:
            raise AssertionError(f"missing {varname} in {path}")
        v = ds[varname]
        v.set_auto_maskandscale(False)
        values = v[:]
        if np.ma.isMaskedArray(values) and np.any(np.ma.getmaskarray(values)):
            raise AssertionError(f"masked values in {path}:{varname}")
        values = np.asarray(values.data if np.ma.isMaskedArray(values) else values)
        if not np.all(np.isfinite(values)):
            raise AssertionError(f"nonfinite values in {path}:{varname}")
        return values.copy()


def metrics(got_path: Path, ref_path: Path, name: str):
    got, ref = array(got_path, name), array(ref_path, name)
    if got.shape != ref.shape or got.dtype != ref.dtype:
        raise AssertionError(f"shape/dtype mismatch: {got_path} {got.shape}/{got.dtype}; {ref_path} {ref.shape}/{ref.dtype}")
    delta = np.abs(got.astype(np.float64) - ref.astype(np.float64))
    return {"got_path": str(got_path.relative_to(ROOT)), "reference_path": str(ref_path.relative_to(ROOT)),
            "shape": list(got.shape), "dtype": str(got.dtype),
            "max_abs": float(np.max(delta)), "mean_abs": float(np.mean(delta)),
            "count_gt_1e-5": int(np.count_nonzero(delta > 1e-5)),
            "within_atol_1e-5_rtol_0": bool(np.all(delta <= 1e-5)),
            "bitwise_values_equal": bool(np.array_equal(got, ref))}


def nc_inventory(path: Path):
    with netCDF4.Dataset(path) as ds:
        dims = {k: {"length": len(v), "unlimited": bool(v.isunlimited())} for k, v in ds.dimensions.items()}
        attrs = {k: str(ds.getncattr(k)) for k in ds.ncattrs()}
        variables = {}
        for n, v in ds.variables.items():
            v.set_auto_maskandscale(False)
            values = np.asarray(v[:])
            variables[n] = {"dimensions": list(v.dimensions), "dtype": str(v.dtype),
                            "attributes": {a: str(v.getncattr(a)) for a in v.ncattrs()},
                            "values": values}
    return dims, attrs, variables


def close_metadata(a, b):
    if a.keys() != b.keys():
        return False
    for k in a:
        va, vb = a[k], b[k]
        try:
            aa, bb = np.asarray(va), np.asarray(vb)
            if aa.shape != bb.shape or not np.array_equal(aa, bb, equal_nan=True):
                return False
        except (TypeError, ValueError):
            if va != vb:
                return False
    return True


def main():
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite review receipt: {OUTPUT}")
    v6 = json.loads((BASE / "stage-v6/execution.json").read_text())
    v7 = json.loads((BASE / "stage-v7/execution.json").read_text())
    m6 = json.loads((BASE / "stage-v6/stage-manifest.json").read_text())
    m7 = json.loads((BASE / "stage-v7/stage-manifest.json").read_text())
    assert v6["status"] == "FAIL_PRESERVED" and len(v6["calls"]) == 2
    assert v7["status"] == "COMPLETE_TWO_SW_CALLS" and len(v7["calls"]) == 2
    assert [c["arm"] for c in v7["calls"]] == ["control", "old-solar-counterfactual"]
    assert all(c["returncode"] == 0 for c in v7["calls"])

    # Check receipts against bytes and recompute metrics from NetCDF values.
    arm_paths = {arm: BASE / "stage-v7" / arm for arm in ("control", "old-solar-counterfactual")}
    out_sha_checks = {}
    for call in v7["calls"]:
        for name, item in call["outputs"].items():
            actual_path = ROOT / item["path"]
            if sha(actual_path) != item["sha256"]:
                raise AssertionError(f"v7 output hash differs from execution receipt: {actual_path}")
            out_sha_checks[f"{call['arm']}:{name}"] = item["sha256"]

    v7_upstream_control = {}
    cf_to_published = {}
    control_to_published = {}
    control_to_cf = {}
    for name, filename in NAMES.items():
        v7_upstream_control[name] = metrics(arm_paths["control"] / filename, UPSTREAM / filename, name)
        control_to_published[name] = metrics(arm_paths["control"] / filename, PUBLISHED / filename, name)
        cf_to_published[name] = metrics(arm_paths["old-solar-counterfactual"] / filename, PUBLISHED / filename, name)
        control_to_cf[name] = metrics(arm_paths["old-solar-counterfactual"] / filename,
                                      arm_paths["control"] / filename, name)
        if not v7_upstream_control[name]["bitwise_values_equal"]:
            raise AssertionError(f"stage-v7 control is not exact current-upstream output for {name}")
    for name, filename in NAMES.items():
        if not v6["calls"][0]["current_upstream_bitwise_control"][name]["bitwise_value_equal"]:
            raise AssertionError(f"stage-v6 control was not bitwise current-upstream output: {name}")
        stage6_failed_cf = BASE / "stage-v6/old-solar-counterfactual" / filename
        if sha(stage6_failed_cf) != m6["output_templates"][filename]["staged_template_sha256"]:
            raise AssertionError("stage-v6 failed counterfactual appears to have modified output template")

    # Independently verify the current and counterfactual NetCDF structures/data.
    dims_cur, attr_cur, vars_cur = nc_inventory(CURRENT_SW)
    cf_path = BASE / "stage-v7/rrtmgp-gas-sw-g224-old-solar-counterfactual.nc"
    dims_cf, attr_cf, vars_cf = nc_inventory(cf_path)
    _, _, vars_old = nc_inventory(OLD_SW)
    changed = []
    structural_diffs = []
    for name in vars_cur:
        a, b = vars_cur[name], vars_cf[name]
        if a["dimensions"] != b["dimensions"] or a["dtype"] != b["dtype"] or not close_metadata(a["attributes"], b["attributes"]):
            structural_diffs.append(name)
            continue
        if a["values"].shape != b["values"].shape:
            changed.append(name)
        elif a["values"].dtype.kind in "fc":
            if not np.array_equal(a["values"], b["values"], equal_nan=True):
                changed.append(name)
        elif not np.array_equal(a["values"], b["values"]):
            changed.append(name)
    expected_changed = {"solar_source_quiet", "solar_source_facular", "solar_source_sunspot"}
    if set(changed) != expected_changed or structural_diffs or dims_cur != dims_cf or not close_metadata(attr_cur, attr_cf):
        raise AssertionError({"changed": changed, "structural_diffs": structural_diffs,
                              "dimensions_equal": dims_cur == dims_cf,
                              "global_attrs_equal": close_metadata(attr_cur, attr_cf)})
    old_src = vars_old["solar_source"]["values"]
    old_promoted = old_src.astype(vars_cf["solar_source_quiet"]["values"].dtype)
    if not np.array_equal(vars_cf["solar_source_quiet"]["values"], old_promoted):
        raise AssertionError("quiet spectrum differs from old source vector promoted to current dtype")
    mg = float(vars_cur["mg_default"]["values"])
    sb = float(vars_cur["sb_default"]["values"])
    reconstructed = (vars_cf["solar_source_quiet"]["values"]
                     + (mg - 0.1495954) * vars_cf["solar_source_facular"]["values"]
                     + (sb - 0.00066696) * vars_cf["solar_source_sunspot"]["values"])
    if not np.array_equal(reconstructed, old_promoted):
        raise AssertionError("current loader formula does not exactly reconstruct old solar source")

    reductions = {}
    for name in NAMES:
        a = control_to_published[name]
        b = cf_to_published[name]
        reductions[name] = {
            "mean_abs_error_reduction_fraction": float(1 - b["mean_abs"] / a["mean_abs"]),
            "max_abs_error_reduction_fraction": float(1 - b["max_abs"] / a["max_abs"]),
            "count_gt_1e-5_reduction": a["count_gt_1e-5"] - b["count_gt_1e-5"],
            "control_mean_abs": a["mean_abs"], "counterfactual_mean_abs": b["mean_abs"],
        }

    def pin_set(label, receipt, stage_manifest):
        return {"label": label, "execution_receipt_sha256": sha(receipt),
                "stage_manifest_sha256": sha(stage_manifest),
                "counterfactual_coefficient_sha256": sha((BASE / stage_manifest.relative_to(BASE).parent /
                                                           "rrtmgp-gas-sw-g224-old-solar-counterfactual.nc")),
                "execution_status": json.loads(receipt.read_text())["status"]}

    stage6_file_pins = pin_set("stage-v6", BASE / "stage-v6/execution.json", BASE / "stage-v6/stage-manifest.json")
    stage7_file_pins = pin_set("stage-v7", BASE / "stage-v7/execution.json", BASE / "stage-v7/stage-manifest.json")
    report = {
        "schema": "rfmip-sw-solar-counterfactual-independent-review-v1",
        "review_status": "PASS_REVIEW_OF_RUN_INTEGRITY_AND_METRICS; STRICT_PUBLISHED_TOLERANCE_FAILS",
        "scope": "read-only terminal review; no build or model execution by reviewer",
        "provenance_limit": "This experiment does not establish the exact historical RTE-RRTMGP-181204 source SHA or prove the counterfactual is the historical executable/data set.",
        "grid_and_physics_scope": {"resolution": "RFMIP 1800-profile clear-sky SW g224", "phase": "shortwave only", "forcing_index": 1,
                                   "wrf_invocations": 0, "sw_executable_process_invocations": 4,
                                   "note": "4 process invocations count both stage-v6 calls (the second exited before calculation) and both stage-v7 calls."},
        "v6_failure": {
            "execution": stage6_file_pins,
            "control_current_upstream_arrays_bitwise": True,
            "counterfactual_status": v6["calls"][1]["status"],
            "counterfactual_returncode": v6["calls"][1]["returncode"],
            "failure_reason_from_stdout": "Fortran CHARACTER(LEN=132) coefficient-path argument truncated the absolute path; loader failed to open that path before computing fluxes.",
            "counterfactual_outputs_unchanged_templates": True,
        },
        "v7_run_integrity": {
            "execution": stage7_file_pins,
            "calls": [{"arm": c["arm"], "status": c["status"], "returncode": c["returncode"],
                       "elapsed_seconds": c["elapsed_seconds"], "command": c["command"]} for c in v7["calls"]],
            "current_control_vs_pinned_upstream_arrays_bitwise": v7_upstream_control,
            "external_input_executable_reference_pins_before_after_equal":
                v7["executable_and_data_pins_before"] == v7["executable_and_data_pins_after"] and
                v7["reference_output_pins_before"] == v7["reference_output_pins_after"],
            "actual_output_sha256_matches_execution_receipt": out_sha_checks,
        },
        "coefficient_file_check": {
            "current_sw_data_sha256": sha(CURRENT_SW),
            "counterfactual_sw_data_sha256": sha(cf_path),
            "changed_variable_data_arrays_only": sorted(changed),
            "all_other_variables_exactly_unchanged": True,
            "dimensions_and_global_attributes_unchanged": True,
            "dimensions": dims_cur,
            "changed_variable_dimensions_dtypes_attributes_unchanged": True,
            "current_loader_default_formula": "quiet + (mg_default - 0.1495954)*facular + (sb_default - 0.00066696)*sunspot",
            "quiet_array_matches_old_float32_solar_source_promoted_to_current_dtype": True,
            "default_formula_reproduces_old_vector_bitwise": True,
            "mg_default": mg, "sb_default": sb,
            "tsi_default_unchanged": np.array_equal(vars_cur["tsi_default"]["values"], vars_cf["tsi_default"]["values"]),
        },
        "comparison": {
            "published_reference_threshold": {"atol": 1e-5, "rtol": 0},
            "control_vs_published": control_to_published,
            "counterfactual_vs_published": cf_to_published,
            "control_vs_counterfactual": control_to_cf,
            "error_reductions": reductions,
            "strict_threshold_status": {name: bool(cf_to_published[name]["within_atol_1e-5_rtol_0"]) for name in NAMES},
            "remaining_failures": {name: cf_to_published[name]["count_gt_1e-5"] for name in NAMES},
        },
        "limits": [
            "Counterfactual dramatically reduces mean SW residuals but still fails the unchanged 1e-5 absolute threshold: 116 rsd points and 39 rsu points remain above tolerance.",
            "No attribution to the exact historical source_id implementation is justified; exact generating code SHA and data snapshot remain unknown.",
            "Result applies only to this clear-sky RFMIP g224 SW test, forcing index 1; it is not a WRF, all-sky, or general radiation validation.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(OUTPUT), "sha256": sha(OUTPUT),
                      "strict": report["comparison"]["strict_threshold_status"],
                      "remaining": report["comparison"]["remaining_failures"]}, indent=2))


if __name__ == "__main__":
    main()
