#!/usr/bin/env python3
"""Compare all emitted fields from independent cloudy all-sky backend runs."""
import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

CASES = {
    "sw-g112.nc": ("sw_flux_dir", "sw_flux_up", "sw_flux_dn"),
    "lw-g128.nc": ("lw_flux_up", "lw_flux_dn"),
}


def fail(message):
    raise ValueError(message)


def read_output(path):
    with netCDF4.Dataset(path) as dataset:
        arrays, metadata = {}, {}
        for name, variable in dataset.variables.items():
            raw = variable[:]
            if np.ma.isMaskedArray(raw) and np.any(np.ma.getmaskarray(raw)):
                fail(f"{path}:{name}: masked samples are not allowed")
            values = np.asarray(raw)
            if not values.size:
                fail(f"{path}:{name}: empty output variable")
            if values.dtype.kind in "biufc" and not np.isfinite(values).all():
                fail(f"{path}:{name}: nonfinite values")
            arrays[name] = values
            metadata[name] = {
                "dimensions": list(variable.dimensions),
                "shape": list(values.shape),
                "dtype": str(values.dtype),
                "units": variable.getncattr("units") if "units" in variable.ncattrs() else None,
                "sha256_c_order_bytes": hashlib.sha256(values.tobytes(order="C")).hexdigest(),
            }
    return arrays, metadata


def compare_file(name, upstream_path, vendor_path):
    upstream, upstream_meta = read_output(upstream_path)
    vendor, vendor_meta = read_output(vendor_path)
    if upstream.keys() != vendor.keys():
        fail(f"{name}: variable names differ")
    variables = {}
    for variable in upstream:
        a, b = upstream[variable], vendor[variable]
        ma, mb = upstream_meta[variable], vendor_meta[variable]
        if ma != mb:
            fail(f"{name}:{variable}: shape, dtype, dimensions, units, or values differ")
        if a.shape != b.shape or a.dtype != b.dtype:
            fail(f"{name}:{variable}: shape or dtype mismatch")
        if ma["dimensions"] != mb["dimensions"] or ma["units"] != mb["units"]:
            fail(f"{name}:{variable}: dimensions or units mismatch")
        bitwise_equal = a.tobytes(order="C") == b.tobytes(order="C")
        delta = np.abs(a.astype(np.float64) - b.astype(np.float64)) if a.dtype.kind in "biufc" else None
        variables[variable] = {
            "metadata": ma,
            "bitwise_equal": bitwise_equal,
            "max_abs_difference": float(delta.max()) if delta is not None else None,
            "count_different": int(np.count_nonzero(a != b)),
        }
        if not bitwise_equal:
            fail(f"{name}:{variable}: outputs are not bitwise equal")

    required_fluxes = CASES[name]
    for variable in required_fluxes:
        if variable not in variables:
            fail(f"{name}: required flux field {variable} missing")
    for variable in ("lwp", "iwp"):
        if variable not in upstream:
            fail(f"{name}: cloudy-state field {variable} missing")
        if not np.any(upstream[variable] > 0):
            fail(f"{name}: {variable} has no cloudy cells; cloud path not exercised")
    return {
        "upstream_file": str(upstream_path.resolve()),
        "vendor_file": str(vendor_path.resolve()),
        "upstream_file_sha256": hashlib.sha256(upstream_path.read_bytes()).hexdigest(),
        "vendor_file_sha256": hashlib.sha256(vendor_path.read_bytes()).hexdigest(),
        "all_variables_finite_and_bitwise_equal": True,
        "cloudy_cells": {key: int(np.count_nonzero(upstream[key] > 0)) for key in ("lwp", "iwp")},
        "variables": variables,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    provenance = json.loads(args.provenance.read_text())
    report = {
        "status": "PASS",
        "scope": provenance["scope"],
        "provenance": provenance,
        "allsky_comparisons": {},
        "direct_cloud_optics_arrays_emitted": False,
    }
    try:
        for filename in CASES:
            report["allsky_comparisons"][filename] = compare_file(
                filename, args.upstream / filename, args.vendor / filename)
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "cases": list(report["allsky_comparisons"])}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
