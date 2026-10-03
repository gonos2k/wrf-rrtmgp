#!/usr/bin/env python3
"""Read-only analysis of the corrected paired UDM27 RA4/RA37 24-hour trial.

This script never launches WRF and refuses partial runs. It validates hashes,
clocks, domain geometry, masks, and field metadata before calculating
AREA2D-weighted comparisons. Internal field identities are recorded as
contract checks; violations are written to the report and cause exit 1.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "build/udm-current-24h-plan"
CASES = PLAN / "cases"
EXPECTED_START = dt.datetime(2010, 6, 11, 0, 0, 0)
EXPECTED_END = dt.datetime(2010, 6, 12, 0, 0, 0)
HOURS = 24
FIELDS = ("SWDOWN", "GLW", "OLR", "T2", "PSFC")
GEOMETRY = ("XLAT", "XLONG", "MAPFAC_M", "AREA2D")
ENERGY_FIELDS = {
    "ACSWDNB": ("I_ACSWDNB", "surface_down_shortwave"),
    "ACLWDNB": ("I_ACLWDNB", "surface_down_longwave"),
    "ACSWUPT": ("I_ACSWUPT", "toa_up_shortwave"),
    "ACLWUPT": ("I_ACLWUPT", "toa_up_longwave"),
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _time_string(ds: netCDF4.Dataset, it: int) -> str:
    values = ds.variables["Times"][it]
    if values.ndim != 1:
        raise ValueError("Times must be a fixed-width character row")
    return b"".join(values.tolist()).decode("ascii")


def expected_times() -> list[str]:
    return [(EXPECTED_START + dt.timedelta(hours=h)).strftime("%Y-%m-%d_%H:%M:%S")
            for h in range(HOURS + 1)]


def parse_namelist(path: Path) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.split("!", 1)[0]
        match = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*?)\s*,?\s*$", line)
        if match:
            assignments[match.group(1).lower()] = re.sub(r"\s+", "", match.group(2)).lower()
    return assignments


def case_manifest(case: Path) -> dict:
    mutable = {"namelist.input", "namelist.output", "wrfinput_d01", "wrfbdy_d01",
               "wrf.exe", "run-receipt.json", "run.log"}
    assets = {}
    for path in sorted(case.iterdir()):
        if path.name in mutable or path.name.startswith(("wrfout_", "wrfrst_", "rsl.")):
            continue
        if path.is_file():
            if not path.exists():
                raise ValueError(f"broken static asset link: {path}")
            assets[path.name] = {"sha256": digest(path),
                                 "link_target": os.readlink(path) if path.is_symlink() else None,
                                 "resolved_path": str(path.resolve())}
        elif path.is_dir():
            raise ValueError(f"unexpected static directory: {path}")
    return {"namelist_sha256": digest(case / "namelist.input"),
            "wrfinput_sha256": digest(case / "wrfinput_d01"),
            "wrfbdy_sha256": digest(case / "wrfbdy_d01"), "assets": assets}


def _check_preflight_and_completion() -> dict:
    pre_path = PLAN / "preflight.json"
    run_path = PLAN / "execution.json"
    if not pre_path.is_file() or not run_path.is_file():
        raise ValueError("preflight.json and execution.json must exist")
    pre = json.loads(pre_path.read_text())
    run = json.loads(run_path.read_text())
    if pre.get("status") != "PREPARED_NOT_RUN":
        raise ValueError(f"unexpected preflight status {pre.get('status')}")
    if run.get("status") != "BOTH_VALIDATED":
        raise ValueError(f"both arms are not validated complete (execution status={run.get('status')})")
    if set(run.get("returncodes", {})) != {"ra4", "ra37"} or any(run["returncodes"][x] != 0 for x in ("ra4", "ra37")):
        raise ValueError("both zero-return-code arms are required")
    if set(run.get("validation", {})) != {"ra4", "ra37"}:
        raise ValueError("completion receipt lacks validated arm records")
    root_review = json.loads((PLAN / "root-review.json").read_text())
    if root_review.get("runner_sha256") != digest(PLAN / "run_pair.py"):
        raise ValueError("approved runner hash changed")
    if root_review.get("preflight_sha256") != digest(pre_path):
        raise ValueError("approved preflight hash changed")
    pinned = pre["inputs"]["sha256"]
    paths = pre["inputs"]["paths"]
    if set(pinned) != set(paths):
        raise ValueError("preflight source paths and hashes have different key sets")
    actual_hashes = {}
    for key, path_text in paths.items():
        path = Path(path_text)
        if not path.is_file():
            raise ValueError(f"pinned input is missing: {key}: {path}")
        actual_hashes[key] = digest(path)
        if actual_hashes[key] != pinned[key]:
            raise ValueError(f"pinned input hash changed: {key}")
    if actual_hashes.get("executable") != root_review["executable_sha256"]:
        raise ValueError("executable does not match root-reviewed build")
    namelists = {name: parse_namelist(CASES / name / "namelist.input") for name in ("ra4", "ra37")}
    allowed = {"ra_lw_physics", "ra_sw_physics", "rrtmgp_udm_frozen_optics", "rrtmgp_udm_frozen_table"}
    keys = set(namelists["ra4"]) | set(namelists["ra37"])
    changed = {k for k in keys if namelists["ra4"].get(k) != namelists["ra37"].get(k)}
    if changed != allowed:
        raise ValueError(f"unexpected paired namelist difference set: {sorted(changed)}")
    if namelists["ra4"].get("ra_lw_physics") != "4,4,4" or namelists["ra4"].get("ra_sw_physics") != "4,4,4":
        raise ValueError("RA4 namelist radiation configuration mismatch")
    if namelists["ra37"].get("ra_lw_physics") != "37,37,37" or namelists["ra37"].get("ra_sw_physics") != "37,37,37":
        raise ValueError("RA37 namelist radiation configuration mismatch")
    if namelists["ra37"].get("rrtmgp_udm_frozen_optics") != "1":
        raise ValueError("RA37 frozen-optics mode 1 is required")
    for name in ("ra4", "ra37"):
        expected = pre["case_immutable_state"][name]
        if case_manifest(CASES / name) != expected:
            raise ValueError(f"immutable case assets changed for {name}")
    return {"preflight": pre, "execution": run, "root_review": root_review,
            "input_hashes": actual_hashes}


def _read_history(case: Path) -> dict:
    paths = sorted(case.glob("wrfout_d01_*"))
    wanted_times = expected_times()
    if len(paths) != len(wanted_times):
        raise ValueError(f"{case.name}: expected 25 history files, found {len(paths)}")
    records = []
    geometry_ref = None
    geometry_metadata = None
    patch_bounds = None
    field_metadata_ref = {}
    dynamic_metadata_ref = {}
    for index, path in enumerate(paths):
        with netCDF4.Dataset(path, "r") as ds:
            if "Times" not in ds.variables or len(ds.dimensions.get("Time", [])) != 1:
                raise ValueError(f"{path}: expected one output Time record")
            stamp = _time_string(ds, 0)
            if stamp != wanted_times[index]:
                raise ValueError(f"{case.name}: history clock mismatch {stamp} vs {wanted_times[index]}")
            if "XTIME" not in ds.variables:
                raise ValueError(f"{path}: missing XTIME")
            xtime = float(np.asarray(ds.variables["XTIME"][0]))
            expected_minute = index * 60.0
            if not math.isfinite(xtime) or abs(xtime - expected_minute) > 1.0e-4:
                raise ValueError(f"{case.name}: XTIME {xtime} at {stamp}; expected {expected_minute} min")
            abs_delta = (dt.datetime.strptime(stamp, "%Y-%m-%d_%H:%M:%S") - EXPECTED_START).total_seconds()
            if abs(xtime * 60.0 - abs_delta) > 1.0e-4:
                raise ValueError(f"{case.name}: XTIME and absolute Times disagree at {stamp}")
            for attr in ("WEST-EAST_PATCH_START_UNSTAG", "WEST-EAST_PATCH_END_UNSTAG",
                         "SOUTH-NORTH_PATCH_START_UNSTAG", "SOUTH-NORTH_PATCH_END_UNSTAG"):
                if attr not in ds.ncattrs():
                    raise ValueError(f"{path}: missing physical-grid bound attribute {attr}")
            bounds = {x: int(ds.getncattr(x)) for x in (
                "WEST-EAST_PATCH_START_UNSTAG", "WEST-EAST_PATCH_END_UNSTAG",
                "SOUTH-NORTH_PATCH_START_UNSTAG", "SOUTH-NORTH_PATCH_END_UNSTAG")}
            nx, ny = len(ds.dimensions["west_east"]), len(ds.dimensions["south_north"])
            if not (1 <= bounds["WEST-EAST_PATCH_START_UNSTAG"] <= bounds["WEST-EAST_PATCH_END_UNSTAG"] <= nx and
                    1 <= bounds["SOUTH-NORTH_PATCH_START_UNSTAG"] <= bounds["SOUTH-NORTH_PATCH_END_UNSTAG"] <= ny):
                raise ValueError(f"{path}: invalid unstaggered mass-grid patch bounds {bounds}")
            if (nx, ny) != (289, 189) or bounds != {
                    "WEST-EAST_PATCH_START_UNSTAG": 1,
                    "WEST-EAST_PATCH_END_UNSTAG": 289,
                    "SOUTH-NORTH_PATCH_START_UNSTAG": 1,
                    "SOUTH-NORTH_PATCH_END_UNSTAG": 189}:
                raise ValueError(f"{path}: expected complete 289x189 physical mass grid, got dims={(nx, ny)} bounds={bounds}")
            if patch_bounds is None:
                patch_bounds = bounds
            elif patch_bounds != bounds:
                raise ValueError(f"{case.name}: mass-grid patch bounds change with time")
            geo = {}
            meta = {}
            for variable in GEOMETRY:
                if variable not in ds.variables:
                    raise ValueError(f"{path}: missing geometry variable {variable}")
                arr = np.ma.asarray(ds.variables[variable][0])
                if arr.ndim != 2:
                    raise ValueError(f"{path}:{variable} expected 2-D mass-grid array")
                if np.ma.getmaskarray(arr).any() or not np.isfinite(np.asarray(arr)).all():
                    raise ValueError(f"{path}:{variable} has masked/nonfinite geometry")
                geo[variable] = np.asarray(arr).copy()
                v = ds.variables[variable]
                meta[variable] = {"dimensions": list(v.dimensions), "dtype": str(v.dtype),
                                  "units": str(getattr(v, "units", ""))}
            if geometry_ref is None:
                geometry_ref, geometry_metadata = geo, meta
            else:
                for variable in GEOMETRY:
                    if not np.array_equal(geometry_ref[variable], geo[variable]):
                        raise ValueError(f"{case.name}: static {variable} changed at {stamp}")
                    if geometry_metadata[variable] != meta[variable]:
                        raise ValueError(f"{case.name}: static geometry metadata changed: {variable}")
            fields = {}
            fields_meta = {}
            expected_field_units = {
                "SWDOWN": {"wm-2", "wm^-2", "w/m2", "w/m^2"},
                "GLW": {"wm-2", "wm^-2", "w/m2", "w/m^2"},
                "OLR": {"wm-2", "wm^-2", "w/m2", "w/m^2"},
                "T2": {"k", "kelvin"},
                "PSFC": {"pa", "pascal", "pascals"},
            }
            for field in FIELDS:
                if field not in ds.variables:
                    raise ValueError(f"{path}: missing comparison field {field}")
                var = ds.variables[field]
                vals = np.ma.asarray(var[0])
                if vals.ndim != 2 or vals.shape != geo["AREA2D"].shape:
                    raise ValueError(f"{path}:{field}: expected matching 2-D mass-grid field")
                fields[field] = vals.copy()
                fields_meta[field] = {"dimensions": list(var.dimensions), "dtype": str(var.dtype),
                                      "units": str(getattr(var, "units", ""))}
                meta_key = (tuple(var.dimensions), str(var.dtype),
                            str(getattr(var, "units", "")).lower().replace(" ", ""))
                expected_dims = ("Time", "south_north", "west_east")
                if tuple(var.dimensions) != expected_dims:
                    raise ValueError(f"{path}:{field}: expected dimensions {expected_dims}, got {var.dimensions}")
                units_key = meta_key[2]
                if units_key not in expected_field_units[field]:
                    raise ValueError(f"{path}:{field}: unexpected units {fields_meta[field]['units']!r}")
                if field in field_metadata_ref and field_metadata_ref[field] != meta_key:
                    raise ValueError(f"{case.name}:{field}: dimensions/dtype/units changed at {stamp}")
                field_metadata_ref[field] = meta_key
                if not np.isfinite(vals.compressed()).all():
                    raise ValueError(f"{path}:{field}: nonfinite valid values")
            dynamic = {}
            for field in ("SWDOWN", "SWDNB", "SWDDIR", "SWDDIF", "GSW", "SWUPB",
                          "GLW", "LWDNB", "OLR", "LWUPT", "RTHRATEN", "RTHRATLW", "RTHRATSW"):
                if field in ds.variables:
                    var = ds.variables[field]
                    vals = np.ma.asarray(var[0])
                    dynamic[field] = vals.copy()
                    fields_meta.setdefault(field, {"dimensions": list(var.dimensions), "dtype": str(var.dtype),
                                                   "units": str(getattr(var, "units", ""))})
                    meta_key = (tuple(var.dimensions), str(var.dtype),
                                str(getattr(var, "units", "")).lower().replace(" ", ""))
                    if (len(var.dimensions) < 3 or var.dimensions[0] != "Time" or
                            tuple(var.dimensions[-2:]) != ("south_north", "west_east") or
                            tuple(vals.shape[-2:]) != geo["AREA2D"].shape):
                        raise ValueError(f"{path}:{field}: expected time-leading fields on the mass grid, got {var.dimensions}")
                    if field.startswith("RTHRATE"):
                        valid_units = {"ks-1", "ks^-1", "k/s"}
                    else:
                        valid_units = {"wm-2", "wm^-2", "w/m2", "w/m^2"}
                    if meta_key[2] not in valid_units:
                        raise ValueError(f"{path}:{field}: unexpected units {getattr(var, 'units', '')!r}")
                    if field in dynamic_metadata_ref and dynamic_metadata_ref[field] != meta_key:
                        raise ValueError(f"{case.name}:{field}: dimensions/dtype/units changed at {stamp}")
                    dynamic_metadata_ref[field] = meta_key
            accum = {}
            for ac_name, (i_name, label) in ENERGY_FIELDS.items():
                if ac_name in ds.variables:
                    ac = np.ma.asarray(ds.variables[ac_name][0])
                    if ac.shape != geo["AREA2D"].shape:
                        raise ValueError(f"{path}:{ac_name}: invalid shape")
                    if np.ma.getmaskarray(ac).any() or not np.isfinite(np.asarray(ac)).all():
                        raise ValueError(f"{path}:{ac_name}: masked or nonfinite accumulated values")
                    if "BUCKET_J" not in ds.ncattrs():
                        raise ValueError(f"{path}: accumulators found without BUCKET_J global attribute")
                    bucket_j = float(ds.getncattr("BUCKET_J"))
                    if not math.isfinite(bucket_j):
                        raise ValueError(f"{path}: nonfinite BUCKET_J={bucket_j}")
                    if bucket_j > 0:
                        if i_name not in ds.variables:
                            raise ValueError(f"{path}: positive BUCKET_J but missing {i_name}")
                        bucket_count = np.ma.asarray(ds.variables[i_name][0])
                        if bucket_count.shape != ac.shape or np.ma.getmaskarray(bucket_count).any() or not np.isfinite(np.asarray(bucket_count)).all():
                            raise ValueError(f"{path}:{i_name}: invalid bucket-count array")
                    else:
                        bucket_count = np.ma.asarray(np.zeros(ac.shape, dtype=np.int64))
                        bucket_j = 0.0
                    accum[ac_name] = {"remainder": ac.copy(), "bucket_count": bucket_count.copy(),
                                      "bucket_j": bucket_j, "bucket_enabled": bucket_j > 0,
                                      "units": str(getattr(ds.variables[ac_name], "units", "")),
                                      "dtype": str(ds.variables[ac_name].dtype),
                                      "dims": list(ds.variables[ac_name].dimensions), "label": label}
            records.append({"path": path, "time": stamp, "xtime_minutes": xtime,
                            "fields": fields, "fields_meta": fields_meta,
                            "dynamic": dynamic, "accum": accum})
    area = geometry_ref["AREA2D"].astype(np.float64)
    if geometry_metadata["AREA2D"]["units"].lower().replace(" ", "") not in ("m2", "m^2"):
        raise ValueError(f"AREA2D units must be m2, found {geometry_metadata['AREA2D']['units']!r}")
    if not np.isfinite(area).all() or np.any(area <= 0):
        raise ValueError("AREA2D must be finite and positive everywhere")
    rows = slice(patch_bounds["SOUTH-NORTH_PATCH_START_UNSTAG"] - 1,
                 patch_bounds["SOUTH-NORTH_PATCH_END_UNSTAG"])
    cols = slice(patch_bounds["WEST-EAST_PATCH_START_UNSTAG"] - 1,
                 patch_bounds["WEST-EAST_PATCH_END_UNSTAG"])
    area = area[rows, cols]
    if area.shape != (189, 289):
        raise ValueError(f"expected complete physical AREA2D shape (189, 289), got {area.shape}")
    geometry = {k: v[rows, cols] for k, v in geometry_ref.items()}
    return {"records": records, "area": area, "geometry": geometry,
            "geometry_metadata": geometry_metadata, "patch_bounds": patch_bounds,
            "physical_slice_zero_based": {"j": [rows.start, rows.stop], "i": [cols.start, cols.stop]}}


def _field_at(record: dict, field: str, rows: slice, cols: slice) -> tuple[np.ndarray, np.ndarray]:
    ma = np.ma.asarray(record["fields"][field])[rows, cols]
    mask = np.ma.getmaskarray(ma)
    vals = np.asarray(ma.filled(np.nan), dtype=np.float64)
    return vals, mask


def area_metrics(a4: np.ndarray, a37: np.ndarray, area: np.ndarray,
                 mask4: np.ndarray | None = None, mask37: np.ndarray | None = None) -> dict:
    """AREA2D-weighted delta mean/RMSE and unweighted domain L-infinity."""
    if a4.shape != a37.shape or a4.shape != area.shape:
        raise ValueError("area_metrics shape mismatch")
    if not np.isfinite(area).all() or np.any(area <= 0):
        raise ValueError("area weights must all be finite and positive; domain cells cannot be dropped")
    mask4 = np.zeros(a4.shape, dtype=bool) if mask4 is None else np.asarray(mask4, dtype=bool)
    mask37 = np.zeros(a37.shape, dtype=bool) if mask37 is None else np.asarray(mask37, dtype=bool)
    if mask4.shape != a4.shape or mask37.shape != a37.shape:
        raise ValueError("field mask shape mismatch")
    if not np.array_equal(mask4, mask37):
        raise ValueError("paired field missing masks differ")
    unmasked = ~mask4
    if np.any(~np.isfinite(a4[unmasked])) or np.any(~np.isfinite(a37[unmasked])):
        raise ValueError("unmasked comparison field contains nonfinite values; domain cells cannot be dropped")
    valid = unmasked
    n = int(np.count_nonzero(valid))
    if n == 0:
        raise ValueError("no common valid cells")
    delta = a37[valid] - a4[valid]
    weights = area[valid]
    wsum = float(np.sum(weights, dtype=np.float64))
    mean_delta = float(np.sum(delta * weights, dtype=np.float64) / wsum)
    rmse = float(np.sqrt(np.sum(delta * delta * weights, dtype=np.float64) / wsum))
    return {"valid_cell_count": n, "area_sum_m2": wsum,
            "ra4_area_mean": float(np.sum(a4[valid] * weights, dtype=np.float64) / wsum),
            "ra37_area_mean": float(np.sum(a37[valid] * weights, dtype=np.float64) / wsum),
            "difference_area_mean_ra37_minus_ra4": mean_delta,
            "difference_area_rmse": rmse,
            "difference_linf_abs": float(np.max(np.abs(delta)))}


def _spacing(x: np.ndarray) -> np.ndarray:
    dtype = x.dtype if np.issubdtype(x.dtype, np.floating) else np.dtype("float32")
    xx = np.asarray(x, dtype=dtype)
    return np.abs(np.spacing(np.abs(xx))).astype(np.float64)


def identity_check(lhs: np.ndarray, a: np.ndarray, b: np.ndarray | None,
                   sign: int, floor: float, label: str) -> dict:
    """Check lhs=a(+/-)b using 4 propagated storage-ULPs plus a small floor."""
    x = np.ma.asarray(lhs)
    aa = np.ma.asarray(a)
    if b is None:
        bb_mask = np.ma.getmaskarray(aa)
        bb = np.ma.array(np.zeros_like(np.asarray(aa)), mask=bb_mask, copy=False)
    else:
        bb = np.ma.asarray(b)
        bb_mask = np.ma.getmaskarray(bb)
    if x.shape != aa.shape or x.shape != bb.shape:
        raise ValueError(f"{label}: identity shape mismatch")
    xm, am = np.ma.getmaskarray(x), np.ma.getmaskarray(aa)
    if not np.array_equal(xm, am) or not np.array_equal(xm, bb_mask):
        return {"label": label, "status": "FAIL", "reason": "operand masks differ", "cells": 0}
    mask = xm | am | bb_mask
    xv, av, bv = np.asarray(x.filled(np.nan)), np.asarray(aa.filled(np.nan)), np.asarray(bb.filled(np.nan))
    finite = np.isfinite(xv) & np.isfinite(av) & np.isfinite(bv)
    if np.any(~finite & ~mask):
        return {"label": label, "status": "FAIL", "reason": "unmasked operand contains nonfinite values",
                "cells": int(np.count_nonzero(~mask & finite)),
                "nonfinite_unmasked_cells": int(np.count_nonzero(~finite & ~mask))}
    residual = xv.astype(np.float64) - av.astype(np.float64) - sign * bv.astype(np.float64)
    tol = 4.0 * (_spacing(xv) + _spacing(av) + _spacing(bv)) + floor
    valid = ~mask & np.isfinite(residual) & np.isfinite(tol) & (tol > 0)
    if not np.any(valid):
        return {"label": label, "status": "FAIL", "reason": "no finite unmasked cells", "cells": 0}
    normalized = np.abs(residual[valid]) / tol[valid]
    worst = int(np.argmax(normalized))
    status = "PASS" if float(normalized[worst]) <= 1.0 else "FAIL"
    return {"label": label, "status": status, "cells": int(valid.sum()),
            "tolerance": f"4*(ULP(lhs)+ULP(term1)+ULP(term2))+{floor:g}",
            "max_abs_residual": float(np.max(np.abs(residual[valid]))),
            "max_normalized_error": float(normalized[worst]),
            "pass_threshold_normalized_error_le": 1.0}


def _check_identity_field(arm: dict, stamp_index: int, lhs: str, a: str,
                          b: str | None, sign: int, floor: float, label: str,
                          rows: slice, cols: slice) -> dict:
    record = arm["records"][stamp_index]
    present = [x in record["dynamic"] for x in (lhs, a) if x]
    if not all(present) or (b is not None and b not in record["dynamic"]):
        return {"label": label, "status": "SKIP", "reason": "required variable absent"}
    result = identity_check(record["dynamic"][lhs][..., rows, cols], record["dynamic"][a][..., rows, cols],
                            record["dynamic"][b][..., rows, cols] if b else None,
                            sign, floor, label)
    operands = {name: record["fields_meta"].get(name) for name in (lhs, a, b) if name}
    result["operands"] = operands
    if all(operands.values()):
        dims = {tuple(x["dimensions"]) for x in operands.values()}
        units = {x["units"].lower().replace(" ", "") for x in operands.values()}
        if len(dims) != 1 or len(units) != 1:
            result["status"] = "FAIL"
            result["reason"] = "operand dimensions or units differ"
        if lhs == "RTHRATEN":
            expected_units = {"ks-1", "ks^-1", "k/s"}
        else:
            expected_units = {"wm-2", "wm^-2", "w/m2", "w/m^2"}
        if units and not units.issubset(expected_units):
            result["status"] = "FAIL"
            result["reason"] = f"unexpected identity units: {sorted(units)}"
    return result


def _variable_metadata(record: dict, field: str) -> dict:
    return record["fields_meta"][field]


def _compare_pair(meta4: dict, meta37: dict, field: str) -> None:
    if meta4[field] != meta37[field]:
        raise ValueError(f"{field}: paired dimensions/dtype/units differ: {meta4[field]} vs {meta37[field]}")
    units = meta4[field]["units"]
    if not units:
        raise ValueError(f"{field}: missing units attribute")


def _energy_analysis(r4: dict, r37: dict, area: np.ndarray,
                     j0: int, j1: int, i0: int, i1: int) -> dict:
    rows, cols = slice(j0, j1), slice(i0, i1)
    output = {}
    records = {"ra4": r4["records"], "ra37": r37["records"]}
    for field, (_count, label) in ENERGY_FIELDS.items():
        if not all(field in rec["accum"] for seq in records.values() for rec in (seq[0], seq[-1])):
            output[field] = {"status": "SKIP", "reason": "accumulator absent at an endpoint"}
            continue
        endpoint = {}
        metadata = {}
        shared_meta = None
        shared_bucket_meta = None
        shared_bucket_j = None
        for arm, seq in records.items():
            e0, e1 = seq[0]["accum"][field], seq[-1]["accum"][field]
            if e0["bucket_j"] != e1["bucket_j"]:
                raise ValueError(f"{arm}/{field}: BUCKET_J changed during run")
            if e0["units"].lower().replace(" ", "") not in ("jm-2", "jm^-2"):
                raise ValueError(f"{arm}/{field}: expected J m-2, found {e0['units']!r}")
            if e0["dims"] != e1["dims"]:
                raise ValueError(f"{arm}/{field}: accumulator dimensions changed")
            if e0["dtype"] != e1["dtype"] or e0["units"] != e1["units"]:
                raise ValueError(f"{arm}/{field}: accumulator dtype or units changed between endpoints")
            if shared_meta is None:
                shared_meta = (e0["dims"], e0["dtype"], e0["units"])
            elif shared_meta != (e0["dims"], e0["dtype"], e0["units"]):
                raise ValueError(f"{field}: accumulator dimensions/dtype/units differ between arms")
            if e0["bucket_count"].dtype != e1["bucket_count"].dtype:
                raise ValueError(f"{arm}/{field}: bucket count dtype changed between endpoints")
            bucket_meta = (str(e0["bucket_count"].dtype), e0["bucket_count"].shape)
            if shared_bucket_meta is None:
                shared_bucket_meta = bucket_meta
            elif shared_bucket_meta != bucket_meta:
                raise ValueError(f"{field}: bucket count dtype/shape differs between arms")
            b0, b1 = e0["bucket_j"], e1["bucket_j"]
            if shared_bucket_j is None:
                shared_bucket_j = b0
            elif shared_bucket_j != b0:
                raise ValueError(f"{field}: BUCKET_J differs between arms")
            total0 = np.asarray(e0["remainder"], dtype=np.float64) + b0 * np.asarray(e0["bucket_count"], dtype=np.float64)
            total1 = np.asarray(e1["remainder"], dtype=np.float64) + b1 * np.asarray(e1["bucket_count"], dtype=np.float64)
            endpoint[arm] = (total0[rows, cols], total1[rows, cols])
            if e0["bucket_enabled"] != e1["bucket_enabled"]:
                raise ValueError(f"{arm}/{field}: bucket mode changed during run")
            metadata[arm] = {"bucket_j": b0, "bucket_enabled": e0["bucket_enabled"],
                             "reconstruction": "AC + BUCKET_J*I_AC" if e0["bucket_enabled"] else "AC (BUCKET_J<=0)",
                             "accumulator_units": e0["units"],
                             "count_dtype": str(e0["bucket_count"].dtype)}
        e4 = endpoint["ra4"][1] - endpoint["ra4"][0]
        e37 = endpoint["ra37"][1] - endpoint["ra37"][0]
        stats = area_metrics(e4, e37, area)
        stats.update({"status": "PASS", "description": label,
                      "ra4_daily_energy_area_mean_j_m2": float(np.average(e4, weights=area)),
                      "ra37_daily_energy_area_mean_j_m2": float(np.average(e37, weights=area)),
                      "paired_energy_area_mean_difference_j_m2": float(np.average(e37-e4, weights=area)),
                      "paired_energy_area_mean_difference_w_m2_24h": float(np.average(e37-e4, weights=area)/86400.0),
                      "domain_integrated_difference_j": float(np.sum((e37-e4)*area, dtype=np.float64)),
                      "interval": {"start": r4["records"][0]["time"], "end": r4["records"][-1]["time"],
                                  "seconds": 86400},
                      "bucket_reconstruction": "per-arm metadata records AC-only when BUCKET_J<=0; otherwise AC + BUCKET_J*I_AC",
                      "arms": metadata})
        output[field] = stats
    return output


def _field_contracts(r4: dict, r37: dict, rows: slice, cols: slice) -> dict:
    out = []
    for arm_name, arm in (("ra4", r4), ("ra37", r37)):
        for n, record in enumerate(arm["records"]):
            for lhs, a, b in (("RTHRATEN", "RTHRATLW", "RTHRATSW"),
                              ("GLW", "LWDNB", None), ("OLR", "LWUPT", None)):
                floor = 1.0e-12 if lhs == "RTHRATEN" else 1.0e-6
                result = _check_identity_field(arm, n, lhs, a, b, 1, floor,
                                               f"{arm_name}/{record['time']}/{lhs}={a}" + (f"+{b}" if b else ""), rows, cols)
                out.append(result)
    for n, record in enumerate(r37["records"]):
        for lhs, a, b in (("SWDOWN", "SWDNB", None),
                          ("SWDOWN", "SWDDIR", "SWDDIF"),
                          ("GSW", "SWDNB", "SWUPB")):
            sign = -1 if lhs == "GSW" else 1
            result = _check_identity_field(r37, n, lhs, a, b, sign, 1.0e-6,
                                           f"ra37/{record['time']}/{lhs}={a}" + (("-" if sign < 0 else "+") + b if b else ""), rows, cols)
            out.append(result)
    failed = sum(x["status"] == "FAIL" for x in out)
    skipped = sum(x["status"] == "SKIP" for x in out)
    status = "FAIL" if failed else ("INCOMPLETE_REQUIRED_FIELDS" if skipped else "PASS")
    return {"status": status,
            "checks": out, "check_count": len(out),
            "failed_count": failed, "skipped_count": skipped,
            "note": "Tolerances use propagated operand storage ULPs plus 1e-12 K/s for tendency or 1e-6 W/m2 for flux identities."}


def _plot(results: dict, r4: dict, r37: dict, output: Path,
          area: np.ndarray, geo: dict, rows: slice, cols: slice) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    made=[]
    times = np.arange(25, dtype=np.float64)
    fig, axes = plt.subplots(3, 2, figsize=(11, 10), constrained_layout=True)
    for ax, field in zip(axes.flat, FIELDS):
        lines=results["timeseries"][field]
        ax.plot(times, [x["ra4_area_mean"] for x in lines], label="RA4")
        ax.plot(times, [x["ra37_area_mean"] for x in lines], label="RA37")
        ax.set_title(field)
        ax.set_xlabel("Hours since 2010-06-11 00:00 UTC")
        ax.set_ylabel(lines[0]["units"])
        ax.grid(True, alpha=.3)
        ax.legend(fontsize=8)
    axes.flat[-1].axis("off")
    fig.suptitle("Area-weighted hourly history values (coupled trajectories)")
    for ext in ("png", "pdf"):
        p=output/f"area_mean_time_curves.{ext}"; fig.savefig(p,dpi=150); made.append(str(p))
    plt.close(fig)
    fig, axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
    # ``geo`` is already cropped to the physical unstaggered grid.
    lon=geo["XLONG"]; lat=geo["XLAT"]
    for ax,field in zip(axes,("SWDOWN","GLW","OLR")):
        v4,_=_field_at(r4["records"][-1],field,rows,cols)
        v37,_=_field_at(r37["records"][-1],field,rows,cols)
        delta=v37-v4
        im=ax.pcolormesh(lon,lat,delta,shading="auto",cmap="RdBu_r")
        fig.colorbar(im,ax=ax,label=f"RA37 − RA4 ({_variable_metadata(r4['records'][-1],field)['units']})")
        ax.set_title(f"{field} difference at 24 h")
        ax.set_xlabel("Longitude (degrees east)"); ax.set_ylabel("Latitude (degrees north)")
    fig.suptitle("Paired endpoint field differences; common physical domain")
    for ext in ("png","pdf"):
        p=output/f"endpoint_difference_maps.{ext}";fig.savefig(p,dpi=150);made.append(str(p))
    plt.close(fig)
    return made


def analyze(output_dir: Path) -> dict:
    if output_dir.exists():
        raise ValueError(f"refusing to overwrite output directory: {output_dir}")
    provenance = _check_preflight_and_completion()
    r4 = _read_history(CASES / "ra4")
    r37 = _read_history(CASES / "ra37")
    if len(r4["records"]) != 25 or len(r37["records"]) != 25:
        raise ValueError("exactly 25 records per arm are required")
    for arm, label in ((r4, "RA4"), (r37, "RA37")):
        if arm["patch_bounds"] != r4["patch_bounds"]:
            raise ValueError("physical mass-grid bounds differ between arms")
        if arm["geometry_metadata"] != r4["geometry_metadata"]:
            raise ValueError("paired geometry dimensions/dtypes/units differ")
        for geo in GEOMETRY:
            if not np.array_equal(arm["geometry"][geo], r4["geometry"][geo]):
                raise ValueError(f"paired physical geometry differs: {geo}")
    times4=[x["time"] for x in r4["records"]]
    times37=[x["time"] for x in r37["records"]]
    if times4 != times37 or times4 != expected_times():
        raise ValueError("paired histories do not have the same exact 25 timestamps")
    r4["rows"],r4["cols"] = (slice(r4["physical_slice_zero_based"]["j"][0],r4["physical_slice_zero_based"]["j"][1]),slice(r4["physical_slice_zero_based"]["i"][0],r4["physical_slice_zero_based"]["i"][1]))
    r37["rows"],r37["cols"] = r4["rows"],r4["cols"]
    area=r4["area"]
    timeseries={}
    for field in FIELDS:
        series=[]
        for i,(a,b) in enumerate(zip(r4["records"],r37["records"])):
            _compare_pair(a["fields_meta"],b["fields_meta"],field)
            v4,m4=_field_at(a,field,r4["rows"],r4["cols"])
            v37,m37=_field_at(b,field,r37["rows"],r37["cols"])
            stat=area_metrics(v4,v37,area,m4,m37)
            stat.update({"time":a["time"],"xtime_minutes":a["xtime_minutes"],
                         "units":a["fields_meta"][field]["units"],
                         "dimensions":a["fields_meta"][field]["dimensions"],
                         "dtype":a["fields_meta"][field]["dtype"]})
            series.append(stat)
        timeseries[field]=series
    contracts=_field_contracts(r4,r37,r4["rows"],r4["cols"])
    energies=_energy_analysis(r4, r37, area,
                              r4["rows"].start, r4["rows"].stop,
                              r4["cols"].start, r4["cols"].stop)
    out={"schema":"UDM_CURRENT_24H_AREA_WEIGHTED_PAIRED_ANALYSIS_V1",
         "status":("FIELD_MATH_CONTRACT_FAILURE" if contracts["status"]=="FAIL" else
                   ("INCOMPLETE_FIELD_MATH_CONTRACTS" if contracts["status"]=="INCOMPLETE_REQUIRED_FIELDS" else "PASS")),
         "case_status":"BOTH_VALIDATED",
         "scope":"paired 24-hour UDM27 RA4/RA4 versus RA37/RA37 mode-1 coupled trajectories; this is not an observational skill or solver-only experiment",
         "difference_convention":"RA37 minus RA4",
         "source_and_inputs":{
             "runner_sha256":provenance["root_review"]["runner_sha256"],
             "preflight_sha256":provenance["root_review"]["preflight_sha256"],
             "executable_sha256":provenance["root_review"]["executable_sha256"],
             "input_hashes":provenance["input_hashes"],
             "namelist_sha256":{"ra4":digest(CASES/"ra4"/"namelist.input"),"ra37":digest(CASES/"ra37"/"namelist.input")},
             "history_file_sha256":{"ra4":[digest(x["path"]) for x in r4["records"]],"ra37":[digest(x["path"]) for x in r37["records"]]},
             "static_geometry_exact_equal":True,
             "geometry_variables":{k:r4["geometry_metadata"][k] for k in GEOMETRY}},
         "time_axis":{"timestamps":times4,"xtime_minutes":[x["xtime_minutes"] for x in r4["records"]],
                      "exactly_25_hourly_records":True,"initial_t0_is_not_counted_as_an_hour":True},
         "domain":{"patch_bounds_one_based_unstaggered":r4["patch_bounds"],
                   "array_slice_zero_based":{"j":[r4["rows"].start,r4["rows"].stop],"i":[r4["cols"].start,r4["cols"].stop]},
                   "physical_cell_count":int(area.size),"area_weighting":"AREA2D (m2)",
                   "area_sum_m2":float(np.sum(area,dtype=np.float64)),
                   "area_mean":"sum(value*AREA2D)/sum(AREA2D)",
                   "area_rmse":"sqrt(sum((RA37-RA4)^2*AREA2D)/sum(AREA2D))",
                   "linf":"max(abs(RA37-RA4)) over same physical grid (not area weighted)"},
         "timeseries":timeseries,
         "daily_accumulator_energy":energies,
         "field_math_contracts":contracts,
         "limits":["Different coupled trajectories combine radiation changes and atmospheric feedback; differences are not same-state solver attribution.",
                   "This paired developer-case run does not establish forecast accuracy or superiority.",
                   "Hourly instantaneous histories are not treated as actual hourly-mean fluxes. Daily energy uses WRF timestep accumulators when present.",
                   "Any failed field identity remains reported as failure; no fields or cells are silently omitted."]}
    output_dir.mkdir(parents=True)
    out["analysis_script_sha256"]=digest(Path(__file__))
    (output_dir/"analysis.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    with (output_dir/"hourly_area_metrics.csv").open("w",newline="") as f:
        cols=["field","time","units","valid_cell_count","area_sum_m2","ra4_area_mean","ra37_area_mean","difference_area_mean_ra37_minus_ra4","difference_area_rmse","difference_linf_abs"]
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        for field,series in timeseries.items():
            for row in series:w.writerow({"field":field,**{k:row[k] for k in cols if k!="field"}})
    plots=[]
    try:
        plots=_plot(out,r4,r37,output_dir,area,r4["geometry"],r4["rows"],r4["cols"])
    except ImportError:
        out["plots"]={"status":"SKIPPED","reason":"matplotlib unavailable"}
    else:
        out["plots"]={"status":"WRITTEN","files":[Path(x).name for x in plots]}
    (output_dir/"analysis.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    return out


def self_test() -> dict:
    area=np.array([[1.,3.]])
    a4=np.array([[1.,2.]])
    a37=np.array([[3.,6.]])
    m=area_metrics(a4,a37,area)
    assert math.isclose(m["difference_area_mean_ra37_minus_ra4"],3.5)
    assert math.isclose(m["difference_area_rmse"],math.sqrt(13.0))
    total0=10.0+100.0*2
    total1=20.0+100.0*5
    assert total1-total0==310.0
    x=np.array([[np.float32(.3)]])
    u=np.array([[np.float32(.1)]])
    v=np.array([[np.float32(.2)]])
    ok=identity_check(x,u,v,1,1e-6,"synthetic-flux-sum")
    assert ok["status"]=="PASS",ok
    bad=identity_check(np.array([[np.float32(2.)]]),u,v,1,1e-6,"synthetic-bad-flux-sum")
    assert bad["status"]=="FAIL",bad
    shared_mask=np.array([[True,False]])
    masked_identity=identity_check(np.ma.array([[0.,np.float32(.3)]],mask=shared_mask,dtype=np.float32),
                                   np.ma.array([[0.,np.float32(.3)]],mask=shared_mask,dtype=np.float32),
                                   None,1,1e-6,"synthetic-masked-two-term")
    assert masked_identity["status"]=="PASS" and masked_identity["cells"]==1,masked_identity
    nonfinite=identity_check(np.array([[np.float32(np.inf),np.float32(.3)]]),
                             np.array([[np.float32(.1),np.float32(.1)]]),
                             np.array([[np.float32(.2),np.float32(.2)]]),
                             1,1e-6,"synthetic-nonfinite")
    assert nonfinite["status"]=="FAIL" and nonfinite["nonfinite_unmasked_cells"]==1,nonfinite
    area2=np.array([[1.,3.]])
    def energy_entry(ac, counts, bucket_j):
        return {"remainder":np.asarray(ac,dtype=np.float32),
                "bucket_count":np.asarray(counts,dtype=np.int32),
                "bucket_j":bucket_j,"bucket_enabled":bucket_j>0,
                "units":"J m-2","dtype":"float32",
                "dims":["south_north","west_east"],"label":"synthetic"}
    def energy_arm(start, end, bucket_j, counts0, counts1):
        return {"records":[{"time":"2010-06-11_00:00:00","accum":{"ACSWDNB":energy_entry(start,counts0,bucket_j)}},
                            {"time":"2010-06-12_00:00:00","accum":{"ACSWDNB":energy_entry(end,counts1,bucket_j)}}]}
    e4=energy_arm([[1,1]],[[3,3]],100,[[1,1]],[[2,2]])
    e37=energy_arm([[4,4]],[[6,6]],100,[[0,0]],[[3,3]])
    energy=_energy_analysis(e4,e37,area2,0,1,0,2)["ACSWDNB"]
    assert energy["status"]=="PASS" and energy["domain_integrated_difference_j"]==800.0,energy
    # With bucket accumulation disabled, reconstruct from AC alone even if a
    # dummy count array is present in the manufactured data.
    e4=energy_arm([[10,10]],[[30,30]],-1,[[99,99]],[[99,99]])
    e37=energy_arm([[10,10]],[[40,40]],-1,[[88,88]],[[88,88]])
    energy=_energy_analysis(e4,e37,area2,0,1,0,2)["ACSWDNB"]
    assert energy["paired_energy_area_mean_difference_j_m2"]==10.0,energy
    masked_metrics=area_metrics(np.array([[1.,np.nan]]),np.array([[2.,np.nan]]),area2,
                                np.array([[False,True]]),np.array([[False,True]]))
    assert masked_metrics["valid_cell_count"]==1,masked_metrics
    for invalid_area in (np.array([[1.,np.nan]]),np.array([[1.,0.]])):
        try:
            area_metrics(a4,a37,invalid_area)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid area weights must fail rather than shrink the domain")
    assert len(expected_times())==25 and expected_times()[0]=="2010-06-11_00:00:00" and expected_times()[-1]=="2010-06-12_00:00:00"
    return {"status":"PASS","area_mean":m["difference_area_mean_ra37_minus_ra4"],
            "area_rmse":m["difference_area_rmse"],"bucket_endpoint_delta":total1-total0,
            "rounding_contract_pass":ok["status"],"corruption_contract_fail_detected":bad["status"],
            "unmasked_nonfinite_fail_detected":nonfinite["status"],
            "shared_mask_two_term_identity":"PASS",
            "invalid_area_rejection":"PASS",
            "energy_orchestration_bucket_and_ac_only":"PASS",
            "timestamps":25}


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir",type=Path,help="new output directory; existing directories are refused")
    ap.add_argument("--self-test",action="store_true",help="test formulas on compact manufactured arrays; does not read forecasts")
    args=ap.parse_args()
    try:
        if args.self_test:
            print(json.dumps(self_test(),indent=2));return 0
        if args.output_dir is None: ap.error("--output-dir is required unless --self-test is used")
        report=analyze(args.output_dir.resolve())
        print(json.dumps({"status":report["status"],"output_dir":str(args.output_dir.resolve()),
                          "field_math_failures":report["field_math_contracts"]["failed_count"]},indent=2))
        return 0 if report["status"]=="PASS" else 1
    except (OSError,KeyError,ValueError,RuntimeError,IndexError) as exc:
        print(f"analysis refused/failed: {exc}",file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
