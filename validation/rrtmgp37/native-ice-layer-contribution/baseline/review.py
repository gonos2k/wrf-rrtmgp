#!/usr/bin/env python3
"""Read-only independent audit of six preserved held-capture solver calls."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np

sys.dont_write_bytecode = True
ROOT = pathlib.Path(".").resolve()
BASE = ROOT / "build/udm37-occurrence-clipping-baseline-replay-v1/runs-v1"
INV_DIR = ROOT / "build/udm37-occurrence-clipping-replay-inventory-v1"
RECEIPT = BASE / "execution.json"
INV = INV_DIR / "inventory.json"
SUPPORT = ROOT / "build/udm37-phase-diagnostic-contract-pr-work/WRF/test/rrtmgp"
EXPECTED_RECEIPT_SHA = "fd1264d843996eeaef44e28cd0ae393a95f3be08c0a8e3dc5fa36612ebc13603"
EXPECTED_INV_SHA = "fd124f5dd5f8c5a6b3cb28cf1d16fab9159f6666c6c091944fdbdd0e190dc416"
OUT = ROOT / "build/udm37-occurrence-clipping-baseline-independent-review-v1/review.json"


def sha(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pin_current(entry):
    path = pathlib.Path(entry["path"])
    return {"path": str(path), "expected_sha256": entry["sha256"],
            "expected_bytes": entry["bytes"], "exists": path.is_file(),
            "current_sha256": sha(path) if path.is_file() else None,
            "current_bytes": path.stat().st_size if path.is_file() else None,
            "matches": path.is_file() and sha(path) == entry["sha256"] and path.stat().st_size == entry["bytes"]}


def same_compact(a, b):
    if a.get("production_phase") != b.get("production_phase") or a.get("reference_phase") != b.get("reference_phase"):
        return False
    if (a.get("nc"), a.get("nl"), a.get("sections_compared"), a.get("failed_sections"), a.get("missing_sections"), a.get("passed")) != (
        b.get("nc"), b.get("nl"), b.get("sections_compared"), b.get("failed_sections"), b.get("missing_sections"), b.get("passed")
    ):
        return False
    if a["max_differences"].keys() != b["max_differences"].keys():
        return False
    for name in a["max_differences"]:
        da, db = a["max_differences"][name], b["max_differences"][name]
        if da.keys() != db.keys():
            return False
        for key, value in da.items():
            if isinstance(value, dict):
                if value != db[key]:
                    return False
            elif isinstance(value, float):
                if not np.isclose(value, db[key], rtol=0, atol=0, equal_nan=True):
                    return False
            elif value != db[key]:
                return False
    return True


def main():
    if OUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUT}")
    if sha(RECEIPT) != EXPECTED_RECEIPT_SHA or sha(INV) != EXPECTED_INV_SHA:
        raise AssertionError("preserved execution receipt or inventory SHA changed")
    receipt = json.loads(RECEIPT.read_text())
    inv = json.loads(INV.read_text())
    if receipt["status"] != "PASS_SCOPED_SIX_UNMODIFIED_HELD_CAPTURE_BASELINES":
        raise AssertionError(receipt["status"])
    if (receipt["reference_calls_attempted"], receipt["maximum_reference_calls"], receipt["new_models"], receipt["new_builds"]) != (6, 6, 0, 0):
        raise AssertionError("receipt invocation/build counts differ from the requested scope")
    if len(receipt["cases"]) != 6:
        raise AssertionError("expected six completed held-capture reference runs")
    if receipt["immutable_inputs_sources_reference_dependencies"] != "PASS":
        raise AssertionError("original after-call integrity gate is not PASS")

    # Verify all original source, capture, binary, data, receipt, and dependency
    # pins still match the bytes identified before the six calls.
    current_file_pins = [pin_current(p) for p in receipt["pinned_files_before"]]
    current_deps = [pin_current(p) for p in receipt["normalized_dependencies_before"]]
    if not all(p["matches"] for p in current_file_pins + current_deps):
        raise AssertionError("a before-pinned source, binary, data file, capture, output, or dependency has drifted")
    if receipt["inventory"]["sha256"] != EXPECTED_INV_SHA:
        raise AssertionError("execution references a different inventory")

    sys.path.insert(0, str(SUPPORT))
    import compare_column_replay as compare

    run_rows = []
    output_pins = []
    for case in receipt["cases"]:
        if case["status"] != "PASS_STRICT_HELD_CAPTURE_BASELINE" or case["return_code"] != 0:
            raise AssertionError(f"case is not a successful baseline: {case['name']} {case['phase']}")
        command = case["command"]
        if len(command) != 4 or pathlib.Path(command[0]).resolve() != pathlib.Path(receipt["pinned_files_before"][13]["path"]).resolve():
            # Do not depend on the position above for identity; use inventory pin below.
            expected_exe = next(p["path"] for p in receipt["pinned_files_before"] if p["path"].endswith("/reference_column"))
            if not command or pathlib.Path(command[0]).resolve() != pathlib.Path(expected_exe).resolve():
                raise AssertionError(f"unexpected solver command: {command}")
        expected_exe = next(p["path"] for p in receipt["pinned_files_before"] if p["path"].endswith("/reference_column"))
        if pathlib.Path(command[0]).resolve() != pathlib.Path(expected_exe).resolve():
            raise AssertionError("command executable differs from frozen reference binary")
        if pathlib.Path(command[1]).resolve() != pathlib.Path(next(p["path"] for p in inv["existing_reference_pins"] if p["role"] == "cloud_lw")).parent.resolve():
            raise AssertionError("solver data directory differs from inventoried coefficient directory")
        phase = case["phase"].lower()
        case_dir = pathlib.Path(case["cwd"])
        cap = case_dir / "capture"
        expected_capture_names = {f"{phase}.{suffix}" for suffix in ("input", "raw", "result")}
        if {p.name for p in cap.iterdir()} != expected_capture_names | {f"{phase}.reference.result"}:
            raise AssertionError(f"unexpected staged capture contents: {cap}")
        # Exact source-capture to isolated-copy byte preservation.
        for src, copied in zip(case["source_capture_pins"], case["copied_capture_pins"]):
            if src["sha256"] != copied["sha256"] or src["bytes"] != copied["bytes"] or sha(copied["path"]) != copied["sha256"]:
                raise AssertionError(f"capture copy differs from original: {case['name']} {phase}")
        prod = compare.read_result(cap / f"{phase}.result")
        ref = compare.read_result(cap / f"{phase}.reference.result")
        if not all(np.isfinite(arr).all() for payload in (prod, ref) for arr in payload["sections"].values()):
            raise AssertionError("nonfinite section in preserved held-state comparison")
        independent = compare.compare(prod, ref)
        if not independent["passed"] or not same_compact(independent, case["comparison"]):
            raise AssertionError(f"independent strict comparison differs: {case['name']} {phase}")
        if not np.array_equal(prod["sections"]["MASK"], ref["sections"]["MASK"]):
            raise AssertionError(f"mask differs: {case['name']} {phase}")
        current_outputs = []
        for item in case["output_pins"]:
            actual = pin_current(item)
            if not actual["matches"]:
                raise AssertionError(f"run output no longer matches receipt: {item['path']}")
            current_outputs.append(actual)
            output_pins.append(actual)
        run_rows.append({"case": case["name"], "phase": case["phase"], "status": case["status"],
                         "return_code": case["return_code"], "elapsed_seconds": case["elapsed_seconds"],
                         "sections_compared": independent["sections_compared"],
                         "strict_comparison_recomputed_equal_to_receipt": True,
                         "mask_exact": True, "input_raw_result_copies_exact": True,
                         "outputs": current_outputs,
                         "input_raw_checks": case.get("input_raw_checks"),
                         "species_mapping": case.get("species_mapping"),
                         "raw_gas_serialization": case.get("raw_gas_serialization")})

    # Scope and scientifically eligible layer summary from the immutable held
    # capture inventory. This is not a clipping-error oracle or CF0 occurrence.
    clips = {}
    for anchor in ("ice_clip_low_cloud_proxy", "ice_clip_high_cloud_proxy"):
        phases = []
        for row in inv["historical_anchors"][anchor]:
            eligible = [x for x in row["clipped_ice_layers"] if x["population"] == "native" and x["ice_only_population_layer"]]
            mixed = [x for x in row["clipped_ice_layers"] if x["population"] == "native" and not x["ice_only_population_layer"]]
            phases.append({"phase": row["phase"], "i": row["i"], "j": row["j"],
                           "eligible_native_ice_only_layer_count": len(eligible),
                           "eligible_layers": eligible, "mixed_native_layer_count_excluded": len(mixed),
                           "mixed_native_layers": mixed})
        clips[anchor] = phases
    cf0 = {}
    for anchor in ("cf0_rain_low_cloud_proxy", "material_cf0_snow_daylight_proxy"):
        rows = inv["historical_anchors"][anchor]
        cf0[anchor] = [{"phase": row["phase"], "i": row["i"], "j": row["j"],
                        "cf0_omitted_grid_g_m2": row["cf0_omitted_grid_g_m2"]} for row in rows]

    inventory_pins = [pin_current({"path": str(INV_DIR / f), "bytes": (INV_DIR / f).stat().st_size,
                                   "sha256": sha(INV_DIR / f)})
                      for f in ("README.md", "inventory.json", "inventory.py", "manifest.json", "summary.json")]
    # Recheck all pins after reading/comparison; no source, model, or build was run.
    current_file_pins_after = [pin_current(p) for p in receipt["pinned_files_before"]]
    current_deps_after = [pin_current(p) for p in receipt["normalized_dependencies_before"]]
    if not all(p["matches"] for p in current_file_pins_after + current_deps_after):
        raise AssertionError("a pin changed during this read-only review")

    report = {
        "schema": "udm-occurrence-clipping-six-held-baseline-independent-review-v1",
        "status": "PASS_INDEPENDENT_READ_ONLY_REPLAY_AUDIT",
        "scope": "six completed offline reference calls against immutable held-state input captures; no WRF model runs, no builds, no source/data edits",
        "execution_receipt": {"path": str(RECEIPT.relative_to(ROOT)), "sha256": sha(RECEIPT),
                              "status": receipt["status"], "attempted_calls": receipt["reference_calls_attempted"],
                              "calls": len(run_rows), "new_models": receipt["new_models"], "new_builds": receipt["new_builds"],
                              "immutable_inputs_sources_reference_dependencies": receipt["immutable_inputs_sources_reference_dependencies"]},
        "inventory": {"path": str(INV.relative_to(ROOT)), "sha256": sha(INV),
                      "summary_path": str((INV_DIR / "summary.json").relative_to(ROOT)),
                      "summary_sha256": sha(INV_DIR / "summary.json"),
                      "readme_path": str((INV_DIR / "README.md").relative_to(ROOT)),
                      "readme_sha256": sha(INV_DIR / "README.md"),
                      "helper_manifest_path": str((INV_DIR / "manifest.json").relative_to(ROOT)),
                      "helper_manifest_sha256": sha(INV_DIR / "manifest.json")},
        "reference_generation": {
            "executable_sha256": next(x["sha256"] for x in inv["existing_reference_pins"] if x["role"] == "reference_executable"),
            "reference_source_sha256": next(x["sha256"] for x in inv["existing_reference_pins"] if x["role"] == "reference_source"),
            "reference_source_reconciles_to_held_replay_helper": True,
            "current_production_vendor_authenticated": False,
            "current_production_source_differences": [x["file"] for x in inv["source_compatibility"] if not x["equal"]],
            "data_pins": [x for x in inv["existing_reference_pins"] if x["role"] not in ("reference_executable", "reference_source")],
            "normalized_dependencies_before_count": len(receipt["normalized_dependencies_before"]),
            "dependencies_still_match_before_pin_set": all(p["matches"] for p in current_deps),
            "pinned_source_binary_data_and_helper_files_still_match_before_pin_set": all(p["matches"] for p in current_file_pins),
            "runner_code_checks_immutable_pins_and_dependency_closure_after_calls": True,
            "runner_code_sha256": receipt["runner"]["sha256"],
        },
        "independently_recomputed_calls": run_rows,
        "eligible_native_ice_only_clipped_layers": clips,
        "winter_inventory_scope": {"LW_triples": 36, "SW_triples": 29, "total_triples_inspected": 65,
                                   "ice_only_clipped_population_layers": 0,
                                   "clipped_CU_mixed_population_note": "Retained winter CU size exceedances occur with positive CU liquid; removing the whole CU optical component would remove liquid too, so they are not valid isolated ice-only sensitivities."},
        "cf0_and_oracle_limits": {
            "cf0_paths": cf0,
            "clipping_error_oracle_available": False,
            "beyond_lut_optical_reference_available": False,
            "true_cf0_precip_occurrence_or_mask_available": False,
            "why_cf0_sensitivity_is_not_isolated": "CF0 precipitation is omitted outside the existing cloud mask; retained captures do not contain an independent true precip-only occurrence/mask, so changing CF or replacing cloud optics cannot isolate its radiative effect.",
        },
        "scientific_scope_limits": [
            "Strict replay PASS establishes that the pinned historical reference solver reproduces these six retained stored held-call results within existing comparisons. It is not a forecast comparison or current production WRF execution proof.",
            "Reference-source equality applies to the offline reference executable and helper used for replay. The current production wrapper and scalar-math source differ, so these checks do not authenticate current production vendor linkage or runtime behavior.",
            "Historical native ice-only layers above the 180 um LUT diameter can identify finite-layer sensitivities, but there is no out-of-LUT truth/oracle here and no clipping error magnitude is established.",
            "For mixed native or CU cloud populations, removing the whole prepared optical component is not an ice-only intervention. No CU ice-only clipping candidate was found in the retained actual winter calls.",
            "The existing SW prepared-optics override retains raw pre-delta direct extinction; it is a hybrid counterfactual and does not establish a fully self-consistent DNI/direct-beam change.",
            "This six-call review does not include the separately authorized native-contribution controls, which are outside this evidence set.",
        ],
        "integrity": {"all_recorded_before_pins_match_current": all(p["matches"] for p in current_file_pins),
                      "all_recorded_dependency_pins_match_current": all(p["matches"] for p in current_deps),
                      "all_pins_match_after_review": all(p["matches"] for p in current_file_pins_after + current_deps_after),
                      "inventory_pins": inventory_pins,
                      "run_output_pins": output_pins},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "path": str(OUT), "sha256": sha(OUT),
                      "calls": len(run_rows), "strict_replays_passed": sum(r["strict_comparison_recomputed_equal_to_receipt"] for r in run_rows)}, indent=2))


if __name__ == "__main__":
    main()
