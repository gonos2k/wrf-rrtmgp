#!/usr/bin/env python3
"""Strict point-scale NOAA SURFRAD vs WRF surface-flux comparison.

Actual scoring is deliberately opt-in with --score. --self-test exercises only
synthetic inputs and never reads the model cases or reports real metrics.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, chartostring

ROOT = Path(__file__).resolve().parents[2]
OBS_DIR = ROOT / "build/udm-observational-validation-inventory/surfrad"
PLAN_DIR = ROOT / "build/udm-current-24h-plan"
EXPECTED_README_SHA = "ed3e5c16f169a9def997877e6037735977f2761c9c3c39d493c8f3127e82f3a6"
DAY_FIELDS = [
    "dw_solar", "uw_solar", "direct_n", "diffuse", "dw_ir", "dw_casetemp",
    "dw_dometemp", "uw_ir", "uw_casetemp", "uw_dometemp", "uvb", "par",
    "netsolar", "netir", "totalnet", "temp", "rh", "windspd", "winddir", "pressure",
]
FIELD_INDEX = {name: 8 + 2 * i for i, name in enumerate(DAY_FIELDS)}
QC_INDEX = {name: index + 1 for name, index in FIELD_INDEX.items()}
FLUX_MAP = {
    "dw_solar": {"model": "SWDOWN", "accum": "ACSWDNB", "model_units": "W m-2", "accum_units": "J m-2"},
    "uw_solar": {"model": "SWUPB", "accum": "ACSWUPB", "model_units": "W m-2", "accum_units": "J m-2"},
    "dw_ir": {"model": "GLW", "accum": "ACLWDNB", "model_units": "W m-2", "accum_units": "J m-2"},
    "uw_ir": {"model": "LWUPB", "accum": "ACLWUPB", "model_units": "W m-2", "accum_units": "J m-2"},
}
STATIONS = {
    "FPK": {"code": "fpk", "name": "Fort Peck, Montana", "lat": 48.30783, "lon": -105.10170, "elevation_m": 634.0},
    "DRA": {"code": "dra", "name": "Desert Rock, Nevada", "lat": 36.62373, "lon": -116.01947, "elevation_m": 1007.0},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def json_default(value):
    """Normalize NumPy scalar metadata while keeping report values JSON-native."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unsupported JSON value {type(value).__name__}")


def qc_valid(values: np.ndarray, qc: np.ndarray) -> np.ndarray:
    """QC=0 and finite/nonmissing; retain negative values when QC passes."""
    values = np.asarray(values, dtype=np.float64)
    qc = np.asarray(qc)
    if values.shape != qc.shape or not np.all(np.isfinite(qc)) or not np.all(qc == np.floor(qc)):
        raise ValueError("observation values/QC shape or integer-QC contract is invalid")
    if np.any(qc < 0):
        raise ValueError("negative QC code in SURFRAD data")
    missing = values == -9999.9
    if np.any(missing & (qc != 1)):
        raise ValueError("NOAA missing value must carry QC=1")
    if np.any((qc == 0) & (missing | ~np.isfinite(values))):
        raise ValueError("QC=0 observation is missing/nonfinite")
    return (qc == 0) & np.isfinite(values) & ~missing


