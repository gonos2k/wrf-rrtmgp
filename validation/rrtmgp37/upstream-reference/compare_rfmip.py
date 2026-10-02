#!/usr/bin/env python3
"""Compare RFMIP runs without substituting backend agreement for reference accuracy."""
import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

VARIABLES = ("rld", "rlu", "rsd", "rsu")
REFERENCE_ATOL = 1.e-5  # Pinned upstream compare-to-reference.py; no widened tolerance.


def load(directory, variable):
    matches = sorted(directory.glob(f"{variable}_*.nc"))
    if len(matches) != 1:
        raise ValueError(f"{directory}: expected one {variable} file, found {len(matches)}")
    path = matches[0]
    with netCDF4.Dataset(path) as dataset:
        field = dataset.variables[variable][:]
        if np.ma.isMaskedArray(field) and np.any(np.ma.getmaskarray(field)):
            raise ValueError(f"{path}: masked flux samples")
        values = np.asarray(field)
        if values.size == 0 or not np.isfinite(values).all():
            raise ValueError(f"{path}: empty or nonfinite flux samples")
        dimensions = list(dataset.variables[variable].dimensions)
    return values, {
        "path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "shape": list(values.shape), "dimensions": dimensions, "dtype": str(values.dtype),
    }


def metrics(first, second):
    if first.shape != second.shape or first.dtype != second.dtype:
        raise ValueError("flux shapes or dtypes differ")
    delta = np.abs(first.astype(np.float64) - second.astype(np.float64))
    return {
        "bitwise_equal": first.tobytes() == second.tobytes(),
        "max_abs_w_m2": float(delta.max()), "mean_abs_w_m2": float(delta.mean()),
        "count_above_reference_atol": int(np.count_nonzero(delta > REFERENCE_ATOL)),
        "published_tolerance_pass": bool(np.all(delta <= REFERENCE_ATOL)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--published-reference", type=Path,
                        help="Only for matching g256/g224 setup; fails if the unchanged tolerance fails")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"reference_atol_w_m2": REFERENCE_ATOL, "reference_rtol": 0,
              "published_reference_checked": args.published_reference is not None,
              "scope": "Clear-sky RFMIP fluxes; no WRF adapter or cloudy/precipitation validation",
              "fields": {}}
    backend_pass, reference_pass = True, True
    for variable in VARIABLES:
        upstream, upstream_meta = load(args.upstream, variable)
        vendor, vendor_meta = load(args.vendor, variable)
        if upstream_meta["dimensions"] != vendor_meta["dimensions"]:
            raise ValueError(f"{variable}: dimension names/order differ")
        row = {"upstream": upstream_meta, "vendor": vendor_meta,
               "vendor_vs_upstream": metrics(vendor, upstream)}
        backend_pass &= row["vendor_vs_upstream"]["bitwise_equal"]
        if args.published_reference is not None:
            reference, reference_meta = load(args.published_reference, variable)
            if upstream_meta["dimensions"] != reference_meta["dimensions"]:
                raise ValueError(f"{variable}: reference dimension names/order differ")
            row.update(published_reference=reference_meta,
                       upstream_vs_reference=metrics(upstream, reference),
                       vendor_vs_reference=metrics(vendor, reference))
            reference_pass &= row["upstream_vs_reference"]["published_tolerance_pass"]
            reference_pass &= row["vendor_vs_reference"]["published_tolerance_pass"]
        report["fields"][variable] = row
    report["backend_status"] = "PASS" if backend_pass else "FAIL"
    report["published_reference_status"] = (
        "NOT_RUN" if args.published_reference is None else "PASS" if reference_pass else "FAIL")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("backend_status", "published_reference_status")}))
    return 0 if backend_pass and reference_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
