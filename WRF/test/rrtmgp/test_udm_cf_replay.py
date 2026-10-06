#!/usr/bin/env python3
"""Compare independent V4–V9 LW/SW replays under diagnostic CF policies.

The B and C variants are controlled counterfactuals, not production choices.
Use a replay input and sibling RRTMGP_RAW_V1 snapshot from the same call. All
records not explicitly varied (including CFC and optional frozen optics) are
retained byte-for-byte. For V9 SW inputs, derived direct-diagnostic records
are intentionally removed and the variant is projected to the matching
legacy schema; their values would be stale after changing CF/seed controls.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from compare_column_replay import compare, read_result
from test_column_replay import (assert_close, corrected_hydrometeor, dry_layer_mass_kg_m2,
                                read_input, read_raw, validate_udm_cf_extent)


PATHS = {"LWP": "LWP", "IWP": "IWP", "RWP": "RWP", "SWP": "SWP"}
SUPPORTED_REPLAY_VERSIONS = {
    "RRTMGP_REPLAY_V4", "RRTMGP_REPLAY_V5", "RRTMGP_REPLAY_V6",
    "RRTMGP_REPLAY_V7", "RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V9",
    "RRTMGP_REPLAY_V10", "RRTMGP_REPLAY_V11", "RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13",
}
V9_DIRECT_RECORDS = {
    "SW_DIRECT_PREDELTA_POLICY", "TOA_GPOINT", "RAW_GAS_TAU", "MCICA_MASK",
    "RAW_CLOUD_TAU", "RAW_PRECIP_TAU", "RAW_GRAUPEL_TAU_EXT", "RAW_HAIL_TAU_EXT",
    "BAND_LIMS_GPOINT", "BAND_LIMS_WAVENUMBER", "VISIBLE_WEIGHT",
}
GRID_NAMES = {
    "LWP": ("GRID_LWP", "LWP_GRID"),
    "IWP": ("GRID_IWP", "IWP_GRID"),
    "RWP": ("GRID_RWP", "RWP_GRID"),
    "SWP": ("GRID_SWP", "SWP_GRID"),
}
Q_NAMES = {"LWP": "QC", "IWP": "QI", "RWP": "QR", "SWP": "QS"}
GRAUPEL_GRID_NAMES = ("GWP_GRID", "GRID_GWP")
USED_CF_NAMES = ("UDM_CF_USED", "CF_USED", "CF_LAST_USED")
RECOMPUTED_CF_NAMES = ("UDM_CF_RECOMPUTED", "CF_RECOMPUTED")


def fail(message: str) -> None:
    raise RuntimeError(message)


def b_last_cf_mode(original_cf: np.ndarray, used_cf: np.ndarray | None,
                   extent: int | None) -> np.ndarray | None:
    """Use UDM CF only where its recorded diagnostic extent is defined."""
    if used_cf is None:
        return None
    used = np.asarray(used_cf, dtype=np.float64).reshape(-1)
    original = np.asarray(original_cf, dtype=np.float64).reshape(-1)
    if used.size != original.size:
        fail("UDM_CF_USED and original radiation CF lengths differ")
    if extent is None:  # Legacy raw capture: preserve old replay, but caller labels it unknown.
        return used.copy()
    if extent == -1:
        return None
    if extent < 0 or extent > original.size:
        fail("UDM_CF_TOP outside native radiation layers")
    if not np.isfinite(used[:extent]).all() or np.any((used[:extent] < 0.0) | (used[:extent] > 1.0)):
        fail("UDM_CF_USED invalid inside recorded diagnostic extent")
    hybrid = original.copy()
    hybrid[:extent] = used[:extent]
    return hybrid


def first_field(records: dict[str, np.ndarray], names: tuple[str, ...]) -> np.ndarray | None:
    return next((records[name] for name in names if name in records), None)


def write_variant(source: Path, destination: Path, updates: dict[str, np.ndarray],
                  seed: int) -> None:
    lines = source.read_text(encoding="ascii").splitlines()
    if len(lines) < 2:
        fail(f"{source}: truncated replay input")
    header = lines[1].split()
    if len(header) != 6:
        fail(f"{source}: invalid replay header")
    header[4] = str(seed)
    source_version = lines[0].strip()
    out = ["RRTMGP_REPLAY_V9" if source_version == "RRTMGP_REPLAY_V9" else source_version,
           " ".join(header)]
    pos = 2
    seen: set[str] = set()
    kept: set[str] = set()
    while pos < len(lines):
        fields = lines[pos].split()
        if len(fields) not in (3, 4):
            fail(f"{source}:{pos + 1}: invalid section header")
        name = fields[0].upper()
        try:
            shape = tuple(int(value) for value in fields[1:])
        except ValueError as exc:
            raise RuntimeError(f"{source}:{pos + 1}: invalid shape") from exc
        count = int(np.prod(shape))
        pos += 1
        values: list[str] = []
        found = 0
        while found < count and pos < len(lines):
            values.append(lines[pos])
            found += len(lines[pos].split())
            pos += 1
        if found != count:
            fail(f"{source}: truncated {name} data")
        seen.add(name)
        if source_version == "RRTMGP_REPLAY_V9" and name in V9_DIRECT_RECORDS:
            continue
        if name not in updates:
            out.append(" ".join([name, *(str(dim) for dim in shape)]))
            out.extend(values)
            kept.add(name)
            continue
        array = np.asarray(updates[name], dtype=np.float64)
        if array.shape != shape or not np.isfinite(array).all():
            fail(f"{name} replacement shape or values are invalid")
        out.append(" ".join([name, *(str(dim) for dim in shape)]))
        out.extend(f"{float(value):.16E}" for value in array.flatten(order="F"))
        kept.add(name)
    missing = sorted(updates.keys() - seen)
    if missing:
        fail(f"replay input has no sections for updates: {missing}")
    if source_version == "RRTMGP_REPLAY_V9":
        frozen = "FROZEN_MODE" in kept
        if frozen:
            out[0] = "RRTMGP_REPLAY_V7"
        elif "NATIVE_DRY_LAYER_MASS_KG_M2" in kept:
            out[0] = "RRTMGP_REPLAY_V6"
        else:
            out[0] = "RRTMGP_REPLAY_V5"
    destination.write_text("\n".join(out) + "\n", encoding="ascii")


def assert_variant_preserves_records(source: Path, variant: Path,
                                     updates: dict[str, np.ndarray],
                                     source_records: dict[str, np.ndarray]) -> None:
    """Ensure variants preserve every input other than the declared controls."""
    _, nc, nl, _, _, _, records = read_input(variant)
    _, source_nc, source_nl, _, _, _, original = read_input(source)
    dropped = V9_DIRECT_RECORDS if source.read_text(encoding="ascii").splitlines()[0].strip() == "RRTMGP_REPLAY_V9" else set()
    expected_keys = original.keys() - dropped
    if (nc, nl) != (source_nc, source_nl) or records.keys() != expected_keys:
        fail(f"{variant}: replay dimensions/sections changed while writing policy variant")
    if source_records.keys() != original.keys():
        fail(f"{source}: parsed sections changed unexpectedly")
    for name, values in original.items():
        if name not in updates and name not in dropped and not np.array_equal(records[name], values):
            fail(f"{variant}: unmodified section {name} changed or was stripped")
    # Strict replay parsing validates schema-dependent gas presence. Keep an
    # explicit invariant for gas/background/frozen records this test must
    # never rewrite, even if their values happen to be all zero.
    for name in ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4",
                 "VMR_N2", "TRACE_GASES_PRESENT",
                 "GWP", "HWP", "LAMBDA_G", "LAMBDA_H", "FROZEN_MODE",
                 "FROZEN_OCCURRENCE", "FROZEN_TABLE_SHA256_BYTES"):
        if name in original and (name in updates or not np.array_equal(records[name], original[name])):
            fail(f"{variant}: protected gas/frozen section {name} was changed")


def run_reference(executable: Path, data_dir: Path, input_path: Path,
                  output_path: Path, sw_policy: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), str(data_dir), str(input_path), str(output_path), str(sw_policy)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )


def raw_grid_paths(raw: dict[str, np.ndarray], inputs: dict[str, np.ndarray],
                   raw_nl: int, gravity: float) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    original_cf = inputs["CF"][0, :raw_nl]
    dry_mass, _ = dry_layer_mass_kg_m2(raw, raw_nl)
    grid: dict[str, np.ndarray] = {}
    wet_path_error: dict[str, float] = {}
    for path_name, input_name in PATHS.items():
        if input_name not in inputs:
            if path_name == "RWP":
                continue
                fail(f"replay input is missing {input_name}")
        path = inputs[input_name][0, :raw_nl]
        reconstructed = original_cf * path
        direct = first_field(raw, GRID_NAMES[path_name])
        if direct is not None:
            if direct.size != raw_nl:
                fail(f"raw grid path {path_name} has {direct.size} values, expected {raw_nl}")
            direct = direct.reshape(-1)
            if np.any(~np.isfinite(direct)) or np.any(direct < 0.0):
                fail(f"raw grid path {path_name} must be finite and nonnegative")
            wet = original_cf > 0.0
            qname = Q_NAMES[path_name]
            if qname in raw:
                q = corrected_hydrometeor(raw, qname, path_name, raw_nl)
                assert_close(direct, q * dry_mass * 1000.0,
                             f"raw {path_name} grid mass from {qname} and dry layer mass",
                             rtol=5.0e-6, atol=1.0e-8)
            wet_path_error[path_name] = float(np.max(np.abs(direct[wet] - reconstructed[wet]), initial=0.0))
            scale = max(1.0, float(np.max(np.abs(direct[wet]), initial=0.0)))
            if not np.allclose(direct[wet], reconstructed[wet], rtol=5.0e-6, atol=1.0e-5 * scale):
                fail(f"raw grid {path_name} disagrees with original CF times replay in-cloud path")
            grid[path_name] = direct.copy()
            continue
        missing_clear = (original_cf == 0.0) & (path <= 0.0)
        qname = Q_NAMES[path_name]
        if np.any(missing_clear):
            if qname not in raw:
                fail(f"cannot recover clear-grid {path_name}: raw {qname} or grid path is missing")
            q = corrected_hydrometeor(raw, qname, path_name, raw_nl)
            recovered = q * dry_mass * 1000.0
            reconstructed[missing_clear] = recovered[missing_clear]
        grid[path_name] = reconstructed
        wet_path_error[path_name] = 0.0
    return grid, wet_path_error


def metric_values(result: dict) -> dict[str, float]:
    sections = result["sections"]
    metrics = {
        "surface_down_w_m2": float(sections["DN"][0, 0, 0]),
        "surface_up_w_m2": float(sections["UP"][0, 0, 0]),
        "toa_down_w_m2": float(sections["DN"][0, -1, 0]),
        "toa_up_w_m2": float(sections["UP"][0, -1, 0]),
        "max_abs_heating_k_day": float(np.max(np.abs(sections["HR"]), initial=0.0)),
        "max_total_tau": float(np.max(sections["TOTAL_TAU"], initial=0.0)),
        "max_prepared_tau": float(np.max(sections["PREPARED_TAU"], initial=0.0)),
    }
    if "DIRECT" in sections:
        metrics["surface_direct_w_m2"] = float(sections["DIRECT"][0, 0, 0])
    return metrics


def summarize_runs(results: list[dict]) -> dict[str, Any]:
    per_seed = [metric_values(result) for result in results]
    summary: dict[str, Any] = {"samples": len(per_seed), "metrics": {}}
    for name in per_seed[0]:
        values = np.asarray([item[name] for item in per_seed], dtype=np.float64)
        summary["metrics"][name] = {
            "mean": float(np.mean(values)),
            "standard_deviation": float(np.std(values, ddof=1)) if values.size > 1 else 0.0,
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("reference_executable", type=Path)
    parser.add_argument("v4_input", type=Path)
    parser.add_argument("raw_snapshot", type=Path)
    parser.add_argument("--cf-policy", choices=("A", "B", "B_now", "C", "all"), default="all")
    parser.add_argument("--delta-policy", choices=("1", "2", "3", "all"), default="1")
    parser.add_argument("--graupel-policy", choices=("omitted", "as-snow", "all"), default="omitted")
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds < 1 or args.seeds > 512:
        parser.error("--seeds must be from 1 to 512")
    data_dir, reference, input_path, raw_path = (
        p.resolve() for p in (args.data_directory, args.reference_executable,
                              args.v4_input, args.raw_snapshot)
    )
    for required in (data_dir, reference, input_path, raw_path):
        if not required.exists():
            parser.error(f"required path does not exist: {required}")

    phase, raw_i, raw_j, raw = read_raw(raw_path)
    phase_in, nc, nl, overlap, base_seed, iceflag, input_records = read_input(input_path)
    if phase != phase_in or nc != 1 or nl < len(raw["DP_HPA"]):
        fail("expected paired one-column LW/SW replay input covering the native raw layers")
    replay_version = input_path.read_text(encoding="ascii").splitlines()[0].strip()
    if replay_version not in SUPPORTED_REPLAY_VERSIONS:
        fail(f"unsupported replay format {replay_version}")
    raw_nl = len(raw["DP_HPA"])
    cf_top = validate_udm_cf_extent(raw, raw_nl, raw_path)
    if raw_i < 1 or raw_j < 1:
        fail("raw snapshot has invalid source indices")
    gravity = float(raw["GRAVITY"][0])
    if not np.isfinite(gravity) or gravity <= 0.0:
        fail("raw gravity must be finite and positive")
    original_cf = input_records["CF"][0, :raw_nl].copy()
    if np.any((original_cf < 0.0) | (original_cf > 1.0)):
        fail("replay input CF outside [0,1]")
    grid_paths, wet_reconstruction_errors = raw_grid_paths(raw, input_records, raw_nl, gravity)

    cf_modes = ("A", "B", "B_now", "C") if args.cf_policy == "all" else (args.cf_policy,)
    sw_policies = ((1,) if phase == "LW" else
                   ((1, 2, 3) if args.delta_policy == "all" else (int(args.delta_policy),)))
    used_cf = first_field(raw, USED_CF_NAMES)
    recomputed_cf = first_field(raw, RECOMPUTED_CF_NAMES)

    def normalize_cf(field: np.ndarray | None, name: str, extent: int | None = None) -> np.ndarray | None:
        if field is None:
            return None
        values = np.asarray(field, dtype=np.float64).reshape(-1)
        if values.size == 1:
            values = np.full(raw_nl, values.item())
        if values.size != raw_nl:
            fail(f"{name} must have raw native-layer length")
        checked = values if extent is None else values[:extent]
        if np.any(~np.isfinite(checked)):
            fail(f"{name} values within its declared extent must be finite")
        if np.any((checked < 0.0) & (checked != -1.0)) or np.any(checked > 1.0):
            fail(f"{name} values within its declared extent must be in [0,1] or sentinel -1")
        if extent is not None and np.any(checked == -1.0):
            fail(f"{name} contains not-called sentinels inside its declared diagnostic extent")
        return values

    used_cf = normalize_cf(used_cf, "UDM_CF_USED", cf_top if cf_top is not None and cf_top >= 0 else None)
    recomputed_cf = normalize_cf(recomputed_cf, "UDM_CF_RECOMPUTED")
    cf_values = {"A": original_cf, "C": original_cf}
    b_extent_metadata: dict[str, Any]
    if cf_top is None:
        if used_cf is not None:
            cf_values["B"] = b_last_cf_mode(original_cf, used_cf, None)
            b_extent_metadata = {"extent_status": "LEGACY_UNKNOWN", "known_layers": None,
                                 "unknown_layers": raw_nl,
                                 "cf_semantics": "legacy whole working vector; extent unavailable"}
        else:
            b_extent_metadata = {"extent_status": "MISSING_CF_USED", "known_layers": None,
                                 "unknown_layers": raw_nl}
    elif cf_top == -1:
        b_extent_metadata = {"extent_status": "NOT_CALLED", "known_layers": 0,
                             "unknown_layers": raw_nl}
    else:
        b_extent_metadata = {"extent_status": "EXTENT_LIMITED_HYBRID", "known_layers": cf_top,
                             "unknown_layers": raw_nl - cf_top,
                             "cf_semantics": "UDM_CF_USED on 1:top; original radiation CF above top"}
        if used_cf is not None:
            cf_values["B"] = b_last_cf_mode(original_cf, used_cf, cf_top)
    if recomputed_cf is not None:
        cf_values["B_now"] = recomputed_cf

    qg_grid_raw = first_field(raw, GRAUPEL_GRID_NAMES)
    qg_grid = None
    if qg_grid_raw is not None:
        qg_grid = np.asarray(qg_grid_raw, dtype=np.float64).reshape(-1)
        if qg_grid.size != raw_nl or np.any(~np.isfinite(qg_grid)) or np.any(qg_grid < 0.0):
            fail("raw GWP_GRID must be finite, nonnegative, and have native-layer length")
    if args.graupel_policy in ("as-snow", "all") and qg_grid is None:
        fail("graupel as-snow counterfactual requires raw GWP_GRID")
    graupel_modes = ("omitted", "as-snow") if args.graupel_policy == "all" else (args.graupel_policy,)
    mode_inputs: dict[str, dict[str, tuple[dict[str, np.ndarray], dict[str, Any]]]] = {}
    diagnostics: dict[str, Any] = {}
    for mode in cf_modes:
        diagnostics[mode] = {}
        if mode == "B":
            diagnostics[mode].update(b_extent_metadata)
        if mode not in cf_values:
            missing_cf = "UDM_CF_USED" if mode == "B" else "UDM_CF_RECOMPUTED"
            diagnostics[mode]["status"] = ("SKIPPED_NOT_CALLED" if mode == "B" and cf_top == -1
                                             else f"SKIPPED_MISSING_{missing_cf}")
            if args.cf_policy == mode:
                fail(f"requested CF policy {mode} requires raw {missing_cf} and a called diagnostic")
            continue
        cf_mode = np.asarray(cf_values[mode], dtype=np.float64)
        if np.any(cf_mode == -1.0):
            diagnostics[mode]["status"] = "SKIPPED_SENTINEL_MINUS_ONE"
            diagnostics[mode]["sentinel_layers"] = int(np.count_nonzero(cf_mode == -1.0))
            continue
        if mode == "B" and cf_top is None:
            diagnostics[mode]["status"] = "READY_LEGACY_EXTENT_UNKNOWN"
        elif mode == "B":
            diagnostics[mode]["status"] = "READY_EXTENT_LIMITED_HYBRID"
        mode_inputs[mode] = {}
        for graupel_mode in graupel_modes:
            updates = {name: values.copy() for name, values in input_records.items()
                       if name in {"CF", *PATHS.values()}}
            omitted_layers: dict[str, np.ndarray] = {}
            shift_layers: dict[str, np.ndarray] = {}
            if mode != "A":
                updates["CF"][0, :raw_nl] = cf_mode
                for phase_path, input_name in PATHS.items():
                    if input_name not in updates or phase_path not in grid_paths:
                        continue
                    grid = grid_paths[phase_path]
                    path = np.zeros(raw_nl, dtype=np.float64)
                    if mode in ("B", "B_now"):
                        wet = cf_mode > 0.0
                        path[wet] = grid[wet] / cf_mode[wet]
                        omitted_layers[phase_path] = np.where(wet, 0.0, grid)
                        shift_layers[phase_path] = -omitted_layers[phase_path]
                    else:  # C: grid-mean paths are passed as in-cloud paths.
                        path = grid.copy()
                        shift_layers[phase_path] = cf_mode * path - grid
                        omitted_layers[phase_path] = np.maximum(-shift_layers[phase_path], 0.0)
                    updates[input_name][0, :raw_nl] = path
            else:
                for phase_path, input_name in PATHS.items():
                    if input_name in updates and phase_path in grid_paths:
                        omitted_layers[phase_path] = np.where(cf_mode == 0.0, grid_paths[phase_path], 0.0)
                        shift_layers[phase_path] = -omitted_layers[phase_path]

            graupel_diag: dict[str, Any] = {"mode": graupel_mode}
            if qg_grid is None:
                graupel_diag["raw_grid_mass_available"] = False
            elif graupel_mode == "omitted":
                omitted_layers["GWP"] = qg_grid.copy()
                shift_layers["GWP"] = -qg_grid
                graupel_diag.update({"raw_grid_mass_available": True, "optical_mapping": "omitted"})
            else:
                if "SWP" not in updates:
                    fail("as-snow mapping requires SWP in the replay input")
                if "RES" not in input_records or "RES" not in raw:
                    fail("as-snow mapping requires the native UDM snow radius RES")
                native_res = raw["RES"][:raw_nl]
                if native_res.size != raw_nl or not np.allclose(
                    input_records["RES"][0, :raw_nl], native_res, rtol=0.0, atol=0.0
                ):
                    fail("replay RES differs from raw native UDM snow radii")
                qg_path = np.zeros(raw_nl, dtype=np.float64)
                positive_cf = cf_mode > 0.0
                if mode == "C":
                    qg_path[positive_cf] = qg_grid[positive_cf]
                else:
                    qg_path[positive_cf] = qg_grid[positive_cf] / cf_mode[positive_cf]
                updates["SWP"][0, :raw_nl] += qg_path
                qg_effective = cf_mode * qg_path
                shift_layers["GWP"] = qg_effective - qg_grid
                omitted_layers["GWP"] = np.maximum(-shift_layers["GWP"], 0.0)
                graupel_diag.update({
                    "raw_grid_mass_available": True,
                    "optical_mapping": "counterfactual qg mass added to SWP using existing native RES",
                    "snow_radius_unchanged": True,
                    "zero_cf_mass_omitted_g_m2": float(np.sum(qg_grid[~positive_cf])),
                    "effective_graupel_mass_shift_g_m2": float(np.sum(shift_layers["GWP"])),
                })

            mass_stats = {}
            for species, omitted_values in omitted_layers.items():
                shift_values = shift_layers[species]
                mass_stats[species] = {
                    "omitted_grid_path_g_m2": {
                        "sum": float(np.sum(omitted_values)),
                        "layer_mean": float(np.mean(omitted_values)),
                        "layer_standard_deviation": float(np.std(omitted_values, ddof=1)) if raw_nl > 1 else 0.0,
                        "layer_maximum": float(np.max(omitted_values, initial=0.0)),
                    },
                    "effective_mass_shift_g_m2": {
                        "sum": float(np.sum(shift_values)),
                        "layer_mean": float(np.mean(shift_values)),
                        "layer_standard_deviation": float(np.std(shift_values, ddof=1)) if raw_nl > 1 else 0.0,
                        "layer_maximum_absolute": float(np.max(np.abs(shift_values), initial=0.0)),
                    },
                }
            mode_inputs[mode][graupel_mode] = (updates, graupel_diag)
            diagnostics[mode][graupel_mode] = {
                "status": "READY",
                "layer_mean_and_standard_deviation_by_species": mass_stats,
                "maximum_wet_layer_grid_reconstruction_error_g_m2_by_species": wet_reconstruction_errors,
                "upper_replay_layers_preserved": nl - raw_nl,
                "cf_min": float(np.min(cf_mode)),
                "cf_max": float(np.max(cf_mode)),
                "graupel": graupel_diag,
            }

    seed_values = [((base_seed + offset - 1) % 2147483646) + 1 for offset in range(args.seeds)]
    sample_results: dict[str, dict[str, dict[int, list[dict]]]] = {
        mode: {graupel: {policy: [] for policy in sw_policies} for graupel in variants}
        for mode, variants in mode_inputs.items()
    }
    default_code1_check = False
    production_default_check: dict[str, Any] | None = None
    source_production = input_path.with_suffix(".result")
    with tempfile.TemporaryDirectory(prefix="rrtmgp-udm-cf-replay-") as temp:
        tmp = Path(temp)
        total_runs = sum(len(variants) for variants in mode_inputs.values()) * len(sw_policies) * args.seeds
        run_index = 0
        for mode, variants in mode_inputs.items():
            for graupel_mode, (updates, _graupel_diag) in variants.items():
                variant_path = tmp / f"cf-{mode}-graupel-{graupel_mode}.input"
                variant_verified = False
                for policy in sw_policies:
                    for seed_offset, seed in enumerate(seed_values):
                        run_index += 1
                        write_variant(input_path, variant_path, updates, seed)
                        if not variant_verified:
                            assert_variant_preserves_records(input_path, variant_path, updates, input_records)
                            variant_verified = True
                        out_path = tmp / f"{mode}-{graupel_mode}-{policy}-{seed_offset}.result"
                        run = run_reference(reference, data_dir, variant_path, out_path, policy)
                        if run.returncode:
                            fail(f"CF {mode}/{graupel_mode} delta policy {policy} seed {seed} failed: {run.stdout[-1400:]}")
                        result = read_result(out_path)
                        sample_results[mode][graupel_mode][policy].append(result)
                        if mode == "A" and graupel_mode == "omitted" and seed_offset == 0 and policy == 1:
                            default_path = tmp / "default-policy.result"
                            default_run = subprocess.run(
                                [str(reference), str(data_dir), str(variant_path), str(default_path)],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                            )
                            if default_run.returncode:
                                fail(f"default reference failed: {default_run.stdout[-1400:]}")
                            report = compare(read_result(default_path), result)
                            if not report.get("passed"):
                                fail("explicit delta policy 1 differs from the default reference path")
                            default_code1_check = True
                            if source_production.is_file():
                                production_report = compare(read_result(source_production), result)
                                production_default_check = {
                                    "passed": bool(production_report.get("passed")),
                                    "failed_sections": production_report.get("failed_sections", []),
                                    "max_differences": production_report.get("max_differences", {}),
                                }
                                if not production_report.get("passed"):
                                    fail("A/policy1/omitted does not reproduce the captured production result")
                        if run_index % 16 == 0 or run_index == total_runs:
                            print(f"CF replay progress: {run_index}/{total_runs}", flush=True)

    scenarios: dict[str, Any] = {}
    for mode, graupel_variants in sample_results.items():
        scenarios[mode] = {}
        for graupel_mode, policies in graupel_variants.items():
            scenarios[mode][graupel_mode] = {}
            for policy, results in policies.items():
                scenarios[mode][graupel_mode][str(policy)] = summarize_runs(results)
            if 1 in policies:
                baseline = scenarios[mode][graupel_mode]["1"]["metrics"]
                for policy in policies:
                    if policy == 1:
                        continue
                    metrics = scenarios[mode][graupel_mode][str(policy)]["metrics"]
                    scenarios[mode][graupel_mode][str(policy)]["mean_delta_vs_policy_1"] = {
                        name: metrics[name]["mean"] - baseline[name]["mean"]
                        for name in baseline
                    }
    summary = {
        "status": "PASS" if mode_inputs else "SKIPPED_SENTINEL_MINUS_ONE",
        "experiment": f"{replay_version} {phase} replay with common captured microphysics paths and independent cloud-mask seeds",
        "source_capture": {"input": str(input_path), "input_format": replay_version,
                           "cfc_record_schema_valid": (
                               (all(name in input_records for name in
                                    ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"))
                                if replay_version in {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V10"}
                                else ((int(input_records["TRACE_GASES_PRESENT"].item()) == 1) ==
                                      all(name in input_records for name in
                                          ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4")))
                                if replay_version in {"RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"} else None)),
                           "n2_profile_preserved": "VMR_N2" in input_records,
                           "trace_gases_present": (int(input_records["TRACE_GASES_PRESENT"].item())
                               if "TRACE_GASES_PRESENT" in input_records else None),
                           "frozen_metadata_present": any(name in input_records for name in
                               ("GWP", "HWP", "LAMBDA_G", "LAMBDA_H", "FROZEN_MODE",
                                "FROZEN_OCCURRENCE", "FROZEN_TABLE_SHA256_BYTES")),
                           "variant_unmodified_records_preserved_exactly": True,
                           "raw": str(raw_path), "i": raw_i, "j": raw_j,
                           "native_raw_layers": raw_nl, "extended_replay_layers": nl},
        "dry_layer_mass_source": ("native_dry_layer_mass" if "DRY_LAYER_MASS_KG_M2" in raw
                                  else "legacy_dp_over_gravity"),
        "seed_ensemble": {"count": args.seeds, "seeds": seed_values},
        "policy_labels": {
            "A": "original captured radiation CF and in-cloud paths",
            "B": "extent-limited hybrid: UDM_CF_USED on 1:UDM_CF_TOP, original radiation CF above top; legacy raw without top retains whole working vector but is explicitly extent-unknown; recompute paths with the selected CF",
            "B_now": "current-state UDM_CF_RECOMPUTED; recompute paths from preserved grid-box mass; zero-CF grid mass is omitted",
            "C": "original radiation CF with grid-mean paths passed as in-cloud paths; intentionally non-mass-preserving counterfactual",
        },
        "graupel_policy_labels": {
            "omitted": "keep graupel out of the precipitation optics; report its raw grid-box path separately",
            "as-snow": "counterfactual only: add GWP grid path to SWP using unchanged native UDM RES; no public graupel optical coefficient was verified",
        },
        "delta_policy_labels": {"1": "D(C)+D(P)", "2": "C+D(P)", "3": "D(C+P)"},
        "delta_policy_scope": "SW delta-scaling benchmark; LW is evaluated once with its unchanged policy.",
        "default_policy_1_matches_default_reference": default_code1_check,
        "captured_production_check": production_default_check,
        "cf_policy_diagnostics": diagnostics,
        "scenarios": scenarios,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote UDM CF replay summary to {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
