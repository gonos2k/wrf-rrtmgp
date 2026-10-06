#!/usr/bin/env python3
"""Derive a compact held-fixed ice-optics attribution summary from pinned JSON only."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKTREE = ROOT / "build/udm37-nested-batching-restart-evidence-pr-work"
INPUT = WORKTREE / "validation/rrtmgp37/runtime-contracts/ice-optics-attribution.json"
INPUT_SHA = "e84cf0f6a3b2e1d4167fa260c556249cca413964da3acd69d89008c0b925563a"
HISTORICAL_REPORT = WORKTREE / "validation/rrtmgp37/udm-physics-audit/REPORT_ko.md"
RUNTIME_DOC = WORKTREE / "WRF/doc/rrtmgp/RUNTIME_CONTRACTS.md"
BRIDGE_TEST = WORKTREE / "WRF/test/rrtmgp/test_rrtmg_optics_attribution.py"
HELD_FIXED = ("GAS_TAU", "GAS_SSA", "GAS_G", "MASK", "UPC", "DNC", "HRC", "DIRECTC")
MODES = ("native_wrapper", "native_physical_fu", "generic_rrtmg")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derive(source: Path) -> dict:
    if sha(source) != INPUT_SHA:
        raise ValueError(f"pinned ice-optics attribution JSON changed: {source}")
    doc = json.loads(source.read_text())
    if doc.get("accuracy_claim") is not False or len(doc.get("captures", [])) != 5:
        raise ValueError("expected five captures and accuracy_claim=false")
    rows = []
    for case in doc["captures"]:
        name = Path(case["capture"]).name
        actual = case["same_state_wrf_comparison"]
        if len(actual) != 1 or actual[0].get("radius_mode") != 1:
            raise ValueError(f"{name}: expected one actual native-radius WRF comparison")
        fixed = {}
        for mode in MODES:
            diffs = case["variants"][mode]["held_fixed_max_difference"]
            fixed[mode] = {key: float(diffs[key]) for key in HELD_FIXED}
            if any(value != 0.0 for value in fixed[mode].values()):
                raise ValueError(f"{name}/{mode}: an allegedly held-fixed field changed")
        base = float(case["baseline"]["surface_down_w_m2"])
        value37 = float(actual[0]["value37"])
        value4 = float(actual[0]["value4"])
        variant_rows = {}
        for mode in MODES:
            flux = float(case["variants"][mode]["metrics"]["surface_down_w_m2"])
            variant_rows[mode] = {
                "rrtmgp_optics_swap_delta_from_baseline_w_m2": flux - base,
                "hybrid_rrtmgp_with_swapped_optics_minus_actual_rrtmg4_w_m2": flux - value4,
                "swapped_case_surface_down_w_m2": flux,
            }
        rows.append({
            "capture": name,
            "actual_wrf_radius_mode": 1,
            "actual_37_minus_4_surface_down_w_m2": value37 - value4,
            "actual_37_w_m2": value37,
            "actual_4_w_m2": value4,
            "rrtmgp_baseline_w_m2": base,
            "held_fixed_exact_zero_max_differences": fixed,
            "variants": variant_rows,
        })
    def values(mode, key):
        return [row["variants"][mode][key] for row in rows]
    def span(items): return {"min": min(items), "max": max(items)}
    return {
        "schema": "udm37-ice-optics-attribution-derived-v1",
        "scope": "offline arithmetic derived only from the five pinned bridge JSON records; no executable/model run",
        "accuracy_claim": False,
        "source_identity": {
            "worktree_head": "9b6c09332e1b0cb3c919882646070443472754ac",
            "bridge_json": {"path": str(source), "sha256": sha(source)},
            "bridge_runner": {"path": str(BRIDGE_TEST), "sha256": sha(BRIDGE_TEST)},
            "runtime_contracts_doc": {"path": str(RUNTIME_DOC), "sha256": sha(RUNTIME_DOC)},
            "historical_same_state_report": {"path": str(HISTORICAL_REPORT), "sha256": sha(HISTORICAL_REPORT)},
        },
        "interpretation": {
            "actual_37_minus_4_surface_down_w_m2": span([x["actual_37_minus_4_surface_down_w_m2"] for x in rows]),
            "native_wrapper_optics_swap_delta_from_rrtmgp_baseline_w_m2": span(values("native_wrapper", "rrtmgp_optics_swap_delta_from_baseline_w_m2")),
            "native_wrapper_hybrid_residual_vs_actual_rrtmg4_w_m2": span(values("native_wrapper", "hybrid_rrtmgp_with_swapped_optics_minus_actual_rrtmg4_w_m2")),
            "native_physical_fu_hybrid_residual_vs_actual_rrtmg4_w_m2": span(values("native_physical_fu", "hybrid_rrtmgp_with_swapped_optics_minus_actual_rrtmg4_w_m2")),
            "generic_rrtmg_hybrid_residual_vs_actual_rrtmg4_w_m2": span(values("generic_rrtmg", "hybrid_rrtmgp_with_swapped_optics_minus_actual_rrtmg4_w_m2")),
            "fu_and_generic_hybrid_residual_combined_range_w_m2": span(values("native_physical_fu", "hybrid_rrtmgp_with_swapped_optics_minus_actual_rrtmg4_w_m2") + values("generic_rrtmg", "hybrid_rrtmgp_with_swapped_optics_minus_actual_rrtmg4_w_m2")),
        },
        "documented_residual_crosscheck": {
            "runtime_contracts_doc_approximate_range_w_m2": {"min": -3.16, "max": -3.12},
            "rederived_from_pinned_json_native_wrapper_range_w_m2": span(values("native_wrapper", "hybrid_rrtmgp_with_swapped_optics_minus_actual_rrtmg4_w_m2")),
            "status": "RECONCILE_APPROXIMATE_TEXT_WITH_PINNED_CASE_ARITHMETIC",
            "note": "The current doc range does not exactly bracket the five arithmetic values from the pinned JSON. Preserve both; this derived artifact does not infer which earlier rounding/subset explains the text.",
        },
        "caveats": [
            doc["spectral_caveat"],
            "The swapped-optics outputs use the RRTMGP reference solver and its gas optics; hybrid residuals versus actual RRTMG4 are not pure RTE-only differences.",
            "Held-fixed exactness applies within each RRTMGP baseline/optics-swap pair to the listed gas, mask, clear-sky flux/heating, and clear direct fields.",
            "Actual 37-minus-4 rows are native-radius mode 1; the historical same-state report's approximately +54 W/m2 control values used the generic RRTMG4 radius path. These are different counterfactuals and are retained separately.",
            "No source-version explanation for the separate published-RFMIP SW tolerance failure is addressed by this bridge.",
        ],
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("ice-attribution-derived.json"))
    args = parser.parse_args()
    result = derive(args.input.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "cases": len(result["cases"]), "accuracy_claim": False}))

if __name__ == "__main__":
    main()
