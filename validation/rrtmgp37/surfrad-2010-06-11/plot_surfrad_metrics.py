#!/usr/bin/env python3
"""Plot the saved SURFRAD-vs-WRF station metrics without rereading source data."""
import argparse
import csv
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


FLUXES = [
    ("dw_solar", "Downwelling SW", "SWDOWN"),
    ("uw_solar", "Upwelling SW", "SWUPB"),
    ("dw_ir", "Downwelling LW", "GLW"),
    ("uw_ir", "Upwelling LW", "LWUPB"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metrics_dir", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"refusing to overwrite plots: {args.output_dir}")
    rows = list(csv.DictReader((args.metrics_dir / "hourly.csv").open(newline="")))
    args.output_dir.mkdir(parents=True)
    for station in ("FPK", "DRA"):
        fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
        for ax, (field, title, modelname) in zip(axes.flat, FLUXES):
            subset = [r for r in rows if r["station"] == station and r["obs_field"] == field]
            times = [datetime.fromisoformat(r["model_time_utc"].replace("Z", "+00:00")) for r in subset]
            obs = [float(r["obs_qc0_minute_mean_Wm2"]) if r["obs_qc0_minute_mean_Wm2"] else np.nan for r in subset]
            ra4 = [float(r["ra4_instant_Wm2"]) if r["ra4_instant_Wm2"] else np.nan for r in subset]
            ra37 = [float(r["ra37_instant_Wm2"]) if r["ra37_instant_Wm2"] else np.nan for r in subset]
            obs_e = [float(r["obs_hour_energy_Jm2"]) / 3600.0 if r["obs_hour_energy_Jm2"] else np.nan for r in subset]
            ra4_e = [float(r["ra4_hour_energy_Jm2"]) / 3600.0 if r["ra4_hour_energy_Jm2"] else np.nan for r in subset]
            ra37_e = [float(r["ra37_hour_energy_Jm2"]) / 3600.0 if r["ra37_hour_energy_Jm2"] else np.nan for r in subset]
            ax.plot(times, obs, color="black", marker="o", ms=3, lw=1.1, label="SURFRAD 1-min mean")
            ax.plot(times, ra4, color="#2878b5", lw=1.1, label="WRF RA4 snapshot")
            ax.plot(times, ra37, color="#d95319", lw=1.1, label="WRF RA37 snapshot")
            ax.plot(times, obs_e, color="black", ls="--", lw=1.0, alpha=0.75, label="SURFRAD hourly energy / 3600")
            ax.plot(times, ra4_e, color="#2878b5", ls="--", lw=1.0, alpha=0.75, label="WRF RA4 hourly energy / 3600")
            ax.plot(times, ra37_e, color="#d95319", ls="--", lw=1.0, alpha=0.75, label="WRF RA37 hourly energy / 3600")
            ax.set_title(f"{title} ({modelname})")
            ax.set_ylabel("Flux-equivalent (W m$^{-2}$)")
            ax.grid(True, alpha=0.25)
        for ax in axes[-1, :]:
            ax.set_xlabel("UTC, 2010-06-11/12")
            ax.tick_params(axis="x", rotation=25)
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8, frameon=False)
        fig.suptitle(f"{station}: SURFRAD point fluxes and WRF radiation cases\nSnapshots and independently integrated hourly energy (dashed); no scheme ranking")
        fig.tight_layout(rect=(0, 0.12, 1, 0.91))
        fig.savefig(args.output_dir / f"{station.lower()}-surface-radiation.png", dpi=180)
        fig.savefig(args.output_dir / f"{station.lower()}-surface-radiation.svg")
        plt.close(fig)
    print(f"wrote station plots under {args.output_dir}")


if __name__ == "__main__":
    main()
