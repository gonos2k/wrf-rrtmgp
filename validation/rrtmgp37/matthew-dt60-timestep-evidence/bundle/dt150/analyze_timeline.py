#!/usr/bin/env python3
"""Read-only timeline analysis for the preserved Jan-? Matthew Courant diagnostic run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "build/udm37-matthew-native-courant-diagnostic-v1"
HISTORY = CASE / "ra37-native-courant/wrfout_d01_2016-10-06_00:00:00"
COURANT = CASE / "wrfout_d01_2016-10-06_00:00:00.courant.json"
OUT = Path(__file__).resolve().parent
I0, J0 = 41, 29  # WRF one-based i=42, j=30.
P0, T0, RD, RV, CP = 100000.0, 300.0, 287.0, 461.6, 3.5 * 287.0


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pin(path: Path) -> dict:
    path = path.resolve(strict=True)
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha(path)}


def rawvar(ds: Dataset, name: str) -> tuple[np.ndarray, np.ndarray]:
    var = ds.variables[name]
    var.set_auto_maskandscale(False)
    a = np.asarray(var[:])
    bad = ~np.isfinite(a) if a.dtype.kind == "f" else np.zeros(a.shape, dtype=bool)
    for key in ("_FillValue", "missing_value"):
        if key in var.ncattrs():
            marker = getattr(var, key)
            if np.issubdtype(a.dtype, np.floating) and np.isnan(marker):
                bad |= np.isnan(a)
            else:
                bad |= a == marker
    return a, bad


def time_string(row) -> str:
    return b"".join(np.asarray(row).tolist()).decode("ascii").rstrip("\x00 ")


def json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def json_safe_floats(value):
    if isinstance(value, list):
        return [json_safe_floats(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, np.generic):
        return json_safe_floats(value.item())
    return value


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with Dataset(HISTORY, "r") as ds:
        names = ("Times", "T", "THM", "P", "PB", "QVAPOR", "RTHRATLW", "GLW")
        values, bad = {}, {}
        metadata = {}
        for name in names:
            values[name], bad[name] = rawvar(ds, name)
            v = ds.variables[name]
            metadata[name] = {
                "dimensions": list(v.dimensions), "shape": list(v.shape),
                "dtype": str(v.dtype), "units": getattr(v, "units", None),
                "description": getattr(v, "description", None),
            }
        attrs = {x: getattr(ds, x) for x in ("USE_THETA_M", "MP_PHYSICS", "RA_LW_PHYSICS", "RA_SW_PHYSICS", "DT")}

    times = [time_string(r) for r in values["Times"]]
    tpert = values["T"].astype(np.float64)
    ptotal = values["P"].astype(np.float64) + values["PB"].astype(np.float64)
    qv = values["QVAPOR"].astype(np.float64)
    # Registry maps history T to th_phy_m_t0 (dry theta perturbation), while
    # THM is the prognostic `t` field and can be moist theta under USE_THETA_M.
    # The former needs only Exner; use THM/QVAPOR as an independent cross-check.
    theta_dry = tpert + T0
    exner = (ptotal / P0) ** (RD / CP)
    temperature = theta_dry * exner
    thm = values["THM"].astype(np.float64)
    theta_dry_from_thm = (thm + T0) / (1.0 + (RV / RD) * qv)
    temperature_from_thm = theta_dry_from_thm * exner
    theta_crosscheck = theta_dry_from_thm - (tpert + T0)
    temperature_crosscheck = temperature_from_thm - temperature

    ntime = len(times)
    finite_summary = {}
    for name in ("T", "P", "QVAPOR"):
        finite_summary[name] = [
            {"nonfinite_count": int(np.count_nonzero(~np.isfinite(values[name][n]))),
             "fill_or_missing_count": int(np.count_nonzero(bad[name][n]))}
            for n in range(ntime)
        ]
    finite_summary["physical_temperature_K"] = [
        {"nonfinite_count": int(np.count_nonzero(~np.isfinite(temperature[n]))),
         "fill_or_missing_count": int(np.count_nonzero(~np.isfinite(temperature[n]) | bad["T"][n] | bad["P"][n] | bad["PB"][n] | bad["QVAPOR"][n]))}
        for n in range(ntime)
    ]
    thm_crosscheck = []
    for n, stamp in enumerate(times):
        valid_thm = (np.isfinite(theta_crosscheck[n]) & ~bad["THM"][n]
                     & ~bad["T"][n] & ~bad["QVAPOR"][n])
        delta = theta_crosscheck[n][valid_thm]
        td = temperature_crosscheck[n][valid_thm]
        thm_crosscheck.append({
            "time": stamp, "finite_count": int(delta.size),
            "nonfinite_or_fill_count": int(valid_thm.size - delta.size),
            "max_abs_dry_theta_difference_K": float(np.max(np.abs(delta))) if delta.size else None,
            "mean_dry_theta_difference_K": float(np.mean(delta)) if delta.size else None,
            "max_abs_physical_temperature_difference_K": float(np.max(np.abs(td))) if td.size else None,
        })

    lw = values["RTHRATLW"].astype(np.float64)
    glw = values["GLW"].astype(np.float64)
    lw_global = []
    for n, stamp in enumerate(times):
        finite = np.isfinite(lw[n]) & ~bad["RTHRATLW"][n]
        lw_global.append({
            "time": stamp,
            "finite_count": int(np.count_nonzero(finite)),
            "nonfinite_or_fill_count": int(finite.size - np.count_nonzero(finite)),
            "min_K_s": float(np.min(lw[n][finite])) if np.any(finite) else None,
            "max_K_s": float(np.max(lw[n][finite])) if np.any(finite) else None,
        })

    cour = json.loads(COURANT.read_text())
    if len(cour["records"]) != ntime or cour.get("times", times) != times:
        raise RuntimeError("Courant analysis does not align with history time records")
    cmax = [r.get("courant_max_abs") for r in cour["records"]]
    selected_tpert = tpert[:, :, J0, I0]
    selected_tphys = temperature[:, :, J0, I0]
    selected_lw = lw[:, :, J0, I0]
    selected_glw = glw[:, J0, I0]

    # Plot 1: history endpoint Courant and data-quality counts.
    fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
    x = np.arange(ntime)
    plotted_cmax = [value if r["nonfinite_courant_count"] == 0 else np.nan
                    for value, r in zip(cmax, cour["records"])]
    ax.plot(x, plotted_cmax, marker="o", ms=3, color="#2455a4", label="max endpoint |eta Courant| (complete record)")
    ax.set_ylabel("Endpoint |eta Courant| (unitless)")
    ax.set_xticks(x[::2], [times[n][11:16] for n in x[::2]], rotation=45, ha="right")
    ax.set_xlabel("2016-10-06 UTC")
    ax.grid(True, alpha=.25)
    ax.legend(loc="upper left")
    ax2 = ax.twinx()
    for name, color in (("T", "#d95f02"), ("P", "#1b9e77"), ("QVAPOR", "#7570b3")):
        count = [r["nonfinite_count"] for r in finite_summary[name]]
        ax2.plot(x, count, linestyle="--", linewidth=1, alpha=.7, color=color, label=f"{name} nonfinite")
    ax2.plot(x, [r["nonfinite_courant_count"] for r in cour["records"]], linestyle=":",
             linewidth=1.4, color="#111111", label="Courant invalid endpoints")
    if cour["records"][-1]["nonfinite_courant_count"]:
        ax.annotate(f"max unavailable; {cour['records'][-1]['nonfinite_courant_count']:,} invalid endpoints",
                    xy=(x[-1], 0.06), xycoords=("data", "axes fraction"),
                    xytext=(-175, 18), textcoords="offset points", color="#a11", fontsize=8,
                    arrowprops={"arrowstyle": "->", "color": "#a11"})
    ax2.set_ylabel("P/T/QVAPOR nonfinite count")
    ax2.set_ylim(bottom=0)
    ax2.legend(loc="upper right", fontsize=8)
    ax.set_title("Endpoint vertical Courant diagnostic and core-field finiteness")
    fig.savefig(OUT / "courant_timeline.png", dpi=160)
    fig.savefig(OUT / "courant_timeline.pdf")
    plt.close(fig)

    # Plot 2: selected column thermodynamic profile at last valid and failing-time outputs.
    indices = [min(17, ntime - 1), min(19, ntime - 1), ntime - 1]
    labels = [times[n] for n in indices]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 6), sharey=True, constrained_layout=True)
    lev = np.arange(1, tpert.shape[1] + 1)
    colors = ("#1b9e77", "#2455a4", "#d95f02")
    for n, label, color in zip(indices, labels, colors):
        a1.plot(selected_tpert[n], lev, color=color, label=label)
        a2.plot(selected_tphys[n], lev, color=color, label=label)
    a1.set_xlabel("T history field (K; perturbation moist theta)")
    a2.set_xlabel("Physical temperature from T (K)")
    a1.set_ylabel("Mass level k (1=lowest)")
    for ax in (a1, a2):
        ax.grid(True, alpha=.25)
        ax.invert_yaxis()
        ax.legend(fontsize=8)
    fig.suptitle("Selected column i=42, j=30: dry-theta T and reconstructed physical T")
    fig.savefig(OUT / "selected_temperature_profiles.png", dpi=160)
    fig.savefig(OUT / "selected_temperature_profiles.pdf")
    plt.close(fig)

    # Plot 3: radiation diagnostic state at the same column.
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    a1.plot(x, selected_glw, marker="o", ms=3, color="#238b45")
    a1.set_xticks(x[::2], [times[n][11:16] for n in x[::2]], rotation=45, ha="right")
    a1.set_xlabel("2016-10-06 UTC")
    a1.set_ylabel("GLW (W m$^{-2}$)")
    a1.set_title("Selected-cell downward LW surface flux")
    a1.grid(True, alpha=.25)
    for n, label, color in zip(indices, labels, colors):
        a2.plot(selected_lw[n], lev, color=color, label=label)
    a2.set_xlabel("RTHRATLW (K s$^{-1}$)")
    a2.set_ylabel("Mass level k (1=lowest)")
    a2.invert_yaxis()
    a2.grid(True, alpha=.25)
    a2.legend(fontsize=8)
    a2.set_title("Selected-cell LW tendency profiles")
    fig.suptitle("Radiation diagnostics at i=42, j=30")
    fig.savefig(OUT / "radiation_selected_column.png", dpi=160)
    fig.savefig(OUT / "radiation_selected_column.pdf")
    plt.close(fig)

    source_files = [
        CASE / "execution-receipt.json", CASE / "manifest.json", CASE / "plan.json",
        CASE / "analyze_history.py", CASE / "wrfout_d01_2016-10-06_00:00:00.courant.json",
        OUT / "analyze_timeline.py",
        ROOT / "build/udm37-matthew-native-stability-timeline-v1/artifact-manifest.json",
        ROOT / "build/udm37-matthew-native-stability-timeline-v1/timeline.json",
        ROOT / "build/udm37-matthew-native-stability-timeline-v1/README.md",
        ROOT / "build/udm37-matthew-native-stability-timeline-v1/analyze_timeline.py",
        HISTORY,
        CASE / "ra37-native-courant/wrf.stdout.log",
        CASE / "ra37-native-courant/rsl.error.0000",
        CASE / "ra37-native-courant/rsl.error.0001",
        CASE / "ra37-native-courant/rsl.error.0002",
        CASE / "ra37-native-courant/rsl.error.0003",
        ROOT / "build/udm37-pr65-fatal-reporter-wrf-build-v1/build-receipt.json",
        ROOT / "WRF/share/module_model_constants.F",
        ROOT / "WRF/Registry/Registry.EM_COMMON",
        ROOT / "WRF/dyn_em/module_initialize_real.F",
    ]
    exe_pin = json.loads((CASE / "execution-receipt.json").read_text())["postflight"]["case_executable"]
    source_pins = {str(p.relative_to(ROOT)): pin(p) for p in source_files}
    source_pins["executed_wrf_executable"] = exe_pin
    plots = {}
    for name in ("courant_timeline.png", "courant_timeline.pdf",
                 "selected_temperature_profiles.png", "selected_temperature_profiles.pdf",
                 "radiation_selected_column.png", "radiation_selected_column.pdf"):
        plots[name] = pin(OUT / name)

    result = {
        "schema": "udm37-matthew-native-stability-timeline-v2",
        "status": "ANALYZED_FAILED_RUN_PRESERVED",
        "scope": "Read-only analysis of 21 history records from one 4-rank, 1-minute case that failed after writing 00:50 output; no new model invocation.",
        "execution": {"status": "FAIL_PRESERVED", "returncode": 1, "timed_out": False,
                      "model_invocations": 1, "forecast_invocations": 1,
                      "failure": "RRTMGP_INPUT_DP_HPA_NOT_FINITE at column=1 layer=1 after 2016-10-06_00:50:00 history write"},
        "history": pin(HISTORY), "source_and_analysis_pins": source_pins,
        "time_records": times,
        "native_courant": {
            "formula": cour["formula"], "scope": cour["formula_scope"],
            "max_abs_by_time": [{"time": t, "max_abs": c,
                                 "finite_count": r["finite_count"],
                                 "nonfinite_count": r["nonfinite_courant_count"],
                                 "location_fortran_indices": r.get("location_fortran_indices")}
                                for t, c, r in zip(times, cmax, cour["records"])],
            "nonfinite_endpoint_count_by_time": [r["nonfinite_courant_count"] for r in cour["records"]],
            "aggregate_nonfinite_endpoint_count": cour["aggregate_nonfinite_courant_count"],
            "aggregate_endpoint_count": cour["aggregate_endpoint_count"],
            "aggregate_invalid_counts_by_source": cour["aggregate_invalid_counts_by_source"],
            "warning": "History endpoint diagnostic, not an internal RK/acoustic-stage peak or a causal test."
        },
        "wrf_thermodynamics": {
            "use_theta_m": int(attrs["USE_THETA_M"]), "attributes": attrs,
            "stored_T_contract": "Registry DataName T maps to th_phy_m_t0, the dry perturbation potential temperature theta_dry-300 K. THM maps to prognostic t and is moist potential temperature under USE_THETA_M=1.",
            "definition_source": "WRF/Registry/Registry.EM_COMMON lines 210-212; module_big_step_utilities_em.F assigns th_phy_m_t0=th_phy-T0 and t_phy=th_phy*pi_phy; module_initialize_real.F defines the moist t conversion.",
            "physical_temperature_formula": "Tphysical=(T+300)*((P+PB)/100000)^(Rd/Cp), because T is dry theta perturbation.",
            "independent_THM_crosscheck": "theta_dry_from_THM=(THM+300)/(1+(Rv/Rd)*QVAPOR); compare theta_dry_from_THM to T+300, then compare physical temperature after the same Exner factor.",
            "THM_crosscheck_by_time": thm_crosscheck,
            "constants": {"T0_K": T0, "P0_Pa": P0, "Rd_J_kgK": RD, "Rv_J_kgK": RV, "Cp_J_kgK": CP,
                          "constant_source": "WRF/share/module_model_constants.F"},
            "selected_cell": {"i_fortran": 42, "j_fortran": 30, "i_zero_based": I0, "j_zero_based": J0,
                              "Tpert_K_by_time_and_mass_level": json_safe_floats(selected_tpert.tolist()),
                              "physical_temperature_K_by_time_and_mass_level": json_safe_floats(selected_tphys.tolist()),
                              "THM_moist_potential_temperature_K_by_time_and_mass_level": json_safe_floats(thm[:, :, J0, I0].tolist()),
                              "physical_temperature_from_THM_K_by_time_and_mass_level": json_safe_floats(temperature_from_thm[:, :, J0, I0].tolist()),
                              "GLW_W_m2_by_time": json_safe_floats(selected_glw.tolist()),
                              "RTHRATLW_K_s_by_time_and_mass_level": json_safe_floats(selected_lw.tolist())},
            "nonfinite_counts_by_time": finite_summary,
            "RTHRATLW_global_finite_extrema_by_time": lw_global,
            "global_nonfinite_RTHRATLW_count": int(np.count_nonzero(~np.isfinite(lw))),
            "global_nonfinite_GLW_count": int(np.count_nonzero(~np.isfinite(glw))),
            "variable_metadata": metadata,
        },
        "interpretation_limits": [
            "The history records are 150-second output samples, not every RK/acoustic-stage state.",
            "Finite RTHRATLW and GLW in written records do not exclude an indirect tendency/thermodynamic trigger, nor establish a radiation-port error.",
            "The run ended FAIL_PRESERVED; the 00:50 record was written before the fatal input check.",
            "No threshold, tolerance, state, or model source was changed for this analysis."
        ],
        "generated_plots": plots,
    }
    (OUT / "timeline.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False, default=json_default) + "\n")


if __name__ == "__main__":
    main()
