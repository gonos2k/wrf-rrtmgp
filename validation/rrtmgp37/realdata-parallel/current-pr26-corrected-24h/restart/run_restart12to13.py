#!/usr/bin/env python3
"""Prepare/execute per-arm 12:00→13:00 restart checks for the current paired run."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PAIR = HERE.parent
CASES = PAIR / "cases"
OUT = HERE / "cases"
EXE = ROOT / "build/udm-sr-row-dm-sm/source/WRF/main/wrf.exe"
MPIEXEC = ROOT / "build/deps/mpich-sock/bin/mpiexec"
NETCDF_LIB = ROOT / "build/deps/root/usr/lib/x86_64-linux-gnu"
TABLE = ROOT / "build/udm-frozen-runtime-wrf/source/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc"
COMMON_STATIC = ROOT / "build/udm-frozen-runtime-mpi/case-mode1"
DATA = ROOT / "build/mpi-wrf-udm-contracts/WRF/run"
CONTINUOUS_NAME = "wrfout_d01_2010-06-11_13:00:00"
CHECKPOINT_NAME = "wrfrst_d01_2010-06-11_12:00:00"
EXPECTED = {
    "executable": "176f589d657ca87df670cef3429d7474e674f3e44445eb7886aed871e36bef8f",
    "wrfinput_d01": "5ef7abe34c516fba107f346bdbdb3777edacb5d48493df467ea2dd8bcf6a75ff",
    "wrfbdy_d01": "e687b73730ab9a2cee4842e1a92b225a4edb074ba080b6053d96d81ec1731a2d",
    "frozen_table": "8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_times(path: Path) -> list[str]:
    with netCDF4.Dataset(path) as ds:
        values = ds.variables["Times"][:]
    return [b"".join(row.tolist()).decode("ascii") for row in values]


def validate_pins() -> dict:
    source_paths = {
        "executable": EXE,
        "wrfinput_d01": CASES / "ra4/wrfinput_d01",
        "wrfbdy_d01": CASES / "ra4/wrfbdy_d01",
        "frozen_table": TABLE,
    }
    hashes = {}
    for name, path in source_paths.items():
        if not path.is_file():
            raise RuntimeError(f"pinned source missing: {path}")
        hashes[name] = sha(path)
        if hashes[name] != EXPECTED[name]:
            raise RuntimeError(f"pinned {name} hash mismatch: {hashes[name]}")
    for name in ("ra4", "ra37"):
        case = CASES / name
        if sha(case / "wrfinput_d01") != EXPECTED["wrfinput_d01"]:
            raise RuntimeError(f"{name} wrfinput hash mismatch")
        if sha(case / "wrfbdy_d01") != EXPECTED["wrfbdy_d01"]:
            raise RuntimeError(f"{name} wrfbdy hash mismatch")
        with netCDF4.Dataset(case / CONTINUOUS_NAME) as ds:
            times = read_times(case / CONTINUOUS_NAME)
            options = [int(ds.getncattr(k)) for k in ("RA_LW_PHYSICS", "RA_SW_PHYSICS", "MP_PHYSICS")]
        wanted = [4, 4, 27] if name == "ra4" else [37, 37, 27]
        if times != ["2010-06-11_13:00:00"] or options != wanted:
            raise RuntimeError(f"{name} continuous anchor/options unexpected: {times}, {options}")
        checkpoint = case / CHECKPOINT_NAME
        if not checkpoint.is_file():
            raise RuntimeError(f"{name} own 12h checkpoint missing")
        if read_times(checkpoint) != ["2010-06-11_12:00:00"]:
            raise RuntimeError(f"{name} checkpoint timestamp mismatch")
    for p in (MPIEXEC, NETCDF_LIB, COMMON_STATIC / "RRTMG_LW_DATA", COMMON_STATIC / "RRTMG_SW_DATA"):
        if not p.exists():
            raise RuntimeError(f"runtime dependency missing: {p}")
    return {"sha256": hashes,
            "source_hashes": {"module_mp_udm.F": sha(ROOT / "build/udm-sr-row-dm-sm/source/WRF/phys/module_mp_udm.F"),
                              "module_ra_rrtmgp.F": sha(ROOT / "build/udm-sr-row-dm-sm/source/WRF/phys/module_ra_rrtmgp.F")},
            "coefficient_sha256": {
                n: sha(DATA / n) for n in ("rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-sw-g112.nc",
                                            "rrtmgp-clouds-lw-bnd.nc", "rrtmgp-clouds-sw-bnd.nc")},
            "continuous_history": {n: sha(CASES / n / CONTINUOUS_NAME) for n in ("ra4", "ra37")},
            "checkpoints": {n: sha(CASES / n / CHECKPOINT_NAME) for n in ("ra4", "ra37")}}


def replace_assignment(text: str, key: str, value: str) -> str:
    pat = re.compile(rf"(?im)^(\s*{re.escape(key)}\s*=)[^\n]*$")
    text, count = pat.subn(rf"\1 " + value + ",", text)
    if count != 1:
        raise RuntimeError(f"expected one {key} assignment, found {count}")
    return text


def make_namelist(source: str) -> str:
    values = {
        "run_days": "0", "run_hours": "1", "run_minutes": "0", "run_seconds": "0",
        "start_year": "2010, 2010", "start_month": "06, 06", "start_day": "11, 11",
        "start_hour": "12, 12", "start_minute": "00, 00", "start_second": "00, 00",
        "end_year": "2010, 2010", "end_month": "06, 06", "end_day": "11, 11",
        "end_hour": "13, 13", "end_minute": "00, 00", "end_second": "00, 00",
        "restart": ".true.", "restart_interval": "720", "history_interval": "60, 60, 60",
        "frames_per_outfile": "1, 1, 1",
    }
    for key, value in values.items():
        source = replace_assignment(source, key, value)
    if re.search(r"(?im)^\s*override_restart_timers\s*=", source):
        source = replace_assignment(source, "override_restart_timers", ".true.")
    else:
        block = re.search(r"(?im)^\s*&time_control\s*$", source)
        if block is None:
            raise RuntimeError("time_control block not found")
        source = source[:block.end()] + "\n override_restart_timers = .true.," + source[block.end():]
    return source


def make_assets(case: Path) -> dict:
    assets = {}
    for path in sorted(case.iterdir()):
        if path.name in {"namelist.input", "namelist.output", "wrfinput_d01", "wrfbdy_d01",
                         CHECKPOINT_NAME, "run.log"} or path.name.startswith(("wrfout_", "wrfrst_", "rsl.")):
            continue
        if path.is_file():
            if not path.exists():
                raise RuntimeError(f"broken asset symlink: {path}")
            assets[path.name] = {"sha256": sha(path), "link_target": os.readlink(path) if path.is_symlink() else None,
                                 "resolved_path": str(path.resolve())}
    return assets


def immutable_state(case: Path) -> dict:
    return {"namelist_sha256": sha(case / "namelist.input"),
            "wrfinput_sha256": sha(case / "wrfinput_d01"),
            "wrfbdy_sha256": sha(case / "wrfbdy_d01"),
            "checkpoint_sha256": sha(case / CHECKPOINT_NAME),
            "assets": make_assets(case)}


def prepare(pins: dict) -> None:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")
    OUT.mkdir(parents=True)
    cases = {}
    for name in ("ra4", "ra37"):
        source_case = CASES / name
        target = OUT / name
        target.mkdir()
        for source in COMMON_STATIC.iterdir():
            if source.name in {"namelist.input", "namelist.output", "wrfinput_d01", "wrfbdy_d01", "wrf.exe", "run-receipt.json"}:
                continue
            if source.name.startswith(("wrfout_", "wrfrst_", "rsl.")) or source.name.endswith(".log"):
                continue
            if source.is_file():
                (target / source.name).symlink_to(source.resolve())
        for filename in ("wrfinput_d01", "wrfbdy_d01", CHECKPOINT_NAME):
            src = source_case / filename
            (target / filename).write_bytes(src.read_bytes())
        (target / "namelist.input").write_text(make_namelist((source_case / "namelist.input").read_text()))
        cases[name] = {"source_checkpoint": str(source_case / CHECKPOINT_NAME),
                       "source_checkpoint_sha256": sha(source_case / CHECKPOINT_NAME),
                       "continuous_history": str(source_case / CONTINUOUS_NAME),
                       "continuous_history_sha256": sha(source_case / CONTINUOUS_NAME),
                       "physics_options": [4, 4, 27] if name == "ra4" else [37, 37, 27],
                       "namelist_sha256": sha(target / "namelist.input"),
                       "wrfinput_sha256": sha(target / "wrfinput_d01"),
                       "wrfbdy_sha256": sha(target / "wrfbdy_d01"),
                       "checkpoint_sha256": sha(target / CHECKPOINT_NAME),
                       "assets": make_assets(target)}
        cases[name]["staged_immutable_state"] = immutable_state(target)
    receipt = {"status": "PREPARED_NOT_RUN", "pins": pins, "cases": cases,
               "restart_window": ["2010-06-11_12:00:00", "2010-06-11_13:00:00"],
               "settings": {"dt_seconds": 60, "radt_minutes": 10, "mpi_ranks": 4, "omp_threads": 1,
                            "override_restart_timers": True,
                            "note": "Each arm starts from its own 12h checkpoint; no cross-arm checkpoint reuse."},
               "prepared_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (HERE / "preflight.json").write_text(json.dumps(receipt, indent=2) + "\n")


def array_state(path: Path) -> dict:
    with netCDF4.Dataset(path) as ds:
        metadata = {"global_attributes": {k: str(ds.getncattr(k)) for k in ds.ncattrs()},
                    "dimensions": {k: (len(v), v.isunlimited()) for k, v in ds.dimensions.items()},
                    "variables": {}}
        for name, var in ds.variables.items():
            values = np.ma.asarray(var[:])
            masked = int(np.ma.count_masked(values))
            raw = values.compressed() if np.ma.isMaskedArray(values) else np.asarray(values).ravel()
            numeric = np.issubdtype(var.dtype, np.number)
            finite = bool(np.isfinite(raw).all()) if numeric else True
            metadata["variables"][name] = {
                "dimensions": var.dimensions, "shape": tuple(var.shape), "dtype": str(var.dtype),
                "numeric": numeric, "values": np.asarray(values.filled(0) if np.ma.isMaskedArray(values) else values),
                "attributes": {k: str(var.getncattr(k)) for k in var.ncattrs()},
                "finite": finite, "masked": masked,
            }
    return metadata


def compare_history(reference: Path, restarted: Path) -> dict:
    ref, rst = array_state(reference), array_state(restarted)
    refvars, rstvars = ref["variables"], rst["variables"]
    missing = sorted(set(refvars) - set(rstvars)); extra = sorted(set(rstvars) - set(refvars))
    numeric = {}; nonnumeric_diffs = []
    exact_numeric = True
    for name in sorted(set(refvars) & set(rstvars)):
        a, b = refvars[name], rstvars[name]
        if a["dimensions"] != b["dimensions"] or a["shape"] != b["shape"] or a["dtype"] != b["dtype"]:
            numeric[name] = {"shape_or_type_mismatch": True, "reference": {k:a[k] for k in ("dimensions","shape","dtype")},
                             "restart": {k:b[k] for k in ("dimensions","shape","dtype")}}
            exact_numeric = False
            continue
        if a["numeric"] and b["numeric"]:
            av, bv = a["values"], b["values"]
            diff = np.asarray(bv, dtype=np.float64) - np.asarray(av, dtype=np.float64)
            neq = int(np.count_nonzero(av != bv))
            maxabs = float(np.max(np.abs(diff))) if diff.size else 0.0
            rms = float(np.sqrt(np.mean(diff * diff))) if diff.size else 0.0
            numeric[name] = {"equal": neq == 0, "different_values": neq, "value_count": int(diff.size),
                             "max_abs": maxabs, "rms": rms, "reference_masked": a["masked"],
                             "restart_masked": b["masked"], "finite": a["finite"] and b["finite"]}
            if neq or not a["finite"] or not b["finite"]:
                exact_numeric = False
        elif not np.array_equal(a["values"], b["values"]):
            nonnumeric_diffs.append(name)
    allowed_clock_attrs = {"START_DATE", "SIMULATION_START_DATE"}
    refattrs, rstattrs = ref["global_attributes"], rst["global_attributes"]
    attr_keys = sorted(set(refattrs) | set(rstattrs))
    attr_diffs = {k: {"reference": refattrs.get(k), "restart": rstattrs.get(k)}
                  for k in attr_keys if refattrs.get(k) != rstattrs.get(k)}
    nonclock_attr_diffs = {k:v for k,v in attr_diffs.items() if k not in allowed_clock_attrs}
    variable_attribute_differences = {}
    for name in sorted(set(refvars) & set(rstvars)):
        aa, bb = refvars[name]["attributes"], rstvars[name]["attributes"]
        diffs = {k: {"reference": aa.get(k), "restart": bb.get(k)}
                 for k in sorted(set(aa) | set(bb)) if aa.get(k) != bb.get(k)}
        if diffs:
            variable_attribute_differences[name] = diffs
    dims_match = ref["dimensions"] == rst["dimensions"]
    variable_metadata_match = not variable_attribute_differences
    return {
        "reference": str(reference), "restart": str(restarted),
        "reference_sha256": sha(reference), "restart_sha256": sha(restarted),
        "variable_set_match": not missing and not extra, "missing_variables": missing, "extra_variables": extra,
        "dimensions_match": dims_match, "numeric_fields_exact": exact_numeric,
        "numeric_field_count": len(numeric), "numeric_comparisons": numeric,
        "nonnumeric_differing_variables": nonnumeric_diffs,
        "global_attribute_differences": attr_diffs,
        "variable_attribute_differences": variable_attribute_differences,
        "variable_metadata_match": variable_metadata_match,
        "metadata_status": "MATCH" if not attr_diffs and dims_match and variable_metadata_match else
                           ("ONLY_ALLOWED_CLOCK_ANCHORS_DIFFER" if not nonclock_attr_diffs and dims_match and variable_metadata_match else "DIFFERENT"),
        "other_global_attribute_differences": nonclock_attr_diffs,
        "overall_status": "PASS_EXACT_FIELDS" if not missing and not extra and dims_match and exact_numeric and not nonnumeric_diffs and not nonclock_attr_diffs and variable_metadata_match else "DIFFERENCES_RECORDED",
    }


def validate_restart_run(case: Path, expected_options: list[int]) -> dict:
    logs = sorted(case.glob("rsl.error.[0-9][0-9][0-9][0-9]"))
    if len(logs) != 4:
        raise RuntimeError(f"expected four rank logs; found {len(logs)}")
    bad = [p.name for p in logs if "SUCCESS COMPLETE WRF" not in p.read_text(errors="replace")]
    if bad:
        raise RuntimeError(f"rank success marker missing: {bad}")
    output = case / CONTINUOUS_NAME
    if not output.is_file() or read_times(output) != ["2010-06-11_13:00:00"]:
        raise RuntimeError("restart run did not produce exact 13:00 history")
    with netCDF4.Dataset(output) as ds:
        opts = [int(ds.getncattr(k)) for k in ("RA_LW_PHYSICS", "RA_SW_PHYSICS", "MP_PHYSICS")]
        if opts != expected_options:
            raise RuntimeError(f"restart history options {opts} != expected {expected_options}")
        for var in ds.variables.values():
            if np.issubdtype(var.dtype, np.number):
                vals = np.ma.asarray(var[:]); raw = vals.compressed()
                if raw.size and not np.isfinite(raw).all():
                    raise RuntimeError(f"nonfinite restarted field {var.name}")
    return {"rank_success_logs": [x.name for x in logs], "history_time": "2010-06-11_13:00:00",
            "physics_options": opts, "history_sha256": sha(output)}


def execute() -> bool:
    pf = HERE / "preflight.json"
    if not pf.is_file() or not OUT.is_dir():
        raise RuntimeError("prepare restart cases first")
    if (HERE / "execution.json").exists():
        raise RuntimeError("restart execution receipt already exists; refusing repeat")
    plan = json.loads(pf.read_text())
    if plan["status"] != "PREPARED_NOT_RUN" or validate_pins() != plan["pins"]:
        raise RuntimeError("pinned source/case state drifted since restart preflight")
    lock = (HERE / "run.lock").open("a+"); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("WRF_RRTMGP_") or key.startswith("WRF_UDM_BOUNDARY_CAPTURE"):
            env.pop(key, None)
    env.update({"OMP_NUM_THREADS":"1", "OMP_STACKSIZE":"512M", "OMP_DYNAMIC":"FALSE",
                "OPENBLAS_NUM_THREADS":"1", "MPICH_INTERFACE_HOSTNAME":"127.0.0.1",
                "LD_LIBRARY_PATH":f"{NETCDF_LIB}:{env.get('LD_LIBRARY_PATH','')}"})
    receipt = {"status":"RUNNING", "started_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
               "executable_sha256":sha(EXE), "preflight_sha256":sha(pf), "arms":{}}
    (HERE / "execution.json").write_text(json.dumps(receipt,indent=2)+"\n")
    ok = True
    try:
        for name in ("ra4", "ra37"):
            case = OUT / name
            expected_state = plan["cases"][name]["staged_immutable_state"]
            if immutable_state(case) != expected_state:
                raise RuntimeError(f"staged case assets changed before launch: {name}")
            stale_restarts = [p.name for p in case.glob("wrfrst_d01_*") if p.name != CHECKPOINT_NAME]
            if any(case.glob("rsl.*")) or any(case.glob("wrfout_d01_*")) or stale_restarts:
                raise RuntimeError(f"stale output exists in {case}")
            command = [str(MPIEXEC),"-launcher","fork","-iface","lo","-n","4",str(EXE)]
            arm = {"command":command, "source_pins_before":validate_pins()["sha256"]}
            receipt["arms"][name] = arm
            try:
                with (case/"run.log").open("wb") as log:
                    proc = subprocess.run(command,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT,check=False)
                arm["returncode"] = proc.returncode
                if proc.returncode:
                    raise RuntimeError(f"launcher exited {proc.returncode}")
                arm["run_validation"] = validate_restart_run(case, [4,4,27] if name == "ra4" else [37,37,27])
                comparison = compare_history(CASES/name/CONTINUOUS_NAME, case/CONTINUOUS_NAME)
                arm["comparison"] = comparison
                arm["staged_immutable_state_after"] = immutable_state(case)
                arm["staged_assets_unchanged"] = arm["staged_immutable_state_after"] == expected_state
                arm["source_pins_after"] = validate_pins()["sha256"]
                arm["source_pins_match"] = arm["source_pins_before"] == arm["source_pins_after"]
                arm["status"] = "PASS" if comparison["overall_status"] == "PASS_EXACT_FIELDS" and arm["source_pins_match"] and arm["staged_assets_unchanged"] else "DIFFERENCES_RECORDED"
                if arm["status"] != "PASS":
                    ok = False
            except Exception as exc:
                arm["status"] = "FAILED"
                arm["failure"] = f"{type(exc).__name__}: {exc}"
                ok = False
            (HERE / "execution.json").write_text(json.dumps(receipt,indent=2)+"\n")
            if not ok:
                break
        receipt["status"] = "BOTH_ARMS_PASS" if ok else "FAILURE_OR_DIFFERENCES_RECORDED"
    except Exception as exc:
        receipt["status"] = "FAILED_RUNNER_PREFLIGHT_OR_EXECUTION"
        receipt.setdefault("failures", []).append(f"{type(exc).__name__}: {exc}")
        ok = False
    finally:
        receipt["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
        (HERE / "execution.json").write_text(json.dumps(receipt,indent=2)+"\n")
    return ok


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare",action="store_true")
    g.add_argument("--execute",action="store_true")
    a=p.parse_args()
    try:
        if a.prepare:
            prepare(validate_pins())
            print(f"Prepared only: {HERE / 'preflight.json'}")
        elif not execute():
            print(f"Restart differences/failure recorded: {HERE / 'execution.json'}",file=sys.stderr)
            return 1
        else:
            print(f"Restart checks passed: {HERE / 'execution.json'}")
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
