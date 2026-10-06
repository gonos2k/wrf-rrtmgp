#!/usr/bin/env python3
"""Prepare, and only with --execute run, an isolated 12 h + 1 h frozen-WRF restart trial."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from netCDF4 import Dataset
import numpy as np

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm-frozen-runtime-mpi")
PLAN = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm-frozen-restart-plan")
CASE = ROOT / "case-mode1"
BINARY = ROOT / "WRF/main/wrf.exe"
BUILD_RECEIPT = ROOT / "build-receipt.json"
TABLE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm-frozen-runtime-wrf/source/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc")
REF_OUT = CASE / "wrfout_d01_2010-06-11_13:00:00"
RESTART_NAME = "wrfrst_d01_2010-06-11_12:00:00"
CHECKPOINT_TIME = "2010-06-11_12:00:00"
COMPARE_TIME = "2010-06-11_13:00:00"
MPICH = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/mpich-sock")
NETCDF = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf")
ROOT_LIB = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/root/usr/lib/x86_64-linux-gnu")
DYNAMIC_RE = re.compile(r"^(?:wrfout_|wrfrst_|rsl\.|namelist\.output$|wrf-mode1-|.*\.log$)")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def decode_times(values: Any) -> str:
    arr = np.asarray(values)
    if arr.ndim == 2 and arr.shape[0] == 1:
        return b"".join(arr[0].tolist()).decode("ascii")
    if arr.ndim == 1:
        return b"".join(arr.tolist()).decode("ascii")
    raise RuntimeError(f"expected one clock string, got Times shape {arr.shape}")


def check_restart_clock(path: Path, expected_time: str, expected_step: int) -> dict[str, Any]:
    with Dataset(path, "r") as ds:
        if "Times" not in ds.variables:
            raise RuntimeError(f"checkpoint lacks Times: {path}")
        times = decode_times(ds.variables["Times"][:])
        if times != expected_time:
            raise RuntimeError(f"checkpoint Times={times}, expected {expected_time}")
        observed: dict[str, Any] = {"Times": times}
        for name, expected in (("ITIMESTEP", expected_step), ("XTIME", float(expected_step))):
            if name in ds.variables:
                raw = np.asarray(ds.variables[name][:]).reshape(-1)
            elif name in ds.ncattrs():
                raw = np.asarray(ds.getncattr(name)).reshape(-1)
            else:
                raise RuntimeError(f"checkpoint missing required clock field {name}")
            if raw.size != 1 or not np.isfinite(raw[0]) or float(raw[0]) != float(expected):
                raise RuntimeError(f"checkpoint {name}={raw.tolist()}, expected {expected}")
            observed[name] = raw.tolist()
        for name in ("JULYR", "JULDAY"):
            if name in ds.variables:
                observed[name] = np.asarray(ds.variables[name][:]).tolist()
            elif name in ds.ncattrs():
                value = ds.getncattr(name)
                observed[name] = value.item() if isinstance(value, np.generic) else value
        observed["dimensions"] = {k: len(v) for k, v in ds.dimensions.items()}
        return observed


def set_namelist_values(text: str, group: str, values: dict[str, str]) -> str:
    start = re.search(rf"(?im)^\s*&{re.escape(group)}\b", text)
    if not start:
        raise RuntimeError(f"namelist group &{group} not found")
    end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", text[start.end():])
    if not end_match:
        raise RuntimeError(f"namelist group &{group} has no closing slash")
    end = start.end() + end_match.start()
    block = text[start.start():end]
    for key, value in values.items():
        pattern = re.compile(rf"(?im)^(\s*{re.escape(key)}\s*=\s*)([^!\n]*)(.*)$")
        block, count = pattern.subn(lambda m: m.group(1) + value + m.group(3), block)
        if count != 1:
            raise RuntimeError(f"expected one {key} in &{group}, found {count}")
    return text[:start.start()] + block + text[end:]


def namelist_for(start_hour: int, end_hour: int, restart: bool, restart_interval: int) -> str:
    source = (CASE / "namelist.input").read_text(encoding="ascii")
    tc = {
        "run_days": "0",
        "run_hours": str(end_hour - start_hour),
        "run_minutes": "0",
        "run_seconds": "0",
        "start_year": "2010, 2010",
        "start_month": "06, 06",
        "start_day": "11, 11",
        "start_hour": f"{start_hour:02d}, {start_hour:02d}",
        "start_minute": "00, 00",
        "start_second": "00, 00",
        "end_year": "2010, 2010",
        "end_month": "06, 06",
        "end_day": "11, 11",
        "end_hour": f"{end_hour:02d}, {end_hour:02d}",
        "end_minute": "00, 00",
        "end_second": "00, 00",
        "restart": ".true." if restart else ".false.",
        "restart_interval": str(restart_interval),
    }
    return set_namelist_values(source, "time_control", tc)


def materialize_run_dir(target: Path, start_hour: int, end_hour: int, restart: bool,
                        restart_interval: int) -> None:
    if target.exists():
        raise RuntimeError(f"refusing to overwrite existing scratch run directory: {target}")
    target.mkdir(parents=True)
    for entry in CASE.iterdir():
        if entry.name in {"namelist.input", "preparation-receipt.json"} or DYNAMIC_RE.match(entry.name):
            continue
        if entry.name in {"wrfinput_d01", "wrfbdy_d01"} or entry.is_symlink():
            if not entry.exists():
                raise RuntimeError(f"static case input is missing/broken: {entry}")
            (target / entry.name).symlink_to(entry.resolve(strict=True))
        elif entry.is_file():
            (target / entry.name).symlink_to(entry.resolve(strict=True))
        elif entry.is_dir():
            (target / entry.name).symlink_to(entry.resolve(strict=True), target_is_directory=True)
    (target / "wrf.exe").symlink_to(BINARY.resolve(strict=True))
    (target / "namelist.input").write_text(
        namelist_for(start_hour, end_hour, restart, restart_interval), encoding="ascii")


def expected_decomposition(run_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    expected_tiles = {
        0: (1, 145, 1, 95),
        1: (146, 290, 1, 95),
        2: (1, 145, 96, 190),
        3: (146, 290, 96, 190),
    }
    for rank in range(4):
        path = run_dir / f"rsl.error.{rank:04d}"
        if not path.is_file():
            raise RuntimeError(f"missing MPI rank log {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"Ntasks in X\s+(\d+)\s*,\s*ntasks in Y\s+(\d+)", text)
        if not m or (int(m.group(1)), int(m.group(2))) != (2, 2):
            raise RuntimeError(f"rank {rank} did not report expected 2x2 MPI decomposition")
        tile = re.search(r"WRF TILE\s+1 IS\s+(\d+) IE\s+(\d+) JS\s+(\d+) JE\s+(\d+)", text)
        if not tile:
            raise RuntimeError(f"rank {rank} has no WRF TILE record")
        bounds = tuple(int(x) for x in tile.groups())
        if bounds != expected_tiles[rank]:
            raise RuntimeError(f"rank {rank} tile={bounds}, expected {expected_tiles[rank]}")
        result[str(rank)] = {"mpi_grid": [2, 2], "tile_i_j_bounds": list(bounds)}
    return result


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(MPICH / "bin") + os.pathsep + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = os.pathsep.join((str(MPICH / "lib"), str(NETCDF / "lib"), str(ROOT_LIB),
                                              "/usr/lib/x86_64-linux-gnu", env.get("LD_LIBRARY_PATH", "")))
    env["NETCDF"] = str(NETCDF)
    env["MPICH_INTERFACE_HOSTNAME"] = "127.0.0.1"
    env["OMP_NUM_THREADS"] = "1"
    env.pop("WRF_RRTMGP_TRACE_DIR", None)
    env.pop("WRF_RRTMGP_TRACE_PHASE", None)
    return env


def execute(run_dir: Path, log_name: str) -> None:
    command = ["mpiexec", "-launcher", "fork", "-iface", "lo", "-n", "4", "./wrf.exe"]
    with (run_dir / log_name).open("w", encoding="utf-8") as out:
        proc = subprocess.run(command, cwd=run_dir, env=runtime_env(), stdout=out,
                              stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{command} exited {proc.returncode}; inspect {run_dir / log_name}")
    rsl0 = (run_dir / "rsl.error.0000").read_text(encoding="utf-8", errors="replace")
    if "SUCCESS COMPLETE WRF" not in rsl0:
        raise RuntimeError(f"WRF success marker missing in {run_dir / 'rsl.error.0000'}")
    expected_decomposition(run_dir)


def immutable_snapshot(expected: dict[str, str]) -> dict[str, Any]:
    observed: dict[str, str] = {}
    missing: list[str] = []
    for name in expected:
        path = Path(name)
        if not path.is_file():
            missing.append(name)
        else:
            observed[name] = sha256(path)
    mismatches = {name: {"expected": digest, "observed": observed.get(name)}
                  for name, digest in expected.items() if observed.get(name) != digest}
    return {"passed": not missing and not mismatches, "sha256": observed,
            "missing": missing, "mismatches": mismatches}


def write_run_receipt(receipt: dict[str, Any]) -> None:
    path = PLAN / "restart-run-receipt.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def preflight() -> dict[str, Any]:
    receipt = json.loads(BUILD_RECEIPT.read_text(encoding="utf-8"))
    if receipt.get("status") != "BUILD_PASS_PREPARED_MODE1_CASE_NOT_RUN":
        raise RuntimeError(f"unexpected build receipt status: {receipt.get('status')}")
    want_binary = receipt["executables"]["wrf.exe"]["sha256"]
    if sha256(BINARY) != want_binary:
        raise RuntimeError("wrf.exe no longer matches frozen build receipt")
    source_hashes = []
    immutable_assets: dict[str, str] = {str(BINARY): want_binary}
    for item in receipt["production_sources"]:
        path = ROOT / item["path"]
        actual = sha256(path)
        if actual != item["sha256"]:
            raise RuntimeError(f"source file changed since build: {item['path']}")
        source_hashes.append({"path": str(path), "sha256": actual})
        immutable_assets[str(path)] = actual
    for key in ("wrfinput_d01", "wrfbdy_d01"):
        item = receipt["case"]["prepared_inputs"][key]
        if sha256(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"{key} no longer matches prepared-case hash")
        immutable_assets[str(Path(item["path"]))] = item["sha256"]
    if sha256(TABLE) != receipt["case"]["table_sha256"]:
        raise RuntimeError("frozen table no longer matches build receipt")
    immutable_assets[str(TABLE)] = receipt["case"]["table_sha256"]
    if sha256(CASE / "namelist.input") != receipt["case"]["namelist_sha256"]:
        raise RuntimeError("existing mode1 namelist changed since preparation")
    immutable_assets[str(CASE / "namelist.input")] = receipt["case"]["namelist_sha256"]
    if not REF_OUT.is_file():
        raise RuntimeError(f"continuous reference output not present: {REF_OUT}")
    ref_clock = check_restart_clock(REF_OUT, COMPARE_TIME, 780)
    immutable_assets[str(REF_OUT)] = sha256(REF_OUT)
    driver_path = Path(__file__).resolve()
    comparator_path = (PLAN / "compare_restart_outputs.py").resolve()
    immutable_assets[str(driver_path)] = sha256(driver_path)
    immutable_assets[str(comparator_path)] = sha256(comparator_path)
    boundary_times: dict[str, list[str]] = {}
    with Dataset(CASE / "wrfbdy_d01", "r") as bdy:
        for role, needle in (("current", "thisbdytime"), ("next", "nextbdytime")):
            matches = [name for name in bdy.variables if needle in name.lower()]
            if len(matches) != 1:
                raise RuntimeError(f"expected one {needle} boundary clock variable, found {matches}")
            vals = np.asarray(bdy.variables[matches[0]][:])
            boundary_times[role] = [decode_times(vals[i:i + 1]) for i in range(vals.shape[0])]
    if "2010-06-12_00:00:00" not in boundary_times["next"]:
        raise RuntimeError("boundary metadata does not cover through the 24-hour endpoint")
    return {
        "source_base_commit": receipt["source_base_commit"],
        "production_source_hashes": source_hashes,
        "immutable_assets_sha256": immutable_assets,
        "tool_hashes": {"runner_sha256": immutable_assets[str(driver_path)],
                        "comparator_sha256": immutable_assets[str(comparator_path)]},
        "binary": {"path": str(BINARY), "sha256": sha256(BINARY)},
        "table": {"path": str(TABLE), "sha256": sha256(TABLE)},
        "wrfinput": {"path": str(CASE / "wrfinput_d01"), "sha256": sha256(CASE / "wrfinput_d01")},
        "wrfbdy": {"path": str(CASE / "wrfbdy_d01"), "sha256": sha256(CASE / "wrfbdy_d01")},
        "mode1_namelist": {"path": str(CASE / "namelist.input"), "sha256": sha256(CASE / "namelist.input")},
        "continuous_13h_reference": {"path": str(REF_OUT), "sha256": sha256(REF_OUT)},
        "continuous_13h_clock_fields": ref_clock,
        "observed_initial_mpi_decomposition": expected_decomposition(CASE),
        "planned_namelists": {
            "0to12_sha256": hashlib.sha256(namelist_for(0, 12, False, 720).encode("ascii")).hexdigest(),
            "12to13_sha256": hashlib.sha256(namelist_for(12, 13, True, 720).encode("ascii")).hexdigest(),
            "only_time_control_changes": ["run_days", "run_hours", "run_minutes", "run_seconds",
                                           "start_year", "start_month", "start_day", "start_hour",
                                           "start_minute", "start_second", "end_year", "end_month",
                                           "end_day", "end_hour", "end_minute", "end_second",
                                           "restart", "restart_interval"],
        },
        "time_step_seconds": 60,
        "checkpoint": {"time": CHECKPOINT_TIME, "xtime_minutes": 720, "timestep_index": 720},
        "comparison_time": {"time": COMPARE_TIME, "xtime_minutes": 780, "timestep_index": 780},
        "mpi": {"ranks": 4, "observed_grid": [2, 2], "tile_strategy": "1D-Y", "threads_per_rank": 1},
        "runtime_libraries": {"mpich": str(MPICH), "netcdf": str(NETCDF), "root_dependency_lib": str(ROOT_LIB)},
        "boundary_coverage": {
            "interval_seconds": 21600,
            "current_bdytime_metadata": boundary_times["current"],
            "next_bdytime_metadata": boundary_times["next"],
            "supports_requested_12_to_13h_segment": True,
        },
    }


def prepare() -> tuple[Path, Path]:
    first = PLAN / "trial-mode1-0to12"
    second = PLAN / "trial-mode1-12to13"
    materialize_run_dir(first, 0, 12, False, 720)
    materialize_run_dir(second, 12, 13, True, 720)
    return first, second


def run(first: Path, second: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    immutable = receipt["immutable_assets_sha256"]
    receipt.update({"status": "RUNNING", "stage": "starting", "stage_asset_checks": []})
    write_run_receipt(receipt)
    checkpoint: Path | None = None
    restarted_out: Path | None = None
    try:
        execute(first, "wrf-mode1-0to12-mpi4.stdout.log")
        receipt["stage"] = "first_segment_complete"
        receipt["stage_asset_checks"].append({"stage": receipt["stage"], **immutable_snapshot(immutable)})
        checkpoint = first / RESTART_NAME
        if not checkpoint.is_file():
            raise RuntimeError(f"checkpoint was not written at 12 h: {checkpoint}")
        checkpoint_meta = check_restart_clock(checkpoint, CHECKPOINT_TIME, 720)
        receipt["checkpoint"] = {"path": str(checkpoint), "sha256": sha256(checkpoint), **checkpoint_meta}
        (second / RESTART_NAME).symlink_to(checkpoint.resolve(strict=True))
        write_run_receipt(receipt)

        execute(second, "wrf-mode1-12to13-mpi4.stdout.log")
        receipt["stage"] = "restart_segment_complete"
        receipt["stage_asset_checks"].append({"stage": receipt["stage"], **immutable_snapshot(immutable)})
        restarted_out = second / f"wrfout_d01_{COMPARE_TIME}"
        if not restarted_out.is_file():
            raise RuntimeError(f"restart run did not write {COMPARE_TIME}: {restarted_out}")
        report_path = PLAN / "restart-output-comparison.json"
        comparator = PLAN / "compare_restart_outputs.py"
        comparison_proc = subprocess.run(
            [sys.executable, str(comparator), str(REF_OUT), str(restarted_out),
             "--expected-time", COMPARE_TIME, "--report", str(report_path)], check=False)
        if not report_path.is_file():
            raise RuntimeError(f"comparator did not write its report (exit {comparison_proc.returncode})")
        comparison = json.loads(report_path.read_text(encoding="utf-8"))
        receipt.update({
            "status": "PASS" if comparison["passed"] else "FAIL",
            "comparison": {"passed": comparison["passed"],
                           "dynamics_passed": comparison["dynamics_passed"],
                           "metadata_match": comparison["metadata_match"],
                           "metadata_differences": comparison["metadata_differences"],
                           "variable_differences": comparison["variable_differences"],
                           "errors": comparison["errors"]},
            "restart_output": {"path": str(restarted_out), "sha256": sha256(restarted_out)},
            "continuous_13h_reference": {"path": str(REF_OUT), "sha256": sha256(REF_OUT)},
            "stage1_decomposition": expected_decomposition(first),
            "stage2_decomposition": expected_decomposition(second),
            "comparison_report": str(report_path),
        })
        return receipt
    except Exception as exc:
        receipt["status"] = "FAIL"
        receipt["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        final_check = immutable_snapshot(immutable)
        receipt["final_immutable_asset_check"] = final_check
        if not final_check["passed"]:
            receipt["status"] = "FAIL"
        receipt["final_asset_hashes"] = final_check["sha256"]
        if checkpoint is not None and checkpoint.is_file():
            receipt.setdefault("checkpoint_final_sha256", sha256(checkpoint))
        if restarted_out is not None and restarted_out.is_file():
            receipt.setdefault("restart_output_final_sha256", sha256(restarted_out))
        write_run_receipt(receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--inspect", action="store_true", help="verify current source/assets and refresh the plan receipt only")
    action.add_argument("--prepare", action="store_true", help="materialize isolated run directories only")
    action.add_argument("--execute", action="store_true", help="run both WRF segments; requires a prepared or empty trial root")
    args = parser.parse_args()
    PLAN.mkdir(parents=True, exist_ok=True)
    receipt = preflight()
    (PLAN / "preflight-plan.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.inspect:
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.prepare:
        first, second = prepare()
        print(f"Prepared isolated run directories only:\n  {first}\n  {second}\nNo forecast was launched.")
        return 0
    first, second = PLAN / "trial-mode1-0to12", PLAN / "trial-mode1-12to13"
    if not first.exists() and not second.exists():
        first, second = prepare()
    if not first.is_dir() or not second.is_dir():
        raise RuntimeError("both isolated run directories must be prepared before --execute")
    result = run(first, second, receipt)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
