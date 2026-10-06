#!/usr/bin/env python3
"""Strict WRF history comparison, retaining raw data/mask and metadata evidence."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parent
FILE = "wrfout_d01_2010-06-11_12:01:00"
CASES = {
    "official_mpi1": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/pristine-wrf-dm-sm/runtime-preflight/restart12-mpi1") / FILE,
    "official_mpi4": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/pristine-wrf-dm-sm/runtime-preflight/restart12-mpi4") / FILE,
    "pr21_mpi1": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm-mpix-diagnosis/ra4-mpi1") / FILE,
    "pr21_mpi4": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm-mpix-diagnosis/ra4-mpi4") / FILE,
    "corrected_mpi1": ROOT / "restart12-fixed-mpi1" / FILE,
    "corrected_mpi4": ROOT / "restart12-fixed-mpi4" / FILE,
}
PAIRS = [
    ("official_mpi1", "official_mpi4"),
    ("official_mpi1", "pr21_mpi1"),
    ("official_mpi4", "pr21_mpi4"),
    ("official_mpi1", "corrected_mpi1"),
    ("official_mpi4", "corrected_mpi4"),
    ("corrected_mpi1", "corrected_mpi4"),
    ("pr21_mpi1", "corrected_mpi1"),
    ("pr21_mpi4", "corrected_mpi4"),
]

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def variable_metadata(ds, name):
    v = ds.variables[name]
    return {"dimensions": list(v.dimensions), "shape": list(v.shape), "dtype": v.dtype.str,
            "attrs": {a: repr(v.getncattr(a)) for a in sorted(v.ncattrs())}}

def raw_and_mask(v):
    v.set_auto_maskandscale(False)
    arr = np.asarray(v[:])
    mask = np.zeros(arr.shape, dtype=bool)
    for attr in ("_FillValue", "missing_value"):
        if attr not in v.ncattrs():
            continue
        for value in np.asarray(v.getncattr(attr)).reshape(-1):
            if arr.dtype.kind == "f" and np.isnan(value):
                mask |= np.isnan(arr)
            else:
                mask |= arr == value
    return arr, mask

def scalar(v):
    return repr(v.item() if hasattr(v, "item") else v)

datasets = {name: netCDF4.Dataset(path) for name, path in CASES.items()}
summary = {"status": "PENDING", "comparison": "strict raw variable-value comparison; exact dtype/dimension/shape and explicit fill/missing-mask audit; no numeric tolerances", "cases": {}, "pairs": {}}
official_names = set(datasets["official_mpi1"].variables)
if official_names != set(datasets["official_mpi4"].variables):
    raise SystemExit("official MPI1/MPI4 variable name sets differ")
summary["official_reference_variable_count"] = len(official_names)
summary["official_reference_names"] = sorted(official_names)
for name, path in CASES.items():
    ds = datasets[name]
    varnames = set(ds.variables)
    summary["cases"][name] = {
        "path": str(path), "sha256": sha(path), "bytes": path.stat().st_size,
        "variable_count": len(varnames), "official_fields_missing": sorted(official_names - varnames),
        "extra_fields": sorted(varnames - official_names),
        "times": netCDF4.chartostring(ds.variables["Times"][:]).tolist(),
        "global_attrs": {a: repr(ds.getncattr(a)) for a in sorted(ds.ncattrs())},
        "variable_metadata": {n: variable_metadata(ds, n) for n in sorted(varnames)},
    }
all_pass = True
for left, right in PAIRS:
    a, b = datasets[left], datasets[right]
    na, nb = set(a.variables), set(b.variables)
    common = sorted(na & nb)
    shape_dtype_mismatch, mask_mismatch, unequal = [], [], []
    nonfinite, variable_stats = {}, {}
    metadata_diffs = {"global": {}, "variables": {}}
    ga, gb = set(a.ncattrs()), set(b.ncattrs())
    for key in sorted(ga | gb):
        av = scalar(a.getncattr(key)) if key in ga else None
        bv = scalar(b.getncattr(key)) if key in gb else None
        if av != bv:
            metadata_diffs["global"][key] = {"left": av, "right": bv}
    for name in common:
        va, vb = a.variables[name], b.variables[name]
        if va.dimensions != vb.dimensions or va.shape != vb.shape or va.dtype != vb.dtype:
            shape_dtype_mismatch.append(name)
            continue
        aa, ma = raw_and_mask(va)
        ab, mb = raw_and_mask(vb)
        mask_equal = bool(np.array_equal(ma, mb))
        raw_equal = aa.tobytes(order="C") == ab.tobytes(order="C")
        if not mask_equal:
            mask_mismatch.append(name)
        if not raw_equal:
            unequal.append(name)
        if aa.dtype.kind in "fci":
            fa, fb = np.isfinite(aa), np.isfinite(ab)
            nonfinite_a = int(np.count_nonzero(~fa & ~ma))
            nonfinite_b = int(np.count_nonzero(~fb & ~mb))
            if nonfinite_a or nonfinite_b:
                nonfinite[name] = {"left": nonfinite_a, "right": nonfinite_b}
            valid = (~ma) & (~mb) & fa & fb
            maxabs = float(np.max(np.abs(aa.astype(np.float64) - ab.astype(np.float64))[valid])) if np.any(valid) else None
            variable_stats[name] = {
                "dtype": aa.dtype.str, "elements": int(aa.size),
                "left_masked": int(np.count_nonzero(ma)), "right_masked": int(np.count_nonzero(mb)),
                "mask_equal": mask_equal, "exact_raw_bytes": raw_equal,
                "left_nonfinite_unmasked": nonfinite_a, "right_nonfinite_unmasked": nonfinite_b,
                "max_abs_unmasked_finite": maxabs,
            }
        am, bm = variable_metadata(a, name)["attrs"], variable_metadata(b, name)["attrs"]
        if am != bm:
            metadata_diffs["variables"][name] = {"left": am, "right": bm}
    missing_a, missing_b = sorted(official_names - na), sorted(official_names - nb)
    extra_a, extra_b = sorted(na - official_names), sorted(nb - official_names)
    exact = not unequal and not shape_dtype_mismatch and not mask_mismatch
    finite_ok = not nonfinite
    pair_ok = exact and finite_ok and not missing_a and not missing_b
    all_pass &= pair_ok
    summary["pairs"][left + "__vs__" + right] = {
        "official_reference_fields": len(official_names), "left_fields": len(na), "right_fields": len(nb),
        "common_fields": len(common), "official_missing_left": missing_a, "official_missing_right": missing_b,
        "extra_left": extra_a, "extra_right": extra_b,
        "shape_dtype_mismatch": shape_dtype_mismatch, "mask_mismatch": mask_mismatch,
        "unequal_raw_value_fields": unequal, "nonfinite_unmasked_counts": nonfinite,
        "all_official_fields_exact": exact and not missing_a and not missing_b,
        "all_compared_unmasked_numeric_values_finite": finite_ok, "strict_pass": pair_ok,
        "global_and_variable_metadata_differences_not_used_as_value_comparisons": metadata_diffs,
        "variable_stats": variable_stats,
    }
for ds in datasets.values():
    ds.close()
summary["status"] = "PASS" if all_pass else "FAIL"
out = ROOT / "strict-history-comparison.json"
out.write_text(json.dumps(summary, indent=2) + "\n")
for name, pair in summary["pairs"].items():
    print(f"{name}: fields={pair['common_fields']} raw-unequal={len(pair['unequal_raw_value_fields'])} shape/dtype={len(pair['shape_dtype_mismatch'])} masks={len(pair['mask_mismatch'])} finite_fail={len(pair['nonfinite_unmasked_counts'])} pass={pair['strict_pass']}")
print(f"status={summary['status']} output={out}")
raise SystemExit(0 if all_pass else 1)
