#!/usr/bin/env python3
"""Run the opt-in paired-seed physics audit without changing WRF state.

For each supplied UDM control/mixed initial state this runs RRTMGP37 once
with the audit disabled and once enabled, then checks that every history
array is byte-identical. Audit outputs and all-call raw captures are retained
under the new work directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

import test_surface_scm
import test_udm_scm
import test_cloud_scm
from compare_column_replay import compare as compare_replay_results, read_result
import test_column_replay

WRF_ROOT = test_surface_scm.WRF_ROOT
VALIDATOR = test_surface_scm.TEMPLATE.parent / "validate_scm.py"
ANALYZER = test_surface_scm.TEMPLATE.parent / "analyse_udm_physics_audit.py"
SUCCESS = "SUCCESS COMPLETE WRF"
ACTIVE_ROOT: Path | None = None
WRF_EXE: Path = WRF_ROOT / "main/wrf.exe"
IDEAL_EXE: Path = WRF_ROOT / "main/ideal.exe"
DATA_DIR: Path = test_udm_scm.DATA_DIR
REFERENCE_EXE: Path | None = None
NETCDF_LIB_DIR: Path | None = None


def fail(message: str) -> None:
    raise RuntimeError(message)


def runtime_environment() -> dict[str, str]:
    env = os.environ.copy()
    if NETCDF_LIB_DIR is not None and NETCDF_LIB_DIR.is_dir():
        old_ld = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = os.pathsep.join(
            [str(NETCDF_LIB_DIR)] + ([old_ld] if old_ld else []))
    return env


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def make_seed(root: Path, name: str, mixed: bool) -> dict[str, Any]:
    case = root / f"seed-{name}"
    test_surface_scm.prepare_case(case, 0)
    base = test_cloud_scm.original_lsm2_namelist()
    (case / "namelist.input").write_text(test_udm_scm.make_namelist(base, 4, 4, 1), encoding="utf-8")
    ideal = subprocess.run([str(IDEAL_EXE)], cwd=case, env=runtime_environment(), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, check=False)
    (case / "ideal.log").write_text(ideal.stdout, encoding="utf-8")
    if ideal.returncode != 0 or not (case / "wrfinput_d01").is_file():
        fail(f"{case}: ideal.exe failed while preparing a state")
    fixture = test_udm_scm.write_initial_udm_fixture(case / "wrfinput_d01", mixed)
    return {"path": case, "wrfinput": case / "wrfinput_d01", "baseline_history": [],
            "fixture": fixture}


def load_seed(path: Path | None, root: Path, name: str, mixed: bool) -> dict[str, Any]:
    if path is None:
        return make_seed(root, name, mixed)
    seed = test_udm_scm.seed_from_directory(path.expanduser().resolve(), name)
    seed["fixture"] = {"source": "supplied-existing-initial-state"}
    return seed


def make_case(seed: dict[str, Any], case: Path, minutes: int, option: int) -> None:
    test_surface_scm.prepare_case(case, 0)
    base_namelist = (seed["path"] / "namelist.input").read_text(encoding="utf-8")
    namelist = test_udm_scm.make_namelist(base_namelist, option, option, minutes)
    namelist = test_udm_scm.replace_assignment(
        namelist, "rrtmgp_data_path", f"'{DATA_DIR}'", required=True)
    (case / "namelist.input").write_text(namelist, encoding="utf-8")
    shutil.copy2(seed["wrfinput"], case / "wrfinput_d01")


def validate_run(case: Path, option: int) -> dict[str, Any]:
    log = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")
    if SUCCESS not in log:
        fail(f"{case}: missing normal WRF success marker")
    paths = sorted(case.glob("wrfout_d01_*"))
    if len(paths) != 1:
        fail(f"{case}: expected one history file, got {len(paths)}")
    result = subprocess.run([sys.executable, str(VALIDATOR), str(case), "--expected-options", str(option)],
                            cwd=WRF_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, check=False)
    if result.returncode:
        fail(f"{case}: validate_scm failed: {result.stdout[-2500:]}")
    validation = json.loads(result.stdout)[str(case)]
    with netCDF4.Dataset(paths[0]) as ds:
        times_raw = np.asarray(ds.variables["Times"][:])
        times = [b"".join(row).decode("ascii") for row in times_raw]
        stamps = [datetime.strptime(x, "%Y-%m-%d_%H:%M:%S") for x in times]
        if len(stamps) < 2:
            fail(f"{case}: expected at least two history timestamps")
        deltas = [(b-a).total_seconds() for a, b in zip(stamps, stamps[1:])]
        if any(x != 10 for x in deltas):
            fail(f"{case}: expected 10 s history spacing, got {deltas}")
        arrays = {name: np.asarray(var[:]).copy() for name, var in ds.variables.items()}
    return {"case": str(case), "history_file": str(paths[0]), "validation": validation,
            "time_records": len(stamps), "time_deltas_seconds": deltas, "arrays": arrays}


AUDIT_HISTORY_METRICS = {
    ("SW", "SURFACE_DOWN"): "SWDNB",
    ("SW", "TOA_UP"): "SWUPT",
    ("SW", "SW_NET"): "GSW",
    ("SW", "SW_DIRECT"): "SWDDIR",
    ("LW", "SURFACE_DOWN"): "GLW",
    ("LW", "TOA_UP"): "LWUPT",
}


def _time_strings(run: dict[str, Any]) -> list[datetime]:
    values = run["arrays"].get("Times")
    if values is None:
        fail(f"{run['case']}: history omitted Times")
    result = []
    for row in values:
        rendered = b"".join(row).decode("ascii") if getattr(row, "dtype", None) is not None else str(row)
        result.append(datetime.strptime(rendered, "%Y-%m-%d_%H:%M:%S"))
    return result


def history_metric(run: dict[str, Any], name: str, source_seconds: float) -> tuple[float, str]:
    wanted = _time_strings(run)[0] + timedelta(seconds=float(source_seconds) + 10.0)
    times = _time_strings(run)
    distance = [abs((stamp-wanted).total_seconds()) for stamp in times]
    index = int(np.argmin(distance))
    if distance[index] > 1.e-3:
        fail(f"{run['case']}: no history timestamp at source_seconds+10={wanted}")
    if name not in run["arrays"]:
        fail(f"{run['case']}: history missing audit metric variable {name}")
    arr = run["arrays"][name]
    if arr.shape[0] <= index:
        fail(f"{run['case']}: {name} lacks record index {index}")
    # i=j=0 CSV records contain the actual tile spatial mean.
    value = np.asarray(arr[index], dtype=np.float64)
    return float(np.mean(value)), times[index].strftime("%Y-%m-%d_%H:%M:%S")


def read_audit_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"phase", "domain", "step", "source_seconds", "i", "j", "metric",
                    "value37", "value4", "sample_count", "mean37", "mean4", "sd_delta"}
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            missing = required - set(reader.fieldnames or [])
            fail(f"{csv_path}: audit CSV lacks required fields {sorted(missing)}")
        return list(reader)


def validate_audit_history_rows(csv_path: Path, run: dict[str, Any], expected_calls: int) -> dict[str, Any]:
    rows = read_audit_rows(csv_path)
    selected = [r for r in rows if int(r["i"]) == 0 and int(r["j"]) == 0]
    checks = []
    for row in selected:
        phase = row["phase"].upper()
        metric = row["metric"].upper()
        history_name = AUDIT_HISTORY_METRICS.get((phase, metric))
        if history_name is None:
            continue
        seconds = float(row["source_seconds"])
        actual, timestamp = history_metric(run, history_name, seconds)
        audited = float(row["value37"])
        tolerance = 8.0 * np.finfo(np.float32).eps * max(1.0, abs(actual), abs(audited)) + 1.0e-3
        if abs(actual - audited) > tolerance:
            fail(f"{csv_path}: {phase}/{metric} call step={row['step']} at {timestamp}: "
                 f"CSV value37 {audited} != history {history_name} {actual} (tol {tolerance})")
        checks.append({"phase": phase, "metric": metric, "history_variable": history_name,
                       "step": int(row["step"]), "source_seconds": seconds,
                       "history_seconds": seconds + 10.0, "timestamp": timestamp,
                       "value37": audited, "history_value": actual, "tolerance": tolerance})
    expected = {(phase, metric) for phase, metric in AUDIT_HISTORY_METRICS}
    observed = {(item["phase"], item["metric"]) for item in checks}
    missing = sorted(expected - observed)
    if missing:
        fail(f"{csv_path}: no aggregate rows for required history metrics {missing}")
    by_metric: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in checks:
        by_metric.setdefault((item["phase"], item["metric"]), []).append(item)
    for key, items in by_metric.items():
        seconds = sorted(item["source_seconds"] for item in items)
        if len(seconds) != expected_calls or any(b-a != 10.0 for a, b in zip(seconds, seconds[1:])):
            fail(f"{csv_path}: {key} expected {expected_calls} 10-second audit calls, got {seconds}")
    return {"status": "PASS", "aggregate_rows_checked": len(checks), "checks": checks}


def attribution_rows(csv_path: Path, coupled37: dict[str, Any], coupled4: dict[str, Any],
                     expected_calls: int) -> list[dict[str, Any]]:
    rows = [r for r in read_audit_rows(csv_path) if int(r["i"]) == 0 and int(r["j"]) == 0]
    output = []
    for row in rows:
        phase, metric = row["phase"].upper(), row["metric"].upper()
        history_name = AUDIT_HISTORY_METRICS.get((phase, metric))
        if history_name is None:
            continue
        seconds = float(row["source_seconds"])
        radius_code = row.get("radius_mode")
        radius_label = ({"0": "PRODUCTION_GENERIC4_RADIUS", "1": "RRTMG4_NATIVE_RADIUS_COUNTERFACTUAL"}
                        .get((radius_code or "").strip(), radius_code or "PRODUCTION_WRAPPER_RADIUS"))
        hist37, timestamp = history_metric(coupled37, history_name, seconds)
        hist4, _ = history_metric(coupled4, history_name, seconds)
        coupled_delta = hist37 - hist4
        operational_delta = float(row["value37"]) - float(row["value4"])
        ensemble_delta = float(row["mean37"]) - float(row["mean4"])
        output.append({
            "phase": phase, "metric": metric, "history_variable": history_name,
            "engine4_radius_mode": radius_label,
            "step": int(row["step"]), "source_seconds": seconds,
            "post_step_history_seconds": seconds + 10., "history_timestamp": timestamp,
            "coupled_history_37_minus_4": coupled_delta,
            "same_state_operational_37_minus_engine4": operational_delta,
            "same_state_ensemble_mean_37_minus_engine4": ensemble_delta,
            "coupled_minus_operational_residual": coupled_delta - operational_delta,
            "coupled_minus_ensemble_residual": coupled_delta - ensemble_delta,
            "same_state_paired_seed_sd_delta": float(row["sd_delta"]),
        })
    if len(output) != 6 * expected_calls:
        fail(f"{csv_path}: expected {6*expected_calls} mapped per-call flux rows, got {len(output)}")
    return output


def validate_radius_mode(csv_path: Path, native_counterfactual: bool) -> dict[str, Any]:
    rows = read_audit_rows(csv_path)
    if not rows or "radius_mode" not in rows[0]:
        if native_counterfactual:
            fail(f"{csv_path}: native-radius counterfactual was requested but radius_mode is absent")
        return {"status": "UNREPORTED_PRODUCTION_DEFAULT", "radius_mode": None}
    expected = "1" if native_counterfactual else "0"
    observed = sorted({r["radius_mode"].strip() for r in rows})
    if observed != [expected]:
        fail(f"{csv_path}: expected radius_mode={expected}, found {observed}")
    label = "RRTMG4_NATIVE_RADIUS_COUNTERFACTUAL" if native_counterfactual else "PRODUCTION_GENERIC4_RADIUS"
    return {"status": "PASS", "radius_mode_code": int(expected), "radius_mode": label}


def validate_raw_calls(case: Path, expected_calls: int) -> dict[str, Any]:
    raw_dir = case / "capture"
    report: dict[str, Any] = {}
    for phase in ("lw", "sw"):
        paths = sorted(raw_dir.glob(f"{phase}_*.raw"))
        if len(paths) != expected_calls:
            fail(f"{case}: expected {expected_calls} {phase.upper()} raw captures, found {len(paths)}")
        per_call = []
        for index, path in enumerate(paths, 1):
            raw_phase, i, j, values = test_column_replay.read_raw(path)
            if raw_phase != phase.upper() or (i, j) != (1, 1):
                fail(f"{path}: unexpected raw capture identity {raw_phase}/{i}/{j}")
            required = ("UDM_CF_USED", "UDM_CF_SOURCE_STEP", "UDM_CF_TOP", "RADIATION_STEP", "CF")
            missing = [key for key in required if key not in values]
            if missing:
                fail(f"{path}: missing UDM audit evidence {missing}")
            used = np.asarray(values["UDM_CF_USED"], dtype=np.float64)
            cf = np.asarray(values["CF"], dtype=np.float64)
            if used.shape != cf.shape:
                fail(f"{path}: UDM_CF_USED and radiation CF dimensions differ")
            source_step = float(values["UDM_CF_SOURCE_STEP"][0])
            source_top = float(values["UDM_CF_TOP"][0])
            radiation_step = float(values["RADIATION_STEP"][0])
            if index == 1:
                if not np.all(used == -1.0) or source_step != -1.0 or source_top != -1.0:
                    fail(f"{path}: first-use UDM CF, step and top must all be not-called sentinels")
            else:
                if (not np.isfinite(used).all() or np.any((used < -1.0) | (used > 1.0)) or
                    np.any((used == -1.0) & (cf > 0.0))):
                    fail(f"{path}: later UDM_CF_USED must be valid for cloudy layers; -1 is allowed only when CF is clear")
                if not np.any(used >= 0.0):
                    fail(f"{path}: later UDM_CF_USED contains no valid prior microphysics CF")
                if (not np.isfinite(source_top) or source_top != np.floor(source_top) or
                    source_top < 0 or source_top > used.size):
                    fail(f"{path}: later UDM_CF_TOP must be an exact extent in [0,native_layers]")
                if source_step < 0.0 or source_step >= radiation_step:
                    fail(f"{path}: source step {source_step} must precede radiation step {radiation_step}")
            per_call.append({"file": path.name, "radiation_step": radiation_step,
                             "udm_cf_source_step": source_step,
                             "udm_cf_top": source_top,
                             "udm_cf_diagnosed_layers": max(0, int(source_top)),
                             "udm_cf_extent_unknown_layers": int(used.size - max(0, int(source_top))),
                             "used_min": float(np.min(used)), "used_max": float(np.max(used)),
                             "first_use_sentinel": bool(index == 1)})
        report[phase.upper()] = {"count": len(paths), "calls": per_call}
    report["interpretation"] = (
        "Captured arrays include the uppermost KTOP layer; CF or path zero there is not evidence that the whole column is clear."
    )
    return report


def replay_all_captures(case: Path, data_dir: Path, reference_exe: Path,
                        expected_calls: int) -> dict[str, Any]:
    capture = case / "capture"
    raw_paths = sorted(capture.glob("*.raw"))
    replay_rows = []
    for raw_path in raw_paths:
        base = raw_path.with_suffix("")
        phase = raw_path.name.split("_")[0].upper()
        input_path, production_path = base.with_suffix(".input"), base.with_suffix(".result")
        if not input_path.is_file() or not production_path.is_file():
            fail(f"{raw_path}: capture-all group is incomplete")
        ref_path = base.with_suffix(".reference.result")
        proc = subprocess.run([str(reference_exe), str(data_dir), str(input_path), str(ref_path)],
                              cwd=case, env=runtime_environment(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, check=False)
        if proc.returncode != 0 or not ref_path.is_file():
            fail(f"{raw_path}: independent {phase} replay failed: {proc.stdout[-2000:]}")
        result = compare_replay_results(read_result(production_path), read_result(ref_path))
        if not result.get("passed"):
            fail(f"{raw_path}: independent replay failed sections {result.get('failed_sections')}")
        replay_rows.append({"raw": raw_path.name, "phase": phase,
                            "sections_compared": result["sections_compared"], "passed": True})
    if len(replay_rows) != 2 * expected_calls:
        fail(f"{case}: expected {2*expected_calls} total LW/SW raw captures, found {len(replay_rows)}")
    return {"status": "PASS", "capture_count": len(replay_rows), "replays": replay_rows}


def run_case(seed: dict[str, Any], case: Path, minutes: int, *, option: int, audit: bool,
             seeds: int, native_rrtmg4_counterfactual: bool = False) -> dict[str, Any]:
    if audit and option != 37:
        fail("the same-state audit is only defined for RRTMGP option 37")
    make_case(seed, case, minutes, option)
    env = runtime_environment()
    for name in ("WRF_RRTMGP_CAPTURE_DIR", "WRF_RRTMGP_CAPTURE_CALL", "WRF_RRTMGP_CAPTURE_ALL",
                 "WRF_RRTMGP_AUDIT_DIR", "WRF_RRTMGP_AUDIT_SEEDS", "WRF_RRTMGP_AUDIT_NATIVE4"):
        env.pop(name, None)
    env["OMP_NUM_THREADS"] = "1"
    if audit:
        audit_dir = case / "audit"
        raw_dir = case / "capture"
        audit_dir.mkdir()
        raw_dir.mkdir()
        env["WRF_RRTMGP_AUDIT_DIR"] = str(audit_dir)
        env["WRF_RRTMGP_AUDIT_SEEDS"] = str(seeds)
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(raw_dir)
        env["WRF_RRTMGP_CAPTURE_ALL"] = "1"
        if native_rrtmg4_counterfactual:
            env["WRF_RRTMGP_AUDIT_NATIVE4"] = "1"
    with (case / "wrf.log").open("w", encoding="utf-8") as stream:
        proc = subprocess.run([str(WRF_EXE)], cwd=case, env=env,
                              stdout=stream, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        tail = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")[-2500:]
        fail(f"{case}: wrf.exe exited {proc.returncode}\n{tail}")
    run = validate_run(case, option)
    run["wrfinput_sha256"] = sha256(case / "wrfinput_d01")
    run["audit_enabled"] = audit
    run["audit_native_rrtmg4_counterfactual"] = bool(audit and native_rrtmg4_counterfactual)
    if audit:
        csv_path = case / "audit/same_state.csv"
        if not csv_path.is_file():
            fail(f"{case}: audit did not create same_state.csv")
        raw = sorted((case / "capture").glob("*.raw"))
        for phase in ("lw", "sw"):
            phase_raw = sorted((case / "capture").glob(f"{phase}_*.raw"))
            if not phase_raw:
                fail(f"{case}: capture-all did not retain {phase.upper()} raw calls")
            for path in phase_raw:
                stem = path.with_suffix("")
                for suffix in (".input", ".result"):
                    if not stem.with_suffix(suffix).is_file():
                        fail(f"{case}: incomplete capture group for {path.name}, missing {suffix}")
        audit_rows = sum(1 for _ in csv_path.open(encoding="utf-8")) - 1
        if audit_rows <= 0:
            fail(f"{case}: same_state.csv has no metric rows")
        run["audit_csv"] = str(csv_path)
        run["audit_rows"] = audit_rows
        run["raw_call_count"] = len(raw)
        run["raw_files"] = [str(p) for p in raw]
    return run


def history_equal(a: dict[str, Any], b: dict[str, Any], label: str) -> dict[str, Any]:
    left, right = a["arrays"], b["arrays"]
    common = sorted(left.keys() & right.keys())
    if not common:
        fail(f"{label}: no common history variables")
    differing = []
    for name in common:
        x, y = left[name], right[name]
        if x.shape != y.shape or x.dtype != y.dtype:
            differing.append(name)
        elif x.dtype.kind in "OUS":
            if not np.array_equal(x, y):
                differing.append(name)
        elif x.tobytes() != y.tobytes():
            differing.append(name)
    if differing:
        fail(f"{label}: audit changed history arrays: {differing[:25]}")
    if len(common) != 211:
        fail(f"{label}: expected all 211 history variables including UDM_CF_TOP, found {len(common)}")
    return {"status": "PASS_BITWISE", "variables": len(common),
            "left_only": sorted(left.keys() - right.keys()), "right_only": sorted(right.keys() - left.keys())}


def compare_prior_37(run: dict[str, Any], prior_dir: Path, seed: dict[str, Any], label: str) -> dict[str, Any]:
    if run["wrfinput_sha256"] != sha256(seed["wrfinput"]):
        fail(f"{label}: current run initial state differs from seed")
    prior_outputs = sorted(prior_dir.glob("wrfout_d01_*"))
    if not prior_outputs:
        fail(f"{prior_dir}: prior RRTMGP37 case has no history file")
    if not (prior_dir / "wrfinput_d01").is_file() or sha256(prior_dir / "wrfinput_d01") != run["wrfinput_sha256"]:
        fail(f"{prior_dir}: prior RRTMGP37 case used a different initial state")
    with netCDF4.Dataset(prior_outputs[-1]) as ds:
        if (int(ds.RA_LW_PHYSICS), int(ds.RA_SW_PHYSICS)) != (37, 37):
            fail(f"{prior_outputs[-1]}: prior comparison is not option 37/37")
        previous = {name: np.asarray(var[:]).copy() for name, var in ds.variables.items()}
    current = run["arrays"]
    common = sorted(current.keys() & previous.keys())
    mismatch = []
    for name in common:
        a, b = current[name], previous[name]
        if a.shape != b.shape or a.dtype != b.dtype:
            mismatch.append(name)
        elif a.dtype.kind in "OUS":
            if not np.array_equal(a, b):
                mismatch.append(name)
        elif a.tobytes() != b.tobytes():
            mismatch.append(name)
    if len(common) < 208:
        fail(f"{label}: expected at least 208 shared variables with prior port, found {len(common)}")
    if mismatch:
        fail(f"{label}: prior port differs in shared history variables {mismatch[:25]}")
    return {"status": "PASS_BITWISE_SHARED", "shared_variables": len(common),
            "history_file": str(prior_outputs[-1])}


def baseline_equal(run: dict[str, Any], seed: dict[str, Any], label: str) -> dict[str, Any]:
    baseline = seed.get("baseline_history", [])
    if not baseline:
        return {"status": "NOT_CHECKED_NO_SUPPLIED_RRTMG4_BASELINE"}
    if run["wrfinput_sha256"] != sha256(seed["wrfinput"]):
        fail(f"{label}: run initial state differs from provided baseline state")
    with netCDF4.Dataset(baseline[-1]) as ds:
        if (int(ds.RA_LW_PHYSICS), int(ds.RA_SW_PHYSICS)) != (4, 4):
            fail(f"{baseline[-1]}: supplied historical output is not RRTMG4/4")
        expected = {name: np.asarray(var[:]).copy() for name, var in ds.variables.items()}
    current = run["arrays"]
    common = sorted(expected.keys() & current.keys())
    mismatch = []
    for name in common:
        a, b = expected[name], current[name]
        if a.shape != b.shape or a.dtype != b.dtype:
            mismatch.append(name)
        elif a.dtype.kind in "OUS":
            if not np.array_equal(a, b):
                mismatch.append(name)
        elif a.tobytes() != b.tobytes():
            mismatch.append(name)
    if mismatch:
        fail(f"{label}: supplied RRTMG4 baseline differs in {mismatch[:25]}")
    return {"status": "PASS_BITWISE", "history_file": str(baseline[-1]), "variables": len(common)}


def main() -> int:
    global ACTIVE_ROOT, WRF_EXE, IDEAL_EXE, DATA_DIR, REFERENCE_EXE, NETCDF_LIB_DIR
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workdir", type=Path, help="new, nonexistent output directory")
    ap.add_argument("--seeds", type=int, default=32, help="paired Monte Carlo seeds (2..8192)")
    ap.add_argument("--run-minutes", type=int, default=1)
    ap.add_argument("--control-state", type=Path,
                    help="existing control case directory with wrfinput_d01; default regenerates SCM state")
    ap.add_argument("--mixed-state", type=Path,
                    help="existing mixed UDM case directory with wrfinput_d01; default regenerates fixture")
    ap.add_argument("--wrf-executable", type=Path, default=WRF_ROOT / "main/wrf.exe")
    ap.add_argument("--ideal-executable", type=Path, default=WRF_ROOT / "main/ideal.exe")
    ap.add_argument("--data-dir", type=Path, default=test_udm_scm.DATA_DIR)
    ap.add_argument("--reference-executable", type=Path,
                    default=WRF_ROOT.parent / "build/replay-reference/reference_column",
                    help="independent V4 replay executable for every captured radiation call")
    ap.add_argument("--netcdf-lib-dir", type=Path,
                    default=WRF_ROOT.parents[1] / "deps/netcdf/lib",
                    help="local NetCDF runtime library directory prepended to LD_LIBRARY_PATH")
    ap.add_argument("--prior-control-37", type=Path,
                    help="optional earlier RRTMGP37 control case for shared-history comparison")
    ap.add_argument("--prior-mixed-37", type=Path,
                    help="optional earlier RRTMGP37 mixed case for shared-history comparison")
    ap.add_argument("--native-rrtmg4-counterfactual", action="store_true",
                    help="audit engine4 with native-radius wrapper flags; production history remains unchanged")
    ap.add_argument("--output-json", type=Path, help="receipt path (default WORKDIR/audit-result.json)")
    args = ap.parse_args()
    if args.seeds < 2 or args.seeds > 8192:
        ap.error("--seeds must be between 2 and 8192")
    if args.run_minutes < 1:
        ap.error("--run-minutes must be positive")
    expected_calls = args.run_minutes * 6
    root = args.workdir.expanduser().resolve()
    if root.exists():
        ap.error(f"refusing existing work directory: {root}")
    if not root.parent.is_dir():
        ap.error(f"work directory parent does not exist: {root.parent}")
    for exe in (args.wrf_executable, args.ideal_executable, args.reference_executable):
        if not exe.is_file() or not os.access(exe, os.X_OK):
            ap.error(f"missing executable: {exe}")
    if not args.data_dir.is_dir():
        ap.error(f"missing coefficient data directory: {args.data_dir}")
    for name in ("rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-sw-g112.nc",
                 "rrtmgp-clouds-lw-bnd.nc", "rrtmgp-clouds-sw-bnd.nc"):
        if not (args.data_dir / name).is_file():
            ap.error(f"missing coefficient file: {args.data_dir / name}")
    root.mkdir()
    ACTIVE_ROOT = root

    # Keep the existing preparation helper on the standard WRF executable
    # paths while permitting callers to select alternate binary locations.
    global WRF_EXE, IDEAL_EXE
    WRF_EXE = args.wrf_executable.expanduser().resolve()
    IDEAL_EXE = args.ideal_executable.expanduser().resolve()
    DATA_DIR = args.data_dir.expanduser().resolve()
    REFERENCE_EXE = args.reference_executable.expanduser().resolve()
    NETCDF_LIB_DIR = args.netcdf_lib_dir.expanduser().resolve()

    native4 = bool(args.native_rrtmg4_counterfactual)
    summary: dict[str, Any] = {"status": "FAIL", "schema": "UDM_PHYSICS_AUDIT_RUN_V1",
        "seeds": args.seeds, "run_minutes": args.run_minutes, "pairs": {},
        "audit_engine4_radius_mode": ("RRTMG4_NATIVE_RADIUS_COUNTERFACTUAL" if native4
                                      else "PRODUCTION_GENERIC4_RADIUS"),
        "audit_engine4_counterfactual_limitations": (
            "Native-radius wrapper flags retain RRTMG4 legacy radius preprocessing; startup background values are not native diagnosed radii."
            if native4 else None),
        "environment": {"wrf_executable": str(args.wrf_executable.resolve()),
                         "wrf_sha256": sha256(args.wrf_executable.resolve()),
                         "ideal_executable": str(args.ideal_executable.resolve()),
                         "reference_executable": str(args.reference_executable.resolve()),
                         "reference_sha256": sha256(args.reference_executable.resolve()),
                         "data_dir": str(args.data_dir.resolve())}}
    for label, seed_path, mixed in (("control", args.control_state, False),
                                    ("mixed", args.mixed_state, True)):
        seed = load_seed(seed_path, root, label, mixed)
        case_root = root / label
        case_root.mkdir()
        off = run_case(seed, case_root / "audit-off", args.run_minutes, option=37,
                       audit=False, seeds=args.seeds)
        on = run_case(seed, case_root / "audit-on", args.run_minutes, option=37,
                      audit=True, seeds=args.seeds,
                      native_rrtmg4_counterfactual=native4)
        if off["wrfinput_sha256"] != on["wrfinput_sha256"]:
            fail(f"{label}: audit OFF/ON initial states differ")
        bitwise = history_equal(off, on, f"{label} audit OFF/ON")
        ra4 = run_case(seed, case_root / "rrtmg4-reference", args.run_minutes, option=4,
                       audit=False, seeds=args.seeds)
        if seed.get("baseline_history"):
            bitwise_baseline = baseline_equal(ra4, seed, f"{label} RRTMG4 baseline preservation")
        else:
            bitwise_baseline = {"status": "NOT_CHECKED_NO_SUPPLIED_RRTMG4_BASELINE"}
        ra4_receipt = {k: v for k, v in ra4.items() if k != "arrays"}
        csv_path = Path(on["audit_csv"])
        radius_mode = validate_radius_mode(csv_path, native4)
        audit_history = validate_audit_history_rows(csv_path, on, expected_calls)
        raw_contract = validate_raw_calls(Path(on["case"]), expected_calls)
        independent_replay = replay_all_captures(Path(on["case"]), DATA_DIR, REFERENCE_EXE, expected_calls)
        attribution = attribution_rows(csv_path, on, ra4, expected_calls)
        prior_path = args.prior_control_37 if label == "control" else args.prior_mixed_37
        prior_check = (compare_prior_37(off, prior_path.expanduser().resolve(), seed,
                                        f"{label} prior RRTMGP37")
                       if prior_path else {"status": "NOT_CHECKED_NO_PRIOR_37_CASE"})
        raw_dir = Path(on["case"]) / "capture"
        analysis_path = case_root / "audit-analysis.json"
        analyzer = subprocess.run([sys.executable, str(ANALYZER), "--csv", on["audit_csv"],
                                   "--raw", str(raw_dir), "--output", str(analysis_path)],
                                  cwd=WRF_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, check=False)
        if analyzer.returncode:
            fail(f"{label}: audit analysis failed: {analyzer.stdout[-2500:]}")
        summary["pairs"][label] = {
            "wrfinput_sha256": off["wrfinput_sha256"], "source_fixture": seed["fixture"],
            "audit_off": {k: v for k, v in off.items() if k != "arrays"},
            "audit_on": {k: v for k, v in on.items() if k != "arrays"},
            "audit_off_on_history": bitwise,
            "rrtmg4_reference": ra4_receipt, "rrtmg4_baseline": bitwise_baseline,
            "prior_port37_shared_history": prior_check,
            "audit_value_vs_history": audit_history,
            "audit_engine4_radius_mode": radius_mode,
            "raw_call_contract": raw_contract,
            "independent_replay": independent_replay,
            "attribution_per_call": attribution,
            "attribution_interpretation": (
                "Residuals are exact differences among coupled history, same-state operational values and seed-ensemble means; "
                "they include feedback/post-processing and do not establish causal attribution. "
                + ("Engine4 values use the native-radius wrapper counterfactual with legacy preprocessing and startup background."
                   if native4 else "Engine4 values use production generic-radius wrapper behavior.")),
            "analysis_json": str(analysis_path), "analyzer_stdout": analyzer.stdout.strip(),
        }
    summary["status"] = "PASS_AUDIT_OBSERVATIONAL; HISTORY_BITWISE; BASELINE_CHECKED_IF_SUPPLIED"
    output = args.output_json.expanduser().resolve() if args.output_json else root / "audit-result.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "receipt": str(output), "pairs": list(summary["pairs"])}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if ACTIVE_ROOT is not None and ACTIVE_ROOT.is_dir():
            (ACTIVE_ROOT / "audit-result.json").write_text(
                json.dumps({"status": "FAIL", "error": str(exc)}, indent=2) + "\n", encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
