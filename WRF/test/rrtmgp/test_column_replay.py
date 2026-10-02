#!/usr/bin/env python3
"""Capture one real WRF radiation column and validate it against a replay."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import netCDF4

import test_cloud_scm
import test_surface_scm
from compare_column_replay import compare, read_result


WRF_ROOT = test_surface_scm.WRF_ROOT
DATA_DIR = test_surface_scm.DATA_DIR
SUCCESS_TOKEN = "SUCCESS COMPLETE WRF"
RAW_FIELDS = {"DP_HPA", "CF", "QC", "QI", "QS", "T", "QV", "REL", "REI", "RES",
              "GRAVITY", "MP_PHYSICS", "PI", "P_HPA", "SOURCE_T", "AMD_W"}
Q_NAMES = ("QC", "QI", "QS")
SOURCE_NAMES = {"QC": "SOURCE_QC", "QI": "SOURCE_QI", "QS": "SOURCE_QS"}
FLAG_NAMES = {"QC": "F_QC", "QI": "F_QI", "QS": "F_QS"}


class ReplayError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ReplayError(message)


def parse_fortran_real(token: str, source: Path, line: int) -> float:
    try:
        value = float(token.replace("D", "E").replace("d", "e"))
    except ValueError as exc:
        raise ReplayError(f"{source}:{line}: invalid numeric token {token!r}") from exc
    if not np.isfinite(value):
        fail(f"{source}:{line}: non-finite numeric token {token!r}")
    return value


def read_records(path: Path, magic: str, header_count: int) -> tuple[list[str], dict[str, np.ndarray]]:
    """Read the trace format: record headers followed by Fortran-order values."""
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines:
        fail(f"{path}: empty capture")
    first = lines[0].split()
    if not first or first[0] != magic:
        fail(f"{path}: expected {magic}, got {lines[0]!r}")
    if len(first) != header_count:
        fail(f"{path}: expected {header_count-1} header fields after magic")
    records: dict[str, np.ndarray] = {}
    pos = 1
    while pos < len(lines):
        if not lines[pos].strip():
            pos += 1
            continue
        line_no = pos + 1
        fields = lines[pos].split()
        pos += 1
        if len(fields) != 3:
            fail(f"{path}:{line_no}: expected name and two dimensions")
        name = fields[0].upper()
        if name in records:
            fail(f"{path}:{line_no}: duplicate record {name}")
        try:
            nrow, ncol = int(fields[1]), int(fields[2])
        except ValueError as exc:
            raise ReplayError(f"{path}:{line_no}: invalid dimensions for {name}") from exc
        if nrow < 1 or ncol < 1:
            fail(f"{path}:{line_no}: nonpositive dimensions for {name}")
        count = nrow * ncol
        values: list[float] = []
        while len(values) < count and pos < len(lines):
            row_line = pos + 1
            tokens = lines[pos].split()
            pos += 1
            values.extend(parse_fortran_real(token, path, row_line) for token in tokens)
            if len(values) > count:
                fail(f"{path}:{row_line}: too many values in {name}")
        if len(values) != count:
            fail(f"{path}: {name} expected {count} values, found {len(values)}")
        records[name] = np.asarray(values, dtype=np.float64).reshape((nrow, ncol), order="F")
    return first, records


def read_raw(path: Path) -> tuple[str, int, int, dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RAW_V1":
        fail(f"{path}: empty raw capture")
    header = lines[1].split()
    if len(header) != 4:
        fail(f"{path}: invalid RRTMGP_RAW_V1 phase/index/layer header")
    phase = header[0].upper()
    try:
        i, j, nl = (int(v) for v in header[1:])
    except ValueError as exc:
        raise ReplayError(f"{path}: invalid raw i/j/nl header") from exc
    if phase not in {"LW", "SW"} or i < 1 or j < 1 or nl < 1:
        fail(f"{path}: invalid phase/index/layer count")
    records: dict[str, np.ndarray] = {}
    pos = 2
    while pos < len(lines):
        if not lines[pos].strip():
            pos += 1
            continue
        line_no = pos + 1
        fields = lines[pos].split()
        pos += 1
        if len(fields) != 2:
            fail(f"{path}:{line_no}: expected raw record name and length")
        name = fields[0].upper()
        if name in records:
            fail(f"{path}:{line_no}: duplicate raw record {name}")
        try:
            nvalue = int(fields[1])
        except ValueError as exc:
            raise ReplayError(f"{path}:{line_no}: invalid length for {name}") from exc
        if nvalue < 1:
            fail(f"{path}:{line_no}: nonpositive length for {name}")
        values: list[float] = []
        while len(values) < nvalue and pos < len(lines):
            value_line = pos + 1
            values.extend(parse_fortran_real(token, path, value_line)
                          for token in lines[pos].split())
            pos += 1
            if len(values) > nvalue:
                fail(f"{path}:{value_line}: too many values in {name}")
        if len(values) != nvalue:
            fail(f"{path}: {name} expected {nvalue} values, found {len(values)}")
        records[name] = np.asarray(values, dtype=np.float64)
    absent = sorted(RAW_FIELDS - records.keys())
    if absent:
        fail(f"{path}: raw snapshot missing required fields: {', '.join(absent)}")
    if len(records["DP_HPA"]) != nl:
        fail(f"{path}: DP_HPA count differs from raw nl={nl}")
    if "DRY_LAYER_MASS_KG_M2" in records:
        dry_mass = records["DRY_LAYER_MASS_KG_M2"]
        if dry_mass.shape != (nl,) or not np.isfinite(dry_mass).all() or np.any(dry_mass <= 0.0):
            fail(f"{path}: DRY_LAYER_MASS_KG_M2 must contain nl finite positive values")
    for field in ("CF", "QC", "QI", "QS", "T", "QV", "REL", "REI", "RES", "P_HPA", "SOURCE_T",
                  "SOURCE_P_PA", "PI"):
        if field == "SOURCE_P_PA" and field not in records:
            continue
        if len(records[field]) != nl:
            fail(f"{path}: {field} count differs from raw nl={nl}")
    for field in ("SOURCE_QC", "SOURCE_QI", "SOURCE_QS", "SOURCE_RE_CLOUD", "SOURCE_RE_ICE", "SOURCE_RE_SNOW"):
        if field in records and len(records[field]) != nl:
            fail(f"{path}: {field} count differs from raw nl={nl}")
    for field in ("HAS_REQC", "HAS_REQI", "HAS_REQS", "AMD_W", "GRAVITY", "MP_PHYSICS"):
        if field in records and records[field].size != 1:
            fail(f"{path}: {field} must be scalar")
    return phase, i, j, records


def read_input(path: Path) -> tuple[str, int, int, int, int, int, dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0].strip() not in {"RRTMGP_REPLAY_V1", "RRTMGP_REPLAY_V2", "RRTMGP_REPLAY_V3", "RRTMGP_REPLAY_V4", "RRTMGP_REPLAY_V5"}:
        fail(f"{path}: unsupported replay format version")
    header = lines[1].split()
    if len(header) != 6:
        fail(f"{path}: expected phase/nc/nl/overlap/seed/iceflag on line 2")
    phase = header[0].upper()
    try:
        nc, nl, overlap, seed, iceflag = (int(v) for v in header[1:])
    except ValueError as exc:
        raise ReplayError(f"{path}: invalid replay header integers") from exc
    if phase not in {"LW", "SW"} or min(nc, nl) < 1:
        fail(f"{path}: invalid replay phase or dimensions")
    # Reuse the generic row/column parser with a synthetic first line and parse
    # records after the independent replay header.
    temporary = path.with_suffix(path.suffix + ".records.tmp")
    temporary.write_text("RRTMGP_INPUT_V1\n" + "\n".join(lines[2:]) + "\n", encoding="ascii")
    try:
        _, records = read_records(temporary, "RRTMGP_INPUT_V1", 1)
    finally:
        temporary.unlink(missing_ok=True)
    if lines[0].strip() != "RRTMGP_REPLAY_V1":
        roughness = records.get("ICE_ROUGHNESS")
        if roughness is None or roughness.shape != (1, 1) or roughness.item() not in (1, 2, 3):
            fail(f"{path}: V2/V3 requires scalar ICE_ROUGHNESS in {{1, 2, 3}}")
    if lines[0].strip() in {"RRTMGP_REPLAY_V3", "RRTMGP_REPLAY_V4", "RRTMGP_REPLAY_V5"} and phase == "SW":
        policy = records.get("SW_BAND_PARTITION")
        if policy is None or policy.shape != (1, 1) or policy.item() != 1:
            fail(f"{path}: V3 SW requires scalar SW_BAND_PARTITION=1 (CCPP transition)")
    if lines[0].strip() == "RRTMGP_REPLAY_V4":
        policy = records.get("PRECIPITATION_OPTICS")
        if policy is None or policy.shape != (1, 1) or policy.item() != 1:
            fail(f"{path}: V4/V5 requires scalar PRECIPITATION_OPTICS=1")
        rain = records.get("RWP")
        if rain is None or rain.shape != (nc, nl) or np.any(rain < 0):
            fail(f"{path}: V4 requires nonnegative RWP matching column layers")
    if lines[0].strip() == "RRTMGP_REPLAY_V5":
        policy = records.get("PRECIPITATION_OPTICS")
        rain = records.get("RWP")
        if (policy is None) != (rain is None):
            fail(f"{path}: V5 precipitation policy and RWP must appear together")
        if policy is not None and (policy.shape != (1, 1) or policy.item() != 1):
            fail(f"{path}: V5 PRECIPITATION_OPTICS must be one when present")
        if rain is not None and (rain.shape != (nc, nl) or np.any(~np.isfinite(rain)) or np.any(rain < 0)):
            fail(f"{path}: V5 RWP must be finite/nonnegative and match column layers")
    if lines[0].strip() == "RRTMGP_REPLAY_V5":
        for name in ("GRAVITY", "CP_DRY", "MOL_WEIGHT_DRY"):
            value = records.get(name)
            if value is None or value.shape != (1, 1) or not np.isfinite(value).all() or value.item() <= 0:
                fail(f"{path}: V5 requires positive finite scalar {name}")
    for name, values in records.items():
        if name in {"ICE_ROUGHNESS", "SW_BAND_PARTITION", "PRECIPITATION_OPTICS",
                    "GRAVITY", "CP_DRY", "MOL_WEIGHT_DRY", "SOLAR"}:
            continue
        if values.shape[0] != nc:
            fail(f"{path}: {name} first dimension {values.shape[0]} != nc={nc}")
    return phase, nc, nl, overlap, seed, iceflag, records


def run_logged(executable: Path, cwd: Path, logfile: str,
               env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    with (cwd / logfile).open("w", encoding="utf-8") as stream:
        return subprocess.run([str(executable)], cwd=cwd, env=env, stdout=stream,
                              stderr=subprocess.STDOUT, text=True, check=False)


def assert_close(actual: np.ndarray, expected: np.ndarray, label: str,
                 rtol: float = 5.0e-7, atol: float = 1.0e-12) -> float:
    actual = np.asarray(actual, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    if actual.shape != expected.shape:
        fail(f"{label}: shape {actual.shape} != {expected.shape}")
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        fail(f"{label}: non-finite values")
    difference = np.abs(actual - expected)
    tolerance = atol + rtol * np.abs(expected)
    if np.any(difference > tolerance):
        index = np.unravel_index(int(np.argmax(difference - tolerance)), difference.shape)
        fail(f"{label}: mismatch at {index}: actual={actual[index]} expected={expected[index]} "
             f"difference={difference[index]} tolerance={tolerance[index]}")
    return float(difference.max(initial=0.0))


def dry_layer_mass_kg_m2(raw: dict[str, np.ndarray], nl: int,
                         require_native: bool = False) -> tuple[np.ndarray, str]:
    """Return dry-air layer mass; historical captures use their explicit dp/g contract."""
    native = raw.get("DRY_LAYER_MASS_KG_M2")
    if native is not None:
        values = np.asarray(native, dtype=np.float64)
        if values.shape != (nl,) or not np.isfinite(values).all() or np.any(values <= 0.0):
            fail("DRY_LAYER_MASS_KG_M2 must contain nl finite positive values")
        return values.copy(), "native_dry_layer_mass"
    if require_native:
        fail("fresh UDM raw capture is missing DRY_LAYER_MASS_KG_M2")
    dp = np.asarray(raw["DP_HPA"][:nl], dtype=np.float64)
    gravity = float(raw["GRAVITY"][0])
    if dp.shape != (nl,) or not np.isfinite(dp).all() or np.any(dp <= 0.0):
        fail("legacy DP_HPA must contain nl finite positive values")
    if not np.isfinite(gravity) or gravity <= 0.0:
        fail("legacy GRAVITY must be finite and positive")
    return dp * 100.0 / gravity, "legacy_dp_over_gravity"


def corrected_hydrometeor(raw: dict[str, np.ndarray], q_name: str,
                          path_name: str, nl: int) -> np.ndarray:
    """Reconstruct the optional negative-input contract from preserved raw q.

    Legacy captures remain strict; new captures must include the independent
    correction records even when no negative input was accepted.
    """
    q = raw[q_name][:nl]
    if q.shape != (nl,) or not np.isfinite(q).all():
        fail(f"{q_name}: wrong shape or nonfinite raw hydrometeor")
    limits = raw.get("NEGATIVE_Q_LIMITS")
    if limits is None:
        if np.any(q < 0.0):
            fail(f"{q_name}: negative raw q without an explicit negative-input contract")
        return q
    if limits.shape != (6,) or not np.isfinite(limits).all() or np.any(limits < 0.0):
        fail("NEGATIVE_Q_LIMITS must contain six finite nonnegative bounds")
    base_q_name = q_name.removeprefix("SOURCE_")
    phase_index = {"QC": 0, "QI": 1, "QR": 2, "QS": 3, "QG": 4, "QH": 5}[base_q_name]
    clipped_name = f"NUMERIC_CLIPPED_{base_q_name}"
    correction_name = f"NEGATIVE_GRID_CORRECTION_{path_name}"
    for name in (clipped_name, correction_name):
        if name not in raw or raw[name].shape != (nl,) or not np.isfinite(raw[name]).all():
            fail(f"{name}: missing, wrong shape, or nonfinite correction record")
    negative = q < 0.0
    if np.any((-q[negative]) >= limits[phase_index]):
        fail(f"{q_name}: accepted raw negative exceeds its strict bound")
    clipped = np.where(negative, q, 0.0)
    assert_close(raw[clipped_name], clipped, clipped_name, rtol=0.0, atol=0.0)
    dry_mass, _ = dry_layer_mass_kg_m2(raw, nl)
    expected_correction = -clipped * dry_mass * 1000.0
    # Default REAL paths may underflow to zero; clipped q remains available for
    # counts. This is one representable float32 quantum, not a physics tolerance.
    quantum = float(np.nextafter(np.float32(0.), np.float32(1.)))
    assert_close(raw[correction_name], expected_correction, correction_name, rtol=1.e-6, atol=quantum)
    if np.any(raw[correction_name] < 0.0):
        fail(f"{correction_name}: correction must be nonnegative")
    return np.where(negative, 0.0, q)


def compare_input_to_raw(phase: str, raw: dict[str, np.ndarray],
                         inp: dict[str, np.ndarray], raw_nl: int) -> dict[str, Any]:
    required = {"PLAY", "PLEV", "TLAY", "TLEV", "H2O", "CF", "LWP", "IWP", "SWP", "REL", "REI", "RES"}
    missing = sorted(required - inp.keys())
    if missing:
        fail(f"{phase}: adapter input is missing {', '.join(missing)}")
    adapter_nl = inp["PLAY"].shape[1]
    if adapter_nl < raw_nl:
        fail(f"{phase}: adapter nl={adapter_nl} is shorter than raw WRF layers={raw_nl}")
    if any(inp[name].shape[1] != adapter_nl for name in ("TLAY", "H2O", "CF", "LWP", "IWP", "SWP", "REL", "REI", "RES")):
        fail(f"{phase}: adapter layer fields have inconsistent dimensions")
    if inp["PLEV"].shape[1] != adapter_nl + 1:
        fail(f"{phase}: PLEV must have adapter_nl+1 interfaces")
    if inp["TLEV"].shape[1] != adapter_nl + 1:
        fail(f"{phase}: TLEV must have adapter_nl+1 interfaces")
    if np.any(np.diff(inp["PLEV"], axis=1) >= 0.0):
        fail(f"{phase}: PLEV must strictly decrease from surface to top")
    if np.any(inp["PLAY"] <= 0.0) or np.any(inp["PLEV"] < 0.0):
        fail(f"{phase}: invalid pressure sign")
    if np.any(inp["PLAY"] >= inp["PLEV"][:, :-1]) or np.any(inp["PLAY"] <= inp["PLEV"][:, 1:]):
        fail(f"{phase}: PLAY must lie between its pressure interfaces")
    dp_from_interfaces = inp["PLEV"][:, :raw_nl] - inp["PLEV"][:, 1:raw_nl+1]
    dp_error = assert_close(dp_from_interfaces, raw["DP_HPA"][None, :raw_nl],
                            f"{phase}: PLEV thickness vs raw DP_HPA", rtol=1.0e-6, atol=1.0e-5)
    play_error = assert_close(inp["PLAY"][:, :raw_nl], raw["P_HPA"][None, :raw_nl],
                              f"{phase}: PLAY vs raw P_HPA", rtol=0.0, atol=0.0)
    pressure_metadata_error = None
    if "SOURCE_P_PA" in raw:
        pressure_metadata_error = assert_close(inp["PLAY"][:, :raw_nl],
                                               (raw["SOURCE_P_PA"][:raw_nl] * 0.01)[None, :],
                                               f"{phase}: PLAY vs SOURCE_P_PA*0.01", rtol=5.0e-7, atol=1.0e-7)
    # LW extends/interpolates the top profile and recomputes the final model
    # layer from its two interfaces. SW retains the source layer temperatures.
    if phase == "LW":
        tlay_source_error = assert_close(inp["TLAY"][:, :max(0, raw_nl - 1)],
                                         raw["SOURCE_T"][None, :max(0, raw_nl - 1)],
                                         f"{phase}: interior TLAY vs raw SOURCE_T", rtol=0.0, atol=0.0)
        top_tlay_expected = 0.5 * (inp["TLEV"][:, raw_nl-1:raw_nl] + inp["TLEV"][:, raw_nl:raw_nl+1])
        tlay_top_error = assert_close(inp["TLAY"][:, raw_nl-1:raw_nl], top_tlay_expected,
                                      f"{phase}: top TLAY vs adjacent TLEV interpolation",
                                      rtol=5.0e-7, atol=1.0e-5)
    else:
        tlay_source_error = assert_close(inp["TLAY"][:, :raw_nl], raw["SOURCE_T"][None, :raw_nl],
                                         f"{phase}: TLAY vs raw SOURCE_T", rtol=0.0, atol=0.0)
        tlay_top_error = None
    h2o_expected = raw["QV"][:raw_nl] * raw["AMD_W"]
    h2o_error = assert_close(inp["H2O"][:, :raw_nl], h2o_expected[None, :],
                              f"{phase}: H2O vs QV*AMD_W", rtol=5.0e-7, atol=1.0e-14)
    cf_error = assert_close(inp["CF"][:, :raw_nl], raw["CF"][None, :raw_nl],
                            f"{phase}: adapter CF vs raw CF", rtol=0.0, atol=0.0)

    dry_mass, dry_mass_source = dry_layer_mass_kg_m2(raw, raw_nl)
    cf = raw["CF"][:raw_nl]
    path_expected: dict[str, np.ndarray] = {}
    omitted: dict[str, Any] = {}
    path_differences: dict[str, float] = {}
    for path_name, q_name in (("LWP", "QC"), ("IWP", "QI"), ("SWP", "QS")) + ((("RWP", "QR"),) if "RWP" in inp else ()):
        q = corrected_hydrometeor(raw, q_name, path_name, raw_nl)
        grid_path = dry_mass * 1000.0 * q
        expected = np.zeros(raw_nl, dtype=np.float64)
        wet = cf > 0.0
        expected[wet] = grid_path[wet] / cf[wet]
        path_expected[path_name] = expected
        path_differences[path_name] = assert_close(inp[path_name][0, :raw_nl], expected,
                                                   f"{phase}: {path_name} from {q_name}/DP/CF",
                                                   rtol=5.0e-7, atol=1.0e-12)
        excluded = (cf == 0.0) & (q > 0.0)
        omitted[path_name] = {
            "layers": int(np.count_nonzero(excluded)),
            "grid_box_mass_g_m2_by_layer": [float(v) for v in grid_path[excluded]],
            "total_grid_box_mass_g_m2_across_snapshot_layers": float(grid_path[excluded].sum()),
            "max_grid_box_mass_g_m2_per_layer": float(grid_path[excluded].max(initial=0.0)),
        }
    # The six-phase contract includes diagnostic-only graupel and refused
    # positive hail. Validate their preserved corrections too, even though no
    # optical input is replayed for these phases.
    if "NEGATIVE_Q_LIMITS" in raw:
        for q_name, path_name in (("QG", "GWP"), ("QH", "HWP")):
            if q_name not in raw:
                fail(f"{phase}: new six-phase correction contract omitted {q_name}")
            q = corrected_hydrometeor(raw, q_name, path_name, raw_nl)
            if q_name == "QH" and np.any(q > 0.0):
                fail(f"{phase}: positive hail must be refused before optical replay")
            expected_grid = dry_mass * 1000.0 * q
            for suffix, expected in (("GRID", expected_grid), ("OMITTED", expected_grid),
                                     ("RADIATION", np.zeros_like(expected_grid))):
                name = f"{path_name}_{suffix}"
                if name not in raw:
                    fail(f"{phase}: new six-phase correction contract omitted {name}")
                path_differences[name] = assert_close(raw[name], expected,
                    f"{phase}: {name} diagnostic-only mass contract", rtol=1.e-6, atol=1.e-12)
    radius_differences = {
        name: assert_close(inp[name][0, :raw_nl], raw[source][:raw_nl],
                           f"{phase}: {name} vs raw {source}", rtol=0.0, atol=0.0)
        for name, source in (("REL", "REL"), ("REI", "REI"), ("RES", "RES"))
    }
    radius_selection_counts: dict[str, dict[str, int]] = {}
    has_snow_radius: bool | None = None
    for has_name, raw_radius, adapter_radius in (
        ("HAS_REQC", "SOURCE_RE_CLOUD", "REL"),
        ("HAS_REQI", "SOURCE_RE_ICE", "REI"),
        ("HAS_REQS", "SOURCE_RE_SNOW", "RES"),
    ):
        if has_name in raw:
            has_explicit = bool(raw[has_name][0] != 0.0)
            if has_name == "HAS_REQS":
                has_snow_radius = has_explicit
            if has_explicit and raw_radius not in raw:
                fail(f"{phase}: {has_name}=1 but {raw_radius} capture is missing")
            if has_explicit:
                source = raw[raw_radius][:raw_nl]
                expected_radius = source * 1.0e6
                fallback_name = "FALLBACK_" + adapter_radius
                background_m = {"REL": 2.49e-6, "REI": 4.99e-6, "RES": 9.99e-6}[adapter_radius]
                phase_q = raw[{"REL": "QC", "REI": "QI", "RES": "QS"}[adapter_radius]][:raw_nl]
                background = ((source.astype(np.float32) == np.float32(background_m)) &
                              (phase_q > 0.0) & (raw["CF"][:raw_nl] > 0.0))
                # Old snapshots retain their original direct-source contract.
                if fallback_name in raw:
                    if len(raw[fallback_name]) != raw_nl:
                        fail(f"{phase}: {fallback_name} shape mismatch")
                    expected_radius[background] = raw[fallback_name][background]
                wet = (phase_q > 0.0) & (raw["CF"][:raw_nl] > 0.0)
                radius_selection_counts[adapter_radius] = {
                    "host_background_fallback_layers": int(np.count_nonzero(background)) if fallback_name in raw else 0,
                    "diagnosed_source_layers": int(np.count_nonzero(wet & ~background)),
                }
                radius_differences[f"{adapter_radius}_vs_{raw_radius}_um"] = assert_close(
                    inp[adapter_radius][0, :raw_nl], expected_radius,
                    f"{phase}: explicit {adapter_radius} radius with initialized-background fallback",
                    rtol=5.0e-7, atol=1.0e-7,
                )
    if has_snow_radius is False:
        radius_differences["RES_ice_proxy"] = assert_close(
            inp["RES"][0, :raw_nl], inp["REI"][0, :raw_nl],
            f"{phase}: absent snow radius uses diagnosed ice radius proxy",
            rtol=0.0, atol=0.0,
        )
    negative_q = {}
    mapped_flags = {name: bool(raw.get(FLAG_NAMES[name], np.array([0.0]))[0] != 0.0)
                    for name in Q_NAMES}
    for name in Q_NAMES:
        if not mapped_flags[name]:
            negative_q[name] = {"registered_source": False, "count": None,
                                "minimum_all": None, "minimum_negative": None}
            continue
        negatives = raw[name][raw[name] < 0.0]
        negative_q[name] = {
            "registered_source": True,
            "count": int(negatives.size),
            "minimum_all": float(raw[name][:raw_nl].min()),
            "minimum_negative": float(negatives.min()) if negatives.size else None,
        }
    return {
        "pressure": {"plev_strictly_decreasing": True, "play_inside_interfaces": True,
                     "adapter_layers": adapter_nl, "raw_wrf_layers": raw_nl,
                     "max_plev_dp_difference_hpa": dp_error, "max_play_p_hpa_difference": play_error,
                     "max_play_source_pressure_difference_hpa": pressure_metadata_error,
                     "max_cf_raw_adapter_difference": cf_error},
        "state_mapping": {"max_tlay_source_t_difference_k": tlay_source_error,
                          "max_top_tlay_interface_interpolation_difference_k": tlay_top_error,
                          "top_domain_layer_temperature_interpolated_from_tlev": phase == "LW",
                          "max_h2o_qv_times_amd_w_difference": h2o_error},
        "cloud_paths": {"max_adapter_path_differences_g_m2": path_differences,
                        "cf_zero_condensate_omission": omitted,
                        "dry_layer_mass_source": dry_mass_source},
        "radii": {"max_difference_um": radius_differences,
                  "selection_counts": radius_selection_counts},
        "raw_mapped_q_negative_snapshot": negative_q,
    }


def check_microphysics_mapping(mp_physics: int, raw: dict[str, np.ndarray],
                               adapter: dict[str, np.ndarray], phase: str, raw_nl: int) -> dict[str, Any]:
    missing_flags = sorted(FLAG_NAMES[q] for q in Q_NAMES if FLAG_NAMES[q] not in raw)
    if missing_flags:
        fail(f"{phase}: raw snapshot missing source flags: {', '.join(missing_flags)}")
    flags = {q: bool(raw.get(FLAG_NAMES[q], np.array([0.0]))[0] != 0.0) for q in Q_NAMES}
    present_sources = sorted(SOURCE_NAMES[q] for q in Q_NAMES if SOURCE_NAMES[q] in raw)
    checks: list[str] = []
    expected_flags = {
        4: {"QC": True, "QI": True, "QS": True},
        27: {"QC": True, "QI": True, "QS": True},
        5: {"QC": True, "QI": True, "QS": False},
        15: {"QC": True, "QI": True, "QS": False},
        85: {"QC": True, "QI": True, "QS": False},
        95: {"QC": True, "QI": False, "QS": True},
    }
    if mp_physics in expected_flags and flags != expected_flags[mp_physics]:
        fail(f"{phase}: MP{mp_physics} source flags {flags} != expected {expected_flags[mp_physics]}")
    if mp_physics in (4, 27):
        for q in Q_NAMES:
            source = SOURCE_NAMES[q]
            if source not in raw:
                fail(f"{phase}: MP4 mapping needs {source} capture")
            assert_close(raw[q][:raw_nl], raw[source][:raw_nl], f"{phase}: MP4 preserved {q}",
                         rtol=0.0, atol=0.0)
            checks.append(f"{q}=source_{q}")
        mapping = "udm_all_native_species_preserved" if mp_physics == 27 else "mp4_all_species_preserved"
    elif mp_physics in {5, 15, 85}:
        for q in ("QC", "QI"):
            source = SOURCE_NAMES[q]
            if source not in raw:
                fail(f"{phase}: MP{mp_physics} mapping needs {source} capture")
            assert_close(raw[q][:raw_nl], raw[source][:raw_nl], f"{phase}: MP{mp_physics} mapped {q}",
                         rtol=0.0, atol=0.0)
            checks.append(f"{q}=source_{q}")
        assert_close(raw["QS"][:raw_nl], np.zeros_like(raw["QS"][:raw_nl]),
                     f"{phase}: MP{mp_physics} snow path source must be zero", rtol=0.0, atol=0.0)
        checks.append("QS=0 (Ferrier ice field carries frozen condensate)")
        mapping = "ferrier_family_all_frozen_qi_snow_zero"
    elif mp_physics == 95:
        for q in ("QC", "QS"):
            source = SOURCE_NAMES[q]
            if source not in raw:
                fail(f"{phase}: MP95 mapping needs {source} capture")
            assert_close(raw[q][:raw_nl], raw[source][:raw_nl], f"{phase}: MP95 restored/retained {q}",
                         rtol=0.0, atol=0.0)
            checks.append(f"{q}=source_{q}")
        assert_close(raw["QI"][:raw_nl], np.zeros_like(raw["QI"][:raw_nl]),
                     f"{phase}: MP95 QI must be zero", rtol=0.0, atol=0.0)
        checks.append("QI=0 (combined ice/snow remains in QS)")
        mapping = "mp95_combined_qs_qc_restored_qi_zero"
    else:
        # For other schemes, report the exact source availability and flags,
        # and verify every flagged raw source exposed by the capture hook.
        for q in Q_NAMES:
            source = SOURCE_NAMES[q]
            if flags[q]:
                if source not in raw:
                    fail(f"{phase}: flagged {q} source has no {source} capture")
                assert_close(raw[q][:raw_nl], raw[source][:raw_nl],
                             f"{phase}: flagged source mapping {q}", rtol=0.0, atol=0.0)
                checks.append(f"{q}=source_{q}")
        mapping = "generic_source_and_flag_report"
    return {"mp_physics": mp_physics, "source_flags": flags,
            "generic_raw_sources_present": present_sources,
            "mapping_classification": mapping, "mapping_checks": checks}


def run_reference(reference_exe: Path, input_path: Path, output_path: Path,
                  case_dir: Path, phase: str) -> dict:
    env = os.environ.copy()
    env.pop("WRF_RRTMGP_CAPTURE_DIR", None)
    env.pop("WRF_RRTMGP_CAPTURE_CALL", None)
    result = subprocess.run([str(reference_exe), str(DATA_DIR), str(input_path), str(output_path)],
                            cwd=case_dir, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, check=False)
    (case_dir / f"reference_{phase.lower()}.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0 or not output_path.is_file():
        fail(f"reference executable failed for {phase} (return {result.returncode}); "
             f"inspect reference_{phase.lower()}.log")
    report = compare(read_result(case_dir / "capture" / f"{phase.lower()}.result"),
                     read_result(output_path))
    if not report.get("passed"):
        fail(f"{phase}: production/reference replay mismatch: " +
             ", ".join(report.get("failed_sections", [])))
    return report


def check_wrf_diagnostics(phase: str, result: dict[str, Any], raw: dict[str, np.ndarray],
                          nl: int) -> dict[str, float]:
    sections = result["sections"]
    errors: dict[str, float] = {}
    if not np.isfinite(raw["PI"]).all() or np.any(raw["PI"] <= 0.0):
        fail(f"{phase}: captured PI must be finite and positive")
    theta = sections.get("WRF_THETA_HR")
    if theta is None:
        fail(f"{phase}: missing WRF_THETA_HR capture")
    expected_theta = sections["HR"][:, :nl, :] / 86400.0 / raw["PI"][None, :, None]
    errors["wrf_theta_hr"] = assert_close(theta, expected_theta, f"{phase}: WRF_THETA_HR",
                                          rtol=5.0e-7, atol=1.0e-12)
    if phase == "LW":
        errors["wrf_glw"] = assert_close(sections["WRF_GLW"], sections["DN"][:, :1, :],
                                        "LW: WRF_GLW vs surface DN", rtol=5.0e-7, atol=2.0e-5)
        errors["wrf_olr"] = assert_close(sections["WRF_OLR"], sections["UP"][:, -1:, :],
                                        "LW: WRF_OLR vs top UP", rtol=5.0e-7, atol=2.0e-5)
    else:
        surface_net = sections["DN"][:, :1, :] - sections["UP"][:, :1, :]
        errors["wrf_gsw"] = assert_close(sections["WRF_GSW"], surface_net, "SW: WRF_GSW vs DN-UP",
                                         rtol=5.0e-7, atol=2.0e-5)
        errors["wrf_swddir"] = assert_close(sections["WRF_SWDDIR"], sections["DIRECT"][:, :1, :],
                                           "SW: WRF_SWDDIR vs direct", rtol=5.0e-7, atol=2.0e-5)
        errors["wrf_swddif"] = assert_close(sections["WRF_SWDDIF"], sections["DIFFUSE"][:, :1, :],
                                           "SW: WRF_SWDDIF vs diffuse", rtol=5.0e-7, atol=2.0e-5)
    return errors


def initialize_cloud_fixture(wrfinput: Path, mp_physics: int) -> dict[str, Any]:
    """Insert registered condensate into a cold, interior wrfinput layer."""
    fields_by_scheme = {
        27: {"QCLOUD": ("QC", 2.0e-5), "QICE": ("QI", 1.0e-5), "QSNOW": ("QS", 3.0e-5)},
        4: {"QCLOUD": ("QC", 2.0e-5), "QICE": ("QI", 1.0e-5), "QSNOW": ("QS", 3.0e-5)},
        5: {"QCLOUD": ("QC", 2.0e-5), "QICE": ("QI", 1.0e-5)},
        15: {"QCLOUD": ("QC", 2.0e-5), "QICE": ("QI", 1.0e-5)},
        85: {"QCLOUD": ("QC", 2.0e-5), "QICE": ("QI", 1.0e-5)},
        95: {"QCLOUD": ("QC", 2.0e-5), "QSNOW": ("QS", 3.0e-5)},
    }
    if mp_physics not in fields_by_scheme:
        fail(f"--cloud-fixture does not define registered condensate fields for MP{mp_physics}")
    with netCDF4.Dataset(wrfinput, "r+") as ds:
        for name in ("T", "P", "PB"):
            if name not in ds.variables:
                fail(f"{wrfinput}: cloud fixture needs {name}")
        theta_perturbation = np.asarray(ds.variables["T"][0], dtype=np.float64)
        pressure_pa = (np.asarray(ds.variables["P"][0], dtype=np.float64) +
                       np.asarray(ds.variables["PB"][0], dtype=np.float64))
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            temperature = (theta_perturbation + 300.0) * np.power(pressure_pa / 100000.0, 287.0 / 1004.0)
        candidates = [k for k in range(temperature.shape[0] - 1)
                      if np.isfinite(temperature[k]).all() and np.isfinite(pressure_pa[k]).all()
                      and 240.0 <= float(np.mean(temperature[k])) < 260.0
                      and float(np.mean(pressure_pa[k])) > 20000.0]
        fallback = not candidates
        if fallback:
            candidates = [k for k in range(temperature.shape[0] - 1)
                          if np.isfinite(temperature[k]).all() and np.isfinite(pressure_pa[k]).all()
                          and float(np.mean(pressure_pa[k])) > 20000.0]
        if not candidates:
            fail(f"{wrfinput}: cloud fixture found no non-top level above 20000 Pa")
        layer = min(candidates, key=lambda k: abs(float(np.mean(temperature[k])) - 250.0))
        mapping: dict[str, Any] = {}
        for variable, (source, mixing_ratio) in fields_by_scheme[mp_physics].items():
            if variable not in ds.variables:
                fail(f"{wrfinput}: registered cloud field {variable} is absent")
            values = np.asarray(ds.variables[variable][:], dtype=np.float64)
            values[0, layer, :, :] = mixing_ratio
            ds.variables[variable][:] = values
            mapping[variable] = {"mapped_species": source, "mixing_ratio_kg_kg": mixing_ratio}
        radius_values = {} if mp_physics == 27 else {"RE_CLOUD": 10.0e-6, "RE_ICE": 30.0e-6, "RE_SNOW": 60.0e-6}
        radius_written: dict[str, float] = {}
        lower_names = {name.lower(): name for name in ds.variables}
        for name, radius_m in radius_values.items():
            actual = lower_names.get(name.lower())
            if actual is not None:
                values = np.asarray(ds.variables[actual][:], dtype=np.float64)
                if values.ndim >= 4 and values.shape[1] > layer:
                    values[0, layer, :, :] = radius_m
                    ds.variables[actual][:] = values
                    radius_written[actual] = radius_m
    return {
        "layer_index_zero_based": layer,
        "temperature_k_mean": float(np.mean(temperature[layer])),
        "pressure_pa_mean": float(np.mean(pressure_pa[layer])),
        "cold_level_fallback_used": fallback,
        "horizontal_cell_count": int(temperature.shape[1] * temperature.shape[2]),
        "registered_condensate_fields": mapping,
        "radius_fields_written_m": radius_written,
    }


def validate_cloud_fixture_phase(phase: str, fixture: dict[str, Any], raw: dict[str, np.ndarray],
                                 adapter: dict[str, np.ndarray], result: dict[str, Any]) -> dict[str, Any]:
    layer = int(fixture["layer_index_zero_based"])
    raw_nl = len(raw["DP_HPA"])
    if layer >= raw_nl:
        fail(f"{phase}: fixture layer {layer} is outside captured WRF layers {raw_nl}")
    if raw["SOURCE_T"][layer] >= 273.15:
        fail(f"{phase}: fixture must exercise a subfreezing WRF layer")
    active_paths = {item["mapped_species"]: item["mixing_ratio_kg_kg"]
                    for item in fixture["registered_condensate_fields"].values()}
    path_names = {"QC": ("QC", "LWP"), "QI": ("QI", "IWP"), "QS": ("QS", "SWP")}
    path_masses: dict[str, Any] = {}
    for source, expected_q in active_paths.items():
        actual_q = float(raw[source][layer])
        if actual_q <= 0.0:
            fail(f"{phase}: cloud fixture {source} is not positive at layer {layer}: {actual_q}")
        dry_mass, _ = dry_layer_mass_kg_m2(raw, raw_nl)
        raw_grid_mass = actual_q * float(dry_mass[layer]) * 1000.0
        q_name, path_name = path_names[source]
        path = float(adapter[path_name][0, layer])
        if raw["CF"][layer] <= 0.0 or path <= 0.0:
            fail(f"{phase}: cloud fixture {source} has no positive CF/path at layer {layer}")
        path_masses[source] = {
            "requested_mixing_ratio_kg_kg": expected_q,
            "captured_mixing_ratio_kg_kg": actual_q,
            "grid_box_mass_g_m2": raw_grid_mass,
            "in_cloud_path_g_m2": path,
            "cloud_fraction": float(raw["CF"][layer]),
        }
    sections = result["sections"]
    if not np.any(sections["MASK"] > 0.0):
        fail(f"{phase}: cloud fixture did not produce any cloudy calculation-mask points")
    cloud_tau = sections.get("CLOUD_TAU")
    if cloud_tau is None or not np.any(cloud_tau > 0.0):
        fail(f"{phase}: cloud fixture did not produce positive CLOUD_TAU")
    return {"fixture_layer_index_zero_based": layer, "active_species_mass_path": path_masses,
            "mask_cloudy_points": int(np.count_nonzero(sections["MASK"] > 0.0)),
            "cloud_tau_max": float(np.max(cloud_tau))}


def validate_capture(case_dir: Path, phase: str, mp_physics: int,
                     reference_exe: Path, cloud_fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    capture = case_dir / "capture"
    raw_phase, i, j, raw = read_raw(capture / f"{phase.lower()}.raw")
    input_phase, nc, nl, overlap, seed, iceflag, adapter = read_input(capture / f"{phase.lower()}.input")
    if raw_phase != phase or input_phase != phase:
        fail(f"{phase}: capture phase tags disagree")
    raw_nl = len(raw["DP_HPA"])
    if raw["MP_PHYSICS"].size != 1:
        fail(f"{phase}: expected scalar MP_PHYSICS in raw snapshot")
    captured_mp = int(round(float(raw["MP_PHYSICS"][0])))
    if captured_mp != mp_physics:
        fail(f"{phase}: captured MP_PHYSICS={captured_mp}, requested {mp_physics}")
    if nc != 1 or nl < raw_nl:
        fail(f"{phase}: expected one captured WRF column and adapter nl>={raw_nl}; got {nc}x{nl}")
    adapter_checks = compare_input_to_raw(phase, raw, adapter, raw_nl)
    mapping = check_microphysics_mapping(mp_physics, raw, adapter, phase, raw_nl)
    ref_output = capture / f"{phase.lower()}.reference.result"
    compare_report = run_reference(reference_exe, capture / f"{phase.lower()}.input",
                                   ref_output, case_dir, phase)
    actual = read_result(capture / f"{phase.lower()}.result")
    wrf_checks = check_wrf_diagnostics(phase, actual, raw, raw_nl)
    cloud_fixture_checks = (validate_cloud_fixture_phase(phase, cloud_fixture, raw, adapter, actual)
                            if cloud_fixture is not None else None)
    return {
        "phase": phase, "captured_column": {"i": i, "j": j},
        "replay_header": {"nc": nc, "nl": nl, "overlap": overlap,
                          "seed": seed, "iceflag": iceflag},
        "adapter_input_checks": adapter_checks,
        "microphysics_mapping": mapping,
        "reference_comparison": compare_report,
        "wrf_diagnostic_checks_max_abs": wrf_checks,
        "cloud_fixture_checks": cloud_fixture_checks,
        "files": {"raw": str(capture / f"{phase.lower()}.raw"),
                  "input": str(capture / f"{phase.lower()}.input"),
                  "production_result": str(capture / f"{phase.lower()}.result"),
                  "reference_result": str(ref_output)},
    }


def set_mp_physics(namelist: str, mp_physics: int) -> str:
    start = namelist.lower().find("&physics")
    end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", namelist[start:]) if start >= 0 else None
    end = start + end_match.start() if end_match else -1
    if start < 0 or end < 0:
        fail("could not locate &physics namelist block")
    block = namelist[start:end]
    block, count = re.subn(r"(?im)^(\s*mp_physics\s*=\s*)[^,\n]+,",
                           rf"\g<1>{mp_physics},", block, count=1)
    if count != 1:
        fail("namelist template must contain one mp_physics assignment")
    return namelist[:start] + block + namelist[end:]


def set_run_minutes(namelist: str, run_minutes: int) -> str:
    """Set a short integration duration and matching end timestamp."""
    start = namelist.lower().find("&time_control")
    end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", namelist[start:]) if start >= 0 else None
    end = start + end_match.start() if end_match else -1
    if start < 0 or end < 0:
        fail("could not locate &time_control namelist block")
    block = namelist[start:end]
    values: dict[str, int] = {}
    for key in ("start_year", "start_month", "start_day", "start_hour", "start_minute", "start_second"):
        match = re.search(rf"(?im)^\s*{key}\s*=\s*(\d+)\s*,", block)
        if not match:
            fail(f"time_control namelist is missing {key}")
        values[key] = int(match.group(1))
    start_time = datetime(values["start_year"], values["start_month"], values["start_day"],
                          values["start_hour"], values["start_minute"], values["start_second"])
    finish = start_time + timedelta(minutes=run_minutes)
    updates = {
        "run_hours": 0,
        "run_minutes": run_minutes,
        "end_year": finish.year,
        "end_month": finish.month,
        "end_day": finish.day,
        "end_hour": finish.hour,
        "end_minute": finish.minute,
        "end_second": finish.second,
    }
    for key, value in updates.items():
        block, count = re.subn(rf"(?im)^(\s*{key}\s*=\s*)\d+\s*,",
                               rf"\g<1>{value},", block, count=1)
        if count != 1:
            fail(f"time_control namelist must contain one {key} assignment")
    return namelist[:start] + block + namelist[end:]


def check_configuration_warnings(case_dir: Path, mp_physics: int) -> dict[str, bool]:
    text = "\n".join((case_dir / name).read_text(errors="replace")
                     for name in ("ideal.log", "wrf.log"))
    if mp_physics != 27:
        fail("RRTMGP37 now supports only UDM27")
    if "RRTMGP37 UDM: graupel optics are diagnostic-only; any positive hail path is unsupported" not in text:
        fail("missing explicit UDM precipitation support scope")
    return {"udm_precipitation_limit_reported": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path, help="new isolated SCM case/capture directory")
    parser.add_argument("reference_exe", type=Path, help="built reference_column executable")
    parser.add_argument("--mp-physics", type=int, choices=(27,), default=27)
    parser.add_argument("--ice-roughness", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--capture-call", type=int, default=1)
    parser.add_argument("--run-minutes", type=int, default=5,
                        help="SCM integration duration in minutes (default: 5)")
    parser.add_argument("--cloud-fixture", action="store_true",
                        help="insert controlled registered condensate into wrfinput after ideal.exe")
    parser.add_argument("--capture-only", action="store_true",
                        help="validate captured column replay even if later forecast integration fails")
    args = parser.parse_args()
    case_dir = args.case_dir.expanduser().resolve()
    reference_exe = args.reference_exe.expanduser().resolve()
    if case_dir.exists():
        parser.error(f"refusing existing case directory: {case_dir}")
    if not case_dir.parent.is_dir():
        parser.error(f"case directory parent must exist: {case_dir.parent}")
    if args.capture_call < 1:
        parser.error("--capture-call must be positive")
    if args.run_minutes < 1:
        parser.error("--run-minutes must be positive")
    if args.capture_only and not args.cloud_fixture:
        parser.error("--capture-only requires --cloud-fixture for a non-vacuous replay contract")
    for exe in (WRF_ROOT / "main/ideal.exe", WRF_ROOT / "main/wrf.exe", reference_exe):
        if not exe.is_file() or not exe.stat().st_mode & 0o111:
            parser.error(f"missing executable {exe}")
    for required in (test_surface_scm.TEMPLATE, test_surface_scm.INPUT_DIR / "input_sounding",
                     test_surface_scm.INPUT_DIR / "input_soil", test_surface_scm.INPUT_DIR / "force_ideal.nc",
                     test_surface_scm.WRF_ROOT / "test/rrtmgp/radiation_iofields.txt",
                     test_cloud_scm.VALIDATOR):
        if not required.is_file():
            parser.error(f"missing required input {required}")

    try:
        test_surface_scm.prepare_case(case_dir, swint_opt=0)
        namelist = set_mp_physics(test_cloud_scm.original_lsm2_namelist(), args.mp_physics)
        namelist = set_run_minutes(namelist, args.run_minutes)
        namelist, count = re.subn(r"(?m)^(\s*rrtmgp_data_path\s*=.*)$",
            lambda match: match.group(0) + f"\n rrtmgp_ice_roughness = {args.ice_roughness},", namelist)
        if count != 1:
            fail("SCM template must contain one rrtmgp_data_path assignment")
        (case_dir / "namelist.input").write_text(namelist, encoding="utf-8")
        capture = case_dir / "capture"
        capture.mkdir()
        ideal_env = os.environ.copy()
        ideal_env.pop("WRF_RRTMGP_CAPTURE_DIR", None)
        ideal_env.pop("WRF_RRTMGP_CAPTURE_CALL", None)
        ideal = run_logged(WRF_ROOT / "main/ideal.exe", case_dir, "ideal.log", ideal_env)
        if ideal.returncode != 0 or not (case_dir / "wrfinput_d01").is_file():
            fail(f"{case_dir}: ideal.exe failed; inspect ideal.log")
        fixture = (initialize_cloud_fixture(case_dir / "wrfinput_d01", args.mp_physics)
                   if args.cloud_fixture else None)
        wrf_env = os.environ.copy()
        wrf_env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
        wrf_env["WRF_RRTMGP_CAPTURE_CALL"] = str(args.capture_call)
        wrf = run_logged(WRF_ROOT / "main/wrf.exe", case_dir, "wrf.log", wrf_env)
        wrf_log = (case_dir / "wrf.log").read_text(errors="replace")
        configuration_scope = check_configuration_warnings(case_dir, args.mp_physics)
        wrf_succeeded = wrf.returncode == 0 and SUCCESS_TOKEN in wrf_log
        if not wrf_succeeded and not args.capture_only:
            fail(f"{case_dir}: wrf.exe returned {wrf.returncode}; inspect wrf.log")
        if not wrf_succeeded:
            required_capture_files = [case_dir / "capture" / f"{phase}.{suffix}"
                                      for phase in ("lw", "sw") for suffix in ("raw", "input", "result")]
            absent = [str(path) for path in required_capture_files if not path.is_file()]
            if absent:
                fail(f"{case_dir}: WRF failed before a complete LW/SW capture was written: " +
                     ", ".join(absent))
            validation = None
            forecast = {"status": "FAILED_AFTER_CAPTURE", "returncode": wrf.returncode,
                        "success_marker": SUCCESS_TOKEN in wrf_log,
                        "log_tail": wrf_log.splitlines()[-60:]}
        else:
            validation = test_cloud_scm.validate_case(case_dir)
            forecast = {"status": "PASS", "returncode": wrf.returncode,
                        "success_marker": SUCCESS_TOKEN in wrf_log,
                        "scm_validation": validation}
        # Later calls use evolved microphysics; the initial fixture need not retain each phase.
        snapshot_fixture = fixture if args.capture_call == 1 else None
        reports = {phase: validate_capture(case_dir, phase, args.mp_physics, reference_exe, snapshot_fixture)
                   for phase in ("LW", "SW")}
        if fixture is not None and args.mp_physics == 4 and args.capture_call in (1, 2):
            count_key = ("host_background_fallback_layers" if args.capture_call == 1 else
                         "diagnosed_source_layers")
            count = sum(item[count_key] for row in reports.values()
                        for item in row["adapter_input_checks"]["radii"]["selection_counts"].values())
            if count == 0:
                fail(f"WSM5 capture {args.capture_call} did not exercise {count_key}")
        for phase in ("LW", "SW"):
            *_, captured = read_input(capture / f"{phase.lower()}.input")
            if captured.get("ICE_ROUGHNESS", np.array([[1]])).item() != args.ice_roughness:
                fail(f"{phase}: captured roughness differs from requested setting")
        report = {
            "ice_roughness": args.ice_roughness,
            "status": "PASS" if wrf_succeeded else "PASS_COLUMN_REPLAY",
            "case": str(case_dir), "mp_physics": args.mp_physics,
            "capture_call": args.capture_call, "run_minutes": args.run_minutes,
            "cloud_fixture": fixture,
            "fixture_check_scope": "initial_snapshot" if args.capture_call == 1 else "evolved_state",
            "configuration_scope": configuration_scope,
            "wrf": {"ideal_returncode": ideal.returncode, "forecast": forecast},
            "phase_replay": reports,
            "scope_note": "One captured column/call snapshot; negative-Q diagnostics describe that snapshot, not a forecast-wide minimum.",
        }
        report_path = case_dir / "replay_report.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (ReplayError, RuntimeError, AssertionError, OSError, subprocess.SubprocessError,
            ValueError, KeyError) as exc:
        if "case_dir" in locals() and case_dir.is_dir():
            failure = {"status": "FAIL", "case": str(case_dir), "error": str(exc)}
            try:
                (case_dir / "replay_report.json").write_text(
                    json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            except OSError:
                pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
