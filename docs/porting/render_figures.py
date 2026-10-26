"""Export figures from existing CSV; no model runs or altered verification scores."""

from pathlib import Path
import csv
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def series(folder):
    with (ROOT / "validation/rrtmgp37" / folder / "hourly-comparison.csv").open() as stream:
        return list(csv.DictReader(stream))


def render_forecast():
    old = series("real-output-independent-comparison")
    new = series("sterling-interior-day-evaluation")
    assert [x["primary_W_m2"] for x in old] == [x["primary_W_m2"] for x in new]
    hours = [int(x["start_utc"][11:13]) + 0.5 for x in new]
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7), sharex=True, layout="constrained")
    axes[0].plot(
        hours, [float(x["primary_W_m2"]) for x in new], "ko-", label="SOLRAD reconstructed GHI"
    )
    axes[0].plot(
        hours,
        [float(x["model_W_m2"]) for x in old],
        "o--",
        color="#b87f24",
        label="Earlier boundary configuration",
    )
    axes[0].plot(
        hours,
        [float(x["model_W_m2"]) for x in new],
        "o-",
        color="#2874a6",
        label="Interior research configuration",
    )
    axes[0].plot(
        hours,
        [float(x["model_clear_W_m2"]) for x in new],
        ":",
        color="#777777",
        label="Interior clear sky",
    )
    axes[0].set_ylabel("Hourly mean downward SW [W/m2]")
    axes[0].legend(loc="upper left", fontsize=8)
    axes[1].bar(hours, [float(x["primary_error_W_m2"]) for x in new], width=0.8, color="#2874a6")
    axes[1].axhline(0, color="k", lw=0.7)
    axes[1].set_ylabel("Interior minus observation [W/m2]")
    axes[1].set_xlabel("2016-10-06 UTC hour; all 24 verification hours retained")
    for panel in axes:
        panel.axvspan(17, 20, color="#f5b7b1", alpha=0.3)
        panel.grid(axis="y", alpha=0.2)
        panel.set_xlim(0, 24)
        panel.set_xticks(range(0, 25, 2))
    fig.suptitle(
        "Sterling fixed-station comparison\nTwo configurations differ in domain, WPS and geography; not an optics-only experiment"
    )
    fig.savefig(OUT / "forecast-comparison.svg", metadata={"Date": "2026-10-26"})
    plt.close(fig)


def render_architecture():
    fig, axis = plt.subplots(figsize=(11, 5.5), layout="constrained")
    axis.set_xlim(0, 11)
    axis.set_ylim(0, 5.5)
    axis.axis("off")
    boxes = [
        (0.1, 3.6, "WRF / UDM state\nq, number, native radius\npressure, T, surface"),
        (3.8, 3.6, "Input boundary\ndry mass / gas columns\nCF and particle paths"),
        (7.5, 3.6, "Optical properties\ngas + cloud + precip\nRRTMGP / LUTs"),
        (7.5, 0.7, "RTE solver\nLW absorption/emission\nSW two stream"),
        (3.8, 0.7, "Return boundary\nflux: W/m2\nheating: K/day -> theta/s"),
        (0.1, 0.7, "WRF update / output\nheld tendencies\ncheckpoint / history"),
    ]
    for x, y, label in boxes:
        axis.add_patch(
            FancyBboxPatch(
                (x, y),
                3.1,
                1.25,
                boxstyle="round,pad=0.08",
                facecolor="#edf4fa",
                edgecolor="#2874a6",
                lw=1.3,
            )
        )
        axis.text(x + 1.55, y + 0.625, label, ha="center", va="center", fontsize=10)
    for start, end in [
        ((3.22, 4.22), (3.68, 4.22)),
        ((6.92, 4.22), (7.38, 4.22)),
        ((9.05, 3.48), (9.05, 2.08)),
        ((7.38, 1.32), (6.92, 1.32)),
        ((3.68, 1.32), (3.22, 1.32)),
    ]:
        axis.add_patch(
            FancyArrowPatch(
                start, end, arrowstyle="-|>", mutation_scale=15, color="#2874a6", lw=1.5
            )
        )
    axis.text(
        5.5,
        2.65,
        "Mapping correctness does not establish atmospheric-state accuracy",
        ha="center",
        fontsize=10,
    )
    fig.savefig(OUT / "architecture.svg", metadata={"Date": "2026-10-26"})
    plt.close(fig)


def main():
    plt.rcParams.update(
        {"svg.fonttype": "none", "svg.hashsalt": "udm27-rrtmgp37-report-v1", "font.size": 10}
    )
    render_forecast()
    render_architecture()


if __name__ == "__main__":
    main()
