#!/usr/bin/env python3
"""Pinned, opt-in REAL initialization runner for the Jan-2000 d01 met_em case."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
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
REPO = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP")
CASE = HERE / "case"
RECEIPT = HERE / "preflight-receipt.json"
VERIFY_RECEIPT = HERE / "preflight-verification.json"
RUN_RECEIPT = HERE / "run-receipt.json"
REAL = CASE / "real.exe"
NAMELIST = CASE / "namelist.input"
START = "2000-01-24_12:00:00"
END = "2000-01-25_12:00:00"
_START_DT = datetime(2000, 1, 24, 12)
EXPECTED_FORCING = [(_START_DT + timedelta(hours=h)).strftime("%Y-%m-%d_%H:%M:%S") for h in range(0, 25, 3)]
HYDROMETEORS = ("QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP", "QHAIL")
NUMBER_FIELDS = ("QNCCN", "QNCLOUD", "QNRAIN")  # Registry I/O names for qnn/qnc/qnr.
BOUNDARY_SUFFIXES = ("BXS", "BXE", "BYS", "BYE", "BTXS", "BTXE", "BTYS", "BTYE")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pins() -> dict:
    return json.loads(RECEIPT.read_text())


def current_static_pins() -> dict[str, str]:
    """Recompute every input/source/config/data pin recorded by preparation."""
    r = load_pins()
    observed: dict[str, str] = {}
    for item in r["static_files"]:
        p = Path(item["path"])
        if not p.is_file():
            raise FileNotFoundError(f"pinned file missing: {p}")
        if item.get("resolved_target") and str(p.resolve()) != item["resolved_target"]:
            raise RuntimeError(f"symlink target changed: {p} -> {p.resolve()}")
        got = sha256(p)
        if got != item["sha256"]:
            raise RuntimeError(f"pinned SHA mismatch for {p}: {got} != {item['sha256']}")
        observed[str(p)] = got
    for item in r["symlinks"]:
        p = Path(item["path"])
        if not p.is_symlink() or str(p.resolve()) != item["resolved_target"]:
            raise RuntimeError(f"pinned symlink changed: {p}")

    # Pin the actual committed source tree, not the generated untracked build products.
    src = Path(r["source_tree"])
    head = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD^{tree}"], text=True).strip()
    tracked_diff = subprocess.check_output(["git", "-C", str(src), "status", "--porcelain", "--untracked-files=no"], text=True)
    if head != r["source_commit"] or tree != r["source_tree_hash"] or tracked_diff.strip():
        raise RuntimeError(f"WRF tracked source/config tree changed: HEAD={head}, tree={tree}, status={tracked_diff!r}")
    return observed


def output_paths() -> list[Path]:
    exact = (CASE / "wrfinput_d01", CASE / "wrfbdy_d01", CASE / "namelist.output",
             CASE / "real.log", CASE / "rsl.error.0000", CASE / "rsl.out.0000",
             CASE / "pre-run-sha256.txt", CASE / "pre-run-pins.json", CASE / "execution.status")
    found = [p for p in exact if p.exists()]
    found.extend(CASE.glob("rsl.error.*"))
    found.extend(CASE.glob("rsl.out.*"))
    return sorted(set(found))


def decode_time_row(row) -> str:
    if isinstance(row, bytes):
        return row.decode("ascii").rstrip("\x00 ")
    vals = np.asarray(row)
    if vals.dtype.kind == "S":
        return b"".join(vals.tolist()).decode("ascii").rstrip("\x00 ")
    return "".join(str(x) for x in vals.tolist()).rstrip("\x00 ")


def validate_numeric_file(path: Path) -> dict:
    from netCDF4 import Dataset

    report = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size,
              "variables": 0, "numeric_variables": 0,
              "raw_nonfinite": 0, "decoded_nonfinite": 0, "masked_values": 0,
              "fill_value_hits": 0, "errors": []}
    with Dataset(path, "r") as ds:
        report["dimensions"] = {name: len(dim) for name, dim in ds.dimensions.items()}
        report["attrs"] = {k: ds.getncattr(k) for k in (
            "TITLE", "START_DATE", "SIMULATION_START_DATE", "WEST-EAST_GRID_DIMENSION",
            "SOUTH-NORTH_GRID_DIMENSION", "BOTTOM-TOP_GRID_DIMENSION", "NUM_LAND_CAT",
            "MMINLU", "MAP_PROJ", "DX", "DY", "MP_PHYSICS", "RA_LW_PHYSICS", "RA_SW_PHYSICS") if k in ds.ncattrs()}
        report["variables"] = len(ds.variables)
        for name, var in ds.variables.items():
            if not np.issubdtype(np.dtype(var.dtype), np.number):
                continue
            report["numeric_variables"] += 1
            # Inspect raw storage independently of netCDF4's scale/mask decoding.
            var.set_auto_maskandscale(False)
            raw = np.asarray(var[...])
            if np.issubdtype(raw.dtype, np.inexact):
                report["raw_nonfinite"] += int(np.size(raw) - np.isfinite(raw).sum())
            for attr in ("_FillValue", "missing_value"):
                if attr in var.ncattrs():
                    markers = np.asarray(var.getncattr(attr)).reshape(-1)
                    for marker in markers:
                        try:
                            report["fill_value_hits"] += int(np.count_nonzero(raw == marker))
                        except (TypeError, ValueError):
                            pass
            var.set_auto_maskandscale(True)
            decoded = np.ma.asarray(var[...])
            report["masked_values"] += int(np.ma.getmaskarray(decoded).sum())
            # Inspect decoded storage while retaining the mask count above; avoid filling
            # integer arrays with NaN, which NumPy rejects even when their mask is empty.
            data = np.asarray(np.ma.getdata(decoded) if np.ma.isMaskedArray(decoded) else decoded)
            if np.issubdtype(data.dtype, np.inexact):
                report["decoded_nonfinite"] += int(np.size(data) - np.isfinite(data).sum())
        if report["raw_nonfinite"] or report["decoded_nonfinite"] or report["masked_values"] or report["fill_value_hits"]:
            report["errors"].append("numeric variables contain nonfinite, masked, or fill/missing values")
    return report


def require_attr(ds, name: str, expected) -> None:
    if name not in ds.ncattrs():
        raise ValueError(f"missing required global attribute {name}")
    actual = ds.getncattr(name)
    if isinstance(expected, (int, float)):
        if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(f"{name}={actual!r}, expected {expected!r}")
    elif str(actual).strip() != str(expected):
        raise ValueError(f"{name}={actual!r}, expected {expected!r}")


def validate_outputs() -> dict:
    from netCDF4 import Dataset

    input_path, bdy_path = CASE / "wrfinput_d01", CASE / "wrfbdy_d01"
    if not input_path.is_file() or not bdy_path.is_file():
        raise FileNotFoundError("REAL did not create both wrfinput_d01 and wrfbdy_d01")
    report = {"wrfinput": validate_numeric_file(input_path), "wrfbdy": validate_numeric_file(bdy_path), "errors": []}
    for part in (report["wrfinput"], report["wrfbdy"]):
        if part["errors"]:
            report["errors"].extend(part["errors"])
    with Dataset(input_path, "r") as ds:
        for key, expected in {"WEST-EAST_GRID_DIMENSION": 74, "SOUTH-NORTH_GRID_DIMENSION": 61,
                              "BOTTOM-TOP_GRID_DIMENSION": 33, "NUM_LAND_CAT": 24, "MAP_PROJ": 1,
                              "DX": 30000.0, "DY": 30000.0, "MP_PHYSICS": 27,
                              "RA_LW_PHYSICS": 4, "RA_SW_PHYSICS": 4}.items():
            require_attr(ds, key, expected)
        require_attr(ds, "MMINLU", "USGS")
        if "REAL_EM" not in str(ds.getncattr("TITLE")):
            raise ValueError("wrfinput TITLE does not identify REAL_EM output")
        if str(ds.getncattr("START_DATE")).strip() != START:
            raise ValueError(f"wrfinput START_DATE mismatch: {ds.getncattr('START_DATE')!r}")
        expected_dims = {"Time": 1, "west_east": 73, "south_north": 60,
                         "bottom_top_stag": 33, "soil_layers_stag": 4}
        for name, length in expected_dims.items():
            if name not in ds.dimensions or len(ds.dimensions[name]) != length:
                raise ValueError(f"wrfinput dimension {name} expected {length}, observed {len(ds.dimensions[name]) if name in ds.dimensions else 'missing'}")
        if "bottom_top" not in ds.dimensions or len(ds.dimensions["bottom_top"]) != 32:
            raise ValueError("wrfinput mass-level count must be 32 for e_vert=33")
        if "Times" not in ds.variables or decode_time_row(ds.variables["Times"][0]) != START:
            raise ValueError("wrfinput Times does not match requested initialization time")
        for name in HYDROMETEORS + NUMBER_FIELDS:
            if name not in ds.variables:
                raise ValueError(f"wrfinput is missing required MP27 field {name}")
            if ds.variables[name].shape != (1, 32, 60, 73):
                raise ValueError(f"wrfinput {name} shape mismatch: {ds.variables[name].shape}")

    with Dataset(bdy_path, "r") as ds:
        for key, expected in {"WEST-EAST_GRID_DIMENSION": 74, "SOUTH-NORTH_GRID_DIMENSION": 61,
                              "BOTTOM-TOP_GRID_DIMENSION": 33, "NUM_LAND_CAT": 24, "MAP_PROJ": 1,
                              "DX": 30000.0, "DY": 30000.0, "MP_PHYSICS": 27,
                              "RA_LW_PHYSICS": 4, "RA_SW_PHYSICS": 4}.items():
            require_attr(ds, key, expected)
        require_attr(ds, "MMINLU", "USGS")
        if "REAL_EM" not in str(ds.getncattr("TITLE")):
            raise ValueError("wrfbdy TITLE does not identify REAL_EM output")
        if "Times" not in ds.variables:
            raise ValueError("wrfbdy lacks Times")
        times = [decode_time_row(row) for row in ds.variables["Times"][:]]
        report["boundary_times"] = times
        this_names = [n for n in ds.variables if "thisbdytime" in n.lower()]
        next_names = [n for n in ds.variables if "nextbdytime" in n.lower()]
        if len(this_names) != 1 or len(next_names) != 1:
            raise ValueError(f"wrfbdy has ambiguous boundary clocks: this={this_names}, next={next_names}")
        this_times = [decode_time_row(row) for row in ds.variables[this_names[0]][:]]
        next_times = [decode_time_row(row) for row in ds.variables[next_names[0]][:]]
        report["thisbdytime"] = this_times
        report["nextbdytime"] = next_times
        if times != EXPECTED_FORCING[:-1] or this_times != EXPECTED_FORCING[:-1] or next_times != EXPECTED_FORCING[1:]:
            raise ValueError("wrfbdy does not exactly span the eight 3-hour intervals through the final forcing time")
        if len(ds.dimensions.get("Time", [])) != 8:
            raise ValueError(f"expected eight boundary intervals; Time={len(ds.dimensions.get('Time', []))}")
        for name in HYDROMETEORS + NUMBER_FIELDS:
            for suffix in BOUNDARY_SUFFIXES:
                boundary_name = f"{name}_{suffix}"
                if boundary_name not in ds.variables:
                    raise ValueError(f"wrfbdy is missing required MP27 boundary field {boundary_name}")
    if report["errors"]:
        raise ValueError("NetCDF integrity check failed: " + "; ".join(report["errors"]))
    report["status"] = "REAL_OUTPUT_VALIDATION_PASS"
    return report


def atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=jsonable) + "\n")
    tmp.replace(path)


def jsonable(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def set_stack_limit() -> None:
    requested = 512 * 1024 * 1024
    _soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    if hard != resource.RLIM_INFINITY and hard < requested:
        raise RuntimeError(f"hard stack limit {hard} is below required {requested}")
    resource.setrlimit(resource.RLIMIT_STACK, (requested, hard))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="execute the pinned REAL initialization (600 s max)")
    args = ap.parse_args()
    result = {"status": "PREFLIGHT_ONLY", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "execution_requested": bool(args.execute), "timeout_seconds": 600, "returncode": None,
              "timeout": False, "success_marker": False, "pins_before": {}, "pins_after": {}, "outputs": {}, "errors": []}
    proc = None
    log_path = CASE / "real.log"
    try:
        r = load_pins()
        if r["status"] != "PREPARED_NOT_EXECUTED":
            raise RuntimeError(f"unexpected preparation receipt status: {r['status']}")
        result["pins_before"] = current_static_pins()
        result["preexisting_outputs"] = [str(p) for p in output_paths()]
        if result["preexisting_outputs"]:
            raise FileExistsError("refusing to overwrite existing REAL outputs: " + ", ".join(result["preexisting_outputs"]))
        ld = (f"{REPO}/build/deps/netcdf/lib:{REPO}/build/deps/root/usr/lib/x86_64-linux-gnu:"
              f"{REPO}/build/deps/mpich-sock/lib:" + os.environ.get("LD_LIBRARY_PATH", ""))
        env = os.environ.copy()
        for k in list(env):
            if k.startswith("WRF_RRTMGP_") or k.startswith("WRF_UDM_BOUNDARY_CAPTURE"):
                env.pop(k)
        env.update({"ROOT_REPO": str(REPO), "LD_LIBRARY_PATH": ld, "OMP_NUM_THREADS": "1",
                    "OMP_DYNAMIC": "FALSE", "OMP_STACKSIZE": "512M", "OPENBLAS_NUM_THREADS": "1",
                    "MPICH_INTERFACE_HOSTNAME": "127.0.0.1"})
        ldd = subprocess.run(["ldd", str(REAL)], capture_output=True, text=True, env=env, check=False)
        result["ldd"] = {"returncode": ldd.returncode, "output": ldd.stdout, "stderr": ldd.stderr}
        if ldd.returncode or "not found" in ldd.stdout:
            raise RuntimeError("REAL shared-library preflight failed")
        result["command"] = [str(REPO / "build/deps/mpich-sock/bin/mpiexec"), "-launcher", "fork",
                              "-iface", "lo", "-n", "1", "./real.exe"]
        result["environment"] = {k: env[k] for k in ("LD_LIBRARY_PATH", "OMP_NUM_THREADS", "OMP_DYNAMIC",
                                  "OMP_STACKSIZE", "OPENBLAS_NUM_THREADS", "MPICH_INTERFACE_HOSTNAME")}
        stack_soft, stack_hard = resource.getrlimit(resource.RLIMIT_STACK)
        result["stack_limit"] = {"child_soft_bytes": 512 * 1024 * 1024,
                                 "parent_soft_bytes": stack_soft, "parent_hard_bytes": stack_hard,
                                 "set_in_child_preexec": True}
        if not args.execute:
            result["status"] = "PREFLIGHT_PASS_NOT_EXECUTED"
        else:
            if RUN_RECEIPT.exists() or log_path.exists() or (CASE / "pre-run-sha256.txt").exists():
                raise FileExistsError("run evidence already exists; refusing a second execution")
            (CASE / "pre-run-pins.json").write_text(json.dumps({
                "pins": result["pins_before"], "namelist_sha256": sha256(NAMELIST),
                "command": result["command"], "environment": result["environment"]}, indent=2, sort_keys=True) + "\n")
            with log_path.open("wb") as log:
                proc = subprocess.Popen(result["command"], cwd=CASE, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, start_new_session=True,
                                        preexec_fn=set_stack_limit)
                try:
                    result["returncode"] = proc.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    result["timeout"] = True
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    result["returncode"] = proc.returncode
            combined = log_path.read_text(errors="replace")
            for p in sorted(CASE.glob("rsl.error.*")):
                combined += "\n" + p.read_text(errors="replace")
            result["success_marker"] = "SUCCESS COMPLETE REAL_EM INIT" in combined
            result["fatal_marker"] = bool(re.search(r"FATAL|forrtl: severe|SIGSEGV|segmentation fault", combined, re.I))
            result["log"] = {"path": str(log_path), "sha256": sha256(log_path), "bytes": log_path.stat().st_size}
            if result["returncode"] != 0 or result["timeout"] or not result["success_marker"] or result["fatal_marker"]:
                result["status"] = "REAL_EXECUTION_FAILED"
                if result["returncode"] == 0 and not result["success_marker"]:
                    result["errors"].append("return code was zero but SUCCESS COMPLETE REAL_EM INIT was absent")
            else:
                result["outputs"] = validate_outputs()
                result["status"] = "REAL_INIT_PASS" if result["outputs"].get("status") == "REAL_OUTPUT_VALIDATION_PASS" else "REAL_OUTPUT_VALIDATION_FAILED"
    except Exception as exc:
        result["status"] = ("REAL_OUTPUT_VALIDATION_FAILED" if result.get("success_marker")
                            else "PREFLIGHT_OR_EXECUTION_FAILED")
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        result["traceback"] = traceback.format_exc()
    finally:
        try:
            result["pins_after"] = current_static_pins()
            result["pins_unchanged"] = result["pins_before"] == result["pins_after"]
            if result["pins_before"] and not result["pins_unchanged"]:
                result["errors"].append("immutable pins changed during REAL preflight/execution")
                result["status"] = "PIN_DRIFT_FAILURE"
        except Exception as exc:
            result["pins_after_error"] = f"{type(exc).__name__}: {exc}"
            result["status"] = "PIN_DRIFT_FAILURE"
        result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if log_path.exists():
            result.setdefault("log", {"path": str(log_path), "sha256": sha256(log_path), "bytes": log_path.stat().st_size})
        atomic_json(VERIFY_RECEIPT if not args.execute else RUN_RECEIPT, result)
    print(json.dumps({"status": result["status"], "execution_requested": args.execute,
                      "receipt": str(RUN_RECEIPT if args.execute else VERIFY_RECEIPT),
                      "errors": result.get("errors", [])}, indent=2, default=jsonable))
    return 0 if result["status"] in ("PREFLIGHT_PASS_NOT_EXECUTED", "REAL_INIT_PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
