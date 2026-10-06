#!/usr/bin/env python3
"""Plot full-grid first-step MPI1 minus MPI4 WRF history differences."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import PowerNorm, SymLogNorm
from netCDF4 import Dataset

TIME = "2010-06-11_12:01:00"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def text_time(ds: Dataset) -> str:
    raw = ds.variables["Times"][0]
    return b"".join(raw).decode("ascii").rstrip("\x00 ")


def read_case(path: Path) -> dict:
    with Dataset(path) as ds:
        actual_time = text_time(ds)
        if actual_time != TIME:
            raise ValueError(f"{path}: expected {TIME}, got {actual_time}")
        required = ("SWDOWN", "T", "QNCLOUD", "QNCCN", "XLAT", "XLONG")
        missing = [name for name in required if name not in ds.variables]
        if missing:
            raise ValueError(f"{path}: missing {missing}")
        shape2 = ds.variables["SWDOWN"].shape[1:]
        if shape2 != (189, 289):
            raise ValueError(f"{path}: unexpected grid shape {shape2}")
        lat = np.asarray(ds["XLAT"][0], dtype=np.float64)
        lon = np.asarray(ds["XLONG"][0], dtype=np.float64)
        result = {
            "SWDOWN": np.asarray(ds["SWDOWN"][0], dtype=np.float64),
            "T": np.asarray(ds["T"][0], dtype=np.float64),
            "QNCLOUD": np.asarray(ds["QNCLOUD"][0], dtype=np.float64),
            "QNCCN": np.asarray(ds["QNCCN"][0], dtype=np.float64),
            "lat": lat,
            "lon": lon,
            "shape": shape2,
            "units": {name: str(getattr(ds.variables[name], "units", "")) for name in required},
            "attributes": {name: (ds.getncattr(name).item() if isinstance(ds.getncattr(name), np.generic) else ds.getncattr(name)) for name in ("DX", "DY", "GRID_ID", "NTASKS_TOTAL", "NTASKS_X", "NTASKS_Y") if name in ds.ncattrs()},
        }
    return result


def stats(a: np.ndarray, title: str) -> dict:
    a = np.asarray(a)
    flat_idx = int(np.argmax(np.abs(a)))
    j, i = np.unravel_index(flat_idx, a.shape)
    return {
        "field": title,
        "shape": list(a.shape),
        "dtype": str(a.dtype),
        "nonzero_cells": int(np.count_nonzero(a)),
        "max_abs": float(np.max(np.abs(a))),
        "min": float(np.min(a)),
        "max": float(np.max(a)),
        "mean": float(np.mean(a)),
        "rms": float(np.sqrt(np.mean(np.square(a)))),
        "max_abs_at_ij_1based": [int(i + 1), int(j + 1)],
        "x_seam_145_146_max_abs": float(np.max(np.abs(a[:, 144:146]))),
        "y_seam_95_96_max_abs": float(np.max(np.abs(a[94:96, :]))),
        "full_grid_included": True,
    }


def main() -> None:
    here = Path(__file__).resolve().parent
    root = here.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mpi1", type=Path, default=root / "build/udm-lw-trace-gases-parallel/mpi1-omp1-v2" / f"wrfout_d01_{TIME}")
    parser.add_argument("--mpi4", type=Path, default=root / "build/udm-lw-trace-gases-parallel/mpi4-omp1-v2" / f"wrfout_d01_{TIME}")
    parser.add_argument("--output-dir", type=Path, default=here)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    left, right = read_case(args.mpi1.resolve()), read_case(args.mpi4.resolve())
    if left["shape"] != right["shape"] or not np.array_equal(left["lat"], right["lat"]) or not np.array_equal(left["lon"], right["lon"]):
        raise ValueError("MPI1/MPI4 domain geometry differs")

    # Surface flux difference is MPI4 - MPI1. T and the stored QN fields show
    # maximum absolute difference over native mass levels. QN is not converted
    # to number density because the UDM number-concentration convention is unresolved.
    sw = right["SWDOWN"] - left["SWDOWN"]
    dt = right["T"] - left["T"]
    fields = [
        (sw, "SWDOWN: MPI4 − MPI1", "W m$^{-2}$", "signed"),
        (np.max(np.abs(dt), axis=0), "max$_k$ |ΔT perturbation|", "K", "magnitude"),
        (np.max(np.abs(right["QNCLOUD"] - left["QNCLOUD"]), axis=0), "max$_k$ |ΔQNCLOUD stored field|", "Registry units (# kg$^{-1}$)", "magnitude"),
        (np.max(np.abs(right["QNCCN"] - left["QNCCN"]), axis=0), "max$_k$ |ΔQNCCN stored field|", "Registry units (# kg$^{-1}$)", "magnitude"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.8), constrained_layout=True)
    for ax, (field, title, unit, mode) in zip(axes.flat, fields):
        vmax = float(np.max(np.abs(field)))
        if mode == "signed":
            norm = SymLogNorm(linthresh=max(vmax * 1e-4, np.finfo(float).tiny), vmin=-vmax, vmax=vmax, base=10)
            cmap = "RdBu_r"
        else:
            norm = PowerNorm(gamma=0.18, vmin=0.0, vmax=max(vmax, np.finfo(float).tiny))
            cmap = "magma"
        image = ax.imshow(field, origin="lower", extent=(0.5, 289.5, 0.5, 189.5), aspect="auto", cmap=cmap, norm=norm, interpolation="nearest")
        ax.axvline(145.5, color="cyan", linewidth=0.9, linestyle="--", alpha=0.95)
        ax.axhline(95.5, color="cyan", linewidth=0.9, linestyle="--", alpha=0.95)
        ax.set_title(title)
        ax.set_xlabel("west_east i (1-based)")
        ax.set_ylabel("south_north j (1-based)")
        cb = fig.colorbar(image, ax=ax, shrink=0.86, pad=0.02)
        cb.set_label(unit)
        ax.text(0.01, 0.99, f"full grid; x split 145|146, y split 95|96\ncolor limit ±{vmax:.4g}" if mode == "signed" else f"full grid; x split 145|146, y split 95|96\nmax={vmax:.4g}",
                transform=ax.transAxes, va="top", ha="left", fontsize=8, color="black",
                bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "none", "pad": 2})
    fig.suptitle(f"First output step decomposition difference at {TIME}\nMPI4 − MPI1 for signed SWDOWN; absolute maxima over k for 3-D fields", fontsize=13)
    png = args.output_dir / "mpi4-minus-mpi1-first-step.png"
    pdf = args.output_dir / "mpi4-minus-mpi1-first-step.pdf"
    fig.savefig(png, dpi=220)
    fig.savefig(pdf)
    plt.close(fig)

    matrix_receipt = root / "build/udm-lw-trace-gases-parallel/matrix-run-receipt.json"
    receipt = {
        "schema": "UDM_MPI_DECOMPOSITION_PLOT_V1",
        "status": "PLOT_GENERATED",
        "interpretation": "Diagnostic spatial association only; not a bias estimate or established source attribution. QNCLOUD/QNCCN are stored-field differences in declared Registry units, with UDM concentration convention unresolved; no density conversion is applied.",
        "time": TIME,
        "difference_convention": "MPI4 minus MPI1",
        "inputs": {
            "mpi1_history": str(args.mpi1.resolve()),
            "mpi1_history_sha256": sha256(args.mpi1.resolve()),
            "mpi1_namelist": str(args.mpi1.resolve().parent / "namelist.input"),
            "mpi1_namelist_sha256": sha256(args.mpi1.resolve().parent / "namelist.input"),
            "mpi4_history": str(args.mpi4.resolve()),
            "mpi4_history_sha256": sha256(args.mpi4.resolve()),
            "mpi4_namelist": str(args.mpi4.resolve().parent / "namelist.input"),
            "mpi4_namelist_sha256": sha256(args.mpi4.resolve().parent / "namelist.input"),
            "matrix_run_receipt": str(matrix_receipt),
            "matrix_run_receipt_sha256": sha256(matrix_receipt),
        },
        "domain": {"shape_j_i": list(left["shape"]), "dx_m": left["attributes"].get("DX"), "dy_m": left["attributes"].get("DY"),
                   "grid_geometry_identical": True, "map_projection_latlon_coordinates_identical": True},
        "seams": {"x_between_1based_columns": [145, 146], "y_between_1based_rows": [95, 96],
                  "plotted_without_boundary_mask": True},
        "fields": {
            "SWDOWN": {"source_units": left["units"]["SWDOWN"], "plot": "signed 2-D surface difference", **stats(sw, "SWDOWN")},
            "T": {"source_units": left["units"]["T"], "plot": "max absolute MPI4-MPI1 perturbation over 39 native mass levels", **stats(np.max(np.abs(dt), axis=0), "max_k_abs_delta_T")},
            "QNCLOUD": {"source_units": left["units"]["QNCLOUD"], "plot": "max absolute stored-field difference over 39 native mass levels; no density conversion", "unit_caveat": "Registry declares # kg(-1); UDM input/output number-concentration convention has not been independently resolved, so these are stored-field differences only", **stats(np.max(np.abs(right["QNCLOUD"]-left["QNCLOUD"]), axis=0), "max_k_abs_delta_QNCLOUD_stored")},
            "QNCCN": {"source_units": left["units"]["QNCCN"], "plot": "max absolute stored-field difference over 39 native mass levels; no density conversion", "unit_caveat": "Registry declares # kg(-1); UDM input/output number-concentration convention has not been independently resolved, so these are stored-field differences only", **stats(np.max(np.abs(right["QNCCN"]-left["QNCCN"]), axis=0), "max_k_abs_delta_QNCCN_stored")},
        },
        "color_scales": {"SWDOWN": "symmetric SymLogNorm, linthresh=1e-4 of full-grid maxabs, limit=full-grid maxabs", "3d_magnitude_panels": "PowerNorm gamma=0.18, full-grid max, zero-valued pixels retained"},
        "plot_files": {"png": png.name, "png_sha256": sha256(png), "pdf": pdf.name, "pdf_sha256": sha256(pdf)},
        "script_sha256": sha256(Path(__file__).resolve()),
        "source_attributes": {"mpi1": left["attributes"], "mpi4": right["attributes"]},
    }
    (args.output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
