#!/usr/bin/env python3
"""Compare preserved Jan-2000 WRF hourly radiation accumulators to SURFRAD."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
PAIR = WORK / "build/udm-alternate-jan2000-data/paired-forecast-v2"
OBS_CSV = HERE / "hourly_observations.csv"
OBS_JSON = HERE / "verified_observations.json"
PLAN = PAIR / "pair-plan.json"
RECEIPT = PAIR / "run-receipt.json"
ARMS = {"RA4": PAIR / "ra4", "RA37": PAIR / "ra37"}
HISTORY_NAME = "wrfout_d01_2000-01-24_12:00:00"
OBS_HASHES = {
    "gwn00024.dat": "6c3edac924706826370fa7efe415ec555773c9210dea190bd7e49c563ab431c0",
    "gwn00025.dat": "e18725d4a106fdbc666b89e82e02c244990630708671cba406f6569b8694060b",
    "psu00024.dat": "803bb4be1b1606b4fe26d1b1afd4f2c3970052f85826a6bf77b2f3a1cceac383",
    "psu00025.dat": "cc70d05546f14f3b2c79ce646404909d074dd971e67c5cb9934294dcbf8fff72",
    "bon00024.dat": "62d1ad850b1b970e2882cb8b8e9f07c1b98886c9b3ccbfe8a69dd144c881eca4",
    "bon00025.dat": "429d7deeda5ae70d620b0b207bf0f0d341ad49cf8ad0f4ea0d5bc0c7269be795",
}
CELLS = {
    "GWN": {"i": 11, "j": 24, "dist_m": 9734.86318398203},
    "PSU": {"i": 41, "j": 53, "dist_m": 11045.3492229176},
    "BON": {"i": 13, "j": 46, "dist_m": 12262.293896813933},
}
FIELDS = {
    "down_sw": {"observed": "dw_solar", "model_accum": "ACSWDNB", "model_units": "J m-2", "obs_units": "W m-2"},
    "down_lw": {"observed": "dw_ir", "model_accum": "ACLWDNB", "model_units": "J m-2", "obs_units": "W m-2"},
    "net_sw_surface": {"observed": "net_sw", "model_accum": "net_sw", "model_units": "J m-2", "obs_units": "W m-2"},
}
EXPECTED_INPUT_SHA = "0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637"
EXPECTED_OBS_RECEIPT_SHA = "f56901a79d32547507c8ef91d26c3755b411787e5a2c33eb78d99f364d08e4bf"
EXPECTED_OBS_CSV_SHA = "69fb3a088ff803b08273bfeb3f9c7c91bd0ed99e93df2672a12d57f7e3f05067"
EXPECTED_HISTORY_SHA = {
    "RA4": "edf0cfbf4efeecbbf69e979c8f4fc21a19a436f4329a3e11330a2c569ea0bcc4",
    "RA37": "e3fa7be56062c640e52f66c73aaa0bd798d56f0809c1d4501e3b4a0c9c227e4c",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def nc_times(ds: Dataset) -> list[str]:
    raw = ds.variables["Times"][:]
    result = []
    for row in raw:
        result.append(b"".join(row.tolist()).decode("ascii").strip())
    return result


def validate_hourly_times(times: list[str]) -> None:
    if len(times) != len(set(times)):
        raise ValueError("duplicate hourly Times entries")
    parsed = [datetime.strptime(t, "%Y-%m-%d_%H:%M:%S") for t in times]
    if any(parsed[k] - parsed[k-1] != timedelta(hours=1) for k in range(1, len(parsed))):
        raise ValueError("history Times entries must be contiguous hourly endpoints")


def mean_from_accumulator_delta(previous_j_m2: float, current_j_m2: float, seconds: float = 3600.0) -> float:
    if not all(math.isfinite(x) for x in (previous_j_m2, current_j_m2, seconds)) or seconds <= 0:
        raise ValueError("invalid accumulator/duration")
    return (current_j_m2 - previous_j_m2) / seconds


def offline_fixture_checks() -> dict:
    """Pure in-memory tests for the accumulator unit conversion and time-grid gates."""
    synthetic_flux, initial_accum = 123.0, 4_000_000.0
    converted = mean_from_accumulator_delta(initial_accum, initial_accum + synthetic_flux*3600.0)
    if converted != synthetic_flux:
        raise AssertionError(f"one-hour accumulator conversion yielded {converted}, expected {synthetic_flux}")
    valid = ["2000-01-24_12:00:00", "2000-01-24_13:00:00", "2000-01-24_14:00:00"]
    validate_hourly_times(valid)
    failures = {}
    for label, bad in (("gap", [valid[0], valid[2]]), ("repeat", [valid[0], valid[1], valid[1]])):
        try:
            validate_hourly_times(bad)
        except ValueError:
            failures[label] = "rejected"
        else:
            raise AssertionError(f"offline fixture failed to reject {label} Times")
    return {"status": "PASS", "synthetic_flux_W_m-2": synthetic_flux,
            "synthetic_accumulator_delta_J_m-2": synthetic_flux*3600.0,
            "derived_hourly_mean_W_m-2": converted, "gap_times": failures["gap"],
            "repeated_times": failures["repeat"], "engine_executed": False}


def load_observations() -> dict[tuple[str, str], dict[str, float]]:
    with OBS_CSV.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 432:
        raise ValueError(f"expected 432 hourly observation rows, got {len(rows)}")
    out = {}
    for row in rows:
        if row["complete"] != "True" or int(row["records_present"]) != 20 or int(row["qc0_usable"]) != 20:
            raise ValueError("cannot score an incomplete or non-QC0 observation hour")
        key = row["station"], row["hour_end_utc"]
        out[(row["station"], row["channel"] + ":" + row["hour_end_utc"])] = {
            "mean": float(row["mean_flux_W_m-2"]), "energy": float(row["energy_J_m-2"]),
            "negatives_retained": int(row["negative_qc0_samples_retained"]),
        }
    # NOAA net solar uses component consistency; derive hourly net directly from simultaneous global/upwelling means.
    for station in CELLS:
        for end in (datetime(2000,1,24,12)+timedelta(hours=h) for h in range(1,25)):
            ts = end.isoformat()+"Z"
            down = out[(station, "dw_solar:"+ts)]
            up = out[(station, "uw_solar:"+ts)]
            out[(station, "net_sw:"+ts)] = {"mean": down["mean"]-up["mean"],
                                              "energy": down["energy"]-up["energy"],
                                              "negatives_retained": down["negatives_retained"]+up["negatives_retained"]}
    return out


def load_history(arm: str) -> tuple[Path, list[str], dict[str, np.ndarray], dict]:
    path = ARMS[arm] / HISTORY_NAME
    if not path.is_file():
        raise FileNotFoundError(path)
    if sha256(path) != EXPECTED_HISTORY_SHA[arm]:
        raise ValueError(f"{arm}: history SHA does not match the reviewed frozen output")
    with Dataset(path) as ds:
        times = nc_times(ds)
        validate_hourly_times(times)
        if not times or times[0] != "2000-01-24_12:00:00":
            raise ValueError(f"{arm}: wrong first history time")
        if len(ds.dimensions["south_north"]) != 60 or len(ds.dimensions["west_east"]) != 73:
            raise ValueError(f"{arm}: wrong horizontal grid shape")
        required = ("ACSWDNB", "ACLWDNB", "ACSWUPB")
        arrays = {}
        units = {}
        for name in required:
            if name not in ds.variables:
                raise ValueError(f"{arm}: missing {name}")
            v = ds.variables[name]
            units[name] = getattr(v, "units", None)
            expected_units = "J m-2"
            if units[name] != expected_units:
                raise ValueError(f"{arm}: {name} units {units[name]!r} != {expected_units}")
            data = np.ma.asarray(v[:])
            if np.ma.getmaskarray(data).any():
                raise ValueError(f"{arm}: masked/fill values in {name}")
            arr = np.asarray(data, dtype=np.float64)
            if arr.shape != (len(times), 60, 73) or not np.isfinite(arr).all():
                raise ValueError(f"{arm}: bad shape/nonfinite {name}: {arr.shape}")
            arrays[name] = arr
        attrs = {k: str(ds.getncattr(k)) for k in ("DX", "DY")}
    return path, times, arrays, {"units": units, "attrs": attrs}


def metric(observed: list[float], modeled: list[float]) -> dict:
    if len(observed) != len(modeled) or not observed:
        raise ValueError("empty/mismatched metric samples")
    errors = np.asarray(modeled, dtype=np.float64) - np.asarray(observed, dtype=np.float64)
    return {"n": int(errors.size), "bias_model_minus_obs_W_m-2": float(errors.mean()),
            "MAE_W_m-2": float(np.abs(errors).mean()), "RMSE_W_m-2": float(np.sqrt(np.mean(errors**2))),
            "min_error_W_m-2": float(errors.min()), "max_error_W_m-2": float(errors.max())}


def main() -> int:
    fixture = offline_fixture_checks()
    obs_receipt = json.loads(OBS_JSON.read_text())
    if sha256(OBS_JSON) != EXPECTED_OBS_RECEIPT_SHA:
        raise ValueError("verified observation receipt SHA mismatch")
    if sha256(OBS_CSV) != EXPECTED_OBS_CSV_SHA:
        raise ValueError("hourly observation CSV SHA mismatch")
    if obs_receipt["status"] != "OBSERVATIONS_VERIFIED_NO_MODEL_COMPARISON":
        raise ValueError("observation parser receipt is not a verified no-model dataset")
    if obs_receipt["grid_match"]["input_sha256"] != EXPECTED_INPUT_SHA:
        raise ValueError("observation grid-match receipt has unexpected input hash")
    raw_paths = sorted((HERE/"raw").glob("*.dat"))
    if {p.name for p in raw_paths} != set(OBS_HASHES):
        raise ValueError("observation raw directory must contain exactly the six pinned daily files")
    for p in raw_paths:
        if sha256(p) != OBS_HASHES[p.name]:
            raise ValueError(f"raw observation changed: {p.name}")
    plan, run = json.loads(PLAN.read_text()), json.loads(RECEIPT.read_text())
    if plan["real_outputs"]["wrfinput_sha256"] != EXPECTED_INPUT_SHA:
        raise ValueError("forecast pair initialized from a different wrfinput")
    if plan["common_case_settings"]["time_step_seconds"] != 60 or plan["common_case_settings"]["history_interval_minutes"] != 60:
        raise ValueError("expected 60s timestep and hourly history")
    if plan["common_case_settings"]["start"] != "2000-01-24_12:00:00":
        raise ValueError("unexpected model start time")
    if run["arms"]["ra4"]["status"] != "FORECAST_PASS" or run["arms"]["ra37"]["status"] != "FORECAST_FAILED":
        raise ValueError("run statuses differ from the documented RA4-full/RA37-partial case")
    observations = load_observations()
    input_paths = [ARMS[arm]/"wrfinput_d01" for arm in ("RA4", "RA37")]
    input_paths += [ARMS[arm]/"wrfbdy_d01" for arm in ("RA4", "RA37")]
    for p in input_paths[:2]:
        if sha256(p) != EXPECTED_INPUT_SHA:
            raise ValueError(f"arm wrfinput SHA mismatch: {p}")
    if any(sha256(p) != plan["real_outputs"]["wrfbdy_sha256"] for p in input_paths[2:]):
        raise ValueError("arm boundary files differ from the planned pinned input")
    integrity_paths = [OBS_JSON, OBS_CSV, PLAN, RECEIPT, *raw_paths,
                       ARMS["RA4"]/HISTORY_NAME, ARMS["RA37"]/HISTORY_NAME,
                       *input_paths]
    integrity_before = {str(p): sha256(p) for p in integrity_paths}
    model, hashes = {}, {}
    time_common = ["2000-01-24_12:00:00", "2000-01-24_13:00:00", "2000-01-24_14:00:00"]
    for arm in ("RA4", "RA37"):
        path, times, arrays, metadata = load_history(arm)
        model[arm] = (times, arrays)
        hashes[arm] = {"history_path": str(path), "history_sha256": sha256(path),
                       "history_bytes": path.stat().st_size, "times": times,
                       "units": metadata["units"], "DX": metadata["attrs"]["DX"], "DY": metadata["attrs"]["DY"],
                       "run_status": run["arms"][arm.lower()]["status"],
                       "returncode": run["arms"][arm.lower()]["returncode"],
                       "run_log_sha256": run["arms"][arm.lower()]["log"]["sha256"]}
    if model["RA4"][0] != [f"{datetime(2000,1,24,12)+timedelta(hours=h):%Y-%m-%d_%H:%M:%S}" for h in range(25)]:
        raise ValueError("RA4 does not have exactly 25 hourly outputs from 12Z through next-day 12Z")
    if model["RA37"][0] != time_common:
        raise ValueError(f"RA37 common-history scope is not exactly 12,13,14: {model['RA37'][0]}")

    station_details = obs_receipt["grid_match"]["stations"]
    scored = {arm: {} for arm in ("RA4", "RA37")}
    model_means, raw_rows = {}, []
    for arm in ("RA4", "RA37"):
        times, arrays = model[arm]
        ninterval = len(times)-1
        for station, cell in CELLS.items():
            i,j = cell["i"],cell["j"]
            actual_cell = station_details[station]
            if actual_cell["nearest_cell_i_j_1based"] != [i,j]:
                raise ValueError(f"stored cell differs for {station}")
            obs_by_var, mod_by_var = {k:[] for k in FIELDS}, {k:[] for k in FIELDS}
            interval_results = []
            for k in range(1,len(times)):
                endstr=times[k].replace("_","T")+"Z"
                startstr=times[k-1].replace("_","T")+"Z"
                obs={}
                for var, spec in FIELDS.items():
                    if var == "net_sw_surface":
                        obsmean=observations[(station,"net_sw:"+endstr)]["mean"]
                        energy=float((arrays["ACSWDNB"][k,j-1,i-1]-arrays["ACSWDNB"][k-1,j-1,i-1])-
                                     (arrays["ACSWUPB"][k,j-1,i-1]-arrays["ACSWUPB"][k-1,j-1,i-1]))
                    else:
                        obsmean=observations[(station,spec["observed"]+":"+endstr)]["mean"]
                        energy=float(arrays[spec["model_accum"]][k,j-1,i-1]-arrays[spec["model_accum"]][k-1,j-1,i-1])
                    modmean=mean_from_accumulator_delta(0.0, energy, 3600.0)
                    obs_by_var[var].append(obsmean); mod_by_var[var].append(modmean)
                    interval_results.append({"station":station,"arm":arm,"variable":var,"interval_start_utc":startstr,
                                             "interval_end_utc":endstr,"obs_mean_W_m-2":obsmean,
                                             "obs_energy_J_m-2":obsmean*3600.0,"model_accumulator_delta_J_m-2":energy,
                                             "model_mean_W_m-2":modmean,"bias_model_minus_obs_W_m-2":modmean-obsmean,
                                             "obs_source": "SURFRAD 20 QC0 period-end means × 180 s"})
            for var in FIELDS:
                scored[arm].setdefault(station,{})[var]=metric(obs_by_var[var],mod_by_var[var])
                model_means[(arm,station,var)]=mod_by_var[var]
            raw_rows.extend(interval_results)

    paired = {}
    for station in CELLS:
        paired[station] = {}
        for var in FIELDS:
            # Same two hours; difference of model means only, not an accuracy statistic.
            paired[station][var] = {"n_intervals":2,
                "RA37_minus_RA4_mean_W_m-2": float(np.mean(np.array(model_means[("RA37",station,var)])-
                                                             np.array(model_means[("RA4",station,var)][:2]))),
                "RA4_common_2h": metric([observations[(station, ("dw_solar" if var=="down_sw" else "dw_ir" if var=="down_lw" else "net_sw")+":"+t.replace("_","T")+"Z")]["mean"] for t in model["RA37"][0][1:]],
                                        model_means[("RA4",station,var)][:2]),
                "RA37_common_2h": metric([observations[(station, ("dw_solar" if var=="down_sw" else "dw_ir" if var=="down_lw" else "net_sw")+":"+t.replace("_","T")+"Z")]["mean"] for t in model["RA37"][0][1:]],
                                         model_means[("RA37",station,var)])}
    integrity_after = {str(p): sha256(p) for p in integrity_paths}
    if integrity_after != integrity_before:
        raise RuntimeError("an observation/model input changed during read-only analysis")
    with (HERE/"model_hourly_comparison.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(raw_rows[0]));writer.writeheader();writer.writerows(raw_rows)
    # Inputs and executable hashes from the exact forecast pair plan.
    arms_pin={}
    for arm in ("ra4","ra37"):
        a=plan["arms"][arm]
        arms_pin[arm]={key:a.get(key) for key in ("wrf_exe_sha256","wrfinput_sha256","wrfbdy_sha256","namelist_sha256","mode","ra_lw","ra_sw")}
    result={"status":"OBSERVATION_COMPARISON_SCOPED_TO_AVAILABLE_HISTORIES",
            "claim_limit":"One-day, three-site point-to-grid comparison. RA4 covers 24 hourly intervals; RA37 covers only 12:00,13:00,14:00 UTC outputs (two intervals) before the recorded forecast failure. The 2-hour paired differences do not establish general forecast skill or a winner.",
            "method":{"observed_values":"NOAA SURFRAD pre-2009 3-minute one-second-sample means; end-time stamped UTC, QC0 only; 20 records per complete hourly bin.",
                       "model_values":"hourly increment in WRF cumulative radiative energy (J m-2) divided by 3600 s; not instantaneous SWDOWN/GLW.",
                       "model_accumulation_source":"WRF Registry declares AC* radiation accumulators J m-2; radiation driver accumulates flux*DT each dynamics timestep; namelist output BUCKET_J=-1 and source derives bucketf_opt=0, so no bucket rollover applies.",
                       "model_timestep_s":60,"radiation_timestep_min":10,"hourly_output_min":60,
                       "variables":{"down_sw":"ACSWDNB vs SURFRAD dw_solar","down_lw":"ACLWDNB vs SURFRAD dw_ir","net_sw_surface":"(ACSWDNB−ACSWUPB) vs (dw_solar−uw_solar); both are same-window surface down-minus-up budgets."}},
            "observation_provenance":{"directory":str(HERE),"verified_receipt_sha256":sha256(OBS_JSON),"hourly_csv_sha256":sha256(OBS_CSV),"raw_sha256":OBS_HASHES},
            "analysis_script":{"path":"compare_wrf_outputs.py","sha256":sha256(Path(__file__).resolve()),"python":sys.version.split()[0]},
            "offline_fixture_checks":fixture,
            "immutable_inputs_sha256_before_after":{"same":True,"sha256":integrity_after},
            "grid":{"input_sha256":EXPECTED_INPUT_SHA,"domain":[73,60],"spacing_m":[30000,30000],"cells":CELLS},
            "model_provenance":{"pair_plan_path":str(PLAN),"pair_plan_sha256":sha256(PLAN),"run_receipt_path":str(RECEIPT),"run_receipt_sha256":sha256(RECEIPT),"arms":arms_pin,"histories":hashes},
            "scores_all_available_intervals":scored,"scores_common_two_hours_and_pair_difference":paired,
            "csv":"model_hourly_comparison.csv","csv_sha256":sha256(HERE/"model_hourly_comparison.csv")}
    (HERE/"model_observation_comparison.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":result["status"],"scores_all_available_intervals":scored,"scores_common_two_hours_and_pair_difference":paired,"csv_sha256":result["csv_sha256"]},indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
