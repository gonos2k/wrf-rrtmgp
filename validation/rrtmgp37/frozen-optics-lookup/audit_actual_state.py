#!/usr/bin/env python3
"""Audit RA4 hourly UDM hydrometeors against frozen optical-table axes.

Lambda is reconstructed from returned grid-mean q (post-sedimentation), not
the in-cloud q and subcycle state used by UDM's process tendencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import netCDF4
import numpy as np

DEFAULT_CASE = Path("build/udm-realdata-24h/ra4")
DEFAULT_SOURCE = Path("build/mpi-wrf-udm-contracts/WRF")
SPECIES = {
    "graupel": {"var": "QGRAUP", "rho_particle": 500.0, "n0": 4.0e6},
    "hail": {"var": "QHAIL", "rho_particle": 912.0, "n0": 4.0e4},
}
RD, RV, CP, P0, T0 = 287.0, 461.6, 1004.5, 100000.0, 300.0
CVPM = -(CP - RD) / CP
Q_CUTOFF = 1.0e-9
LAMBDA_MAX = 2.0e4
TABLE_LAMBDA = (300.0, 20000.0)
TABLE_TEMP = (180.0, 300.0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_inventory(paths, workspace):
    return {str(p.relative_to(workspace)): {"size_bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(set(paths))}


def hash_inputs(workspace, case, source_root, histories):
    other = [case / x for x in ("wrfinput_d01", "wrfbdy_d01", "namelist.input", "namelist.output",
                                 "wrf-mpi4-omp1.log")]
    # Runtime source used for the executable; source hashes make the diagnostic
    # formula traceable without implying that output fields preserve source precision.
    source = [source_root / x for x in (
        "phys/module_mp_udm.F", "dyn_em/start_em.F", "dyn_em/module_big_step_utilities_em.F",
        "share/module_model_constants.F")]
    exe = case / "wrf.exe"
    extra_provenance = [workspace / "build/udm-realdata-24h/ra4-24h-summary.json",
                        workspace / "build/udm-realdata-24h/24h-comparison-receipt.json"]
    return file_inventory(histories + other + source + [exe] + extra_provenance, workspace)


def new_stats():
    return {"count": 0, "positive_count": 0, "zero_count": 0, "negative_count": 0,
            "q_min": math.inf, "q_max": -math.inf, "lambda_min": math.inf,
            "lambda_max": -math.inf, "rho_min": math.inf, "rho_max": -math.inf,
            "temperature_min_K": math.inf, "temperature_max_K": -math.inf,
            "lambda_below_300_count": 0, "lambda_above_20000_count": 0,
            "temperature_below_180_count": 0, "temperature_above_300_count": 0,
            "lambda_and_temperature_in_table_count": 0, "positive_below_q_cutoff_count": 0,
            "positive_above_q_cutoff_count": 0,
            "positive_q_min_kgkg": math.inf, "positive_q_max_kgkg": -math.inf,
            "positive_lambda_min_m-1": math.inf, "positive_lambda_max_m-1": -math.inf,
            "positive_temperature_min_K": math.inf, "positive_temperature_max_K": -math.inf,
            "above_cutoff_lambda_min_m-1": math.inf, "above_cutoff_lambda_max_m-1": -math.inf,
            "above_cutoff_lambda_and_temperature_in_table_count": 0,
            "above_cutoff_temperature_below_180_count": 0, "above_cutoff_temperature_above_300_count": 0,
            "lambda_samples_by_hour": []}


def minmax_update(s, key, arr):
    if arr.size:
        s[key + "_min"] = min(s[key + "_min"], float(np.min(arr)))
        s[key + "_max"] = max(s[key + "_max"], float(np.max(arr)))


def cldf_diag(qc, qi, ktop_mask, dx_m=10000.):
    """Vectorized transcription of module_mp_udm.F cldf_diag (current state)."""
    qc = np.maximum(qc, 0.)
    qi = np.maximum(qi, 0.)
    cv_w_min = 4.82 * (qc * 1000.)**0.94 / 1.04
    cv_w_max = 5.77 * (qc * 1000.)**1.07 / 1.04
    cv_i_min = 4.82 * (qi * 1000.)**0.94 / 0.96
    cv_i_max = 5.77 * (qi * 1000.)**1.07 / 0.96
    cvf_min, cvf_max = cv_w_min + cv_i_min, cv_w_max + cv_i_max
    dxkm = dx_m / 1000.
    cf = ((dxkm - 50.) * (cvf_max - cvf_min) + 50. * cvf_min) / 50.
    cf = np.clip(cf, 0., 1.)
    cf = np.where(qc + qi < 1.e-6, 0., cf)
    cf = np.where(cf < .01, 0., cf)
    cf = np.where(cf > .99, 1., cf)
    cf = np.where((cf >= .01) & (cf < .5), .5, cf)
    # For each column, cldf_diag only writes through highest cloud/ice index;
    # UDM's setup initializes the untouched levels to 1.
    cf = np.where(ktop_mask, cf, 1.)
    return cf


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path, required=True,
                    help="workspace root containing build/udm-realdata-24h")
    ap.add_argument("--output", type=Path, required=True,
                    help="JSON destination, absolute or relative to workspace")
    ap.add_argument("--case-dir", type=Path, default=DEFAULT_CASE,
                    help="RA4 case path, relative to workspace unless absolute")
    ap.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE,
                    help="isolated runtime WRF source tree, relative to workspace unless absolute")
    ap.add_argument("--expected-records", type=int, default=25)
    args = ap.parse_args()
    if args.expected_records < 1:
        ap.error('Expected record count must be positive')
    workspace = args.workspace.resolve()
    case = (args.case_dir if args.case_dir.is_absolute() else workspace / args.case_dir).resolve()
    source_root = (args.source_dir if args.source_dir.is_absolute() else workspace / args.source_dir).resolve()
    out = (args.output if args.output.is_absolute() else workspace / args.output).resolve()
    if out.exists():
        ap.error('Use a new output file; preserve prior evidence')
    source_text = (source_root/'phys/module_mp_udm.F').read_text()
    if not re.search(r'dxmeter\s*\(\s*:\s*\)\s*=\s*10000\.', source_text):
        raise RuntimeError('Secondary CF diagnostic expects UDM internal dxmeter=10000 m')
    script_hash = sha256(Path(__file__).resolve())
    nmlout = (case / 'namelist.output').read_text()
    for name, expected in [('MP_PHYSICS',27),('RA_LW_PHYSICS',4),('RA_SW_PHYSICS',4),
                           ('USE_MP_RE',1),('USE_THETA_M',1)]:
        match = re.search(r'\b'+name+r'\s*=\s*(?:\d+\s*\*\s*)?([0-9]+)', nmlout)
        if match is None or int(match.group(1)) != expected:
            raise RuntimeError('This case audit requires '+name+'='+str(expected))
    files = sorted(case.glob("wrfout_d01_2010-06-*_*:*:*"))
    if len(files) != args.expected_records:
        raise SystemExit(f"Expected {args.expected_records} hourly histories, found {len(files)}")
    before = hash_inputs(workspace, case, source_root, files)
    summary = json.loads((workspace / "build/udm-realdata-24h/ra4-24h-summary.json").read_text())
    comparison_receipt = json.loads((workspace / "build/udm-realdata-24h/24h-comparison-receipt.json").read_text())
    ra4_receipt = comparison_receipt["ra4"]
    if not summary.get("all_numeric_finite") or not ra4_receipt.get("all_201_numeric_variables_finite_for_all_25_records"):
        raise RuntimeError("The preserved RA4 completion receipt does not certify finite history fields")
    if ra4_receipt.get("status") != "SUCCESS COMPLETE WRF" or ra4_receipt.get("exit_code") != 0:
        raise RuntimeError("Preserved RA4 WRF completion receipt is not successful")
    stats = {name: new_stats() for name in SPECIES}
    cf_counts = {"count": 0, "zero": 0, "half": 0, "one": 0, "other": 0}
    warmhail = {"positive_count": 0, "positive_and_T_ge_273_15_count": 0,
                "q_max_kgkg": 0., "warm_q_max_kgkg": 0., "warm_temperature_max_K": -math.inf}
    all_times = []
    field_shapes = {}
    use_theta_m = None
    p_hyd_absdiff_max = 0.0
    domain_spacing = None

    for hour_index, fpath in enumerate(files):
        with netCDF4.Dataset(fpath) as ds:
            spacing = {'DX_m':float(ds.DX),'DY_m':float(ds.DY)}
            if len(ds.dimensions['Time']) != 1 or not all(math.isfinite(x) and x>0 for x in spacing.values()):
                raise RuntimeError('Audit expects one record per file and positive finite spacing')
            if domain_spacing is None:
                domain_spacing = spacing
            elif domain_spacing != spacing:
                raise RuntimeError('Domain spacing differs between histories')
            def read_field(name):
                variable = ds.variables[name]
                if variable.dimensions != ('Time','bottom_top','south_north','west_east'):
                    raise RuntimeError(name+': unexpected axis order')
                data = variable[0]
                if np.any(np.ma.getmaskarray(data)):
                    raise RuntimeError(name+': masked history values')
                return np.asarray(data,dtype=np.float64)
            time_text = netCDF4.chartostring(ds.variables["Times"][:])[0].decode("ascii") if \
                isinstance(netCDF4.chartostring(ds.variables["Times"][:])[0], bytes) else \
                str(netCDF4.chartostring(ds.variables["Times"][:])[0])
            all_times.append(time_text)
            if use_theta_m is None:
                # The namelist.output is independently hashed; enforce its actual setting.
                nmlout = (case / "namelist.output").read_text(errors="replace")
                use_theta_m = "USE_THETA_M=1" in nmlout.replace(" ", "")
                if not use_theta_m:
                    raise RuntimeError("This reconstruction is only implemented for observed USE_THETA_M=1")
            needed = ["P", "PB", "T", "QVAPOR", "QCLOUD", "QICE", "QGRAUP", "QHAIL"]
            missing = [n for n in needed if n not in ds.variables]
            if missing:
                raise RuntimeError(f"{fpath.name}: missing fields {missing}")
            p = read_field('P') + read_field('PB')
            tpert = read_field('T')
            qv = read_field('QVAPOR')
            if not all(np.all(np.isfinite(x)) for x in (p, tpert, qv)):
                raise RuntimeError(f"{fpath.name}: nonfinite pressure, T, or qv")
            if np.any(p <= 0.) or np.any(tpert + T0 <= 0.) or np.any(1. + qv <= 0.):
                raise RuntimeError(f"{fpath.name}: nonpositive pressure/theta_m factor/moist density factor")
            rho_alt = (RD / P0) * (tpert + T0) * (p / P0)**CVPM
            rho = (1. + qv) / rho_alt
            # WRF theta_m conversion: recover th_phy, then multiply by Exner
            # based on total pressure.
            tair = ((tpert + T0) / (1. + (RV / RD) * qv)) * (p / P0)**(RD / CP)
            if "P_HYD" in ds.variables:
                p_hyd = read_field('P_HYD')
                p_hyd_absdiff_max = max(p_hyd_absdiff_max, float(np.max(np.abs(p - p_hyd))))
            qc = read_field('QCLOUD')
            qi = read_field('QICE')
            if (not all(np.all(np.isfinite(x)) for x in (qc, qi, rho, tair)) or
                    np.any(rho <= 0.) or np.any(tair <= 0.)):
                raise RuntimeError(f"{fpath.name}: nonfinite cloud/ice or invalid reconstructed rho/T")
            cloud_any = (qc > 0.) | (qi > 0.)
            # bottom_top increases from bottom toward top in WRF output.
            ktop = np.max(np.where(cloud_any, np.arange(cloud_any.shape[0])[:, None, None] + 1, 0), axis=0)
            kindex = np.arange(cloud_any.shape[0])[:, None, None] + 1
            cf_diag = cldf_diag(qc, qi, kindex <= ktop[None, :, :])
            cf_counts["count"] += int(cf_diag.size)
            cf_counts["zero"] += int(np.count_nonzero(cf_diag == 0.))
            cf_counts["half"] += int(np.count_nonzero(cf_diag == .5))
            cf_counts["one"] += int(np.count_nonzero(cf_diag == 1.))
            cf_counts["other"] += int(np.count_nonzero((cf_diag != 0.) & (cf_diag != .5) & (cf_diag != 1.)))

            for name, spec in SPECIES.items():
                q = read_field(spec['var'])
                if not np.all(np.isfinite(q)):
                    raise RuntimeError(f"{fpath.name}: nonfinite {spec['var']}")
                active = q > 0.
                if name == "hail":
                    warm = active & (tair >= 273.15)
                    warmhail["positive_count"] += int(np.count_nonzero(active))
                    warmhail["positive_and_T_ge_273_15_count"] += int(np.count_nonzero(warm))
                    if np.any(active): warmhail["q_max_kgkg"] = max(warmhail["q_max_kgkg"], float(q[active].max()))
                    if np.any(warm):
                        warmhail["warm_q_max_kgkg"] = max(warmhail["warm_q_max_kgkg"], float(q[warm].max()))
                        warmhail["warm_temperature_max_K"] = max(warmhail["warm_temperature_max_K"], float(tair[warm].max()))
                lam = np.full(q.shape, LAMBDA_MAX, dtype=np.float64)
                use_slope = q > Q_CUTOFF
                lam[use_slope] = np.minimum((math.pi * spec["rho_particle"] * spec["n0"] /
                                             (q[use_slope] * rho[use_slope]))**.25, LAMBDA_MAX)
                # Optional current-state CF-recomputed diagnostic. The main λ
                # remains based on grid q; this one deliberately divides q by CF.
                q_cf = np.where(cf_diag > 0., q / np.where(cf_diag > 0., cf_diag, 1.), q)
                lam_cf = np.full(q.shape, LAMBDA_MAX, dtype=np.float64)
                use_cf_slope = q_cf > Q_CUTOFF
                lam_cf[use_cf_slope] = np.minimum((math.pi * spec["rho_particle"] * spec["n0"] /
                                                   (q_cf[use_cf_slope] * rho[use_cf_slope]))**.25, LAMBDA_MAX)
                s = stats[name]
                s["count"] += q.size
                s["positive_count"] += int(np.count_nonzero(q > 0.))
                s["zero_count"] += int(np.count_nonzero(q == 0.))
                s["negative_count"] += int(np.count_nonzero(q < 0.))
                s["positive_below_q_cutoff_count"] += int(np.count_nonzero((q > 0.) & (q <= Q_CUTOFF)))
                s["positive_above_q_cutoff_count"] += int(np.count_nonzero(q > Q_CUTOFF))
                minmax_update(s, "q", q)
                minmax_update(s, "lambda", lam)
                minmax_update(s, "rho", rho)
                s["temperature_min_K"] = min(s["temperature_min_K"], float(np.min(tair)))
                s["temperature_max_K"] = max(s["temperature_max_K"], float(np.max(tair)))
                if np.any(active):
                    s["positive_q_min_kgkg"] = min(s["positive_q_min_kgkg"], float(q[active].min()))
                    s["positive_q_max_kgkg"] = max(s["positive_q_max_kgkg"], float(q[active].max()))
                    s["positive_lambda_min_m-1"] = min(s["positive_lambda_min_m-1"], float(lam[active].min()))
                    s["positive_lambda_max_m-1"] = max(s["positive_lambda_max_m-1"], float(lam[active].max()))
                    s["positive_temperature_min_K"] = min(s["positive_temperature_min_K"], float(tair[active].min()))
                    s["positive_temperature_max_K"] = max(s["positive_temperature_max_K"], float(tair[active].max()))
                s["lambda_below_300_count"] += int(np.count_nonzero(active & (lam < TABLE_LAMBDA[0])))
                s["lambda_above_20000_count"] += int(np.count_nonzero(active & (lam > TABLE_LAMBDA[1])))
                s["temperature_below_180_count"] += int(np.count_nonzero(active & (tair < TABLE_TEMP[0])))
                s["temperature_above_300_count"] += int(np.count_nonzero(active & (tair > TABLE_TEMP[1])))
                s["lambda_and_temperature_in_table_count"] += int(np.count_nonzero(
                    active & (lam >= TABLE_LAMBDA[0]) & (lam <= TABLE_LAMBDA[1]) &
                    (tair >= TABLE_TEMP[0]) & (tair <= TABLE_TEMP[1])))
                if np.any(use_slope):
                    s["above_cutoff_lambda_min_m-1"] = min(s["above_cutoff_lambda_min_m-1"], float(lam[use_slope].min()))
                    s["above_cutoff_lambda_max_m-1"] = max(s["above_cutoff_lambda_max_m-1"], float(lam[use_slope].max()))
                s["above_cutoff_lambda_and_temperature_in_table_count"] += int(np.count_nonzero(
                    use_slope & (lam >= TABLE_LAMBDA[0]) & (lam <= TABLE_LAMBDA[1]) &
                    (tair >= TABLE_TEMP[0]) & (tair <= TABLE_TEMP[1])))
                s["above_cutoff_temperature_below_180_count"] += int(np.count_nonzero(use_slope & (tair < 180.)))
                s["above_cutoff_temperature_above_300_count"] += int(np.count_nonzero(use_slope & (tair > 300.)))
                s["lambda_samples_by_hour"].append({
                    "time": time_text,
                    "grid_q_lambda_min_m-1": float(lam[active].min()) if np.any(active) else None,
                    "grid_q_lambda_max_m-1": float(lam[active].max()) if np.any(active) else None,
                    "cf_recomputed_lambda_min_m-1": float(lam_cf[active].min()) if np.any(active) else None,
                    "cf_recomputed_lambda_max_m-1": float(lam_cf[active].max()) if np.any(active) else None,
                    "above_cutoff_grid_q_lambda_min_m-1": float(lam[use_slope].min()) if np.any(use_slope) else None,
                    "above_cutoff_grid_q_lambda_max_m-1": float(lam[use_slope].max()) if np.any(use_slope) else None,
                    "positive_q_min_kgkg": float(q[active].min()) if np.any(active) else None,
                    "positive_q_max_kgkg": float(q[active].max()) if np.any(active) else None,
                    "positive_temperature_min_K": float(tair[active].min()) if np.any(active) else None,
                    "positive_temperature_max_K": float(tair[active].max()) if np.any(active) else None,
                    "positive_count": int(np.count_nonzero(active)),
                    "positive_q_below_cutoff_count": int(np.count_nonzero((q > 0.) & (q <= Q_CUTOFF))),
                    "positive_lambda_below_300_count": int(np.count_nonzero(active & (lam < 300.))),
                    "positive_temperature_outside_180_300_count": int(np.count_nonzero(
                        active & ((tair < 180.) | (tair > 300.))))})
                field_shapes[spec["var"]] = list(q.shape)

    after = hash_inputs(workspace, case, source_root, files)
    unchanged = before == after
    if sha256(Path(__file__).resolve()) != script_hash:
        raise RuntimeError('Audit runner changed during execution')
    # Convert infinities from absent-value sentinels into JSON nulls.
    def clean(o):
        if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list): return [clean(v) for v in o]
        if isinstance(o, float) and not math.isfinite(o): return None
        return o

    result = {
        "status": "PASS_READ_ONLY_AUDIT" if unchanged else "FAIL_INPUT_CHANGED_DURING_AUDIT",
        "purpose": "Post-sedimentation returned-grid-q reconstruction for frozen UDM graupel/hail optics axis coverage; not an exact process-time lambda export or production table validation.",
        "time_sampling": {"kind": "hourly WRF history snapshots only", "count": len(files), "times": all_times,
                          "does_not_resolve": "within-hour microphysics states or every radiation call"},
        "case": {"path_relative_to_workspace": str(case.relative_to(workspace)), "mp_physics": 27,
                 "ra_lw_sw_physics": 4, "use_mp_re": 1, "USE_THETA_M": 1,
                 "all_numeric_output_finite": True,
                 "finite_status_source": "preserved ra4-24h-summary.json and 24h-comparison-receipt.json; selected audit fields additionally checked directly",
                 "field_shape_without_time": field_shapes,
                 "domain_spacing": domain_spacing,
                 "mpi_ranks_completed": ra4_receipt.get("mpi_ranks_completed"),
                 "observed_history_records": ra4_receipt.get("expected_and_observed_hourly_history_records")},
        "formula": {
            "pressure": "P_total = P + PB (Pa), exactly the source expression in start_em.F for ALT. P_HYD is a separate hydrostatic diagnostic and is not substituted; its max absolute difference from P+PB is recorded.",
            "wrf_ALT": "(Rd/P0)*(Tpert+300)*(P_total/P0)**cvpm because USE_THETA_M=1; cvpm=-(Cp-Rd)/Cp",
            "rho_kg_m-3": "(1+QVAPOR)/ALT, matching module_big_step_utilities_em.F; reconstructed from float32 histories, not bitwise native density",
            "temperature_K": "th_phy=(Tpert+300)/(1+(Rv/Rd)*QVAPOR), then T=th_phy*(P_total/P0)**(Rd/Cp), matching WRF theta_m/Exner conversion",
            "lambda_m-1": "if q_grid <= 1e-9 kg/kg use 20000; else min((pi*rho_particle*N0/(q_grid*rho_air))**0.25,20000)",
            "species": SPECIES,
            "cutoff_kg_kg": Q_CUTOFF,
            "table_axes": {"lambda_m-1": list(TABLE_LAMBDA), "temperature_K": list(TABLE_TEMP)},
            "main_q_semantics": "Uses returned grid-mean q. UDM process code divides q by cldf when cldf>0 before slope calls; that in-cloud process slope is not reconstructed here.",
            "secondary_variant": "cf_recomputed_lambda uses a post-state transcription of cldf_diag and q_grid/CF when CF>0; CF=0 leaves q unchanged. It is a separate sensitivity diagnostic, not actual last-used subcycle CF.",
            "CF_detail": "cldf_diag uses QCLOUD/QICE and UDM's source-hardcoded internal dxmeter=10000 m, independent of the recorded nominal domain DX/DY; its thresholds/clamps and CF=1 above highest positive QCLOUD or QICE follow the current UDM initialization/call behavior."
        },
        "pressure_diagnostic": {"max_abs_PplusPB_minus_P_HYD_Pa": p_hyd_absdiff_max},
        "udm_q_cutoff_lambda_reconstruction": stats,
        "post_state_cf_recomputed_lambda_by_hour": {n: s["lambda_samples_by_hour"] for n, s in stats.items()},
        "recomputed_cf_category_counts": cf_counts,
        "warm_hail": warmhail,
        "provenance": {"hashes_before": before, "hashes_after": after,
                       "audit_runner_sha256": script_hash,
                       "all_inputs_unchanged": unchanged,
                       "sources_are_isolated_runtime_tree": str(source_root.relative_to(workspace)),
                       "source_sha256s": {k: v["sha256"] for k, v in before.items()
                                          if k.startswith(str(source_root.relative_to(workspace)) + "/")},
                       "software": {"python": __import__("platform").python_version(),
                                    "numpy": np.__version__, "netCDF4": netCDF4.__version__}},
        "limitations": ["No RA37 full forecast was completed; this is RA4 history coverage only.",
                        "Hourly snapshots are not a continuous-time or every-radiation-call census.",
                        "Reconstructed lambda uses returned grid q and output-reconstructed air density; it is not the UDM in-cloud process slope.",
                        "Homogeneous solid-ice Mie material/density assumptions in experimental optics are not validated by this coverage audit."]
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(clean(result), indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "output": str(out), "times": len(all_times),
                      "species": {n: {k: stats[n][k] for k in ("positive_count", "positive_below_q_cutoff_count",
                          "positive_above_q_cutoff_count", "above_cutoff_lambda_min_m-1",
                          "above_cutoff_lambda_max_m-1", "above_cutoff_lambda_and_temperature_in_table_count",
                          "positive_q_min_kgkg", "positive_q_max_kgkg", "positive_lambda_min_m-1",
                          "positive_lambda_max_m-1", "positive_temperature_min_K", "positive_temperature_max_K",
                          "lambda_below_300_count", "temperature_above_300_count")}
                                  for n in SPECIES}, "warm_hail": warmhail,
                      "input_unchanged": unchanged}, indent=2))
    if not unchanged:
        raise SystemExit("Input hash changed during audit")


if __name__ == "__main__":
    main()
