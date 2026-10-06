#!/usr/bin/env python3
"""Recompute the saved 2x2 fixed-optics RTE comparison; no solver calls."""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FIXED = REPO / "validation/rrtmgp37/rfmip-fixed-rte"
HIST = HERE
NLEV = 61
ATOL = 1.0e-5
EXPECTED_HIST_EXEC_SHA = "5e21ba94671dd5f2c876b823146a8c4e7782d2a67aede05e6958bffbd92ea8de"
EXPECTED_CURRENT_EXEC_SHA = "de63e764cf2bb4649b54ad444d2662f8c3b7e2013aa7ba7c17019c2634e998fc"
EXPECTED_STRICT_DETAILS_SHA = "58a3901f6e6f4f7c255ae0d0b4629315842bedbe1a244c3cff220ed484aa5879"
EXPECTED_PROFILES_SHA = "d3d7037d48dbe603ce93d2a70610a140d4c5373f91d691942b9f50a2eb8d1178"
EXPECTED_FIXED_PACKAGE_MANIFEST_SHA = "7b1b66f9c0bc77a8086a53159b4dc72bf5602c4f3279b4521e440868af0dfe1b"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stats(values: list[float]) -> dict:
    if not values:
        raise ValueError("empty metric")
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "mean_abs": sum(abs(x) for x in values) / len(values),
        "max_abs": max(abs(x) for x in values),
        "rms": math.sqrt(sum(x * x for x in values) / len(values)),
    }


