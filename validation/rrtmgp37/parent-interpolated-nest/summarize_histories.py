#!/usr/bin/env python3
"""Summarize the nested WRF history files without copying the NetCDF files.

The reported hydrometeor counts/maxima and flux statistics are instantaneous
per output time. Flux means are arithmetic means over grid points, not
geographically area weighted or time integrated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from netCDF4 import Dataset


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def time_string(ds: Dataset) -> str:
    row = ds.variables["Times"][0]
    return row.tobytes().decode("ascii").replace("\x00", "").strip()


def read_finite(ds: Dataset, name: str) -> np.ndarray:
    a = np.ma.asarray(ds.variables[name][:])
    if np.any(np.ma.getmaskarray(a)):
        raise ValueError(f"masked value in {name}")
    out = np.asarray(np.ma.getdata(a), dtype=np.float64)
    if not np.all(np.isfinite(out)):
        raise ValueError(f"nonfinite value in {name}")
    return out


def jsonable(value):
    arr = np.asarray(value)
    return arr.item() if arr.ndim == 0 else arr.tolist()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case-dir", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()
    case_dir = args.case_dir.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inventory = []
    records = []
    state = {"semantics": {
        "hydrometeor_counts": "Instantaneous positive layer-grid cells per history record; summing these counts over time repeats cells and is not path- or mass-integrated.",
        "radiation_statistics": "Instantaneous arithmetic grid-point min/mean/max/std for each domain; no geographic area weighting or time integration.",
        "units": {"QGRAUP": "kg kg-1", "QHAIL": "kg kg-1", "SWDOWN": "W m-2", "GLW": "W m-2", "OLR": "W m-2"},
    }, "domains": {}}
    radiation_rows = []
    for domain in (1, 2):
        files = sorted(case_dir.glob(f"wrfout_d{domain:02d}_*"))
        if not files:
            raise FileNotFoundError(f"no domain {domain} history files in {case_dir}")
        domain_records = []
        for f in files:
            with Dataset(f) as ds:
                stamp = time_string(ds)
                dim_meta = {name: len(dim) for name, dim in ds.dimensions.items()}
                global_meta = {k: jsonable(ds.getncattr(k)) for k in (
                    "GRID_ID", "PARENT_ID", "PARENT_GRID_RATIO", "DX", "DY",
                    "MP_PHYSICS", "RA_LW_PHYSICS", "RA_SW_PHYSICS",
                    "BL_PBL_PHYSICS", "SF_SURFACE_PHYSICS", "SF_SFCLAY_PHYSICS", "CU_PHYSICS") if k in ds.ncattrs()}
                required = ("QGRAUP", "QHAIL", "SWDOWN", "GLW", "OLR")
                missing = [n for n in required if n not in ds.variables]
                if missing:
                    raise ValueError(f"{f}: missing fields {missing}")
                rec = {"time": stamp, "file": f.name}
                for species in ("QGRAUP", "QHAIL"):
                    arr = read_finite(ds, species)
                    rec[species] = {
                        "max_kg_kg": float(np.max(arr)),
                        "positive_layer_grid_cells": int(np.count_nonzero(arr > 0.0)),
                        "sample_scope": "this output timestamp and full domain",
                    }
                for field in ("SWDOWN", "GLW", "OLR"):
                    arr = read_finite(ds, field)
                    spatial = arr[0] if arr.ndim == 3 else arr
                    stats = {"min": float(np.min(spatial)), "gridpoint_mean": float(np.mean(spatial)),
                             "max": float(np.max(spatial)), "gridpoint_std": float(np.std(spatial)),
                             "unit": "W m-2", "weighting": "equal grid-point arithmetic; not geographic area weighted"}
                    rec[field] = stats
                    radiation_rows.append({"domain": domain, "time": stamp, "field": field, **stats})
                domain_records.append(rec)
            inventory.append({"domain": domain, "file": f.name, "bytes": f.stat().st_size,
                              "sha256": sha256(f), "timestamp": stamp, "dimensions": dim_meta,
                              "global_metadata": global_meta})
        state["domains"][f"d{domain:02d}"] = {
            "records": domain_records,
            "record_count": len(domain_records),
            "QGRAUP_domain_max_kg_kg": max(r["QGRAUP"]["max_kg_kg"] for r in domain_records),
            "QHAIL_domain_max_kg_kg": max(r["QHAIL"]["max_kg_kg"] for r in domain_records),
            "QGRAUP_positive_cells_sum_of_record_counts": sum(r["QGRAUP"]["positive_layer_grid_cells"] for r in domain_records),
            "QHAIL_positive_cells_sum_of_record_counts": sum(r["QHAIL"]["positive_layer_grid_cells"] for r in domain_records),
            "count_note": "Sum is across instantaneous records and is not a unique-cell count, path integral, or mass integral.",
        }
    inventory.sort(key=lambda x: (x["domain"], x["timestamp"]))
    (out / "history_file_inventory.json").write_text(json.dumps({
        "case_dir": str(case_dir), "history_file_count": len(inventory), "files": inventory,
        "raw_history_copied": False,
    }, indent=2, sort_keys=True) + "\n")
    (out / "state_presence.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    with (out / "radiation_gridpoint_stats.csv").open("w", newline="") as f:
        fields = ["domain", "time", "field", "unit", "min", "gridpoint_mean", "max", "gridpoint_std", "weighting"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(radiation_rows)

    child = state["domains"]["d02"]["records"]
    times = [datetime.strptime(r["time"], "%Y-%m-%d_%H:%M:%S") for r in child]
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True, constrained_layout=True)
    axes[0].plot(times, [r["QGRAUP"]["max_kg_kg"] for r in child], marker="o", color="tab:blue", label="QGRAUP")
    axes[0].set_ylabel("QGRAUP max (kg kg$^{-1}$)", color="tab:blue")
    axes[0].tick_params(axis="y", labelcolor="tab:blue")
    hail_axis = axes[0].twinx()
    hail_axis.plot(times, [r["QHAIL"]["max_kg_kg"] for r in child], marker="s", color="tab:orange", label="QHAIL")
    hail_axis.set_ylabel("QHAIL max (kg kg$^{-1}$)", color="tab:orange")
    hail_axis.tick_params(axis="y", labelcolor="tab:orange")
    axes[0].set_title("Child d02 hydrometeor state: per-record maxima")
    axes[0].grid(True, alpha=.3)
    lines = axes[0].get_lines() + hail_axis.get_lines()
    axes[0].legend(lines, [line.get_label() for line in lines], loc="upper left")
    for field in ("SWDOWN", "GLW", "OLR"):
        axes[1].plot(times, [r[field]["gridpoint_mean"] for r in child], marker="o", label=field)
    axes[1].set_ylabel("grid-point arithmetic mean (W m$^{-2}$)")
    axes[1].set_title("Child d02 radiation: instantaneous spatial means")
    axes[1].set_xlabel("history timestamp")
    axes[1].grid(True, alpha=.3)
    axes[1].legend()
    fig.autofmt_xdate()
    fig.savefig(out / "child_state_and_radiation.png", dpi=160)
    print(json.dumps({"output_dir": str(out), "history_files": len(inventory),
                      "child_QGRAUP_max_kg_kg": state["domains"]["d02"]["QGRAUP_domain_max_kg_kg"],
                      "child_QHAIL_max_kg_kg": state["domains"]["d02"]["QHAIL_domain_max_kg_kg"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