def end_time_energy(
    values_by_end_time: dict[dt.datetime, tuple[float, int]], start: dt.datetime, end: dt.datetime
) -> tuple[float | None, str | None]:
    """Integrate one-minute means ending in (start,end], in J m-2."""
    if end <= start or (end - start).total_seconds() % 60:
        raise ValueError("energy interval must be positive and minute aligned")
    expected = [start + dt.timedelta(minutes=n) for n in range(1, int((end - start).total_seconds() // 60) + 1)]
    values = []
    for stamp in expected:
        entry = values_by_end_time.get(stamp)
        if entry is None:
            return None, f"missing_end_time:{stamp.isoformat()}"
        value, qc = entry
        if qc != 0 or not math.isfinite(value) or value == -9999.9:
            return None, f"invalid_qc_or_value:{stamp.isoformat()}"
        values.append(value)
    return math.fsum(values) * 60.0, None


def error_stats(model: list[float], observed: list[float]) -> dict:
    if len(model) != len(observed):
        raise ValueError("paired samples must have same length")
    if not model:
        return {"n": 0, "status": "INSUFFICIENT_DATA", "bias_model_minus_obs": None,
                "mae": None, "rmse": None, "max_abs_error": None}
    delta = np.asarray(model, dtype=np.float64) - np.asarray(observed, dtype=np.float64)
    if not np.all(np.isfinite(delta)):
        raise ValueError("nonfinite paired error")
    return {
        "n": int(delta.size),
        "bias_model_minus_obs": float(np.mean(delta)),
        "mae": float(np.mean(np.abs(delta))),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
        "max_abs_error": float(np.max(np.abs(delta))),
    }


def validate_variable_contract(name: str, actual_units: str, actual_dims: tuple[str, ...], expected_units: str, expected_dims: tuple[str, ...]) -> None:
    if actual_units.strip() != expected_units:
        raise ValueError(f"{name} units {actual_units!r} != {expected_units!r}")
    if tuple(actual_dims) != tuple(expected_dims):
        raise ValueError(f"{name} dimensions {actual_dims!r} != {expected_dims!r}")


def _self_test() -> None:
    # End timestamps: the 00:00 row is outside [00:00,01:00]; 00:01..01:00 are 60 samples.
    start = dt.datetime(2010, 6, 11, 0, 0)
    end = start + dt.timedelta(hours=1)
    series = {start: (999.0, 0)}
    for minute in range(1, 61):
        series[start + dt.timedelta(minutes=minute)] = (100.0, 0)
    energy, reason = end_time_energy(series, start, end)
    assert reason is None and energy == 360000.0, (energy, reason)
    # A valid negative nighttime signal is retained when NOAA QC is good.
    mask = qc_valid(np.array([-0.7, 20.0]), np.array([0, 0]))
    assert mask.tolist() == [True, True]
    # Flagged/missing minute makes the whole hourly observation energy incomplete.
    series[start + dt.timedelta(minutes=28)] = (-9999.9, 1)
    energy, reason = end_time_energy(series, start, end)
    assert energy is None and reason and "invalid_qc_or_value" in reason
    # A missing minute also fails; no interpolation/fill.
    del series[start + dt.timedelta(minutes=28)]
    energy, reason = end_time_energy(series, start, end)
    assert energy is None and reason and "missing_end_time" in reason
    stats = error_stats([11.0, 8.0], [10.0, 10.0])
    assert stats["n"] == 2 and stats["bias_model_minus_obs"] == -0.5
    assert stats["mae"] == 1.5 and stats["rmse"] == math.sqrt(2.5)
    validate_variable_contract("SWDOWN", "W m-2", ("Time", "south_north", "west_east"), "W m-2", ("Time", "south_north", "west_east"))
    try:
        validate_variable_contract("SWDOWN", "J m-2", ("Time", "south_north", "west_east"), "W m-2", ("Time", "south_north", "west_east"))
    except ValueError:
        pass
    else:
        raise AssertionError("bad flux units must be rejected")
    assert error_stats([], []) == {"n": 0, "status": "INSUFFICIENT_DATA", "bias_model_minus_obs": None,
                                   "mae": None, "rmse": None, "max_abs_error": None}
    try:
        parse_daily_rows(np.array([[2010.5, 162, 6, 11, 0, 0] + [0.0] * 42]), dt.date(2010, 6, 11), 162, "synthetic")
    except RuntimeError as exc:
        assert "integer" in str(exc)
    else:
        raise AssertionError("fractional date/time fields must be rejected")
    try:
        validate_bucket_settings("&physics\n bucket_J = 1.0\n/", "&physics\n bucket_J = -1.\n/")
    except RuntimeError as exc:
        assert "bucket_J" in str(exc)
    else:
        raise AssertionError("positive bucket_J must be rejected for accumulator scoring")
    try:
        validate_grid_shape((1, 188, 289), (1, 189, 289))
    except RuntimeError:
        pass
    else:
        raise AssertionError("unexpected grid dimensions must be rejected")
    try:
        validate_exact_schedule([start, start + dt.timedelta(minutes=2)], start, start + dt.timedelta(minutes=2), 1)
    except RuntimeError:
        pass
    else:
        raise AssertionError("timestamp gaps must be rejected")
    try:
        validate_exact_schedule([start, start + dt.timedelta(minutes=1), start + dt.timedelta(minutes=1)], start,
                                start + dt.timedelta(minutes=2), 1)
    except RuntimeError:
        pass
    else:
        raise AssertionError("duplicate timestamps must be rejected")
    print("SYNTHETIC_SELF_TEST_PASS; no real observations or WRF output read")


def parse_daily_rows(rows: np.ndarray, expected_date: dt.date, expected_doy: int, label: str) -> list[dict]:
    if rows.ndim != 2 or rows.shape[1] != 48:
        raise RuntimeError(f"{label}: expected 48 columns per record, got {rows.shape}")
    records: list[dict] = []
    stamps = []
    for row in rows:
        if not np.all(np.isfinite(row[:6])) or not np.all(row[:6] == np.floor(row[:6])):
            raise RuntimeError(f"{label}: date/time fields must be finite exact integers")
        yr, doy, month, day, hour, minute = (int(x) for x in row[:6])
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 1 <= month <= 12 and 1 <= day <= 31):
            raise RuntimeError(f"{label}: date/time component out of range")
        stamp_date = dt.date(yr, month, day)
        if stamp_date != expected_date or doy != expected_doy:
            raise RuntimeError(f"{label}: bad date/DOY {stamp_date} {doy}")
        stamp = dt.datetime(yr, month, day, hour, minute)
        values = {}
        qcs = {}
        for name in DAY_FIELDS:
            k = FIELD_INDEX[name]
            raw_qc = float(row[k + 1])
            if not raw_qc.is_integer():
                raise RuntimeError(f"{label}: noninteger QC for {name}: {raw_qc}")
            values[name] = float(row[k])
            qcs[name] = int(raw_qc)
        # Validate QC semantics for every station field, not just scored fluxes.
        qc_valid(np.array(list(values.values())), np.array(list(qcs.values())))
        records.append({"time": stamp, "values": values, "qc": qcs})
        stamps.append(stamp)
    if len(set(stamps)) != len(stamps) or stamps != sorted(stamps):
        raise RuntimeError(f"{label}: duplicate or unordered timestamps")
    return records


def validate_exact_schedule(stamps: list[dt.datetime], start: dt.datetime, end: dt.datetime, step_minutes: int) -> None:
    expected_count = int((end - start).total_seconds() // (60 * step_minutes)) + 1
    expected = [start + dt.timedelta(minutes=step_minutes * i) for i in range(expected_count)]
    if stamps != expected:
        raise RuntimeError("timestamp coverage is not the exact expected schedule (gap, duplicate, or offset)")


def parse_daily(path: Path, expected_date: dt.date, expected_doy: int) -> tuple[list[dict], dict]:
    lines = path.read_text(encoding="ascii", errors="strict").splitlines()
    rows = np.loadtxt(path, skiprows=2)
    records = parse_daily_rows(rows, expected_date, expected_doy, str(path))
    stamps = [r["time"] for r in records]
    metadata = {
        "header_station": lines[0].strip(),
        "header_position_text": lines[1].strip(),
        "row_count": len(records),
        "first_utc": stamps[0].isoformat() + "Z",
        "last_utc": stamps[-1].isoformat() + "Z",
        "sha256": sha256(path),
    }
    return records, metadata


def parse_header_coords(metadata: dict, label: str) -> tuple[float, float]:
    try:
        header_parts = metadata["header_position_text"].replace("m version", " ").split()
        return float(header_parts[0]), float(header_parts[1])
    except Exception as exc:
        raise RuntimeError(f"{label}: could not parse station header coordinates") from exc


def validate_bucket_settings(*namelists: str) -> None:
    # WRF's bucket_J defaults to -1 (inactive). Positive bucket accumulation is
    # encoded as bucket-count plus bucket_J and cannot be scored as raw J m-2.
    import re
    for text in namelists:
        match = re.search(r"(?im)^\s*bucket_J\s*=\s*([-+]?\d+(?:\.\d*)?(?:[EeDd][-+]?\d+)?)", text)
        value = float(match.group(1).replace("D", "E").replace("d", "e")) if match else -1.0
        if not math.isfinite(value) or value > 0.0:
            raise RuntimeError(f"bucket_J must be inactive (<=0) for direct J m-2 accumulator differences; got {value}")


def validate_grid_shape(*shapes: tuple[int, ...]) -> None:
    if any(tuple(shape) != (1, 189, 289) for shape in shapes):
        raise RuntimeError(f"expected mass-grid array shape (1, 189, 289), got {shapes}")


def expected_file_records(code: str) -> tuple[list[dict], list[dict], dict]:
    path_day = OBS_DIR / f"{code.lower()}10162.dat"
    path_next = OBS_DIR / f"{code.lower()}10163.dat"
    for path, receipt_name in (
        (path_day, "download-receipt.json"),
        (path_next, "endpoint-download-receipt.json"),
    ):
        receipt = json.loads((OBS_DIR / receipt_name).read_text())
        entry = next(x for x in receipt["files"] if x["station"] == code)
        if path.stat().st_size != entry["size_bytes"] or sha256(path) != entry["sha256"]:
            raise RuntimeError(f"observation file no longer matches retrieval receipt: {path}")
        if not entry["url"].startswith("https://gml.noaa.gov/aftp/data/radiation/surfrad/"):
            raise RuntimeError(f"nonofficial/unexpected observation URL: {entry['url']}")
    day, day_meta = parse_daily(path_day, dt.date(2010, 6, 11), 162)
    next_day, endpoint_meta = parse_daily(path_next, dt.date(2010, 6, 12), 163)
    if len(day) != 1440 or len(next_day) != 1440:
        raise RuntimeError(f"{code}: expected 1440 1-minute rows in each date file")
    validate_exact_schedule([r["time"] for r in day], dt.datetime(2010, 6, 11, 0, 0), dt.datetime(2010, 6, 11, 23, 59), 1)
    validate_exact_schedule([r["time"] for r in next_day], dt.datetime(2010, 6, 12, 0, 0), dt.datetime(2010, 6, 12, 23, 59), 1)
    if day[0]["time"] != dt.datetime(2010, 6, 11, 0, 0) or day[-1]["time"] != dt.datetime(2010, 6, 11, 23, 59):
        raise RuntimeError(f"{code}: 2010-06-11 file does not cover exact nominal UTC day")
    if next_day[0]["time"] != dt.datetime(2010, 6, 12, 0, 0):
        raise RuntimeError(f"{code}: missing exact full-day endpoint row")
    expected_coords = STATIONS[code]
    for label, meta in (("day", day_meta), ("endpoint", endpoint_meta)):
        hlat, hlon = parse_header_coords(meta, f"{code} {label}")
        if abs(hlat - expected_coords["lat"]) > 0.02 or abs(hlon - expected_coords["lon"]) > 0.02:
            raise RuntimeError(f"{code} {label}: station header coordinate does not match NOAA metadata")
    return day, next_day, {"day": day_meta, "next_day": endpoint_meta}


def read_times(ds: Dataset) -> list[str]:
    values = chartostring(ds.variables["Times"][:])
    return [str(v).strip().replace("_", "T") for v in np.asarray(values).reshape(-1)]


def get_array(ds: Dataset, name: str, units: str, expected_dims: tuple[str, ...]) -> np.ndarray:
    if name not in ds.variables:
        raise RuntimeError(f"missing WRF variable {name}")
    variable = ds.variables[name]
    actual_units = getattr(variable, "units", "")
    try:
        validate_variable_contract(name, actual_units, tuple(variable.dimensions), units, expected_dims)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    value = variable[:]
    if np.ma.isMaskedArray(value) and np.any(np.ma.getmaskarray(value)):
        raise RuntimeError(f"masked/fill value encountered in {name}")
    value = np.asarray(value, dtype=np.float64)
    if not np.all(np.isfinite(value)):
        raise RuntimeError(f"nonfinite value encountered in {name}")
    fill_attrs = [a for a in ("_FillValue", "missing_value") if a in variable.ncattrs()]
    for attr in fill_attrs:
        fill = float(np.asarray(getattr(variable, attr)).reshape(-1)[0])
        if np.any(value == fill):
            raise RuntimeError(f"explicit fill value encountered in {name}")
    return value


def validate_pair_run(receipt_path: Path, preflight_path: Path, ra4_dir: Path, ra37_dir: Path) -> tuple[list[str], dict]:
    run = json.loads(receipt_path.read_text())
    pre = json.loads(preflight_path.read_text())
    if run.get("status") != "BOTH_VALIDATED" or run.get("returncodes") != {"ra4": 0, "ra37": 0}:
        raise RuntimeError("paired WRF execution receipt is not BOTH_VALIDATED/zero return code")
    for arm in ("ra4", "ra37"):
        validation = run["validation"][arm]
        if validation["history_count"] != 25 or validation["history_first"] != "2010-06-11T00:00:00" or validation["history_last"] != "2010-06-12T00:00:00":
            raise RuntimeError(f"{arm} run receipt does not assert exact 25-record 24-hour window")
        if len(validation["rank_success_logs"]) != 4:
            raise RuntimeError(f"{arm} run receipt lacks four-rank success record")
        checks = run["hash_checks"][arm]
        if not checks.get("before_match") or not checks.get("after_match"):
            raise RuntimeError(f"{arm} immutable input/source hash check failed")
        if checks["before"] != checks["after"]:
            raise RuntimeError(f"{arm} input/source changed during run")
        case_state = pre.get("case_immutable_state", {}).get(arm, {})
        case_dir = {"ra4": ra4_dir, "ra37": ra37_dir}[arm]
        for key, filename, receipt_key in (
            ("namelist_sha256", "namelist.input", None),
            ("wrfinput_sha256", "wrfinput_d01", "wrfinput_d01"),
            ("wrfbdy_sha256", "wrfbdy_d01", "wrfbdy_d01"),
        ):
            expected_hash = case_state.get(key)
            if not expected_hash or not (case_dir / filename).is_file() or sha256(case_dir / filename) != expected_hash:
                raise RuntimeError(f"{arm}: current {filename} differs from prepared immutable-state hash")
            if receipt_key and expected_hash != checks["before"].get(receipt_key):
                raise RuntimeError(f"{arm}: {filename} hash differs between preflight and execution receipt")
        validate_bucket_settings((case_dir / "namelist.input").read_text(errors="strict"))
    h4 = run["hash_checks"]["ra4"]["before"]
    h37 = run["hash_checks"]["ra37"]["before"]
    for key in ("executable", "wrfinput_d01", "wrfbdy_d01", "gas_lw", "gas_sw", "cloud_lw", "cloud_sw", "rrtmg_lw", "rrtmg_sw", "source_provenance", "module_mp_udm", "module_ra_rrtmgp"):
        if h4.get(key) != h37.get(key):
            raise RuntimeError(f"paired arms differ in expected common input/source {key}")
    if pre.get("inputs", {}).get("sha256", {}).get("executable") != h4["executable"]:
        raise RuntimeError("execution binary hash does not match preflight")
    physics = pre.get("physics", {})
    if not ("RA4" in physics.get("ra4", "") and "mode 0" in physics.get("ra4", "")):
        raise RuntimeError("preflight does not identify the baseline as RRTMG4 frozen-optics mode 0")
    if not ("RRTMGP37" in physics.get("ra37", "") and "mode 1" in physics.get("ra37", "")):
        raise RuntimeError("preflight does not identify the RRTMGP37 arm as frozen-optics mode 1")
    if "UDM27" not in physics.get("common", ""):
        raise RuntimeError("preflight does not confirm common UDM27 microphysics")
    expected = [dt.datetime(2010, 6, 11, 0) + dt.timedelta(hours=k) for k in range(25)]
    expected_s = [x.strftime("%Y-%m-%dT%H:%M:%S") for x in expected]
    arrays_by_arm = {}
    grid_identity = None
    field_metadata = {}
    global_metadata = {}
    for arm, case_dir in (("ra4", ra4_dir), ("ra37", ra37_dir)):
        files = [case_dir / f"wrfout_d01_{x.strftime('%Y-%m-%d_%H:%M:%S')}" for x in expected]
        discovered = sorted(case_dir.glob("wrfout_d01_*"))
        if not all(p.is_file() for p in files) or len(files) != 25 or len(discovered) != 25 or {p.resolve() for p in discovered} != {p.resolve() for p in files}:
            raise RuntimeError(f"{arm}: expected exactly 25 hourly history files")
        for logname in run["validation"][arm]["rank_success_logs"]:
            logpath = case_dir / logname
            if not logpath.is_file() or "SUCCESS COMPLETE WRF" not in logpath.read_text(errors="replace"):
                raise RuntimeError(f"{arm}: missing rank success marker in {logname}")
        values = {name: [] for info in FLUX_MAP.values() for name in (info["model"], info["accum"])}
        times = []
        for fi, path in enumerate(files):
            with Dataset(path) as ds:
                local_times = read_times(ds)
                if local_times != [expected_s[fi]]:
                    raise RuntimeError(f"{arm} {path.name}: Times={local_times}, expected {[expected_s[fi]]}")
                times.append(local_times[0])
                coords = {}
                coord_dims = ("Time", "south_north", "west_east")
                for name, units in (("XLAT", "degree_north"), ("XLONG", "degree_east"), ("HGT", "m")):
                    if name not in ds.variables:
                        raise RuntimeError(f"{arm}: missing coordinate/terrain field {name}")
                    if getattr(ds.variables[name], "units", "").strip() != units or tuple(ds.variables[name].dimensions) != coord_dims:
                        raise RuntimeError(f"{arm}: {name} coordinate units/dimensions contract failed")
                    arr = ds.variables[name][:]
                    if np.ma.isMaskedArray(arr) and np.any(np.ma.getmaskarray(arr)):
                        raise RuntimeError(f"masked value in {name}")
                    arr = np.asarray(arr)
                    if not np.all(np.isfinite(arr)):
                        raise RuntimeError(f"nonfinite values in {name}")
                    coords[name] = arr.copy()
                if "LANDMASK" not in ds.variables:
                    raise RuntimeError(f"{arm}: missing LANDMASK field")
                if tuple(ds.variables["LANDMASK"].dimensions) != coord_dims:
                    raise RuntimeError(f"{arm}: LANDMASK dimensions {ds.variables['LANDMASK'].dimensions} != {coord_dims}")
                if getattr(ds.variables["LANDMASK"], "units", "").strip() not in ("", "1"):
                    raise RuntimeError(f"{arm}: LANDMASK units must be dimensionless/blank")
                landmask = ds.variables["LANDMASK"][:]
                if np.ma.isMaskedArray(landmask) and np.any(np.ma.getmaskarray(landmask)):
                    raise RuntimeError("masked LANDMASK")
                landmask = np.asarray(landmask)
                if not np.all(np.isfinite(landmask)):
                    raise RuntimeError("nonfinite LANDMASK")
                coords["LANDMASK"] = landmask.copy()
                if grid_identity is None:
                    grid_identity = {k: v for k, v in coords.items()}
                else:
                    for k, v in coords.items():
                        if not np.array_equal(v, grid_identity[k]):
                            raise RuntimeError(f"static grid {k} changed across arms/times")
                dims = tuple(ds.dimensions)
                if not {"Time", "south_north", "west_east"}.issubset(dims):
                    raise RuntimeError(f"unexpected mass-grid dimensions in {path}")
                validate_grid_shape(coords["XLAT"].shape, coords["XLONG"].shape, coords["HGT"].shape, landmask.shape)
                expected_ra = 4 if arm == "ra4" else 37
                for attr, expected_value in (("RA_LW_PHYSICS", expected_ra), ("RA_SW_PHYSICS", expected_ra), ("MP_PHYSICS", 27), ("DX", 20000.0), ("DY", 20000.0), ("WEST-EAST_GRID_DIMENSION", 290), ("SOUTH-NORTH_GRID_DIMENSION", 190)):
                    actual = getattr(ds, attr, None)
                    if actual != expected_value:
                        raise RuntimeError(f"{arm} {path.name}: global {attr}={actual!r}, expected {expected_value!r}")
                gattrs = ("START_DATE", "SIMULATION_START_DATE", "WEST-EAST_GRID_DIMENSION", "SOUTH-NORTH_GRID_DIMENSION", "MAP_PROJ", "DX", "DY", "RA_LW_PHYSICS", "RA_SW_PHYSICS", "MP_PHYSICS")
                metadata = {a: getattr(ds, a, None) for a in gattrs}
                prior = global_metadata.setdefault(arm, metadata)
                if metadata != prior:
                    raise RuntimeError(f"{arm}: global output metadata changed within run")
                expected_dims = ("Time", "south_north", "west_east")
                for name, info in FLUX_MAP.items():
                    for var, units in ((info["model"], info["model_units"]), (info["accum"], info["accum_units"])):
                        arr = get_array(ds, var, units, expected_dims)
                        values[var].append(arr.copy())
                        metadata = {a: str(getattr(ds.variables[var], a)) for a in ("description", "MemoryOrder", "stagger", "coordinates", "units") if a in ds.variables[var].ncattrs()}
                        old = field_metadata.setdefault(var, metadata)
                        if metadata != old:
                            raise RuntimeError(f"inconsistent {var} metadata across history files/arms")
        if times != expected_s:
            raise RuntimeError(f"{arm}: unexpected history sequence")
        arrays_by_arm[arm] = {name: np.concatenate(seq, axis=0) for name, seq in values.items()}
    shape = grid_identity["XLAT"].shape
    if len(shape) == 3 and shape[0] == 1:
        shape2 = shape[1:]
    elif len(shape) == 2:
        shape2 = shape
    else:
        raise RuntimeError(f"unexpected static grid shape {shape}")
    grid_lat, grid_lon, grid_hgt = (grid_identity[k].reshape(shape2) for k in ("XLAT", "XLONG", "HGT"))
    if global_metadata["ra4"]["RA_LW_PHYSICS"] != 4 or global_metadata["ra4"]["RA_SW_PHYSICS"] != 4 or global_metadata["ra37"]["RA_LW_PHYSICS"] != 37 or global_metadata["ra37"]["RA_SW_PHYSICS"] != 37:
        raise RuntimeError("global radiation option metadata does not match RA4/RA37 pair")
    if global_metadata["ra4"]["MP_PHYSICS"] != global_metadata["ra37"]["MP_PHYSICS"] or global_metadata["ra4"]["MP_PHYSICS"] != 27:
        raise RuntimeError("paired global microphysics metadata differs from UDM27")
    return expected_s, {"run": run, "preflight": pre, "arrays": arrays_by_arm, "grid_lat": grid_lat, "grid_lon": grid_lon, "grid_hgt": grid_hgt, "grid_shape": shape2, "landmask": grid_identity["LANDMASK"], "field_metadata": field_metadata, "global_metadata": global_metadata}


def nearest_grid(site: dict, data: dict) -> dict:
    lat1 = np.deg2rad(site["lat"])
    lat2 = np.deg2rad(data["grid_lat"])
    dlat = lat2 - lat1
    dlon = np.deg2rad(data["grid_lon"] - site["lon"])
    hav = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    j, i = np.unravel_index(np.argmin(hav), hav.shape)
    distance = 6371.0088 * 2 * np.arcsin(np.sqrt(hav[j, i]))
    return {"j_zero_based": int(j), "i_zero_based": int(i), "lat": float(data["grid_lat"][j, i]), "lon": float(data["grid_lon"][j, i]), "distance_km": float(distance), "model_HGT_m": float(data["grid_hgt"][j, i]), "station_elevation_m": site["elevation_m"], "height_difference_model_minus_station_m": float(data["grid_hgt"][j, i] - site["elevation_m"])}


def station_maps(code: str) -> tuple[dict[dt.datetime, dict], dict[dt.datetime, dict], dict]:
    day, next_day, files = expected_file_records(code)
    return ({r["time"]: r for r in day}, {r["time"]: r for r in next_day}, files)


def score(receipt_path: Path, preflight_path: Path, ra4_dir: Path, ra37_dir: Path, output_dir: Path) -> None:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite prior evidence: {output_dir}")
    readme = OBS_DIR / "README_SURFRAD.txt"
    if sha256(readme) != EXPECTED_README_SHA:
        raise RuntimeError("NOAA format/QC README differs from pinned local copy")
    expected_stamps = [dt.datetime(2010, 6, 11, 0) + dt.timedelta(hours=k) for k in range(25)]
    history_paths = [
        case_dir / f"wrfout_d01_{stamp.strftime('%Y-%m-%d_%H:%M:%S')}"
        for case_dir in (ra4_dir, ra37_dir) for stamp in expected_stamps
    ]
    observation_paths = [
        OBS_DIR / f"{code.lower()}10162.dat" for code in STATIONS
    ] + [OBS_DIR / f"{code.lower()}10163.dat" for code in STATIONS]
    script_path = Path(__file__).resolve()
    immutable_paths = [receipt_path, preflight_path, readme, script_path,
                       OBS_DIR / "download-receipt.json", OBS_DIR / "endpoint-download-receipt.json",
                       *observation_paths, *history_paths]
    for case_dir in (ra4_dir, ra37_dir):
        immutable_paths.extend(case_dir / name for name in ("namelist.input", "wrfinput_d01", "wrfbdy_d01"))
    absent = [str(path) for path in immutable_paths if not path.is_file()]
    if absent:
        raise RuntimeError(f"missing immutable evidence inputs: {absent}")
    hashes_before = {str(path): sha256(path) for path in immutable_paths}
    times, data = validate_pair_run(receipt_path, preflight_path, ra4_dir, ra37_dir)
    metrics = {}
    hourly_rows = []
    station_file_hashes = {}
    fields_used = list(FLUX_MAP)
    for code, site in STATIONS.items():
        day, next_day, obs_files = station_maps(code)
        station_file_hashes[code] = obs_files
        grid_point = nearest_grid(site, data)
        j, i = grid_point["j_zero_based"], grid_point["i_zero_based"]
        # Selected mass point must be land; no spatial interpolation is performed.
        landmask = data["landmask"].reshape(data["grid_shape"])
        if landmask[j, i] < 0.5:
            raise RuntimeError(f"{code}: nearest SURFRAD grid point is not land")
        metrics[code] = {"station": site, "grid_point": grid_point, "instantaneous_hourly": {}, "hourly_energy": {}, "daily_energy": {}}
        for obs_field, mapping in FLUX_MAP.items():
            instantaneous = {"ra4": [], "ra37": [], "obs": [], "times": []}
            hourly_energy = {"ra4": [], "ra37": [], "obs": [], "times": [], "hours": []}
            skipped = []
            for hour in range(1, 25):
                t1 = dt.datetime(2010, 6, 11, 0) + dt.timedelta(hours=hour)
                t0 = t1 - dt.timedelta(hours=1)
                # The timestamp marks the end of the measured 1-minute average.
                record = day.get(t1) if t1.date() == dt.date(2010, 6, 11) else next_day.get(t1)
                if record is None:
                    raise RuntimeError(f"{code}: no minute observation at exact endpoint {t1}")
                obs_value = record["values"][obs_field]
                obs_qc = record["qc"][obs_field]
                obs_ok = bool(qc_valid(np.array([obs_value]), np.array([obs_qc]))[0])
                out_index = hour
                model_values = {}
                for arm in ("ra4", "ra37"):
                    flux = data["arrays"][arm][mapping["model"]]
                    accum = data["arrays"][arm][mapping["accum"]]
                    model_values[arm] = float(flux[out_index, j, i])
                if obs_ok:
                    instantaneous["obs"].append(obs_value)
                    instantaneous["ra4"].append(model_values["ra4"])
                    instantaneous["ra37"].append(model_values["ra37"])
                    instantaneous["times"].append(t1.isoformat() + "Z")
                else:
                    skipped.append({"hour_end_utc": t1.isoformat() + "Z", "reason": f"observation_qc={obs_qc}_or_missing"})
                hourly_row = {"station": code, "obs_field": obs_field, "model_time_utc": t1.isoformat() + "Z", "obs_qc0_minute_mean_Wm2": obs_value if obs_ok else None, "ra4_instant_Wm2": model_values["ra4"] if obs_ok else None, "ra37_instant_Wm2": model_values["ra37"] if obs_ok else None, "obs_hour_energy_Jm2": None, "ra4_hour_energy_Jm2": None, "ra37_hour_energy_Jm2": None, "end_time_qc0": obs_ok, "complete_60_minute_energy_bin": False}
                interval_obs_energy, reason = end_time_energy(
                    {stamp: (rec["values"][obs_field], rec["qc"][obs_field]) for stamp, rec in {**day, **next_day}.items()},
                    t0, t1,
                )
                if interval_obs_energy is None:
                    skipped.append({"energy_interval_end_utc": t1.isoformat() + "Z", "reason": reason})
                else:
                    idx0, idx1 = hour - 1, hour
                    wrf_energy = {
                        arm: float(data["arrays"][arm][mapping["accum"]][idx1, j, i] - data["arrays"][arm][mapping["accum"]][idx0, j, i])
                        for arm in ("ra4", "ra37")
                    }
                    if not all(math.isfinite(v) for v in wrf_energy.values()):
                        raise RuntimeError("nonfinite WRF accumulator difference")
                    hourly_energy["obs"].append(interval_obs_energy)
                    hourly_energy["ra4"].append(wrf_energy["ra4"])
                    hourly_energy["ra37"].append(wrf_energy["ra37"])
                    hourly_energy["times"].append(t1.isoformat() + "Z")
                    hourly_energy["hours"].append(hour)
                    hourly_row.update({"obs_hour_energy_Jm2": interval_obs_energy, "ra4_hour_energy_Jm2": wrf_energy["ra4"], "ra37_hour_energy_Jm2": wrf_energy["ra37"], "complete_60_minute_energy_bin": True})
                hourly_rows.append(hourly_row)
            instant_stats = {arm: error_stats(instantaneous[arm], instantaneous["obs"]) for arm in ("ra4", "ra37")}
            energy_stats = {arm: error_stats(hourly_energy[arm], hourly_energy["obs"]) for arm in ("ra4", "ra37")}
            metrics[code]["instantaneous_hourly"][obs_field] = {"units": "W m-2", "n_common_qc0_times": len(instantaneous["obs"]), "times_utc": instantaneous["times"], "stats_by_arm": instant_stats, "aggregation_note": "WRF timestamp diagnostic compared with SURFRAD trailing 1-minute average ending at the same UTC timestamp; WRF cadence/held-value state is separately flagged as a representativeness limitation."}
            metrics[code]["hourly_energy"][obs_field] = {"units": "J m-2", "n_common_complete_hour_bins": len(hourly_energy["obs"]), "complete_hour_end_times_utc": hourly_energy["times"], "stats_by_arm": energy_stats, "excluded_intervals": [x for x in skipped if "energy_interval_end_utc" in x], "aggregation_note": "WRF hourly accumulation increment vs sum of 60 QC0 one-minute SURFRAD means times 60 s; no filling/interpolation."}
            # Full-day energy is reported only if every expected minute is valid.
            start = dt.datetime(2010, 6, 11, 0)
            end = dt.datetime(2010, 6, 12, 0)
            obs_day_energy, reason = end_time_energy(
                {stamp: (rec["values"][obs_field], rec["qc"][obs_field]) for stamp, rec in {**day, **next_day}.items()}, start, end,
            )
            if obs_day_energy is None:
                metrics[code]["daily_energy"][obs_field] = {"status": "INCOMPLETE_OBSERVATION", "units": "J m-2", "reason": reason, "observed_complete_energy": None, "wrf_accumulation_change": None}
            else:
                ra4 = data["arrays"]["ra4"][mapping["accum"]]
                ra37 = data["arrays"]["ra37"][mapping["accum"]]
                metrics[code]["daily_energy"][obs_field] = {
                    "status": "COMPLETE_QC0_24H",
                    "units": "J m-2",
                    "observation_sum": obs_day_energy,
                    "ra4_accumulation_change": float(ra4[24, j, i] - ra4[0, j, i]),
                    "ra37_accumulation_change": float(ra37[24, j, i] - ra37[0, j, i]),
                    "ra4_error_model_minus_obs": float((ra4[24, j, i] - ra4[0, j, i]) - obs_day_energy),
                    "ra37_error_model_minus_obs": float((ra37[24, j, i] - ra37[0, j, i]) - obs_day_energy),
                    "n_minute_intervals": 1440,
                    "coverage_utc": "[2010-06-11T00:00,2010-06-12T00:00]",
                }
    hashes_after = {str(path): sha256(path) for path in immutable_paths}
    if hashes_before != hashes_after:
        raise RuntimeError("one or more model/observation/receipt inputs changed during scoring")
    output_dir.mkdir(parents=True)
    report = {
        "status": "METRICS_COMPUTED",
        "scope": "Point-scale observed surface broadband radiation comparison for two QC-eligible SURFRAD stations; not a domain cloud/forecast accuracy score.",
        "run_receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path)},
        "preflight": {"path": str(preflight_path), "sha256": sha256(preflight_path)},
        "noaa_readme": {"path": str(readme), "sha256": sha256(readme)},
        "observation_file_hashes": station_file_hashes,
        "input_immutability": {"sha256_before": hashes_before, "sha256_after": hashes_after,
                               "all_unchanged": True, "history_file_count": len(history_paths)},
        "scoring_script": {"path": str(script_path), "sha256": hashes_before[str(script_path)]},
        "observed_fields": fields_used,
        "model_grid_shape": list(data["grid_shape"]),
        "model_times_utc": times,
        "model_field_metadata": data["field_metadata"],
        "global_metadata_by_arm": data["global_metadata"],
        "metrics": metrics,
        "limitations": [
            "One minute point observations are compared to a 20-km model cell about 10-12 km from the station.",
            "WRF flux snapshots may represent a held radiation-cadence diagnostic; the instant comparison pairs timestamp with a trailing one-minute mean.",
            "Daily energy is only reported when all 1,440 minute intervals pass QC; DRA downwelling longwave has one missing/flagged minute and receives no daily energy score.",
            "No comparison is made for near-surface temperature or station pressure in this primary radiation score because SURFRAD temp is at 10m vs WRF T2 at 2m and surface pressure requires height correction.",
            "The WRF input's upstream FNL observation assimilation was not audited; treat these as external station checks, not necessarily independent of every assimilated upstream datum.",
            "No cloud-fraction or hydrometeor observation score is implied by radiation-flux agreement.",
            "QC-passing negative SURFRAD shortwave values are preserved, not clipped.",
        ],
    }
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, default=json_default) + "\n")
    with (output_dir / "hourly.csv").open("w", newline="") as f:
        fields = list(hourly_rows[0]) if hourly_rows else []
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(hourly_rows)
    print(json.dumps({"status": report["status"], "output": str(output_dir), "stations": list(metrics), "fields": fields_used}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true", help="run synthetic-only helper tests; no real files read")
    mode.add_argument("--score", action="store_true", help="read validated paired WRF cases and SURFRAD observations to calculate actual metrics")
    parser.add_argument("--ra4-dir", type=Path, default=PLAN_DIR / "cases/ra4")
    parser.add_argument("--ra37-dir", type=Path, default=PLAN_DIR / "cases/ra37")
    parser.add_argument("--run-receipt", type=Path, default=PLAN_DIR / "execution.json")
    parser.add_argument("--preflight", type=Path, default=PLAN_DIR / "preflight.json")
    parser.add_argument("--output", type=Path, help="new output directory; must not already exist")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
        return 0
    if args.output is None:
        parser.error("--score requires --output NEW_DIRECTORY")
    score(args.run_receipt, args.preflight, args.ra4_dir, args.ra37_dir, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
