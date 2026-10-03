#!/usr/bin/env python3
"""Opt-in paired RA4/RA37 Jan-2000 d01 forecast runner; prepared, not run."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import time
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP")
PREP = ROOT / "build/udm-alternate-jan2000-data/real-preflight"
PIN_FILE = PREP / "preflight-receipt.json"
REAL_RECEIPT = PREP / "run-receipt.json"
RUN_RECEIPT = HERE / "run-receipt.json"
START = datetime(2000, 1, 24, 12)
HOURS = 24
EXPECTED_HISTORY = [(START + timedelta(hours=h)).strftime("%Y-%m-%d_%H:%M:%S") for h in range(25)]
EXPECTED_RESTARTS = {"2000-01-25_00:00:00", "2000-01-25_12:00:00"}
WATER = ("QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP", "QHAIL",
         "QNCCN", "QNCLOUD", "QNRAIN")
EXPECTED_COMMON_INPUT = "0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637"
EXPECTED_COMMON_BDY = "ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4"
REQUIRED_RADIATION = ("SWDNB", "SWUPB", "SWDDIR", "SWDDIF", "GSW",
                      "RTHRATEN", "RTHRATLW", "RTHRATSW",
                      "ACSWDNB", "ACLWDNB", "ACSWUPT", "ACLWUPT")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj, indent=2, sort_keys=True, default=jsonable) + "\n")
    temp.replace(path)


def jsonable(x):
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, bytes):
        return x.decode("utf-8", errors="replace")
    raise TypeError(type(x).__name__)


def decode_row(row) -> str:
    a = np.asarray(row)
    if a.dtype.kind == "S":
        return b"".join(a.tolist()).decode("ascii").rstrip("\x00 ")
    return "".join(str(x) for x in a.tolist()).rstrip("\x00 ")


def pinned_hashes() -> dict[str, str]:
    prep = json.loads(PIN_FILE.read_text())
    observed = {}
    for item in prep["static_files"]:
        p = Path(item["path"])
        if not p.is_file() or (item.get("resolved_target") and str(p.resolve()) != item["resolved_target"]):
            raise RuntimeError(f"pinned source/static asset missing or moved: {p}")
        val = sha(p)
        if val != item["sha256"]:
            raise RuntimeError(f"pinned static hash changed: {p}")
        observed[str(p)] = val
    for item in prep["symlinks"]:
        p = Path(item["path"])
        if not p.is_symlink() or str(p.resolve()) != item["resolved_target"]:
            raise RuntimeError(f"pinned directory/data link moved: {p}")
    if prep["status"] != "PREPARED_NOT_EXECUTED":
        raise RuntimeError("REAL input preparation receipt has unexpected status")
    if json.loads(REAL_RECEIPT.read_text()).get("status") != "REAL_INIT_PASS":
        raise RuntimeError("common REAL initialization receipt is not PASS")
    return observed


def runtime_directory_hashes() -> dict[str, str]:
    root = HERE / "ra4/rrtmgp_data"
    result = {}
    for path in sorted(p for p in root.iterdir() if p.is_file()):
        result[path.name] = sha(path)
    return result


def verify_case(case: Path, mode: str) -> None:
    expected_ra = 4 if mode == "ra4" else 37
    expected_frozen = 0 if mode == "ra4" else 1
    text = (case / "namelist.input").read_text()
    checks = {
        "mp_physics": (r"(?m)^\s*mp_physics\s*=\s*(\d+)", 27),
        "use_mp_re": (r"(?m)^\s*use_mp_re\s*=\s*(\d+)", 1),
        "ra_lw_physics": (r"(?m)^\s*ra_lw_physics\s*=\s*(\d+)", expected_ra),
        "ra_sw_physics": (r"(?m)^\s*ra_sw_physics\s*=\s*(\d+)", expected_ra),
        "radt": (r"(?m)^\s*radt\s*=\s*(\d+)", 10),
        "time_step": (r"(?m)^\s*time_step\s*=\s*(\d+)", 60),
        "interval_seconds": (r"(?m)^\s*interval_seconds\s*=\s*(\d+)", 10800),
        "rrtmgp_udm_frozen_optics": (r"(?m)^\s*rrtmgp_udm_frozen_optics\s*=\s*(\d+)", expected_frozen),
        "restart_interval": (r"(?m)^\s*restart_interval\s*=\s*(\d+)", 720),
    }
    for name, (pattern, want) in checks.items():
        m = re.search(pattern, text)
        if not m or int(m.group(1)) != want:
            raise RuntimeError(f"{mode}: namelist {name} does not equal {want}")
    if "run_hours                           = 24," not in text or "history_interval                    = 60," not in text:
        raise RuntimeError(f"{mode}: run duration/history schedule differs from plan")
    for name in ("wrfinput_d01", "wrfbdy_d01", "wrf.exe", "namelist.input", "radiation_iofields.txt"):
        if not (case / name).exists():
            raise FileNotFoundError(case / name)
    if (case / "wrf.exe").resolve() != Path(json.loads(PIN_FILE.read_text())["wrf_executable"]).resolve():
        raise RuntimeError(f"{mode}: WRF executable link does not target the pinned build")
    expected_data = (PREP / "case/rrtmgp_data").resolve()
    expected_table = (PREP / "case/frozen-ice-psd-moments.nc").resolve()
    for name, target in (("rrtmgp_data", expected_data), ("frozen-ice-psd-moments.nc", expected_table)):
        p = case / name
        if not p.is_symlink() or p.resolve() != target:
            raise RuntimeError(f"{mode}: radiation data link {name} changed")
    if sha(case / "wrfinput_d01") != sha(PREP / "case/wrfinput_d01"):
        raise RuntimeError(f"{mode}: initialized input differs from common REAL state")
    if sha(case / "wrfbdy_d01") != sha(PREP / "case/wrfbdy_d01"):
        raise RuntimeError(f"{mode}: boundary input differs from common REAL state")
    if sha(case / "wrfinput_d01") != EXPECTED_COMMON_INPUT:
        raise RuntimeError(f"{mode}: common REAL input does not match the reviewed fixed SHA256")
    if sha(case / "wrfbdy_d01") != EXPECTED_COMMON_BDY:
        raise RuntimeError(f"{mode}: common REAL boundary does not match the reviewed fixed SHA256")
    diagnostic_fields = case / "radiation_iofields.txt"
    expected_fields = "+:h:0:RTHRATEN,RTHRATLW,RTHRATSW,SWDDIR,SWDDIF,GSW\n"
    if not diagnostic_fields.is_file() or diagnostic_fields.read_text() != expected_fields:
        raise RuntimeError(f"{mode}: radiation output request file differs from reviewed field list")
    if 'iofields_filename' not in text or 'radiation_iofields.txt' not in text:
        raise RuntimeError(f"{mode}: namelist does not enable the reviewed output-only radiation fields")


def pair_case_hashes() -> dict:
    result = {}
    for arm in ("ra4", "ra37"):
        case = HERE / arm
        verify_case(case, arm)
        result[arm] = {name: sha(case / name) for name in
                       ("namelist.input", "wrfinput_d01", "wrfbdy_d01", "wrf.exe",
                        "radiation_iofields.txt", "frozen-ice-psd-moments.nc")}
    return result


def scan_numeric(ds) -> dict:
    counts = {"numeric_variables": 0, "raw_nonfinite": 0, "decoded_nonfinite": 0,
              "masked_values": 0, "fill_value_hits": 0}
    for _, var in ds.variables.items():
        if not np.issubdtype(np.dtype(var.dtype), np.number):
            continue
        counts["numeric_variables"] += 1
        var.set_auto_maskandscale(False)
        raw = np.asarray(var[...])
        if np.issubdtype(raw.dtype, np.inexact):
            counts["raw_nonfinite"] += int(raw.size - np.isfinite(raw).sum())
        for attr in ("_FillValue", "missing_value"):
            if attr in var.ncattrs():
                for marker in np.asarray(var.getncattr(attr)).reshape(-1):
                    counts["fill_value_hits"] += int(np.count_nonzero(raw == marker))
        var.set_auto_maskandscale(True)
        decoded = np.ma.asarray(var[...])
        counts["masked_values"] += int(np.ma.getmaskarray(decoded).sum())
        data = np.asarray(np.ma.getdata(decoded))
        if np.issubdtype(data.dtype, np.inexact):
            counts["decoded_nonfinite"] += int(data.size - np.isfinite(data).sum())
    return counts


def output_inventory(case: Path, mode: str) -> dict:
    from netCDF4 import Dataset

    hist = sorted(case.glob("wrfout_d01_*"))
    if len(hist) != 1:
        raise RuntimeError(f"{mode}: expected one history file, found {len(hist)}")
    hp = hist[0]
    report = {"history": {"path": str(hp), "sha256": sha(hp), "bytes": hp.stat().st_size},
              "history_numeric_variables": 0, "history_raw_nonfinite": 0,
              "history_decoded_nonfinite": 0, "history_masked": 0, "history_fill_hits": 0}
    with Dataset(hp) as ds:
        if "Times" not in ds.variables:
            raise RuntimeError(f"{mode}: history file has no Times")
        times = [decode_row(row) for row in ds.variables["Times"][:]]
        report["history_times"] = times
        if times != EXPECTED_HISTORY:
            raise RuntimeError(f"{mode}: history Times not exactly the 25 requested hourly records")
        for name, want in {"MP_PHYSICS": 27, "RA_LW_PHYSICS": 4 if mode == "ra4" else 37,
                           "RA_SW_PHYSICS": 4 if mode == "ra4" else 37,
                           "WEST-EAST_GRID_DIMENSION": 74, "SOUTH-NORTH_GRID_DIMENSION": 61,
                           "BOTTOM-TOP_GRID_DIMENSION": 33, "DX": 30000., "DY": 30000.}.items():
            if name not in ds.ncattrs() or not np.isclose(float(ds.getncattr(name)), float(want), rtol=0, atol=1e-6):
                raise RuntimeError(f"{mode}: output metadata {name} != {want}")
        for name in ("SWDOWN", "GLW", "OLR") + REQUIRED_RADIATION + WATER:
            if name not in ds.variables:
                raise RuntimeError(f"{mode}: output missing {name}")
        scan = scan_numeric(ds)
        report["history_numeric_variables"] = scan["numeric_variables"]
        report["history_raw_nonfinite"] = scan["raw_nonfinite"]
        report["history_decoded_nonfinite"] = scan["decoded_nonfinite"]
        report["history_masked"] = scan["masked_values"]
        report["history_fill_hits"] = scan["fill_value_hits"]
    if report["history_raw_nonfinite"] or report["history_decoded_nonfinite"] or report["history_masked"] or report["history_fill_hits"]:
        raise RuntimeError(f"{mode}: history has nonfinite/masked/fill numeric values")
    restarts = sorted(case.glob("wrfrst_d01_*"))
    rst_times = set()
    restart_validation = []
    for p in restarts:
        with Dataset(p) as ds:
            if "Times" in ds.variables:
                rst_times.add(decode_row(ds.variables["Times"][0]))
            for name in WATER:
                if name not in ds.variables:
                    raise RuntimeError(f"{mode}: restart {p.name} lacks state field {name}")
            counts = scan_numeric(ds)
            if any(counts[k] for k in ("raw_nonfinite", "decoded_nonfinite", "masked_values", "fill_value_hits")):
                raise RuntimeError(f"{mode}: restart {p.name} has nonfinite/masked/fill numeric values: {counts}")
            for name, want in {"MP_PHYSICS": 27, "RA_LW_PHYSICS": 4 if mode == "ra4" else 37,
                               "RA_SW_PHYSICS": 4 if mode == "ra4" else 37}.items():
                if name in ds.ncattrs() and int(ds.getncattr(name)) != want:
                    raise RuntimeError(f"{mode}: restart {p.name} metadata {name} mismatch")
            restart_validation.append({"path": str(p), "sha256": sha(p), "numeric_validation": counts})
    report["restarts"] = [{"path": str(p), "sha256": sha(p), "bytes": p.stat().st_size} for p in restarts]
    report["restart_numeric_validation"] = restart_validation
    report["restart_times"] = sorted(rst_times)
    if not EXPECTED_RESTARTS.issubset(rst_times):
        raise RuntimeError(f"{mode}: 12h/24h restart outputs not present: {sorted(rst_times)}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run both 24-hour forecast arms (not run yet)")
    args = parser.parse_args()
    receipt = {"status": "PREPARED_NOT_EXECUTED", "execution_requested": args.execute,
               "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "timeout_seconds_per_arm": 1800, "arms": {}, "errors": []}
    receipt_written_this_run = False
    tracked_paths = [HERE / "run_pair.py", HERE / "run-paired-forecast.sh", HERE / "pair-plan.json",
                     HERE / "ra4/namelist.input", HERE / "ra37/namelist.input"]
    frozen_runner_plan_before = None

    def runner_plan_hashes() -> dict[str, str]:
        return {str(p): sha(p) for p in tracked_paths}

    def update_progress(arm: str, entry: dict, proc: subprocess.Popen, started: float) -> None:
        case = HERE / arm
        log = case / "run.log"
        rank_logs = sorted(case.glob("rsl.error.*"))
        success = [p.name for p in rank_logs if "SUCCESS COMPLETE WRF" in p.read_text(errors="replace")]
        timestamps = set()
        for p in [log, *rank_logs]:
            if p.is_file():
                text = p.read_text(errors="replace")
                timestamps.update(re.findall(r"20\d\d-\d\d-\d\d_\d\d:\d\d:\d\d", text))
        entry["progress"] = {
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "process_returncode": proc.poll(),
            "rank_log_count": len(rank_logs),
            "success_ranks_seen": success,
            "history_file_count": len(list(case.glob("wrfout_d01_*"))),
            "restart_file_count": len(list(case.glob("wrfrst_d01_*"))),
            "latest_model_time_seen_in_logs": max(timestamps) if timestamps else None,
            "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        write_json(RUN_RECEIPT, receipt)
    try:
        receipt["pins_before"] = pinned_hashes()
        frozen_runner_plan_before = runner_plan_hashes()
        receipt["runner_plan_namelist_hashes_before"] = frozen_runner_plan_before
        plan = json.loads((HERE / "pair-plan.json").read_text())
        if plan["arms"]["ra4"]["wrfinput_sha256"] != EXPECTED_COMMON_INPUT or \
           plan["arms"]["ra37"]["wrfinput_sha256"] != EXPECTED_COMMON_INPUT or \
           plan["arms"]["ra4"]["wrfbdy_sha256"] != EXPECTED_COMMON_BDY or \
           plan["arms"]["ra37"]["wrfbdy_sha256"] != EXPECTED_COMMON_BDY:
            raise RuntimeError("frozen pair plan does not pin the reviewed common REAL input/boundary files")
        if plan.get("run_pair.py_sha256") != sha(HERE / "run_pair.py"):
            raise RuntimeError("runner does not match the reviewed pair-plan SHA256")
        if plan.get("run-paired-forecast.sh_sha256") != sha(HERE / "run-paired-forecast.sh"):
            raise RuntimeError("launcher does not match the reviewed pair-plan SHA256")
        if args.execute:
            preflight = json.loads((HERE / "preflight-verification.json").read_text())
            if preflight.get("status") != "PREFLIGHT_PASS_NOT_EXECUTED":
                raise RuntimeError("a successful non-executing preflight must exist before forecasts are authorized")
            if preflight.get("runner_plan_namelist_hashes_after") != runner_plan_hashes():
                raise RuntimeError("runner/plan/namelist bytes differ from the last reviewed preflight")
            if preflight.get("pair_plan_sha256") != sha(HERE / "pair-plan.json"):
                raise RuntimeError("pair plan differs from the reviewed preflight receipt")
            if preflight.get("runner_sha256") != sha(HERE / "run_pair.py"):
                raise RuntimeError("runner differs from the reviewed preflight receipt")
        expected_runtime = plan.get("runtime_directory_files_sha256", {})
        current_runtime = runtime_directory_hashes()
        if expected_runtime != current_runtime:
            raise RuntimeError("radiation runtime directory file manifest differs from frozen pair plan")
        receipt["runtime_directory_files_sha256_before"] = current_runtime
        for arm in ("ra4", "ra37"):
            item = plan["arms"][arm]
            if sha(HERE / arm / "namelist.input") != item["namelist_sha256"]:
                raise RuntimeError(f"{arm}: namelist does not match frozen pair-plan SHA256")
            if sha(HERE / arm / "wrfinput_d01") != item["wrfinput_sha256"] or \
               sha(HERE / arm / "wrfbdy_d01") != item["wrfbdy_sha256"]:
                raise RuntimeError(f"{arm}: initial/boundary file does not match frozen pair-plan SHA256")
            if sha(HERE / arm / "radiation_iofields.txt") != item["radiation_iofields_sha256"]:
                raise RuntimeError(f"{arm}: radiation output field request differs from frozen pair-plan SHA256")
        if RUN_RECEIPT.exists():
            raise FileExistsError(f"refusing to overwrite {RUN_RECEIPT}")
        for arm in ("ra4", "ra37"):
            case = HERE / arm
            verify_case(case, arm)
            preexisting = sorted(p.name for p in case.iterdir()
                                 if p.name.startswith(("wrfout", "wrfrst", "rsl.")) or
                                 p.name in ("namelist.output", "run.log", "arm-receipt.json"))
            if preexisting:
                raise FileExistsError(f"{arm}: preexisting run outputs: {preexisting}")
        receipt["pair_case_pins_before"] = pair_case_hashes()
        receipt["input_sha256"] = {arm: {"wrfinput": sha(HERE / arm / "wrfinput_d01"),
                                          "wrfbdy": sha(HERE / arm / "wrfbdy_d01"),
                                          "namelist": sha(HERE / arm / "namelist.input")}
                                   for arm in ("ra4", "ra37")}
        if receipt["input_sha256"]["ra4"]["wrfinput"] != receipt["input_sha256"]["ra37"]["wrfinput"] or \
           receipt["input_sha256"]["ra4"]["wrfbdy"] != receipt["input_sha256"]["ra37"]["wrfbdy"]:
            raise RuntimeError("the two forecast arms do not use byte-identical initialized and boundary files")
        n4 = (HERE / "ra4/namelist.input").read_text().replace(str(HERE / "ra4"), "<CASE>")
        n37 = (HERE / "ra37/namelist.input").read_text().replace(str(HERE / "ra37"), "<CASE>")
        n4norm = re.sub(r"(?m)^\s*ra_lw_physics\s*=.*$", " ra_lw_physics = <RADIATION>", n4)
        n4norm = re.sub(r"(?m)^\s*ra_sw_physics\s*=.*$", " ra_sw_physics = <RADIATION>", n4norm)
        n4norm = re.sub(r"(?m)^\s*rrtmgp_udm_frozen_optics\s*=.*$", " rrtmgp_udm_frozen_optics = <FROZEN>", n4norm)
        n37norm = re.sub(r"(?m)^\s*ra_lw_physics\s*=.*$", " ra_lw_physics = <RADIATION>", n37)
        n37norm = re.sub(r"(?m)^\s*ra_sw_physics\s*=.*$", " ra_sw_physics = <RADIATION>", n37norm)
        n37norm = re.sub(r"(?m)^\s*rrtmgp_udm_frozen_optics\s*=.*$", " rrtmgp_udm_frozen_optics = <FROZEN>", n37norm)
        if n4norm != n37norm:
            diff = "".join(difflib.unified_diff(n4norm.splitlines(True), n37norm.splitlines(True), fromfile="ra4", tofile="ra37"))
            raise RuntimeError("forecast namelists differ beyond RA selectors/frozen mode:\n" + diff)
        runtime_env = os.environ.copy()
        for key in list(runtime_env):
            if key.startswith("WRF_RRTMGP_") or key.startswith("WRF_UDM_BOUNDARY_CAPTURE"):
                runtime_env.pop(key)
        runtime_env.update({"LD_LIBRARY_PATH": f"{ROOT}/build/deps/netcdf/lib:{ROOT}/build/deps/root/usr/lib/x86_64-linux-gnu:{ROOT}/build/deps/mpich-sock/lib:" + runtime_env.get("LD_LIBRARY_PATH", ""),
                            "OMP_NUM_THREADS": "1", "OMP_STACKSIZE": "512M", "OMP_DYNAMIC": "FALSE",
                            "OPENBLAS_NUM_THREADS": "1", "MPICH_INTERFACE_HOSTNAME": "127.0.0.1"})
        ldd = subprocess.run(["ldd", str(HERE / "ra4/wrf.exe")], capture_output=True, text=True, env=runtime_env, check=False)
        receipt["ldd"] = {"returncode": ldd.returncode, "output": ldd.stdout, "stderr": ldd.stderr}
        if ldd.returncode or "not found" in ldd.stdout:
            raise RuntimeError("pinned WRF executable has unresolved shared libraries")
        receipt["status"] = "PREFLIGHT_PASS_NOT_EXECUTED"
        receipt["pair_plan_sha256"] = sha(HERE / "pair-plan.json")
        receipt["runner_sha256"] = sha(HERE / "run_pair.py")
        receipt["launcher_sha256"] = sha(HERE / "run-paired-forecast.sh")
        if not args.execute:
            returncode = 0
        else:
            receipt["status"] = "RUNNING"
            write_json(RUN_RECEIPT, receipt)
            receipt_written_this_run = True
            env = runtime_env
            receipt["environment"] = {k: env[k] for k in ("LD_LIBRARY_PATH", "OMP_NUM_THREADS", "OMP_STACKSIZE", "OMP_DYNAMIC", "OPENBLAS_NUM_THREADS", "MPICH_INTERFACE_HOSTNAME")}
            for arm in ("ra4", "ra37"):
                case = HERE / arm
                log_path = case / "run.log"
                cmd = [str(ROOT / "build/deps/mpich-sock/bin/mpiexec"), "-launcher", "fork", "-iface", "lo", "-n", "4", "./wrf.exe"]
                entry = {"command": cmd, "returncode": None, "timeout": False, "success_ranks": [], "fatal_marker": False}
                with log_path.open("wb") as log:
                    proc = subprocess.Popen(cmd, cwd=case, env=env, stdout=log, stderr=subprocess.STDOUT,
                                            start_new_session=True,
                                            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_STACK,
                                                (512 * 1024 * 1024, resource.getrlimit(resource.RLIMIT_STACK)[1])))
                    arm_started = time.monotonic()
                    deadline = arm_started + 1800
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            entry["timeout"] = True
                            try:
                                os.killpg(proc.pid, signal.SIGTERM)
                                proc.wait(timeout=30)
                            except subprocess.TimeoutExpired:
                                os.killpg(proc.pid, signal.SIGKILL)
                                proc.wait()
                            entry["returncode"] = proc.returncode
                            break
                        try:
                            entry["returncode"] = proc.wait(timeout=min(60, remaining))
                            break
                        except subprocess.TimeoutExpired:
                            update_progress(arm, entry, proc, arm_started)
                combined = log_path.read_text(errors="replace")
                for rp in sorted(case.glob("rsl.error.*")):
                    text = rp.read_text(errors="replace")
                    if "SUCCESS COMPLETE WRF" in text:
                        entry["success_ranks"].append(rp.name)
                    combined += "\n" + text
                entry["fatal_marker"] = bool(re.search(r"FATAL|forrtl: severe|SIGSEGV|segmentation fault", combined, re.I))
                entry["log"] = {"path": str(log_path), "sha256": sha(log_path), "bytes": log_path.stat().st_size}
                receipt["arms"][arm] = entry
                write_json(RUN_RECEIPT, receipt)
                if entry["returncode"] != 0 or entry["timeout"] or entry["fatal_marker"] or len(entry["success_ranks"]) != 4:
                    entry["status"] = "FORECAST_FAILED"
                    receipt["status"] = "FORECAST_FAILED"
                    break
                entry["outputs"] = output_inventory(case, arm)
                entry["status"] = "FORECAST_PASS"
                write_json(RUN_RECEIPT, receipt)
                receipt_written_this_run = True
            if receipt["status"] == "RUNNING":
                receipt["status"] = "PAIRED_FORECAST_PASS"
    except Exception as exc:
        receipt["status"] = "PREFLIGHT_OR_VALIDATION_FAILED"
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["traceback"] = traceback.format_exc()
    finally:
        receipt["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            receipt["pins_after"] = pinned_hashes()
            receipt["pins_unchanged"] = receipt.get("pins_before") == receipt["pins_after"]
            if receipt.get("pins_before") and not receipt["pins_unchanged"]:
                receipt["status"] = "PIN_DRIFT_FAILURE"
                receipt["errors"].append("immutable source/data/input pins changed during preflight/forecast")
            receipt["pair_case_pins_after"] = pair_case_hashes()
            if receipt.get("pair_case_pins_before") and receipt["pair_case_pins_before"] != receipt["pair_case_pins_after"]:
                receipt["status"] = "PAIR_CASE_PIN_DRIFT_FAILURE"
                receipt["errors"].append("forecast case namelist or initial/boundary/executable/table bytes changed")
            receipt["runtime_directory_files_sha256_after"] = runtime_directory_hashes()
            receipt["runtime_directory_files_unchanged"] = receipt.get("runtime_directory_files_sha256_before") == receipt["runtime_directory_files_sha256_after"]
            if receipt.get("runtime_directory_files_sha256_before") and not receipt["runtime_directory_files_unchanged"]:
                receipt["status"] = "RUNTIME_DATA_DRIFT_FAILURE"
                receipt["errors"].append("linked runtime data directory contents changed during run")
            receipt["runner_plan_namelist_hashes_after"] = runner_plan_hashes()
            receipt["runner_plan_namelists_unchanged"] = frozen_runner_plan_before == receipt["runner_plan_namelist_hashes_after"]
            if frozen_runner_plan_before and not receipt["runner_plan_namelists_unchanged"]:
                receipt["status"] = "RUNNER_PLAN_DRIFT_FAILURE"
                receipt["errors"].append("runner, plan, shell, or namelist changed during execution")
        except Exception as exc:
            receipt["pins_after_error"] = f"{type(exc).__name__}: {exc}"
            if receipt.get("execution_requested"):
                receipt["status"] = "PIN_DRIFT_FAILURE"
        if args.execute:
            if not RUN_RECEIPT.exists() or receipt_written_this_run:
                write_json(RUN_RECEIPT, receipt)
            else:
                refused = HERE / ("refused-attempt-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + ".json")
                if not refused.exists():
                    write_json(refused, receipt)
        elif not RUN_RECEIPT.exists():
            write_json(HERE / "preflight-verification.json", receipt)
    print(json.dumps({"status": receipt["status"], "execute": args.execute,
                      "receipt": str(RUN_RECEIPT if args.execute else HERE / "preflight-verification.json"),
                      "errors": receipt["errors"]}, indent=2))
    return 0 if receipt["status"] == "PREFLIGHT_PASS_NOT_EXECUTED" else (0 if receipt["status"] == "PAIRED_FORECAST_PASS" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
