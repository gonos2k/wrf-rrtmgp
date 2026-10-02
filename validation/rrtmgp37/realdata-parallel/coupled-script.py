#!/usr/bin/env python3
"""Paired whole-domain WRF history comparison (runtime trajectories only)."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

G = 9.81
HISTORY_VARS = ["SWDOWN", "GLW", "OLR", "T2", "PSFC", "HAILNC", "GRAUPELNC"]
PRECIP_VARS = ["RAINC", "RAINNC"]
QPATHS = {
    "QCLOUD": "LWP", "QICE": "IWP", "QRAIN": "RWP",
    "QSNOW": "SWP", "QGRAUP": "GRAUPEL_PATH", "QHAIL": "HAIL_PATH",
}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def time_string(ds):
    raw = ds.variables["Times"][0]
    if hasattr(raw, "tobytes"):
        return raw.tobytes().decode("ascii").rstrip("\x00 ")
    return "".join(x.decode() if isinstance(x, bytes) else str(x) for x in raw).strip()


def weighted_stats(delta, area):
    d = np.asarray(delta, dtype=np.float64)
    w = np.asarray(area, dtype=np.float64)
    den = float(np.sum(w, dtype=np.float64))
    return {"area_weighted_mean_delta": float(np.sum(d * w, dtype=np.float64) / den),
            "area_weighted_rmse": float(np.sqrt(np.sum(d * d * w, dtype=np.float64) / den)),
            "linf_abs_delta": float(np.max(np.abs(d))),
            "min_delta": float(np.min(d)), "max_delta": float(np.max(d))}


def list_histories(directory):
    files = sorted(Path(directory).glob("wrfout_d01_*"))
    if len(files) != 25:
        raise RuntimeError(f"expected 25 hourly histories in {directory}; found {len(files)}")
    return files


def load_grid(path):
    with netCDF4.Dataset(path) as ds:
        area = np.asarray(ds.variables["AREA2D"][0], dtype=np.float64)
        if not np.all(np.isfinite(area)) or np.any(area <= 0):
            raise RuntimeError(f"invalid AREA2D in {path}")
        shape = area.shape
        return area, shape


def one_record(path, expected_time):
    with netCDF4.Dataset(path) as ds:
        timestamp = time_string(ds)
        if timestamp != expected_time:
            raise RuntimeError(f"history timestamp mismatch in {path}: {timestamp} != {expected_time}")
        area = np.asarray(ds.variables["AREA2D"][0], dtype=np.float64)
        mu = np.asarray(ds.variables["MU"][0], dtype=np.float64)
        mub = np.asarray(ds.variables["MUB"][0], dtype=np.float64)
        dnw = np.asarray(ds.variables["DNW"][0], dtype=np.float64)
        c1h = np.asarray(ds.variables["C1H"][0], dtype=np.float64)
        c2h = np.asarray(ds.variables["C2H"][0], dtype=np.float64)
        # WRF dry hydrostatic layer mass, kg dry air m-2. DNW is negative
        # in eta ordering; C1H*(MU+MUB)+C2H is interface pressure thickness.
        mass = -dnw[:, None, None] * (
            c1h[:, None, None] * (mu + mub)[None, :, :] + c2h[:, None, None]
        ) / G
        if not np.all(np.isfinite(mass)) or np.any(mass <= 0):
            raise RuntimeError(f"invalid native dry layer mass in {path}")
        fields = {}
        for name in HISTORY_VARS + PRECIP_VARS:
            if name in ds.variables:
                fields[name] = np.asarray(ds.variables[name][0], dtype=np.float64)
        for qname, pname in QPATHS.items():
            q = np.asarray(ds.variables[qname][0], dtype=np.float64)
            # Mixing ratios are kg species / kg dry air. Sum native mass
            # layers to the whole-column species path in g m-2.
            fields[pname] = np.sum(q * mass, axis=0, dtype=np.float64) * 1000.0
        return timestamp, area, fields


def per_variable(left, right, area, labels):
    times = []
    diffs = []
    for stamp, a, b in zip(labels, left, right):
        if a is None or b is None:
            continue
        delta = b - a
        diffs.append(delta)
        times.append({"time": stamp,
                      "mode1_area_weighted_mean": float(np.sum(a * area, dtype=np.float64) / np.sum(area, dtype=np.float64)),
                      "ra4_area_weighted_mean": float(np.sum(b * area, dtype=np.float64) / np.sum(area, dtype=np.float64)),
                      **weighted_stats(delta, area)})
    stack = np.stack(diffs, axis=0)
    allw = np.broadcast_to(area, stack.shape)
    return {"units": None, "all_times": weighted_stats(stack, allw),
            "mode1_all_times_area_weighted_mean": float(np.sum(np.stack(left) * allw, dtype=np.float64) / np.sum(allw, dtype=np.float64)),
            "ra4_all_times_area_weighted_mean": float(np.sum(np.stack(right) * allw, dtype=np.float64) / np.sum(allw, dtype=np.float64)),
            "initial_time": times[0],
            "feedback_times_01_to_24": {
                "time_count": len(times) - 1,
                "max_hourly_linf": max(x["linf_abs_delta"] for x in times[1:]),
                "mean_hourly_area_weighted_rmse": float(np.mean([x["area_weighted_rmse"] for x in times[1:]])),
                "max_abs_hourly_area_weighted_mean": max(abs(x["area_weighted_mean_delta"]) for x in times[1:]),
            }, "hourly": times}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode1", required=True)
    p.add_argument("--ra4", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mode1-exe", required=True)
    p.add_argument("--ra4-exe", required=True)
    p.add_argument("--frozen-table", required=True)
    args = p.parse_args()
    mode_files, ra4_files = list_histories(args.mode1), list_histories(args.ra4)
    with netCDF4.Dataset(mode_files[0]) as ds:
        labels = [time_string(ds)]
    start = dt.datetime.strptime(labels[0], "%Y-%m-%d_%H:%M:%S")
    labels = [(start + dt.timedelta(hours=i)).strftime("%Y-%m-%d_%H:%M:%S") for i in range(25)]
    if [x.name for x in mode_files] != [x.name for x in ra4_files]:
        raise RuntimeError("history filename sets differ")
    area, shape = load_grid(mode_files[0])
    baseline_area, baseline_shape = load_grid(ra4_files[0])
    if shape != baseline_shape or not np.array_equal(area, baseline_area):
        raise RuntimeError("native grid or AREA2D differs between experiments")
    left, right = {}, {}
    timestamps = []
    for fp, fr, stamp in zip(mode_files, ra4_files, labels):
        t1, a1, f1 = one_record(fp, stamp)
        t2, a2, f2 = one_record(fr, stamp)
        if t1 != t2 or not np.array_equal(a1, a2):
            raise RuntimeError(f"time/grid mismatch at {stamp}")
        if not np.array_equal(a1, area):
            raise RuntimeError(f"AREA2D changed within the run at {stamp}; time-varying weights need explicit handling")
        timestamps.append(stamp)
        for name in f1:
            if name not in f2:
                continue
            left.setdefault(name, []).append(f1[name])
            right.setdefault(name, []).append(f2[name])
    result = {
        "classification": "COUPLED_TRAJECTORY_DIFFERENCE",
        "interpretation": "Paired radiation/microphysics trajectories from the same initial and boundary files. Initial radiation history fields are zero before the first actual radiation call; later differences include model feedback. This is neither same-state intrinsic radiation physics nor observational bias/accuracy.",
        "scope": {"hours": 24, "hourly_records_including_initial": 25,
                  "native_grid_shape_south_north_west_east": list(shape),
                  "boundary_masking": "none; entire common native grid retained",
                  "precipitation": "each cumulative field is differenced after subtracting its own t0 value; negative increments are retained without clamping",
                  "hydrometeor_paths": "native column dry layer mass = -DNW*(C1H*(MU+MUB)+C2H)/9.81 kg dry air m-2; species mixing ratio times this layer mass, summed over bottom_top and multiplied by 1000 gives g m-2"},
        "area_weighting": {"difference_convention": "RRTMG4 minus PR20 RRTMGP37 mode1 (ra4 - mode1)", "source": "AREA2D history variable (m2)",
                           "formula_mean": "sum(delta*AREA2D)/sum(AREA2D)",
                           "formula_rmse": "sqrt(sum(delta^2*AREA2D)/sum(AREA2D))",
                           "linf": "max(abs(delta)) over all common native-grid cells"},
        "experiments": {"mode1": {"directory": str(Path(args.mode1).resolve()), "executable": str(Path(args.mode1_exe).resolve()), "executable_sha256": sha(args.mode1_exe), "frozen_table": str(Path(args.frozen_table).resolve()), "frozen_table_sha256": sha(args.frozen_table), "history_files": [{"name": x.name, "sha256": sha(x)} for x in mode_files]},
                        "ra4": {"directory": str(Path(args.ra4).resolve()), "executable": str(Path(args.ra4_exe).resolve()), "executable_sha256": sha(args.ra4_exe), "history_files": [{"name": x.name, "sha256": sha(x)} for x in ra4_files]}},
        "times": timestamps,
        "available_fields": {},
        "unavailable_requested_fields": ["GSW", "SWDDIR", "SWDDIF", "RTHRATLW", "RTHRATSW"],
    }
    units = {"SWDOWN": "W m-2", "GLW": "W m-2", "OLR": "W m-2", "T2": "K", "PSFC": "Pa",
             "HAILNC": "mm", "GRAUPELNC": "mm", "RAINC": "mm", "RAINNC": "mm",
             "LWP": "g m-2", "IWP": "g m-2", "RWP": "g m-2", "SWP": "g m-2",
             "GRAUPEL_PATH": "g m-2", "HAIL_PATH": "g m-2"}
    for name, vals in left.items():
        if name not in right or name not in units:
            continue
        a, b = vals, right[name]
        if name in PRECIP_VARS:
            a0, b0 = a[0], b[0]
            a = [x - a0 for x in a]
            b = [x - b0 for x in b]
        report = per_variable(a, b, area, timestamps)
        report["units"] = units[name]
        if name in PRECIP_VARS:
            report["comparison_basis"] = "increments from each run's own initial cumulative value; unclamped"
            report["mode1_negative_increment_cells"] = int(sum(np.count_nonzero(x < 0) for x in a))
            report["ra4_negative_increment_cells"] = int(sum(np.count_nonzero(x < 0) for x in b))
        result["available_fields"][name] = report
    result["provenance"] = {
        "mode1_receipt": str((Path(args.mode1) / "run-receipt.json").resolve()),
        "ra4_receipt": str((Path(args.ra4).parent / "24h-comparison-receipt.json").resolve()),
        "source_base_commit": "f8cbfeea7f4c59e5e0655bd2f23e3b424b8359b3",
        "source_overlay_receipt": str(Path("build/udm-frozen-runtime-mpi/frozen-overlay-receipt.json").resolve()),
        "source_overlay_receipt_sha256": sha("build/udm-frozen-runtime-mpi/frozen-overlay-receipt.json"),
        "inputs": {},
        "known_physics_differences": ["RA4 retains its earlier UDM generic-radius behavior and legacy cloud/precipitation optics; PR20 mode 1 uses UDM-native radii, CCPP rain/snow and experimental homogeneous-ice PSD graupel/hail optics.", "PR20 RRTMGP explicitly sets six gas VMRs and omits the four LW CFC11/CFC12/CFC22/CCl4 profiles used by the RRTMG wrapper. The later PR21 correction is absent from this 24-hour executable."],
    }
    for input_name in ("wrfinput_d01", "wrfbdy_d01"):
        mpath = Path(args.mode1) / input_name
        rpath = Path(args.ra4) / input_name
        mh, rh = sha(mpath), sha(rpath)
        if mh != rh:
            raise RuntimeError(f"input file mismatch: {input_name}: {mh} != {rh}")
        result["provenance"]["inputs"][input_name] = {
            "mode1_path": str(mpath.resolve()), "mode1_sha256": mh,
            "ra4_path": str(rpath.resolve()), "ra4_sha256": rh,
            "byte_identical": True,
        }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
