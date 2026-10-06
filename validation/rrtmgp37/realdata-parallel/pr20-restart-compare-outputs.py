#!/usr/bin/env python3
"""Compare every WRF output field at a matching timestamp; default is exact."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


def canonical_attr(value: Any) -> Any:
    arr = np.asarray(value)
    if arr.dtype.kind == "S":
        return [x.decode("utf-8", errors="replace") for x in arr.reshape(-1)]
    if arr.dtype.kind == "U":
        return arr.reshape(-1).tolist()
    if arr.dtype.kind in "fiu":
        return arr.tolist()
    return str(value)


def time_text(dataset: Dataset) -> str:
    if "Times" not in dataset.variables:
        raise ValueError(f"{dataset.filepath()}: missing Times")
    values = np.asarray(dataset.variables["Times"][:])
    if values.ndim != 2 or values.shape[0] != 1:
        raise ValueError(f"{dataset.filepath()}: expected one output record in Times, got {values.shape}")
    return b"".join(values[0].tolist()).decode("ascii")


def compare(first_path: Path, second_path: Path, expected_time: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "files": [str(first_path), str(second_path)],
        "expected_time": expected_time,
        "comparison": {"mode": "exact", "rtol": 0.0, "atol": 0.0, "ignored_variables": []},
        "passed": False,
        "dynamics_passed": False,
        "metadata_match": False,
        "errors": [],
        "metadata_differences": [],
        "variable_differences": {},
        "compared_variables": 0,
        "compared_numeric_values": 0,
    }
    with Dataset(first_path, "r") as left, Dataset(second_path, "r") as right:
        for label, ds in (("continuous", left), ("restarted", right)):
            try:
                observed = time_text(ds)
                report[f"{label}_time"] = observed
                if observed != expected_time:
                    report["errors"].append(f"{label} Times={observed}, expected {expected_time}")
            except ValueError as exc:
                report["errors"].append(str(exc))

        left_dims = {name: {"length": len(dim), "unlimited": bool(dim.isunlimited())}
                     for name, dim in left.dimensions.items()}
        right_dims = {name: {"length": len(dim), "unlimited": bool(dim.isunlimited())}
                      for name, dim in right.dimensions.items()}
        if left_dims != right_dims:
            report["errors"].append({"dimension_mismatch": {"continuous": left_dims, "restarted": right_dims}})

        left_names, right_names = set(left.variables), set(right.variables)
        if left_names != right_names:
            report["errors"].append({"variable_set_mismatch": {
                "only_continuous": sorted(left_names - right_names),
                "only_restarted": sorted(right_names - left_names),
            }})

        # Compare all global attributes; no provenance or diagnostic fields are filtered.
        left_attrs, right_attrs = set(left.ncattrs()), set(right.ncattrs())
        if left_attrs != right_attrs:
            report["metadata_differences"].append({"global_attribute_set_mismatch": {
                "only_continuous": sorted(left_attrs - right_attrs),
                "only_restarted": sorted(right_attrs - left_attrs),
            }})
        for name in sorted(left_attrs & right_attrs):
            a, b = canonical_attr(left.getncattr(name)), canonical_attr(right.getncattr(name))
            if a != b:
                report["metadata_differences"].append({"global_attribute_mismatch": name,
                                                        "continuous": a, "restarted": b})

        for name in sorted(left_names & right_names):
            a_var, b_var = left.variables[name], right.variables[name]
            difference: dict[str, Any] = {}
            if a_var.dimensions != b_var.dimensions:
                difference["dimension_names"] = {"continuous": a_var.dimensions, "restarted": b_var.dimensions}
            a = np.asarray(a_var[:])
            b = np.asarray(b_var[:])
            if a.shape != b.shape:
                difference["shape"] = {"continuous": list(a.shape), "restarted": list(b.shape)}
                report["variable_differences"][name] = difference
                continue
            if a.dtype.kind in "fiu" and b.dtype.kind in "fiu":
                if a.dtype != b.dtype:
                    difference["dtype"] = {"continuous": str(a.dtype), "restarted": str(b.dtype)}
                if a.dtype.kind == "f" and (not np.isfinite(a).all() or not np.isfinite(b).all()):
                    difference["nonfinite"] = {
                        "continuous": int(np.size(a) - np.isfinite(a).sum()),
                        "restarted": int(np.size(b) - np.isfinite(b).sum()),
                    }
                    report["errors"].append({"nonfinite_variable": name, **difference["nonfinite"]})
                report["compared_numeric_values"] += int(a.size)
                equal = np.array_equal(a, b)
                if not equal:
                    delta = np.abs(a.astype(np.float64) - b.astype(np.float64))
                    first_bad = tuple(int(i) for i in np.argwhere(a != b)[0]) if np.any(a != b) else None
                    difference.update({
                        "dtype": {"continuous": str(a.dtype), "restarted": str(b.dtype)},
                        "different_values": int(np.count_nonzero(a != b)),
                        "max_abs_difference": float(np.nanmax(delta)) if delta.size else 0.0,
                        "first_different_index": first_bad,
                    })
            else:
                equal = np.array_equal(a, b)
                if not equal:
                    indices = np.argwhere(a != b)
                    difference.update({
                        "different_values": int(len(indices)),
                        "first_different_index": tuple(int(i) for i in indices[0]) if len(indices) else None,
                    })
            # Per-variable attributes (units, descriptions, fill values, etc.) are also exact.
            a_attrs, b_attrs = set(a_var.ncattrs()), set(b_var.ncattrs())
            if a_attrs != b_attrs:
                report["metadata_differences"].append({"variable": name, "attribute_set_mismatch": {
                    "only_continuous": sorted(a_attrs - b_attrs), "only_restarted": sorted(b_attrs - a_attrs)}
                })
            for attr in sorted(a_attrs & b_attrs):
                if canonical_attr(a_var.getncattr(attr)) != canonical_attr(b_var.getncattr(attr)):
                    report["metadata_differences"].append({
                        "variable": name, "attribute": attr,
                        "continuous": canonical_attr(a_var.getncattr(attr)),
                        "restarted": canonical_attr(b_var.getncattr(attr)),
                    })
            report["compared_variables"] += 1
            if difference:
                report["variable_differences"][name] = difference

    report["dynamics_passed"] = not report["errors"] and not report["variable_differences"]
    report["metadata_match"] = not report["metadata_differences"]
    report["passed"] = report["dynamics_passed"] and report["metadata_match"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("continuous", type=Path)
    parser.add_argument("restarted", type=Path)
    parser.add_argument("--expected-time", default="2010-06-11_13:00:00")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.continuous, args.restarted, args.expected_time)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
