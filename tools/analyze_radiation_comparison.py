#!/usr/bin/env python3
"""Analyze paired WRF SCM history output for RRTMG 4/4 vs RRTMGP 37/37.

The analysis is descriptive. It verifies paired initial conditions and time
grids, then reports area-weighted radiation differences and unweighted
vertical-layer heating diagnostics; it does not assess physical accuracy.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SURFACE_FIELDS = (
    "SWDOWN", "GSW", "GLW", "SWDNB", "SWUPB", "SWDDIR", "SWDDIF",
    "LWUPT", "SWUPT", "SWDNT", "LWDNB", "LWDNT", "LWUPB",
    "SWDNTC", "SWUPTC", "SWDNBC", "SWUPBC", "LWDNTC", "LWUPTC",
    "LWDNBC", "LWUPBC",
)
HEATING_FIELDS = ("RTHRATLW", "RTHRATSW", "RTHRATEN")
ACCUMULATED_FIELDS = ("ACSWDNB", "ACLWDNB")


class AnalysisError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise AnalysisError(message)


def relpath(path: Path, base: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        try:
            return path.relative_to(base.resolve()).as_posix()
        except ValueError:
            return os.path.relpath(path, ROOT)


def find_case(entry: Any, label: str, receipt_base: Path) -> Path:
    """Accept runner receipt case objects or direct paths."""
    candidates: list[Any] = []
    if isinstance(entry, str):
        candidates.append(entry)
    elif isinstance(entry, dict):
        for key in ("case_dir_relative", "case_dir", "case", "path", "directory", "run_dir", "output_dir"):
            if key in entry:
                candidates.append(entry[key])
        if "history_file" in entry:
            candidates.append(Path(str(entry["history_file"])).parent)
    for candidate in candidates:
        if not isinstance(candidate, (str, Path)):
            continue
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = receipt_base / path
        if path.is_dir():
            return path.resolve()
    fail(f"suite receipt has no readable {label} case directory: {entry!r}")


def case_member(pair: dict[str, Any], scheme: str) -> Any:
    aliases = {"ra4": ("4", "ra4", "rrtmg4", "rrtmg", "baseline", "reference"),
               "ra37": ("37", "ra37", "rrtmgp37", "rrtmgp", "port", "candidate")}[scheme]
    for key in aliases:
        if key in pair:
            return pair[key]
    cases = pair.get("cases")
    if isinstance(cases, dict):
        for key in aliases:
            if key in cases:
                return cases[key]
    fail(f"pair has no {scheme} case path (accepted keys: {', '.join(aliases)})")


def pair_paths(pair: dict[str, Any], receipt_base: Path, index: int) -> dict[str, Path]:
    initial_entry = next((pair[k] for k in ("initial", "init", "initial_case", "source_case", "initialization") if k in pair), None)
    initial = find_case(initial_entry, f"pair {index} initial", receipt_base) if initial_entry is not None else None
    ra4 = find_case(case_member(pair, "ra4"), f"pair {index} ra4", receipt_base)
    ra37 = find_case(case_member(pair, "ra37"), f"pair {index} ra37", receipt_base)
    if initial is None:
        for root in (ra4, ra37):
            possible = root.parent / "initial"
            if possible.is_dir():
                initial = possible.resolve()
                break
    if initial is None:
        fail(f"pair {index}: receipt must identify the shared initial case directory")
    return {"initial": initial, "ra4": ra4, "ra37": ra37}


def find_history(case_dir: Path) -> Path:
    preferred = case_dir / "wrfout_d01_1999-10-22_19:00:00"
    if preferred.is_file():
        return preferred
    matches = sorted(case_dir.glob("wrfout_d01_*"))
    matches = [path for path in matches if path.is_file()]
    if not matches:
        fail(f"{case_dir}: no WRF history output found")
    return matches[0]


def bytes_of_variable(var: netCDF4.Variable) -> tuple[bytes, bytes | None]:
    raw = var[:]
    if np.ma.isMaskedArray(raw):
        mask = np.ma.getmaskarray(raw).tobytes(order="C")
        raw = np.ma.getdata(raw)
    else:
        mask = None
    array = np.asarray(raw)
    return array.tobytes(order="C"), mask


def compare_initial_arrays(initial: Path, ra4: Path, ra37: Path) -> dict[str, Any]:
    paths = {name: case / "wrfinput_d01" for name, case in
             (("initial", initial), ("ra4", ra4), ("ra37", ra37))}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        fail("missing wrfinput_d01 file(s): " + ", ".join(missing))
    opened = {name: netCDF4.Dataset(path) for name, path in paths.items()}
    try:
        base_names = set(opened["initial"].variables)
        if any(set(ds.variables) != base_names for ds in opened.values()):
            fail("initial/RA4/RA37 wrfinput variable inventories differ")
        variable_hashes: dict[str, str] = {}
        differences: list[str] = []
        digest = hashlib.sha256()
        for name in sorted(base_names):
            encoded_name = name.encode("utf-8")
            digest.update(len(encoded_name).to_bytes(4, "little"))
            digest.update(encoded_name)
            base_var = opened["initial"].variables[name]
            base_bytes, base_mask = bytes_of_variable(base_var)
            digest.update(str(base_var.dtype).encode("ascii"))
            digest.update(np.asarray(base_var.shape, dtype=np.int64).tobytes())
            digest.update(base_bytes)
            if base_mask is not None:
                digest.update(base_mask)
            variable_hashes[name] = hashlib.sha256(base_bytes + (base_mask or b"")).hexdigest()
            for scheme in ("ra4", "ra37"):
                var = opened[scheme].variables[name]
                other_bytes, other_mask = bytes_of_variable(var)
                if (var.dtype != base_var.dtype or var.shape != base_var.shape or
                        other_bytes != base_bytes or other_mask != base_mask):
                    differences.append(f"{scheme}:{name}")
        if differences:
            fail("source initial-condition arrays are not bitwise identical: " + ", ".join(differences[:20]))
        ignored_attrs = ("RA_LW_PHYSICS", "RA_SW_PHYSICS")
        attr_differences: dict[str, list[str]] = {}
        for attr in sorted(set(opened["ra4"].ncattrs()) | set(opened["ra37"].ncattrs())):
            if attr in ignored_attrs:
                continue
            value4 = getattr(opened["ra4"], attr, None)
            value37 = getattr(opened["ra37"], attr, None)
            if value4 != value37:
                attr_differences[attr] = [str(value4), str(value37)]
        if attr_differences:
            fail(f"unexpected wrfinput global attribute differences: {attr_differences}")
        return {"bitwise_equal": True, "variable_count": len(base_names),
                "initial_array_sha256": digest.hexdigest(),
                "variable_sha256": variable_hashes,
                "ignored_expected_radiation_attributes": list(ignored_attrs)}
    finally:
        for ds in opened.values():
            ds.close()


def get_numeric(ds: netCDF4.Dataset, name: str, path: Path) -> np.ndarray:
    var = ds.variables[name]
    data = var[:]
    if np.ma.isMaskedArray(data):
        if np.ma.getmaskarray(data).any():
            fail(f"{path}: {name} contains masked values")
        data = np.ma.getdata(data)
    values = np.asarray(data)
    if values.dtype.kind not in "iuf":
        fail(f"{path}: {name} is not numeric")
    values = values.astype(np.float64)
    if not np.isfinite(values).all():
        fail(f"{path}: {name} contains non-finite values")
    return values


def get_times(ds: netCDF4.Dataset, path: Path) -> tuple[list[str], np.ndarray, float | None]:
    if "Times" in ds.variables:
        raw = ds.variables["Times"][:]
        strings = netCDF4.chartostring(raw)
        times = [str(item).strip() for item in strings]
    elif "XTIME" in ds.variables:
        xtime = get_numeric(ds, "XTIME", path).reshape(-1)
        times = [f"XTIME={value:.12g}" for value in xtime]
    else:
        fail(f"{path}: no Times or XTIME variable")
    if len(set(times)) != len(times):
        fail(f"{path}: time grid contains duplicate timestamps")
    xtime_difference = None
    if "Times" in ds.variables:
        try:
            stamps = [dt.datetime.strptime(item, "%Y-%m-%d_%H:%M:%S") for item in times]
            seconds = np.asarray([(stamp - stamps[0]).total_seconds() for stamp in stamps], dtype=np.float64)
        except ValueError as exc:
            raise AnalysisError(f"{path}: cannot derive elapsed seconds from Times") from exc
        if "XTIME" in ds.variables:
            xtime = get_numeric(ds, "XTIME", path).reshape(-1)
            xtime_seconds = xtime * 60.0
            if xtime_seconds.size != seconds.size:
                fail(f"{path}: XTIME length does not match Times")
            xtime_difference = float(np.max(np.abs(xtime_seconds - seconds)))
            xtime32 = xtime.astype(np.float32)
            xtime_roundoff = np.abs(np.spacing(xtime32).astype(np.float64)) * 60.0
            if np.any(np.abs(xtime_seconds - seconds) > xtime_roundoff + 1.0e-5):
                fail(f"{path}: XTIME is inconsistent with exact Times timestamps")
    elif "XTIME" in ds.variables:
        seconds = get_numeric(ds, "XTIME", path).reshape(-1) * 60.0
    else:
        fail(f"{path}: no Times or XTIME variable")
    if seconds.size != len(times) or not np.isfinite(seconds).all() or np.any(np.diff(seconds) <= 0.0):
        fail(f"{path}: invalid XTIME sequence")
    return times, seconds, xtime_difference


def verify_output_pair(path4: Path, path37: Path) -> tuple[netCDF4.Dataset, netCDF4.Dataset, dict[str, Any]]:
    ds4, ds37 = netCDF4.Dataset(path4), netCDF4.Dataset(path37)
    try:
        attrs = {}
        for ds, code in ((ds4, 4), (ds37, 37)):
            got = (int(getattr(ds, "RA_LW_PHYSICS", -1)), int(getattr(ds, "RA_SW_PHYSICS", -1)))
            expected = (code, code)
            if got != expected:
                fail(f"{ds.filepath()}: expected radiation attributes {expected}, got {got}")
            attrs[str(code)] = list(got)
        times4, seconds4, xtime_diff4 = get_times(ds4, path4)
        times37, seconds37, xtime_diff37 = get_times(ds37, path37)
        if times4 != times37 or not np.array_equal(seconds4, seconds37):
            fail(f"paired output time grids differ: {times4} vs {times37}")
        if len(times4) < 2:
            fail("history output must include initialization and at least one active timestep")
        if "AREA2D" not in ds4.variables or "AREA2D" not in ds37.variables:
            fail("both WRF outputs must contain AREA2D for area weighting")
        area4 = get_numeric(ds4, "AREA2D", path4)
        area37 = get_numeric(ds37, "AREA2D", path37)
        if area4.shape != area37.shape or not np.array_equal(area4, area37):
            fail("paired AREA2D grids differ")
        area = area37[1] if area37.ndim == 3 else area37
        if area.ndim != 2 or np.any(area <= 0.0):
            fail("AREA2D must be positive and shaped (south_north,west_east)")
        meta = {"radiation_attributes": attrs, "times": times4,
                "seconds_from_start": seconds4.tolist(), "active_time_index_start": 1,
                "xtime_max_difference_seconds": {"ra4": xtime_diff4, "ra37": xtime_diff37},
                "area_m2_min": float(area.min()), "area_m2_max": float(area.max()),
                "grid_shape": list(area.shape)}
        return ds4, ds37, {**meta, "area": area}
    except Exception:
        ds4.close()
        ds37.close()
        raise


def area_mean(field: np.ndarray, area: np.ndarray) -> np.ndarray:
    weights = area / area.sum()
    if field.ndim == 3:
        return np.sum(field * weights[None, :, :], axis=(1, 2))
    if field.ndim == 4:
        return np.sum(field * weights[None, None, :, :], axis=(2, 3))
    fail(f"unsupported field rank for area mean: {field.shape}")


def time_metrics(field4: np.ndarray, field37: np.ndarray, area: np.ndarray,
                 seconds: np.ndarray) -> dict[str, Any]:
    t4 = area_mean(field4, area)
    t37 = area_mean(field37, area)
    delta = t37 - t4
    active_delta = delta[1:]
    return {
        "ra4_area_mean_final": float(t4[-1]),
        "ra37_area_mean_final": float(t37[-1]),
        "difference_area_mean_final": float(delta[-1]),
        "ra4_active_temporal_mean": float(t4[1:].mean()),
        "ra37_active_temporal_mean": float(t37[1:].mean()),
        "difference_active_temporal_mean": float(active_delta.mean()),
        "active_temporal_mean_bias": float(active_delta.mean()),
        "active_temporal_mean_rmse_of_domain_means": float(np.sqrt(np.mean(active_delta ** 2))),
        "max_abs_active_domain_mean_difference": float(np.max(np.abs(active_delta))),
        "time_minutes": (seconds / 60.0).tolist(),
        "ra4_area_mean_timeseries": t4.tolist(),
        "ra37_area_mean_timeseries": t37.tolist(),
        "difference_area_mean_timeseries": delta.tolist(),
        "spatial_sampling": {
            "first_active_record": weighted_spatial_stats(field4[1], field37[1], area),
            "final_record": weighted_spatial_stats(field4[-1], field37[-1], area),
            "standard_error_interpretation": "the SE-like scale applies the usual effective-sample-count formula under an unverified independent-gridpoint assumption; it is not a validated McICA ensemble-mean error or confidence interval. Legacy deterministic pressure-seeded streams may repeat one sample across homogeneous columns, producing zero spread despite unknown sampling uncertainty",
        },
    }


def weighted_spatial_stats(field4: np.ndarray, field37: np.ndarray,
                           area: np.ndarray) -> dict[str, Any]:
    weights = np.asarray(area, dtype=np.float64) / float(np.sum(area))
    effective_n = 1.0 / float(np.sum(weights ** 2))
    result: dict[str, Any] = {"effective_grid_sample_count": effective_n}
    for label, values in (("ra4", field4), ("ra37", field37),
                          ("paired_difference", field37 - field4)):
        values = np.asarray(values, dtype=np.float64)
        mean = float(np.sum(values * weights))
        variance = float(np.sum(weights * (values - mean) ** 2))
        correction = 1.0 - float(np.sum(weights ** 2))
        unbiased_variance = variance / correction if correction > 0.0 else 0.0
        result[label] = {
            "area_weighted_mean": mean,
            "area_weighted_population_std": math.sqrt(max(0.0, variance)),
            "paired_area_difference_standard_error": (
                math.sqrt(max(0.0, unbiased_variance) / effective_n)
                if label == "paired_difference" else None),
        }
    return result


def weighted_spacetime_metrics(a: np.ndarray, b: np.ndarray, area: np.ndarray,
                               seconds: np.ndarray) -> dict[str, Any]:
    # Exclude the shared zero-initialized record; associate each active record
    # with its preceding interval and exact horizontal cell areas.
    delta = b[1:] - a[1:]
    dt = np.diff(seconds)
    if np.any(dt <= 0.0):
        fail("nonpositive output interval")
    tweight = dt
    weights = (tweight[:, None, None] * (area / area.sum())[None, :, :])
    weights = np.broadcast_to(weights, delta.shape)
    norm = float(weights.sum())
    return {"bias_time_space": float(np.sum(delta * weights) / norm),
            "rmse_time_space": float(np.sqrt(np.sum(delta * delta * weights) / norm)),
            "max_abs_time_space": float(np.max(np.abs(delta))),
            "active_spacetime_samples": int(delta.size),
            "temporal_weighting": "preceding-interval duration weights on active endpoint records; area-weighted grid cells"}


def derive_cre(fields: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    cre: dict[str, np.ndarray] = {}
    pairs = {"SW_CRE_SURFACE_DOWN": ("SWDNB", "SWDNBC"),
             "LW_CRE_SURFACE_DOWN": ("LWDNB", "LWDNBC")}
    for name, (allsky, clearsky) in pairs.items():
        if allsky in fields and clearsky in fields:
            cre[name] = fields[allsky] - fields[clearsky]
    if all(key in fields for key in ("SWDNT", "SWUPT", "SWDNTC", "SWUPTC")):
        cre["SW_CRE_TOA_NET"] = ((fields["SWDNT"] - fields["SWUPT"]) -
                                 (fields["SWDNTC"] - fields["SWUPTC"]))
    if all(key in fields for key in ("LWDNT", "LWUPT", "LWDNTC", "LWUPTC")):
        cre["LW_CRE_TOA_NET"] = ((fields["LWDNT"] - fields["LWUPT"]) -
                                 (fields["LWDNTC"] - fields["LWUPTC"]))
    return cre


def accumulator_closure(ds: netCDF4.Dataset, path: Path, field: str,
                        flux: str, seconds: np.ndarray, area: np.ndarray) -> dict[str, Any] | None:
    if field not in ds.variables or flux not in ds.variables:
        return None
    accum = get_numeric(ds, field, path)
    flux_values = get_numeric(ds, flux, path)
    if accum.shape != flux_values.shape or accum.ndim != 3:
        return {"status": "UNAVAILABLE", "reason": f"unexpected shapes {accum.shape} {flux_values.shape}"}
    d_acc = accum[1:] - accum[:-1]
    dt = np.diff(seconds)
    current = flux_values[1:] * dt[:, None, None]
    previous = flux_values[:-1] * dt[:, None, None]
    trapezoid = 0.5 * (flux_values[1:] + flux_values[:-1]) * dt[:, None, None]
    weights = np.broadcast_to((area / area.sum())[None, :, :], d_acc.shape)
    candidates = {"current_flux_times_dt": current, "previous_flux_times_dt": previous,
                  "endpoint_trapezoid": trapezoid}
    scores = {}
    for name, expected in candidates.items():
        residual = d_acc - expected
        scores[name] = {"area_weighted_mean_abs_closure_error_j_m2": float(np.sum(np.abs(residual) * weights) / (d_acc.shape[0])),
                        "max_abs_closure_error_j_m2": float(np.max(np.abs(residual)))}
    best = min(scores, key=lambda name: scores[name]["area_weighted_mean_abs_closure_error_j_m2"])
    # Float32 accumulators round each large cumulative value; 2 ULPs for both
    # endpoints plus 2 ULPs in the flux-times-step product form the tolerance.
    expected = candidates["current_flux_times_dt"]
    acc32 = accum.astype(np.float32)
    flux32 = flux_values.astype(np.float32)
    acc_ulp = (np.abs(np.spacing(acc32[1:]).astype(np.float64)) +
               np.abs(np.spacing(acc32[:-1]).astype(np.float64)))
    product32 = (flux32[1:] * dt[:, None, None]).astype(np.float32)
    product_ulp = np.abs(np.spacing(product32).astype(np.float64))
    tolerance = 2.0 * acc_ulp + 2.0 * product_ulp
    residual = d_acc - expected
    within = np.abs(residual) <= tolerance
    return {"status": "PASS" if np.all(within) else "CHECK",
            "required_contract": "current_flux_times_dt",
            "best_diagnostic_convention": best, "candidate_scores": scores,
            "max_abs_error_j_m2": float(np.max(np.abs(residual))),
            "max_float32_roundoff_tolerance_j_m2": float(np.max(tolerance)),
            "fraction_samples_within_roundoff_tolerance": float(np.mean(within)),
            "active_intervals": int(d_acc.shape[0]),
            "note": "tests current, previous, and endpoint-trapezoid flux integration; zero-init record is used only as accumulator baseline"}


def profile_metrics(field4: np.ndarray, field37: np.ndarray, area: np.ndarray,
                    seconds: np.ndarray) -> dict[str, Any]:
    if field4.shape != field37.shape or field4.ndim != 4:
        fail(f"heating profile fields are not matching rank-4 arrays: {field4.shape}/{field37.shape}")
    t4 = area_mean(field4, area) * 86400.0
    t37 = area_mean(field37, area) * 86400.0
    delta = t37 - t4
    active = delta[1:]
    sample_weights = np.diff(seconds)[:, None, None, None] * (area / area.sum())[None, None, :, :]
    normalization = float(np.diff(seconds).sum())
    layer_bias = np.sum((field37[1:] - field4[1:]) * 86400.0 * sample_weights,
                        axis=(0, 2, 3)) / normalization
    layer_rmse = np.sqrt(np.sum(((field37[1:] - field4[1:]) * 86400.0) ** 2 * sample_weights,
                               axis=(0, 2, 3)) / normalization)
    layer_max = np.max(np.abs((field37[1:] - field4[1:]) * 86400.0), axis=(0, 2, 3))
    return {
        "units": "K/day of potential-temperature tendency",
        "vertical_aggregation": "none; per-model-layer profiles, horizontal area weighted",
        "ra4_active_temporal_mean_profile": t4[1:].mean(axis=0).tolist(),
        "ra37_active_temporal_mean_profile": t37[1:].mean(axis=0).tolist(),
        "difference_active_temporal_mean_profile": active.mean(axis=0).tolist(),
        "ra4_first_active_profile": t4[1].tolist(),
        "ra37_first_active_profile": t37[1].tolist(),
        "difference_first_active_profile": delta[1].tolist(),
        "layerwise_bias_active_spacetime": layer_bias.tolist(),
        "layerwise_rmse_active_spacetime": layer_rmse.tolist(),
        "layerwise_max_abs_active_spacetime": layer_max.tolist(),
        "layer_count": int(field4.shape[1]),
        "time_minutes": (seconds / 60.0).tolist(),
    }


def cre_metrics(cre4: dict[str, np.ndarray], cre37: dict[str, np.ndarray],
                area: np.ndarray, seconds: np.ndarray) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for name in sorted(set(cre4) & set(cre37)):
        a, b = cre4[name], cre37[name]
        if a.shape != b.shape:
            fail(f"{name}: paired CRE shapes differ")
        rows[name] = {"ra4": series_summary(a, area),
                      "ra37": series_summary(b, area),
                      "rrtmgp_minus_rrtmg": time_metrics(a, b, area, seconds),
                      "units": "W m-2",
                      "definition": "all-sky minus clear-sky; TOA is net downward minus upward"}
    return rows


def series_summary(values: np.ndarray, area: np.ndarray) -> dict[str, Any]:
    series = area_mean(values, area)
    return {"area_mean_final": float(series[-1]),
            "active_temporal_mean": float(series[1:].mean()),
            "area_mean_timeseries": series.tolist()}


def source_identity() -> dict[str, Any]:
    try:
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              check=True, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        head = None
    def binary_sha(path: Path) -> str | None:
        if not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    return {"source_head_sha": head,
            "analysis_tool_sha256": binary_sha(Path(__file__)),
            "current_wrf_executable_sha256": binary_sha(ROOT / "WRF/main/wrf.exe"),
            "current_ideal_executable_sha256": binary_sha(ROOT / "WRF/main/ideal.exe")}


def analyze_pair(pair: dict[str, Any], index: int, receipt_base: Path,
                 output_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scenario = str(pair.get("scenario", pair.get("name", f"pair-{index:02d}")))
    paths = pair_paths(pair, receipt_base, index)
    history = {scheme: find_history(paths[scheme]) for scheme in ("ra4", "ra37")}
    for scheme, case_dir in (("ra4", paths["ra4"]), ("ra37", paths["ra37"])):
        log = case_dir / "wrf.log"
        if not log.is_file() or "SUCCESS COMPLETE WRF" not in log.read_text(errors="replace"):
            fail(f"{scenario}: {scheme} case lacks SUCCESS COMPLETE WRF in wrf.log")
    input_report = compare_initial_arrays(paths["initial"], paths["ra4"], paths["ra37"])
    ds4, ds37, meta = verify_output_pair(history["ra4"], history["ra37"])
    area = meta.pop("area")
    try:
        all_fields: dict[str, dict[str, np.ndarray]] = {"ra4": {}, "ra37": {}}
        field_rows: list[dict[str, Any]] = []
        surface_data: dict[str, dict[str, np.ndarray]] = {"ra4": {}, "ra37": {}}
        for name in SURFACE_FIELDS:
            if name not in ds4.variables or name not in ds37.variables:
                continue
            a, b = get_numeric(ds4, name, history["ra4"]), get_numeric(ds37, name, history["ra37"])
            if a.shape != b.shape or a.ndim != 3:
                fail(f"{scenario}:{name}: paired surface field shape mismatch {a.shape}/{b.shape}")
            if a.shape[0] != len(meta["times"]) or a.shape[1:] != area.shape:
                fail(f"{scenario}:{name}: unexpected history dimensions {a.shape}")
            unit4 = str(getattr(ds4.variables[name], "units", ""))
            unit37 = str(getattr(ds37.variables[name], "units", ""))
            if unit4 != unit37:
                fail(f"{scenario}:{name}: units differ: {unit4!r} vs {unit37!r}")
            surface_data["ra4"][name], surface_data["ra37"][name] = a, b
            metrics = time_metrics(a, b, area, np.asarray(meta["seconds_from_start"]))
            metrics.update(weighted_spacetime_metrics(a, b, area, np.asarray(meta["seconds_from_start"])))
            metrics["units"] = unit4
            field_rows.append({"scenario": scenario, "field": name, "kind": "surface_flux", **{
                key: value for key, value in metrics.items() if not isinstance(value, (list, dict))
            }})
            all_fields["ra4"][name], all_fields["ra37"][name] = a, b
        missing_core = [name for name in ("SWDOWN", "GLW", "SWDNB", "SWUPB", "SWDDIR", "SWDDIF", "LWUPT", "SWDNT")
                        if name not in surface_data["ra4"]]
        if missing_core:
            fail(f"{scenario}: missing comparison surface fields: {', '.join(missing_core)}")

        cre4, cre37 = derive_cre(all_fields["ra4"]), derive_cre(all_fields["ra37"])
        cre_report = cre_metrics(cre4, cre37, area, np.asarray(meta["seconds_from_start"]))
        for name, metric in cre_report.items():
            comp = metric["rrtmgp_minus_rrtmg"]
            field_rows.append({"scenario": scenario, "field": name, "kind": "cloud_radiative_effect",
                               "units": metric["units"],
                               "difference_area_mean_final": comp["difference_area_mean_final"],
                               "difference_active_temporal_mean": comp["difference_active_temporal_mean"],
                               "active_temporal_mean_rmse_of_domain_means": comp["active_temporal_mean_rmse_of_domain_means"],
                               "max_abs_active_domain_mean_difference": comp["max_abs_active_domain_mean_difference"]})

        heating_report: dict[str, Any] = {}
        for name in HEATING_FIELDS:
            if name not in ds4.variables or name not in ds37.variables:
                continue
            a, b = get_numeric(ds4, name, history["ra4"]), get_numeric(ds37, name, history["ra37"])
            if a.shape != b.shape or a.ndim != 4 or a.shape[0] != len(meta["times"]) or a.shape[2:] != area.shape:
                fail(f"{scenario}:{name}: paired heating field shape mismatch {a.shape}/{b.shape}")
            profile = profile_metrics(a, b, area, np.asarray(meta["seconds_from_start"]))
            profile["source_units"] = str(getattr(ds4.variables[name], "units", ""))
            heating_report[name] = profile
            for layer, (bias, rmse, maxabs) in enumerate(zip(profile["layerwise_bias_active_spacetime"],
                                                               profile["layerwise_rmse_active_spacetime"],
                                                               profile["layerwise_max_abs_active_spacetime"])):
                field_rows.append({"scenario": scenario, "field": name, "kind": "heating_layer_theta_tendency",
                                   "units": "K/day", "layer_zero_based": layer,
                                   "bias_active_spacetime": bias, "rmse_active_spacetime": rmse,
                                   "max_abs_active_spacetime": maxabs})

        first_active_cloud_fraction = None
        if "CLDFRA" in ds4.variables and "CLDFRA" in ds37.variables:
            cf4 = get_numeric(ds4, "CLDFRA", history["ra4"])
            cf37 = get_numeric(ds37, "CLDFRA", history["ra37"])
            if cf4.shape != cf37.shape or cf4.ndim != 4:
                fail(f"{scenario}: CLDFRA shapes differ or are not rank 4")
            first_active_equal = np.array_equal(cf4[1], cf37[1])
            if not first_active_equal:
                fail(f"{scenario}: first-active-record CLDFRA differs between paired radiation runs")
            first_active_cloud_fraction = {
                "first_active_record_bitwise_equal": True,
                "first_active_max_abs_difference": float(np.max(np.abs(cf37[1] - cf4[1]))),
                "first_active_max_ra4": float(np.max(cf4[1])),
                "first_active_max_ra37": float(np.max(cf37[1])),
                "sha256_ra4_first_active": hashlib.sha256(cf4[1].tobytes(order="C")).hexdigest(),
                "sha256_ra37_first_active": hashlib.sha256(cf37[1].tobytes(order="C")).hexdigest(),
            }

        accum_report = {}
        accum_map = {"ACSWDNB": "SWDNB", "ACLWDNB": "LWDNB"}
        for accum, flux in accum_map.items():
            accum_report[accum] = {
                "ra4": accumulator_closure(ds4, history["ra4"], accum, flux,
                                           np.asarray(meta["seconds_from_start"]), area),
                "ra37": accumulator_closure(ds37, history["ra37"], accum, flux,
                                            np.asarray(meta["seconds_from_start"]), area),
            }
            if accum in ds4.variables and accum in ds37.variables:
                av4 = get_numeric(ds4, accum, history["ra4"])
                av37 = get_numeric(ds37, accum, history["ra37"])
                endpoint = area_mean(av37[-1:] - av4[-1:], area)[0]
                duration = float(meta["seconds_from_start"][-1] - meta["seconds_from_start"][0])
                accum_report[accum]["rrtmgp_minus_rrtmg_endpoint_j_m2_area_mean"] = float(endpoint)
                accum_report[accum]["mean_flux_difference_from_accum_endpoint_w_m2"] = float(endpoint / duration)
                accum_report[accum]["duration_seconds"] = duration
                field_rows.append({"scenario": scenario, "field": accum, "kind": "accumulated_energy",
                                   "units": "J m-2", "difference_area_mean_endpoint": float(endpoint),
                                   "duration_seconds": duration,
                                   "mean_flux_difference_from_accumulator_w_m2": float(endpoint / duration)})
        closure_failures = [f"{scheme}:{name}" for name, per_scheme in accum_report.items()
                            for scheme, detail in per_scheme.items()
                            if isinstance(detail, dict) and detail.get("status") != "PASS"]
        if closure_failures:
            fail(f"{scenario}: required current-flux accumulator closure failed/check-needed for " +
                 ", ".join(closure_failures))

        plot_dir = output_dir / scenario
        plot_dir.mkdir(parents=True, exist_ok=True)
        plot_surface(scenario, surface_data, area, np.asarray(meta["seconds_from_start"]), plot_dir)
        plot_heating(scenario, heating_report, plot_dir)
        plot_cre(scenario, cre4, cre37, area, np.asarray(meta["seconds_from_start"]), plot_dir)

        report = {
            "scenario": scenario,
            "microphysics": pair.get("mp_physics"),
            "overlap": pair.get("overlap"),
            "species": pair.get("species"),
            "forcing_input_sha256": pair.get("forcing_input_sha256"),
            "fixture": pair.get("fixture"),
            "case_paths": {name: relpath(path, receipt_base) for name, path in paths.items()},
            "history_files": {name: relpath(path, receipt_base) for name, path in history.items()},
            "initial_condition_identity": input_report,
            "first_active_cloud_fraction": first_active_cloud_fraction,
            "time_grid_and_domain": {key: value for key, value in meta.items() if key != "area"},
            "surface_fields": {name: {"units": str(getattr(ds4.variables[name], "units", "")),
                                       "metrics": time_metrics(surface_data["ra4"][name],
                                                                surface_data["ra37"][name], area,
                                                                np.asarray(meta["seconds_from_start"])),
                                       "spacetime_difference_metrics": weighted_spacetime_metrics(
                                           surface_data["ra4"][name], surface_data["ra37"][name], area,
                                           np.asarray(meta["seconds_from_start"]))}
                               for name in surface_data["ra4"]},
            "cloud_radiative_effects": cre_report,
            "heating_profiles": heating_report,
            "accumulator_closure_and_endpoint_energy": accum_report,
            "plot_files": {
                name: [f"{scenario}/{stem}.{suffix}" for suffix in ("png", "svg")]
                for name, stem in (("surface", "surface_flux_timeseries"),
                                   ("heating", "heating_profiles"),
                                   ("cre", "cloud_radiative_effects"))
            },
            "interpretation_note": "Differences are descriptive for this paired SCM setup; no physical-accuracy or climate-bias claim is implied.",
        }
        return report, field_rows
    finally:
        ds4.close()
        ds37.close()


def plot_surface(scenario: str, data: dict[str, dict[str, np.ndarray]], area: np.ndarray,
                 seconds: np.ndarray, output: Path) -> None:
    fields = [name for name in ("SWDOWN", "SWDNB", "SWUPB", "SWDNT", "GLW", "LWDNB", "LWUPT", "SWDDIR")
              if name in data["ra4"]]
    if not fields:
        return
    ncols = 2
    nrows = math.ceil(len(fields) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 3.0 * nrows), squeeze=False, constrained_layout=True)
    minutes = seconds[1:] / 60.0
    for ax, name in zip(axes.flat, fields):
        a, b = area_mean(data["ra4"][name], area)[1:], area_mean(data["ra37"][name], area)[1:]
        ax.plot(minutes, a, marker="o", markersize=3, label="RRTMG 4/4")
        ax.plot(minutes, b, marker="s", markersize=3, label="RRTMGP 37/37")
        ax.set_title(name)
        ax.set_xlabel("Time from initialization (min)")
        ax.set_ylabel("Flux (W m$^{-2}$)")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
    for ax in list(axes.flat)[len(fields):]:
        ax.set_visible(False)
    fig.suptitle(f"{scenario}: area-weighted surface radiation")
    fig.savefig(output / "surface_flux_timeseries.png", dpi=200)
    fig.savefig(output / "surface_flux_timeseries.svg")
    plt.close(fig)


def plot_heating(scenario: str, heating: dict[str, Any], output: Path) -> None:
    names = [name for name in HEATING_FIELDS if name in heating]
    if not names:
        return
    fig, axes = plt.subplots(1, len(names), figsize=(4.5 * len(names), 7), squeeze=False, constrained_layout=True)
    for ax, name in zip(axes[0], names):
        item = heating[name]
        z = np.arange(item["layer_count"])
        ax.plot(item["ra4_active_temporal_mean_profile"], z, label="RRTMG 4/4")
        ax.plot(item["ra37_active_temporal_mean_profile"], z, label="RRTMGP 37/37")
        ax.plot(item["difference_active_temporal_mean_profile"], z, label="Difference", linestyle="--")
        ax.axvline(0.0, color="black", linewidth=0.7)
        ax.set_title(name)
        ax.set_xlabel("Potential-temperature tendency (K/day)")
        ax.set_ylabel("Model layer (bottom-up index)")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle(f"{scenario}: active-record heating profiles (horizontal area-weighted)")
    fig.savefig(output / "heating_profiles.png", dpi=200)
    fig.savefig(output / "heating_profiles.svg")
    plt.close(fig)


def plot_cre(scenario: str, cre4: dict[str, np.ndarray], cre37: dict[str, np.ndarray],
             area: np.ndarray, seconds: np.ndarray, output: Path) -> None:
    names = sorted(set(cre4) & set(cre37))
    if not names:
        return
    fig, axes = plt.subplots(len(names), 1, figsize=(9, 2.7 * len(names)), squeeze=False, constrained_layout=True)
    minutes = seconds[1:] / 60.0
    for ax, name in zip(axes[:, 0], names):
        a, b = area_mean(cre4[name], area)[1:], area_mean(cre37[name], area)[1:]
        ax.plot(minutes, a, marker="o", markersize=3, label="RRTMG 4/4")
        ax.plot(minutes, b, marker="s", markersize=3, label="RRTMGP 37/37")
        ax.set_title(name)
        ax.set_ylabel("W m-2")
        ax.set_xlabel("Time from initialization (min)")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle(f"{scenario}: all-sky minus clear-sky CRE")
    fig.savefig(output / "cloud_radiative_effects.png", dpi=200)
    fig.savefig(output / "cloud_radiative_effects.svg")
    plt.close(fig)


def plot_overview(reports: list[dict[str, Any]], output: Path) -> None:
    labels = {
        "mp2-control": "MP2 control",
        "mp2-clear-sky-overlap0": "MP2 clear-sky control",
        "mp4-mixed": "MP4 mixed initial condensate",
        "mp4-liquid-only": "MP4 liquid-only initial condensate",
        "mp4-ice-only": "MP4 ice-only initial condensate",
        "mp4-snow-only": "MP4 snow-only initial condensate",
        "mp5-mixed": "MP5 mixed initial condensate",
    }
    names = [item["scenario"] for item in reports]
    display = [labels.get(name, name) for name in names]
    swdnb = [item["surface_fields"]["SWDNB"]["metrics"]["difference_active_temporal_mean"]
             for item in reports]
    glw = [item["surface_fields"]["GLW"]["metrics"]["difference_active_temporal_mean"]
           for item in reports]
    heating = [max(item["heating_profiles"].get("RTHRATEN", {}).get(
                       "layerwise_max_abs_active_spacetime", [0.0])) for item in reports]
    fig, axes = plt.subplots(1, 3, figsize=(16, 6.8), constrained_layout=True)
    colors = ["#7b3294" if "clear" in name else "#008837" for name in names]
    for ax, values, title, xlabel in (
        (axes[0], swdnb, "Surface downward shortwave", "Active-time mean difference (W m$^{-2}$)"),
        (axes[1], glw, "Surface downward longwave", "Active-time mean difference (W m$^{-2}$)"),
        (axes[2], heating, "Total potential-temperature tendency", "Maximum |difference| (K day$^{-1}$)"),
    ):
        ax.barh(display, values, color=colors)
        ax.axvline(0.0, color="black", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.grid(axis="x", alpha=0.25)
        ax.invert_yaxis()
    fig.suptitle("WRF SCM paired comparison: RRTMGP 37/37 minus RRTMG 4/4\n"
                 "Area-weighted active-time flux means; layerwise space-time maximum for heating")
    fig.savefig(output / "overview.png", dpi=220)
    fig.savefig(output / "overview.svg")
    plt.close(fig)


def find_pairs(suite: dict[str, Any]) -> list[dict[str, Any]]:
    pairs = suite.get("pairs")
    if isinstance(pairs, list) and pairs:
        return pairs
    # Also accept direct suite members for one-pair receipts.
    if any(key in suite for key in ("ra4", "rrtmg4", "rrtmg")) and any(
            key in suite for key in ("ra37", "rrtmgp37", "rrtmgp")):
        return [suite]
    fail("suite receipt must contain a non-empty `pairs` list")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path,
                        help="paired-runner receipt.json")
    parser.add_argument("--output-directory", type=Path,
                        default=Path("validation/rrtmgp37/rrtmg-comparison"),
                        help="directory for JSON/CSV metrics and PNG/SVG figures")
    args = parser.parse_args()
    suite_path = args.suite.expanduser().resolve()
    outdir = args.output_directory.expanduser()
    if not outdir.is_absolute():
        outdir = ROOT / outdir
    outdir = outdir.resolve()
    try:
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        if suite.get("status") != "PASS":
            fail(f"paired-runner receipt status is not PASS: {suite.get('status')!r}")
        pairs = find_pairs(suite)
        outdir.mkdir(parents=True, exist_ok=True)
        reports = []
        table: list[dict[str, Any]] = []
        for index, pair in enumerate(pairs, start=1):
            report, rows = analyze_pair(pair, index, suite_path.parent, outdir)
            reports.append(report)
            table.extend(rows)
        plot_overview(reports, outdir)
        # Keep generated vector files reviewable by git's whitespace checks.
        for svg in outdir.rglob("*.svg"):
            svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines())
                           + "\n", encoding="utf-8")
        json_report = {
            "schema": "WRF_RRTMG_4_4_VS_RRTMGP_37_37_ANALYSIS_V1",
            **source_identity(),
            "suite_receipt": os.path.relpath(suite_path, ROOT),
            "suite_reference_directory": os.path.relpath(suite_path.parent, ROOT),
            "suite_status": suite.get("status"),
            "suite_run_metadata": {
                "run_minutes": suite.get("run_minutes"),
                "history_interval_seconds": suite.get("history_interval_seconds"),
                "history_interval_minutes": suite.get("history_interval_minutes"),
                "receipt_sha256": hashlib.sha256(suite_path.read_bytes()).hexdigest(),
                "runner_sha256": suite.get("executable_environment", {}).get("runner_sha256"),
                "source_head_sha": suite.get("executable_environment", {}).get("git_head"),
                "wrf_executable_sha256": suite.get("executable_environment", {}).get("wrf_executable_sha256"),
                "ideal_executable_sha256": suite.get("executable_environment", {}).get("ideal_executable_sha256"),
                "gfortran_version": suite.get("executable_environment", {}).get("gfortran_version"),
                "configure_wrf_settings": suite.get("executable_environment", {}).get("configure_wrf_settings"),
                "environment": {key: value for key, value in suite.get("executable_environment", {}).get("environment", {}).items()
                                if key in {"OMP_NUM_THREADS", "NETCDF", "JASPERINC", "JASPERLIB"}},
            },
            "pairs_analyzed": len(reports),
            "analysis": {
                "difference_sign": "RRTMGP 37/37 minus RRTMG 4/4",
                "initialization_record": "excluded from active flux/heating temporal metrics; retained as accumulator baseline",
                "spatial_weighting": "AREA2D weights; output requires identical positive area grids",
                "spatial_variability_note": "first-active/final gridpoint spread and paired-difference SE are descriptive only; they do not imply independent columns or confidence intervals. Homogeneous native-RRTMG random streams can repeat the same sample across columns, so grid size alone does not establish Monte Carlo convergence.",
                "temporal_weighting": "uniform history records for temporal means; preceding-interval duration weights for spacetime bias/RMSE",
                "heating_conversion": "RTHRAT* source K s-1 multiplied by 86400 to potential-temperature tendency K day-1; profiles reported per layer with no vertical averaging",
                "cloud_radiative_effect": "all-sky minus clear-sky flux within each scheme; TOA net is downward minus upward; reported difference is RRTMGP minus RRTMG",
                "accumulated_energy": "endpoint difference in ACSWDNB/ACLWDNB J m-2; mean flux difference is endpoint delta divided by elapsed seconds",
                "accumulator_closure": "compares each interval accumulator increment against current, previous, and endpoint-trapezoid flux times elapsed seconds; reports float32 ULP-based closure tolerance",
                "accuracy_claim": "none; this is a paired descriptive comparison, not a physical validation",
            },
            "pairs": reports,
        }
        (outdir / "comparison.json").write_text(json.dumps(json_report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                                                   encoding="utf-8")
        if table:
            keys = sorted({key for row in table for key in row})
            with (outdir / "comparison_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=keys, lineterminator="\n")
                writer.writeheader()
                writer.writerows(table)
        print(json.dumps({"status": "PASS", "pairs_analyzed": len(reports),
                          "output_directory": relpath(outdir, ROOT),
                          "json": (outdir / "comparison.json").as_posix(),
                          "csv": (outdir / "comparison_metrics.csv").as_posix()}, indent=2))
        return 0
    except (AnalysisError, OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