def read_flux(path: Path, keys: list[tuple[int, int]], pin: dict) -> dict:
    raw = path.read_bytes()
    if len(raw) != pin["size_bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError(f"flux output pin mismatch: {path}")
    recbytes = 8 + 2 * NLEV * 8
    if len(raw) != len(keys) * recbytes:
        raise ValueError(f"flux stream geometry mismatch: {path}")
    result = {}
    for n, key in enumerate(keys):
        off = n * recbytes
        if struct.unpack_from("<ii", raw, off) != key:
            raise ValueError(f"key/order mismatch in {path} record {n + 1}")
        vals = struct.unpack_from("<" + "d" * (2 * NLEV), raw, off + 8)
        if not all(math.isfinite(x) for x in vals):
            raise ValueError(f"nonfinite flux in {path} record {n + 1}")
        result[key] = {"up": vals[:NLEV], "down": vals[NLEV:]}
    return result


def main() -> None:
    hist_exec_path = HIST / "execution/execution.json"
    current_exec_path = FIXED / "execution-v4/execution.json"
    he = json.loads(hist_exec_path.read_text())
    ce = json.loads(current_exec_path.read_text())
    if sha(hist_exec_path) != EXPECTED_HIST_EXEC_SHA or sha(current_exec_path) != EXPECTED_CURRENT_EXEC_SHA:
        raise ValueError("terminal execution receipt pin mismatch")
    if he.get("status") != "TERMINAL" or he.get("research_status") != "HISTORICAL_RTE_BASELINE_EXACT":
        raise ValueError("historical execution is not terminal exact")
    if he.get("new_fixed_rte_calls") != 40 or he.get("gas_optics_calls") != 0 or he.get("model_forecasts") != 0:
        raise ValueError("historical execution scope mismatch")
    if ce.get("rte_calls_expected") != 40 or ce.get("gas_optics_calls") != 0 or ce.get("model_forecasts") != 0:
        raise ValueError("current fixed-RTE execution scope mismatch")
    for receipt in (he, ce):
        children = receipt["children"]
        if len(children) != 5 or any(x.get("returncode") != 0 or not x.get("reaped") or x.get("timed_out") for x in children):
            raise ValueError("child completion mismatch")

    profile_path = FIXED / "inputs/profiles20.txt"
    if sha(profile_path) != EXPECTED_PROFILES_SHA:
        raise ValueError("frozen profile roster pin mismatch")
    fixed_manifest_path = FIXED / "package-manifest.json"
    if sha(fixed_manifest_path) != EXPECTED_FIXED_PACKAGE_MANIFEST_SHA:
        raise ValueError("adjacent fixed-RTE package manifest pin mismatch")
    fixed_manifest = json.loads(fixed_manifest_path.read_text())
    for rel in (
        "validation/rrtmgp37/rfmip-fixed-rte/inputs/profiles20.txt",
        "validation/rrtmgp37/rfmip-fixed-rte/references/original-strict-residual-details.json",
        *(f"validation/rrtmgp37/rfmip-fixed-rte/references/{name}.bin" for name in (
            "current_solver", "current_written", "historical_solver", "historical_written")),
        "validation/rrtmgp37/rfmip-fixed-rte/execution-v4/execution.json",
    ):
        p = REPO / rel
        pin = fixed_manifest["files"].get(rel)
        if pin is None or sha(p) != pin["sha256"] or p.stat().st_size != pin["size_bytes"]:
            raise ValueError(f"adjacent fixed-RTE package manifest pin mismatch: {rel}")
    keys = [tuple(map(int, row.split())) for row in profile_path.read_text().splitlines()]
    if len(keys) != 20 or len(set(keys)) != 20 or keys != sorted(keys):
        raise ValueError("profile roster mismatch")
    refs = {}
    names = ("current_solver", "current_written", "historical_solver", "historical_written")
    for name in names:
        ref = FIXED / "references" / f"{name}.bin"
        refs[name] = read_flux(ref, keys, {"sha256": sha(ref), "size_bytes": ref.stat().st_size})
    # Explicit 2x2 solver outputs (the written outputs are separately checked below).
    F = {
        ("current", "current_optics"): read_flux(FIXED / "execution-v4/replay_current_solver.bin", keys, ce["outputs"]["current_solver"]),
        ("current", "historical_optics"): read_flux(FIXED / "execution-v4/replay_historical_solver.bin", keys, ce["outputs"]["historical_solver"]),
        ("historical", "current_optics"): read_flux(HIST / "outputs/replay_current_solver.bin", keys, he["outputs"]["replay_current_solver.bin"]),
        ("historical", "historical_optics"): read_flux(HIST / "outputs/replay_historical_solver.bin", keys, he["outputs"]["replay_historical_solver.bin"]),
    }
    written = {
        ("current", "current_optics"): read_flux(FIXED / "execution-v4/replay_current_written.bin", keys, ce["outputs"]["current_written"]),
        ("current", "historical_optics"): read_flux(FIXED / "execution-v4/replay_historical_written.bin", keys, ce["outputs"]["historical_written"]),
        ("historical", "current_optics"): read_flux(HIST / "outputs/replay_current_written.bin", keys, he["outputs"]["replay_current_written.bin"]),
        ("historical", "historical_optics"): read_flux(HIST / "outputs/replay_historical_written.bin", keys, he["outputs"]["replay_historical_written.bin"]),
    }
    # Exact anchors: current-runtime current-optics and historical-runtime historical-optics.
    exact_current = all(F[("current", "current_optics")][k] == refs["current_solver"][k] for k in keys)
    exact_historical = all(F[("historical", "historical_optics")][k] == refs["historical_solver"][k] for k in keys)
    exact_written_current = all(written[("current", "current_optics")][k] == refs["current_written"][k] for k in keys)
    exact_written_historical = all(written[("historical", "historical_optics")][k] == refs["historical_written"][k] for k in keys)
    if not all((exact_current, exact_historical, exact_written_current, exact_written_historical)):
        raise ValueError("one of the two diagonal solver/written saved-stream anchors is not exact")
    solver_written_equal = {f"{rt}_{op}": F[(rt, op)] == written[(rt, op)] for rt in ("current", "historical") for op in ("current_optics", "historical_optics")}

    components = {name: {direction: [] for direction in ("up", "down")} for name in (
        "optics_effect_current_runtime", "optics_effect_historical_runtime",
        "runtime_effect_current_optics", "runtime_effect_historical_optics", "interaction",
        "total_diagonal_change", "component_closure")}
    for key in keys:
        for direction in ("up", "down"):
            for level in range(NLEV):
                cc = F[("current", "current_optics")][key][direction][level]
                ch = F[("current", "historical_optics")][key][direction][level]
                hc = F[("historical", "current_optics")][key][direction][level]
                hh = F[("historical", "historical_optics")][key][direction][level]
                optics_c = ch - cc
                optics_h = hh - hc
                runtime_c = hc - cc
                runtime_h = hh - ch
                interaction = optics_h - optics_c
                total = hh - cc
                closure = optics_c + runtime_c + interaction - total
                for name, value in (
                    ("optics_effect_current_runtime", optics_c),
                    ("optics_effect_historical_runtime", optics_h),
                    ("runtime_effect_current_optics", runtime_c),
                    ("runtime_effect_historical_optics", runtime_h),
                    ("interaction", interaction),
                    ("total_diagonal_change", total),
                    ("component_closure", closure),
                ):
                    components[name][direction].append(value)
    component_stats = {name: {direction: stats(values) for direction, values in bydir.items()} for name, bydir in components.items()}

    strict_path = FIXED / "references/original-strict-residual-details.json"
    if sha(strict_path) != EXPECTED_STRICT_DETAILS_SHA:
        raise ValueError("original selected strict-cell details pin mismatch")
    strict = json.loads(strict_path.read_text())
    rows = []
    strict_counts = {arm: {"double": 0, "cast_f32": 0} for arm in (
        "current_runtime_current_optics", "current_runtime_historical_optics",
        "historical_runtime_current_optics", "historical_runtime_historical_optics")}
    for cell in strict["residual_cells"]:
        e0, s0, l0 = cell["index0_experiment_site_level"]
        key = (e0 + 1, s0 + 1)
        var = cell["variable"].lower()
        direction = {"rsd": "down", "rsu": "up"}[var]
        level = int(l0)
        if key not in F[("historical", "historical_optics")] or not 0 <= level < NLEV:
            raise ValueError("strict cell not in 20-profile selection")
        ref = float(cell["reference_stored_W_m2"])
        row = {"variable": var.upper(), "key_one_based": list(key), "level_index0": level,
               "published_reference_f32_W_m2": ref,
               "saved_historical_solver_W_m2": refs["historical_solver"][key][direction][level],
               "saved_historical_written_W_m2": refs["historical_written"][key][direction][level],
               "current_runtime_current_optics_W_m2": F[("current", "current_optics")][key][direction][level],
               "current_runtime_historical_optics_W_m2": F[("current", "historical_optics")][key][direction][level],
               "historical_runtime_current_optics_W_m2": F[("historical", "current_optics")][key][direction][level],
               "historical_runtime_historical_optics_W_m2": F[("historical", "historical_optics")][key][direction][level]}
        row["historical_optics_historical_runtime_minus_f32_reference_W_m2"] = row["historical_runtime_historical_optics_W_m2"] - ref
        row["historical_optics_historical_runtime_cast_f32_minus_reference_W_m2"] = struct.unpack("<f", struct.pack("<f", row["historical_runtime_historical_optics_W_m2"]))[0] - ref
        row["diagonal_delta_total_W_m2"] = row["historical_runtime_historical_optics_W_m2"] - row["current_runtime_current_optics_W_m2"]
        for arm in strict_counts:
            val = row[arm + "_W_m2"]
            cast = struct.unpack("<f", struct.pack("<f", val))[0]
            err = val - ref
            cast_err = cast - ref
            row[arm + "_minus_reference_W_m2"] = err
            row[arm + "_cast_f32_minus_reference_W_m2"] = cast_err
            if abs(err) > ATOL:
                strict_counts[arm]["double"] += 1
            if abs(cast_err) > ATOL:
                strict_counts[arm]["cast_f32"] += 1
        rows.append(row)
    if len(rows) != 21:
        raise ValueError("original selected strict-cell diagnostic roster changed")

    build_summary_path = HIST / "provenance/runtime-build-summary.json"
    build_summary = json.loads(build_summary_path.read_text())
    report = {
        "schema": "RFMIP_HISTORICAL_RTE_2X2_FIXED_OPTICS_ANALYSIS_V1",
        "status": "PASS_SCOPED_HISTORICAL_REPLAY_AND_COMPONENT_DECOMPOSITION_NOT_GLOBAL_STRICT_PASS",
        "scope": "Saved-only independent parsing and arithmetic over the two retained 20-profile fixed-optics RTE runs. No build, solver, or model execution by this analyzer.",
        "scope_counts": {"profiles": 20, "flux_levels": NLEV, "directions": ["up", "down"], "flux_values_per_arm": 2440,
                         "rte_calls_current_runtime": 40, "rte_calls_historical_runtime": 40, "new_historical_runtime_rte_calls_in_this_stage": 40,
                         "gas_optics_calls": 0, "forecasts": 0},
        "terminal_receipts": {
            "historical_runtime": {"path": "execution/execution.json", "sha256": sha(hist_exec_path), "plan_sha256": he["plan_sha256"], "runner_sha256": he["runner_sha256"], "status": he["status"],
                                   "research_status": he["research_status"], "children": [{"label": c["label"], "rc": c["returncode"], "reaped": c["reaped"], "timeout": c["timed_out"]} for c in he["children"]]},
            "current_runtime": {"path": "../rfmip-fixed-rte/execution-v4/execution.json", "sha256": sha(current_exec_path), "runner_plan_sha256": ce.get("run_plan_sha256"), "status": ce["status"],
                                "rte_calls": ce["rte_calls_expected"]},
        },
        "2x2_definition": {"F(current,current)": "Current RTE with current optics",
                           "F(current,historical)": "Current RTE with historical optics",
                           "F(historical,current)": "Retained historical RTE with current optics",
                           "F(historical,historical)": "Retained historical RTE with historical optics",
                           "optics_effect_current_runtime": "F(current,historical) - F(current,current)",
                           "optics_effect_historical_runtime": "F(historical,historical) - F(historical,current)",
                           "runtime_effect_current_optics": "F(historical,current) - F(current,current)",
                           "runtime_effect_historical_optics": "F(historical,historical) - F(current,historical)",
                           "interaction": "optics_effect_historical_runtime - optics_effect_current_runtime",
                           "total_diagonal_change": "F(historical,historical) - F(current,current)",
                           "closure": "optics_effect_current_runtime + runtime_effect_current_optics + interaction - total_diagonal_change"},
        "anchor_checks": {"current_runtime_current_optics_solver_exact_saved": exact_current,
                           "current_runtime_current_optics_written_exact_saved": exact_written_current,
                           "historical_runtime_historical_optics_solver_exact_saved": exact_historical,
                           "historical_runtime_historical_optics_written_exact_saved": exact_written_historical,
                           "solver_written_streams_equal_for_all_four_arms": solver_written_equal},
        "component_metrics_by_direction_W_m2": component_stats,
        "selected_original_21_strict_failure_diagnostic": {"count": 21, "atol_W_m2": ATOL, "rtol": 0,
            "global_strict_gate_changed": False, "rows": rows,
            "selected_subset_only_fail_counts_vs_published_f32_reference": strict_counts,
            "scope_note": "Only the 21 previously selected cells associated with these 20 profiles are reported; this is not a census or closure of all strict RFMIP failures."},
        "source_and_build_provenance": {**build_summary,
            "runtime_build_summary_pin": {"path": "provenance/runtime-build-summary.json", "sha256": sha(build_summary_path)},
            "warning": "The comparison changes the retained RTE source/build/runtime stack and can also reflect its compiler/build path; the difference is not isolated as a pure algorithm change. Historical optics were reused across distinct coefficient/g-point metadata; no per-g-point physical equivalence is claimed."},
        "strict_and_scientific_limits": ["The original strict RFMIP gate and all 21 selected failures are preserved; no tolerance changed.",
            "A bitwise historical-runtime match verifies this saved 20-profile replay only; it does not establish historical published-executable provenance or physical accuracy.",
            "The interaction term is a finite-sample 2x2 decomposition over broadband fluxes at matched profile and level indices, not a g-point pairing or universal attribution."]
    }
    out = HIST / "two_by_two_analysis.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "output": str(out), "sha256": sha(out),
                      "anchors": report["anchor_checks"], "component_metrics_by_direction_W_m2": component_stats},
                     sort_keys=True))


if __name__ == "__main__":
    main()
