#!/usr/bin/env python3
"""Compare WRF continuous and restarted history at matching physical times.

Usage:
  python compare_restart.py continuous.nc restarted.nc [--checkpoint restart.nc --checkpoint-time YYYY-MM-DD_HH:MM:SS]

Requires netCDF4 and NumPy. Writes a JSON comparison report to stdout.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def read(path):
    with Dataset(path) as ds:
        times = ["".join(x.decode() if isinstance(x, bytes) else str(x) for x in row).strip()
                 for row in np.asarray(ds.variables["Times"][:])]
        variables = {
            name: {"data": np.asarray(var[:]), "dimensions": var.dimensions,
                   "dtype": str(var.dtype)}
            for name, var in ds.variables.items()
        }
        return times, variables


def at_time(variable, index):
    data = variable["data"]
    if "Time" not in variable["dimensions"]:
        return data
    return np.take(data, index, axis=variable["dimensions"].index("Time"))


def compare(left, right):
    if left.shape != right.shape or left.dtype != right.dtype:
        return {"equal": False, "shape_or_dtype_mismatch": True,
                "left_shape": list(left.shape), "right_shape": list(right.shape),
                "left_dtype": str(left.dtype), "right_dtype": str(right.dtype)}
    bitwise_equal = left.tobytes(order="C") == right.tobytes(order="C")
    result = {"equal": bitwise_equal, "bitwise_equal": bitwise_equal,
              "differing_elements": 0}
    if left.dtype.kind in "biufc":
        a = left.astype(np.float64)
        b = right.astype(np.float64)
        equal = (a == b) | (np.isnan(a) & np.isnan(b)) if a.dtype.kind in "fc" else (a == b)
        delta = a - b
        finite = np.isfinite(delta)
        result.update({
            "numerically_equal": bool(np.all(equal)),
            "differing_elements": int(np.count_nonzero(~equal)),
            "l_inf": float(np.max(np.abs(delta[finite]))) if finite.any() else 0.0,
            "l2": float(np.sqrt(np.sum(delta[finite] ** 2))),
        })
    else:
        result["differing_elements"] = int(np.count_nonzero(left != right))
    return result


def compare_pair(left_path, right_path, checkpoint_time=None, checkpoint_path=None):
    left_times, left_vars = read(left_path)
    right_times, right_vars = read(right_path)
    left_idx = {time: i for i, time in enumerate(left_times)}
    right_idx = {time: i for i, time in enumerate(right_times)}
    times = sorted(set(left_idx) & set(right_idx))
    names = sorted(set(left_vars) & set(right_vars))
    if len(left_idx) != len(left_times) or len(right_idx) != len(right_times):
        raise ValueError("duplicate physical history timestamps")
    if not times:
        raise ValueError("no common physical history timestamps")
    if set(left_vars) != set(right_vars):
        raise ValueError("history variable sets differ")
    per_time = {}
    per_variable = {}
    all_comparisons = []
    for time in times:
        mismatches = []
        for name in names:
            metric = compare(at_time(left_vars[name], left_idx[time]),
                            at_time(right_vars[name], right_idx[time]))
            all_comparisons.append((name, metric))
            if not metric["equal"]:
                mismatches.append(name)
        per_time[time] = {"matching_variables": len(names) - len(mismatches),
                          "differing_variables": mismatches}
    for name in names:
        pairs = [metric for variable, metric in all_comparisons if variable == name]
        numeric = [metric for metric in pairs if "l_inf" in metric]
        per_variable[name] = {
            "bitwise_equal_all_times": all(metric["equal"] for metric in pairs),
            "differing_time_count": sum(not metric["equal"] for metric in pairs),
            "differing_elements": sum(metric.get("differing_elements", 0) for metric in numeric),
            "l_inf": max((metric.get("l_inf", 0.0) for metric in numeric), default=0.0),
            "l2": float(np.sqrt(sum(metric.get("l2", 0.0) ** 2 for metric in numeric))),
        }
    report = {
        "left": {"path": str(left_path), "sha256": hashlib.sha256(Path(left_path).read_bytes()).hexdigest(),
                 "times": left_times},
        "right": {"path": str(right_path), "sha256": hashlib.sha256(Path(right_path).read_bytes()).hexdigest(),
                  "times": right_times},
        "common_times": times,
        "common_variable_count": len(names),
        "matching_variables_each_time": per_time,
        "variable_metrics": per_variable,
        "summary": {"matching_time_count": len(times),
                    "exact_match_times": sum(not x["differing_variables"] for x in per_time.values()),
                    "differing_variable_time_pairs": sum(len(x["differing_variables"]) for x in per_time.values()),
                    "bitwise_equal_variables_all_times": sum(x["bitwise_equal_all_times"] for x in per_variable.values())},
    }
    if checkpoint_time:
        if checkpoint_time not in left_idx:
            raise ValueError(f"checkpoint time missing from continuous history: {checkpoint_time}")
        snap_times, snap_vars = read(checkpoint_path)
        if checkpoint_time not in snap_times:
            raise ValueError("checkpoint file does not contain the requested physical time")
        snap_idx = snap_times.index(checkpoint_time)
        snapshot = {}
        for name in sorted(set(left_vars) & set(snap_vars)):
            snapshot[name] = compare(at_time(left_vars[name], left_idx[checkpoint_time]),
                                     at_time(snap_vars[name], snap_idx))
        report["checkpoint"] = {
            "path": str(checkpoint_path), "sha256": hashlib.sha256(Path(checkpoint_path).read_bytes()).hexdigest(),
            "time": checkpoint_time, "common_variable_count": len(snapshot),
            "differing_variables": [name for name, metric in snapshot.items() if not metric["equal"]],
            "variable_metrics": snapshot,
        }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("continuous")
    parser.add_argument("restarted")
    parser.add_argument("--checkpoint", help="one-record wrfrst file at the restart boundary")
    parser.add_argument("--checkpoint-time", help="physical timestamp in the continuous run")
    args = parser.parse_args()
    if bool(args.checkpoint) != bool(args.checkpoint_time):
        parser.error("--checkpoint and --checkpoint-time must be supplied together")
    print(json.dumps(compare_pair(args.continuous, args.restarted, args.checkpoint_time, args.checkpoint), indent=2))
