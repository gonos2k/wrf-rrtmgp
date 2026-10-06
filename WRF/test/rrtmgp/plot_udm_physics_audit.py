#!/usr/bin/env python3
"""Plot descriptive same-state audit results from the saved evidence receipt."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.receipt.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), sharey=True)
    for ax, case in zip(axes, ("control", "mixed")):
        def rows(run):
            return [r for r in data["runs"][run]["cases"][case]["attribution_per_call"]
                    if r["phase"] == "SW" and r["metric"] == "SURFACE_DOWN"]
        actual = rows("production_1024")
        native = rows("native4_counterfactual_128")
        time = np.array([r["source_seconds"] for r in actual])
        mean = np.array([r["same_state_ensemble_mean_37_minus_engine4"] for r in actual])
        sd = np.array([r["same_state_paired_seed_sd_delta"] for r in actual])
        ax.fill_between(time, mean - sd, mean + sd, color="C0", alpha=.14,
                        label="Seed SD (descriptive)")
        ax.plot(time, mean, "o-", color="C0", label="Same state, 1024-seed mean")
        ax.plot(time, [r["same_state_operational_37_minus_engine4"] for r in actual],
                "s--", color="C1", label="Same state, operational seeds")
        ax.plot(time, [r["coupled_history_37_minus_4"] for r in actual],
                "x:", color="black", label="Coupled run difference")
        ax.plot([r["source_seconds"] for r in native],
                [r["same_state_ensemble_mean_37_minus_engine4"] for r in native],
                "^--", color="C2", label="4 native-radius path, 128 seeds")
        ax.axhline(0, color="gray", linewidth=.7)
        ax.set_title(f"UDM27 {case}")
        ax.set_xlabel("Radiation input time (s)")
        ax.grid(alpha=.2)
    axes[0].set_ylabel("Surface downward SW: 37 - engine 4 (W/m²)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, fontsize=8)
    fig.suptitle("One-minute serial SCM: same-state attribution, no forecast accuracy claim")
    fig.tight_layout(rect=(0, .18, 1, .95))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
