#!/usr/bin/env python3
"""Prepare or explicitly execute the corrected paired UDM real-domain trial.

No run is started unless --execute is passed. All paths and hashes are pinned
to the reviewed scratch build and archived common initial/boundary conditions.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PLAN = Path(__file__).resolve().parent
OUT = PLAN / "cases"
EXE = ROOT / "build/udm-sr-row-dm-sm/source/WRF/main/wrf.exe"
INPUT_CASE = ROOT / "build/udm-realdata-24h/ra4"
TEMPLATE37 = ROOT / "build/udm-frozen-runtime-mpi/case-mode1/namelist.input"
COMMON_STATIC = ROOT / "build/udm-frozen-runtime-mpi/case-mode1"
TABLE = ROOT / "build/udm-frozen-runtime-wrf/source/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc"
DATA = ROOT / "build/mpi-wrf-udm-contracts/WRF/run"
MPIEXEC = ROOT / "build/deps/mpich-sock/bin/mpiexec"
NETCDF_LIB = ROOT / "build/deps/root/usr/lib/x86_64-linux-gnu"
SOURCE_PROVENANCE = ROOT / "build/udm-sr-row-dm-sm/source-provenance.json"
UDM_SOURCE = ROOT / "build/udm-sr-row-dm-sm/source/WRF/phys/module_mp_udm.F"
RRTMGP_ADAPTER = ROOT / "build/udm-sr-row-dm-sm/source/WRF/phys/module_ra_rrtmgp.F"

EXPECTED = {
    "executable": "176f589d657ca87df670cef3429d7474e674f3e44445eb7886aed871e36bef8f",
    "wrfinput_d01": "5ef7abe34c516fba107f346bdbdb3777edacb5d48493df467ea2dd8bcf6a75ff",
    "wrfbdy_d01": "e687b73730ab9a2cee4842e1a92b225a4edb074ba080b6053d96d81ec1731a2d",
    "frozen_table": "8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583",
    "gas_lw": "70ad65d116531122660318e5da2a2af9db74b425916202860e9527ef2375b8f6",
    "gas_sw": "361ed541324068ded28a275a4dd757bcaa0a845aebefa630f43a04678668fe62",
    "cloud_lw": "09d6704c5b863b4c3ceb417d20bb3076ec492e6bf2dfbcc9f3c5996a3706f0b0",
    "cloud_sw": "7671835992a45afe66244b591a02c0b3df73d7d59ecb746bbffd9763497651cd",
    "rrtmg_lw": "bcfdee24b63a4c909522a329b8e16c539f0173c7e5aea2caf933ab4fe28c5c97",
    "rrtmg_sw": "a7d25f5b4d33be8629cbef7ecacc1ff413bf398a021297793e843ba1cc627baf",
    "source_provenance": "31b15112a72b0b337679cfd122ec641641b0e8fa431838eb15fd014554c2e94f",
    "module_mp_udm": "7564be3e5ad7b26ffc00c2680eb632745850baeac01529d48d6bc8393cb9e53d",
    "module_ra_rrtmgp": "74378cc255088422ff8f770c1f342e135c538436d0bc0dcf67ec7b7abde1f5bb",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_inputs() -> dict:
    paths = {
        "executable": EXE,
        "wrfinput_d01": INPUT_CASE / "wrfinput_d01",
        "wrfbdy_d01": INPUT_CASE / "wrfbdy_d01",
        "frozen_table": TABLE,
        "gas_lw": DATA / "rrtmgp-gas-lw-g128.nc",
        "gas_sw": DATA / "rrtmgp-gas-sw-g112.nc",
        "cloud_lw": DATA / "rrtmgp-clouds-lw-bnd.nc",
        "cloud_sw": DATA / "rrtmgp-clouds-sw-bnd.nc",
        "rrtmg_lw": COMMON_STATIC / "RRTMG_LW_DATA",
        "rrtmg_sw": COMMON_STATIC / "RRTMG_SW_DATA",
        "source_provenance": SOURCE_PROVENANCE,
        "module_mp_udm": UDM_SOURCE,
        "module_ra_rrtmgp": RRTMGP_ADAPTER,
    }
    hashes = {}
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"required file missing: {path}")
        hashes[name] = sha(path)
        if hashes[name] != EXPECTED[name]:
            raise RuntimeError(f"{name} SHA mismatch: {hashes[name]} != {EXPECTED[name]}")
    for path in (TEMPLATE37,
                 MPIEXEC, NETCDF_LIB):
        if not path.exists():
            raise RuntimeError(f"required runtime dependency missing: {path}")
    boundary = read_times(paths["wrfbdy_d01"])
    this_bdy = read_times(paths["wrfbdy_d01"], "md___thisbdytimee_x_t_d_o_m_a_i_n_m_e_t_a_data_")
    next_bdy = read_times(paths["wrfbdy_d01"], "md___nextbdytimee_x_t_d_o_m_a_i_n_m_e_t_a_data_")
    input_times = read_times(paths["wrfinput_d01"])
    expected_boundary = [f"2010-06-11_{hour:02d}:00:00" for hour in (0, 6, 12, 18)]
    expected_next = [f"2010-06-11_{hour:02d}:00:00" for hour in (6, 12, 18)] + ["2010-06-12_00:00:00"]
    if boundary != expected_boundary or this_bdy != expected_boundary or next_bdy != expected_next:
        raise RuntimeError(f"boundary coverage mismatch: Times={boundary}, this={this_bdy}, next={next_bdy}")
    if input_times != ["2010-06-11_00:00:00"]:
        raise RuntimeError(f"initial input time mismatch: {input_times}")
    return {"sha256": hashes, "paths": {k: str(v.resolve()) for k, v in paths.items()},
            "boundary_time_coverage": {"this": this_bdy, "next": next_bdy,
                                       "verified_end": "2010-06-12_00:00:00"}}


def read_times(path: Path, variable: str = "Times") -> list[str]:
    with netCDF4.Dataset(path, "r") as ds:
        if variable not in ds.variables:
            raise RuntimeError(f"{path} lacks time variable {variable}")
        values = ds.variables[variable][:]
    if values.ndim == 1:
        values = values[None, :]
    return [b"".join(row.tolist()).decode("ascii") for row in values]


MUTABLE_NAMES = {"namelist.input", "namelist.output", "wrfinput_d01", "wrfbdy_d01",
                 "wrf.exe", "run-receipt.json", "run.log"}


def case_asset_manifest(case: Path) -> dict:
    assets = {}
    for path in sorted(case.iterdir()):
        if path.name in MUTABLE_NAMES or path.name.startswith(("wrfout_", "wrfrst_", "rsl.")):
            continue
        if path.is_file():
            if not path.exists():
                raise RuntimeError(f"broken static asset link: {path}")
            assets[path.name] = {"sha256": sha(path), "link_target": os.readlink(path) if path.is_symlink() else None,
                                 "resolved_path": str(path.resolve())}
        elif path.is_dir():
            raise RuntimeError(f"unexpected static directory in case tree: {path}")
    return assets


def immutable_case_state(case: Path) -> dict:
    return {"namelist_sha256": sha(case / "namelist.input"),
            "wrfinput_sha256": sha(case / "wrfinput_d01"),
            "wrfbdy_sha256": sha(case / "wrfbdy_d01"),
            "assets": case_asset_manifest(case)}


def check_immutable_case(case: Path, expected: dict) -> None:
    actual = immutable_case_state(case)
    if actual != expected:
        raise RuntimeError(f"immutable staged case content changed: {case}")


def replace_one(text: str, key: str, value: str) -> str:
    pat = re.compile(rf"(?im)^(\s*{re.escape(key)}\s*=)[^\n]*$")
    text2, n = pat.subn(rf"\1 " + value + ",", text)
    if n != 1:
        raise RuntimeError(f"expected one namelist assignment for {key}, found {n}")
    return text2


def make_namelist(radiation: int) -> str:
    text = TEMPLATE37.read_text()
    for key, value in (("run_days", "0"), ("run_hours", "24"), ("run_minutes", "0"),
                       ("run_seconds", "0"), ("start_year", "2010, 2010"),
                       ("start_month", "06, 06"), ("start_day", "11, 11"),
                       ("start_hour", "00, 00"), ("start_minute", "00, 00"),
                       ("start_second", "00, 00"), ("end_year", "2010, 2010"),
                       ("end_month", "06, 06"), ("end_day", "12, 12"),
                       ("end_hour", "00, 00"), ("end_minute", "00, 00"),
                       ("end_second", "00, 00"), ("time_step", "60"),
                       ("restart_interval", "720"), ("restart", ".false."),
                       ("history_interval", "60, 60, 60"), ("frames_per_outfile", "1, 1, 1"),
                       ("mp_physics", "27, 27, 27"),
                       ("ra_lw_physics", f"{radiation}, {radiation}, {radiation}"),
                       ("ra_sw_physics", f"{radiation}, {radiation}, {radiation}"),
                       ("radt", "10, 10, 10"), ("use_mp_re", "1"),
                       ("rrtmgp_data_path", f"'{DATA}'")):
        text = replace_one(text, key, value)
    # Keep the experimental frozen model active only for the RRTMGP37 arm.
    text = re.sub(r"(?im)^\s*rrtmgp_udm_frozen_optics\s*=.*\n", "", text)
    text = re.sub(r"(?im)^\s*rrtmgp_udm_frozen_table\s*=.*\n", "", text)
    if radiation == 37:
        text = text.replace(" &physics\n", " &physics\n rrtmgp_udm_frozen_optics = 1,\n" +
                            f" rrtmgp_udm_frozen_table = '{TABLE}',\n", 1)
    return text


def prepare(inputs: dict) -> None:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite existing trial directory: {OUT}")
    OUT.mkdir(parents=True)
    for name, ra in (("ra4", 4), ("ra37", 37)):
        case = OUT / name
        case.mkdir()
        for source in COMMON_STATIC.iterdir():
            if source.name in {"namelist.input", "namelist.output", "wrfinput_d01", "wrfbdy_d01", "wrf.exe"}:
                continue
            if source.name.startswith(("wrfout_", "wrfrst_", "rsl.")) or source.name.endswith(".log"):
                continue
            if source.name == "run-receipt.json":
                continue
            target = case / source.name
            if source.is_symlink():
                target.symlink_to(source.resolve())
            elif source.is_file():
                target.symlink_to(source.resolve())
        shutil.copy2(INPUT_CASE / "wrfinput_d01", case / "wrfinput_d01")
        shutil.copy2(INPUT_CASE / "wrfbdy_d01", case / "wrfbdy_d01")
        (case / "namelist.input").write_text(make_namelist(ra))
    receipt = {
        "status": "PREPARED_NOT_RUN",
        "case_paths": {"ra4": str(OUT / "ra4"), "ra37": str(OUT / "ra37")},
        "case_immutable_state": {name: immutable_case_state(OUT / name) for name in ("ra4", "ra37")},
        "inputs": inputs,
        "physics": {
            "ra4": "RA4 legacy/generic cloud radii and precipitation optics, mode 0",
            "ra37": "RRTMGP37 with UDM-native radii and frozen-optics table mode 1",
            "common": "UDM27; d01 290x190; 60-s timestep; 4 MPI ranks; 1 OpenMP thread",
        },
        "run": "2010-06-11 00:00 through 2010-06-12 00:00; hourly history; restart at 12 h and 24 h",
        "data": {"coefficient_directory": str(DATA), "frozen_table": str(TABLE)},
        "notes": [
            "CFC species are connected in the current binary; do not reuse PR20 six-gas wording.",
            "The 24-hour archived metrics are historical and are not overwritten by this plan.",
            "This corrected paired run is not a pristine-WRF comparison.",
            "Hydrometeor diagnostics are opt-in only; no model or namelist physics changes are made to collect them.",
        ],
        "prepared_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (PLAN / "preflight.json").write_text(json.dumps(receipt, indent=2) + "\n")


def validate_completed_case(case: Path) -> dict:
    rank_logs = sorted(case.glob("rsl.error.[0-9][0-9][0-9][0-9]"))
    if len(rank_logs) != 4:
        raise RuntimeError(f"expected four rank rsl.error files, found {len(rank_logs)}")
    missing_success = [p.name for p in rank_logs if "SUCCESS COMPLETE WRF" not in p.read_text(errors="replace")]
    if missing_success:
        raise RuntimeError(f"SUCCESS COMPLETE WRF absent in rank logs: {missing_success}")
    histories = sorted(case.glob("wrfout_d01_*"))
    expected = [datetime(2010, 6, 11) + timedelta(hours=h) for h in range(25)]
    if len(histories) != 25:
        raise RuntimeError(f"expected 25 hourly history files, found {len(histories)}")
    actual_times = []
    checked_numeric_arrays = 0
    for path in histories:
        with netCDF4.Dataset(path, "r") as ds:
            if "Times" not in ds.variables:
                raise RuntimeError(f"{path} has no Times variable")
            row = ds.variables["Times"][0]
            actual_times.append(datetime.strptime(b"".join(row.tolist()).decode("ascii"), "%Y-%m-%d_%H:%M:%S"))
            for var in ds.variables.values():
                if not np.issubdtype(var.dtype, np.number):
                    continue
                values = np.ma.asarray(var[:])
                raw = values.compressed() if np.ma.isMaskedArray(values) else np.asarray(values).ravel()
                if raw.size and not np.isfinite(raw).all():
                    raise RuntimeError(f"nonfinite values in {path.name}:{var.name}")
                checked_numeric_arrays += 1
    if actual_times != expected:
        raise RuntimeError(f"history Times do not match exact hourly sequence: {actual_times}")
    restarts = {"wrfrst_d01_2010-06-11_12:00:00": "2010-06-11_12:00:00",
                "wrfrst_d01_2010-06-12_00:00:00": "2010-06-12_00:00:00"}
    restart_checks = {}
    for name, expected_time in restarts.items():
        path = case / name
        if not path.is_file():
            raise RuntimeError(f"expected restart file missing: {name}")
        with netCDF4.Dataset(path, "r") as ds:
            if "Times" not in ds.variables:
                raise RuntimeError(f"{name} has no Times variable")
            row = ds.variables["Times"][0]
            found_time = b"".join(row.tolist()).decode("ascii")
            if found_time != expected_time:
                raise RuntimeError(f"{name} timestamp {found_time} != {expected_time}")
            arrays = 0
            masked = 0
            for var in ds.variables.values():
                if not np.issubdtype(var.dtype, np.number):
                    continue
                values = np.ma.asarray(var[:])
                masked += int(np.ma.count_masked(values))
                raw = values.compressed() if np.ma.isMaskedArray(values) else np.asarray(values).ravel()
                if raw.size and not np.isfinite(raw).all():
                    raise RuntimeError(f"nonfinite values in {name}:{var.name}")
                arrays += 1
            restart_checks[name] = {"time": found_time, "numeric_arrays_checked": arrays,
                                    "masked_value_count": masked}
    return {"rank_success_logs": [p.name for p in rank_logs],
            "history_count": len(histories), "history_first": actual_times[0].isoformat(),
            "history_last": actual_times[-1].isoformat(),
            "numeric_variable_arrays_checked": checked_numeric_arrays,
            "restart_validation": restart_checks}


def reject_nonfresh_execution() -> None:
    if (PLAN / "execution.json").exists():
        raise RuntimeError("execution.json already exists; refusing repeated launch")
    for name in ("ra4", "ra37"):
        case = OUT / name
        stale = [p.name for p in case.iterdir()
                 if p.name.startswith(("rsl.", "wrfout_d01_", "wrfrst_d01_"))]
        if stale:
            raise RuntimeError(f"refusing existing run output in {case}: {stale[:8]}")


def execute() -> bool:
    ready_path = PLAN / "preflight.json"
    if not ready_path.exists() or not OUT.is_dir():
        raise RuntimeError("run --prepare first; no prepared case tree found")
    ready = json.loads(ready_path.read_text())
    if ready.get("status") != "PREPARED_NOT_RUN":
        raise RuntimeError("preflight status is not PREPARED_NOT_RUN")
    current = validate_inputs()
    if current["sha256"] != ready["inputs"]["sha256"]:
        raise RuntimeError("one or more pinned executable/table/input hashes changed after preparation")
    reject_nonfresh_execution()
    for name in ("ra4", "ra37"):
        check_immutable_case(OUT / name, ready["case_immutable_state"][name])
    lock = (PLAN / "run.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OMP_STACKSIZE": "512M", "OMP_DYNAMIC": "FALSE",
                "OPENBLAS_NUM_THREADS": "1",
                "MPICH_INTERFACE_HOSTNAME": "127.0.0.1",
                "LD_LIBRARY_PATH": f"{NETCDF_LIB}:{env.get('LD_LIBRARY_PATH', '')}"})
    for key in list(env):
        if key.startswith("WRF_RRTMGP_") or key.startswith("WRF_UDM_BOUNDARY_CAPTURE"):
            env.pop(key, None)
    receipt = {"status": "RUNNING", "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "commands": {}, "returncodes": {},
               "environment": {k: env.get(k) for k in
                               ("OMP_NUM_THREADS", "OMP_STACKSIZE", "OMP_DYNAMIC", "OPENBLAS_NUM_THREADS",
                                "MPICH_INTERFACE_HOSTNAME", "LD_LIBRARY_PATH")},
               "cleared_environment_prefixes": ["WRF_RRTMGP_", "WRF_UDM_BOUNDARY_CAPTURE"]}
    (PLAN / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
    all_valid = True
    try:
        for name in ("ra4", "ra37"):
            case = OUT / name
            arm_pre = validate_inputs()
            if arm_pre != ready["inputs"]:
                raise RuntimeError(f"pinned source/input/coefficient hashes drifted before {name}")
            receipt.setdefault("hash_checks", {})[name] = {"before": arm_pre["sha256"],
                                                              "before_match": True}
            command = [str(MPIEXEC), "-launcher", "fork", "-iface", "lo", "-n", "4", str(EXE)]
            receipt["commands"][name] = command
            try:
                with (case / "run.log").open("wb") as log:
                    result = subprocess.run(command, cwd=case, env=env, stdout=log,
                                            stderr=subprocess.STDOUT, check=False)
            except Exception as exc:
                receipt["status"] = f"FAILED_LAUNCH_{name.upper()}"
                receipt.setdefault("failures", {})[name] = f"{type(exc).__name__}: {exc}"
                all_valid = False
                (PLAN / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
                break
            receipt["returncodes"][name] = result.returncode
            (PLAN / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
            if result.returncode:
                receipt["status"] = f"FAILED_{name.upper()}"
                receipt.setdefault("failures", {})[name] = f"launcher exited {result.returncode}"
                all_valid = False
                break
            try:
                receipt.setdefault("validation", {})[name] = validate_completed_case(case)
                check_immutable_case(case, ready["case_immutable_state"][name])
                arm_post = validate_inputs()
                if arm_post != ready["inputs"]:
                    raise RuntimeError(f"pinned source/input/coefficient hashes drifted after {name}")
                receipt["hash_checks"][name]["after"] = arm_post["sha256"]
                receipt["hash_checks"][name]["after_match"] = True
                receipt["status"] = f"{name.upper()}_VALIDATED"
            except Exception as exc:
                receipt["status"] = f"FAILED_VALIDATION_{name.upper()}"
                receipt.setdefault("failures", {})[name] = str(exc)
                all_valid = False
                (PLAN / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
                break
            (PLAN / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
        else:
            receipt["status"] = "BOTH_VALIDATED"
    except Exception as exc:
        if receipt.get("status") == "RUNNING":
            receipt["status"] = "FAILED_RUNNER_OR_PREFLIGHT"
        receipt.setdefault("failures", {})["runner"] = f"{type(exc).__name__}: {exc}"
        all_valid = False
    finally:
        receipt["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (PLAN / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return all_valid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true", help="verify assets and create fresh isolated case dirs; do not run")
    group.add_argument("--execute", action="store_true", help="run the prepared RA4 then RA37 24-hour pair")
    args = ap.parse_args()
    try:
        if args.prepare:
            prepare(validate_inputs())
            print(f"Prepared only; no model launched. Review {PLAN / 'preflight.json'}")
        else:
            okay = execute()
            print(f"Execution record: {PLAN / 'execution.json'}")
            if not okay:
                return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
