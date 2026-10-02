#!/usr/bin/env python3
"""Plot recorded coupled-trajectory metrics; no observational accuracy inference."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

root = Path(__file__).resolve().parent
data = json.loads((root / "coupled-metrics.json").read_text())
assert data["classification"] == "COUPLED_TRAJECTORY_DIFFERENCE"
assert data["area_weighting"]["difference_convention"].endswith("(ra4 - mode1)")
fig, axes = plt.subplots(3, 2, figsize=(10, 8), sharex=True, layout="constrained")
hours = np.arange(len(data["times"]))
for row, name in enumerate(("SWDOWN", "GLW", "OLR")):
    records = data["available_fields"][name]["hourly"]
    left, right = axes[row]
    left.plot(hours, [r["ra4_area_weighted_mean"] for r in records], label="RRTMG4", color="#1f77b4")
    left.plot(hours, [r["mode1_area_weighted_mean"] for r in records], label="PR20 RRTMGP37 mode 1", color="#d95f02", linestyle="--")
    left.set_ylabel(f"{name} (W m$^{{-2}}$)")
    right.plot(hours, [r["area_weighted_mean_delta"] for r in records], label="Mean: RRTMG4 minus 37", color="#7570b3")
    right.plot(hours, [r["area_weighted_rmse"] for r in records], label="Spatial RMS difference", color="#1b9e77")
    right.axhline(0, color="0.5", linewidth=0.6)
    for ax in (left, right):
        ax.grid(alpha=0.25)
        ax.set_xlim(0, 24)
        ax.set_xticks(np.arange(0, 25, 4))
axes[0, 0].set_title("Area-weighted domain means")
axes[0, 1].set_title("Coupled-trajectory differences (W m$^{-2}$)")
axes[0, 0].legend(fontsize=8)
axes[0, 1].legend(fontsize=8)
for ax in axes[-1]:
    ax.set_xlabel("Hours since 2010-06-11 00:00 UTC")
fig.suptitle("UDM27, 24-hour actual-domain comparison\nDifferent optical configurations and evolving states; no observation comparison", fontsize=12)
fig.supxlabel("Full 289 × 189 native mass grid; AREA2D weighting. Initial radiation fields are zero before first RTE call.", fontsize=8)
for suffix in ("png", "pdf"):
    fig.savefig(root / f"coupled-radiation.{suffix}", dpi=180)
