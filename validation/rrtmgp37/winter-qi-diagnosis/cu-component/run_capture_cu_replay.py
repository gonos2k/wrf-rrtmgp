#!/usr/bin/env python3
"""Prepare an isolated one-arm Jan-2000 winter QI capture replay.

The default action only stages and verifies a fresh directory. --execute is
intentionally separate so a reviewer can inspect the staged case first.
"""
from __future__ import annotations
import argparse
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

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
BASE = BUILD / "udm-alternate-jan2000-data/paired-forecast-v2/ra37"
MANIFEST = BUILD / "udm-alternate-jan2000-data/paired-forecast-v2/runtime-link-manifest.json"
EXECUTABLE = BUILD / "udm-winter-cu-adjustment/source/WRF/main/wrf.exe"
MPIEXEC = BUILD / "deps/mpich-sock/bin/mpiexec"
ORIGINAL_HISTORY = BASE / "wrfout_d01_2000-01-24_12:00:00"
INPUT_SHA = "0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637"
BDY_SHA = "ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4"
NAMELIST_SHA = "37806b6230d9a9479bae32611b6b70d0318ce852fe3931af84ba1e7a15bdcc58"
TABLE_SHA = "8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583"
IOFIELDS_SHA = "3890e55c599314f0fddb56585d64164eebaf70b2280589aa679439bc35b505c3"
HISTORY_SHA = "e3fa7be56062c640e52f66c73aaa0bd798d56f0809c1d4501e3b4a0c9c227e4c"
FATAL_QI = -5.623554244493789e-8
FATAL_RANK_LOG_SHA = "2d70d7d1ad0472450bf824eeef8a504e88b67c03c6c2ed3a05173f260caef0cc"
EXPECTED_EXE_SHA = "640d0128e099aaaebf30b5d2a2fdd8f29772d328cb946b4f1b88d99ae5d2c6a8"
EXPECTED_MPIEXEC_SHA = "7cbfc90b3903375252de00c92fd0ec8d51274da76365028de5c6edd645416946"
EXPECTED_SOURCE_SHA = {
    "phys/module_radiation_driver.F": "560b9e13ff95ff93e6e08f28152140be2442863b6bbfeab3e6f2c6d3f5a90af5",
    "phys/udm_winter_capture.F": "3c67a4a476fe0cfae56af90eebd7c091b1be6e1176a3567fd661b27bbe1e168e",
    "phys/Makefile": "55f251d045e2dfb19a787e50a814a9072679a5c8d03268eba7b0af6edc7d161a",
    "phys/module_ra_rrtmg_lw.F": "28ad145fdd507a7e80e8a8cc8006a35224667b47f774d9395c3e58d286117a7c",
    "phys/module_microphysics_driver.F": "925af47f0c6d699d5330425b0c4d4479029af8f87c5cf4883aff8016e9ba9ef1",
    "dyn_em/solve_em.F": "172f69a40087b2aa4c66da602ff8409c15730c9ecbfd47a62341cf436b78ee74",
    "configure.wrf": "44f85b7fc9b6994cb3784567e69d310580740a021b5f1ab1efb0586f25cfcba2",
}
EXPECTED_TIMES = ["2000-01-24_12:00:00", "2000-01-24_13:00:00", "2000-01-24_14:00:00"]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def textrow(row) -> str:
    return b"".join(np.asarray(row).tolist()).decode("ascii").rstrip("\x00 ")


def verify_source_inputs() -> dict:
    expected = {"wrfinput_d01": INPUT_SHA, "wrfbdy_d01": BDY_SHA,
                "namelist.input": NAMELIST_SHA, "frozen-ice-psd-moments.nc": TABLE_SHA,
                ORIGINAL_HISTORY.name: HISTORY_SHA}
    result = {}
    for name, digest in expected.items():
        p = (BASE / name) if name != "frozen-ice-psd-moments.nc" else (BASE / name).resolve()
        if not p.is_file() or sha(p) != digest:
            raise RuntimeError(f"frozen source pin mismatch: {p}")
        result[name] = digest
    if sha(BASE / "radiation_iofields.txt") != IOFIELDS_SHA:
        raise RuntimeError("radiation output-request file hash mismatch")
    if not EXECUTABLE.is_file():
        raise RuntimeError(f"scratch executable missing: {EXECUTABLE}")
    if sha(EXECUTABLE) != EXPECTED_EXE_SHA:
        raise RuntimeError(f"scratch executable hash mismatch: {EXECUTABLE}")
    for log in (BASE / "rsl.error.0002",):
        if sha(log) != FATAL_RANK_LOG_SHA:
            raise RuntimeError(f"fatal-log source pin mismatch: {log}")
    manifest = json.loads(MANIFEST.read_text())
    for entry in manifest["arms"]["ra37"]:
        if entry["name"] in ("wrf.exe", "namelist.input") or entry.get("kind") == "arm_owned_file":
            continue
        target_text = entry.get("link_text", entry.get("resolved_target"))
        if not target_text:
            raise RuntimeError(f"runtime manifest target is absent for {entry['name']}")
        target = Path(target_text)
        if not target.exists() or sha(target) != entry["sha256"]:
            raise RuntimeError(f"runtime asset hash mismatch: {target}")
    source_root = EXECUTABLE.parents[1]
    source_hashes = {}
    for rel, wanted in EXPECTED_SOURCE_SHA.items():
        p = source_root / rel
        if not p.is_file():
            raise RuntimeError(f"scratch source file is absent: {p}")
        source_hashes[rel] = sha(p)
        if source_hashes[rel] != wanted:
            raise RuntimeError(f"scratch source pin mismatch: {p}")
    if not MPIEXEC.is_file():
        raise RuntimeError(f"pinned MPICH launcher missing: {MPIEXEC}")
    if sha(MPIEXEC) != EXPECTED_MPIEXEC_SHA:
        raise RuntimeError(f"pinned MPICH launcher hash mismatch: {MPIEXEC}")
    result["scratch_executable_sha256"] = sha(EXECUTABLE)
    result["scratch_source_sha256"] = source_hashes
    result["runtime_manifest_sha256"] = sha(MANIFEST)
    result["runtime_assets_sha256"] = {entry["name"]: entry["sha256"]
                                       for entry in manifest["arms"]["ra37"]
                                       if entry["name"] not in ("wrf.exe", "namelist.input")}
    result["mpiexec_sha256"] = sha(MPIEXEC)
    return result


def stage_case(case: Path) -> dict:
    if case.exists():
        raise FileExistsError(f"refusing to overwrite replay case: {case}")
    pins = verify_source_inputs()
    manifest = json.loads(MANIFEST.read_text())
    case.mkdir(parents=True)
    links = []
    for entry in manifest["arms"]["ra37"]:
        name = entry["name"]
        if name in ("wrf.exe", "namelist.input") or entry.get("kind") == "arm_owned_file":
            continue
        target_text = entry.get("link_text", entry.get("resolved_target"))
        if not target_text:
            raise RuntimeError(f"runtime manifest has no target for {name}")
        target = Path(target_text)
        if not target.exists():
            raise RuntimeError(f"runtime asset missing: {target}")
        (case / name).symlink_to(str(target))
        links.append({"name": name, "target": str(target), "sha256": sha(target)})
    (case / "wrf.exe").symlink_to(EXECUTABLE)
    for name in ("namelist.input", "radiation_iofields.txt", "wrfinput_d01", "wrfbdy_d01"):
        src = BASE / name
        if not src.is_file():
            raise RuntimeError(f"case input missing: {src}")
        (case / name).write_bytes(src.read_bytes())
    for name in ("frozen-ice-psd-moments.nc", "rrtmgp_data"):
        src = BASE / name
        if not src.exists():
            raise RuntimeError(f"RRTMGP case asset missing: {src}")
        (case / name).symlink_to(os.readlink(src) if src.is_symlink() else str(src.resolve()))
    after = verify_source_inputs()
    if after != pins:
        raise RuntimeError("frozen inputs changed while staging")
    return {"source_pins": pins, "runtime_links": links,
            "special_links": {n: str((case / n).resolve()) for n in
                               ("frozen-ice-psd-moments.nc", "rrtmgp_data")},
            "copied_case_files": {n: sha(case / n) for n in
                                   ("namelist.input", "radiation_iofields.txt", "wrfinput_d01", "wrfbdy_d01")},
            "executable_sha256": sha(EXECUTABLE)}


def verify_staged_case(case: Path, staged: dict) -> None:
    if sha(case / "namelist.input") != NAMELIST_SHA:
        raise RuntimeError("staged replay namelist changed")
    if sha(case / "wrfinput_d01") != INPUT_SHA or sha(case / "wrfbdy_d01") != BDY_SHA:
        raise RuntimeError("staged replay input/boundary changed")
    if sha(case / "radiation_iofields.txt") != IOFIELDS_SHA:
        raise RuntimeError("staged radiation output-request file changed")
    if (case / "wrf.exe").resolve() != EXECUTABLE.resolve() or sha(case / "wrf.exe") != EXPECTED_EXE_SHA:
        raise RuntimeError("staged replay executable target/content changed")
    for entry in staged["runtime_links"]:
        link = case / entry["name"]
        if not link.is_symlink() or str(link.resolve()) != entry["target"]:
            raise RuntimeError(f"staged runtime symlink changed: {link}")
        if sha(link.resolve()) != entry["sha256"]:
            raise RuntimeError(f"staged runtime target changed: {link}")
    for name, target in staged["special_links"].items():
        link = case / name
        if not link.is_symlink() or str(link.resolve()) != target:
            raise RuntimeError(f"staged special runtime link changed: {link}")
        if name == "frozen-ice-psd-moments.nc" and sha(link.resolve()) != TABLE_SHA:
            raise RuntimeError("staged frozen optics table hash changed")


def ldd_output(path: Path) -> str:
    result = subprocess.run(["ldd", str(path)], text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    return result.stdout


def _attrs(var) -> dict:
    return {name: np.asarray(getattr(var, name)).tolist() if isinstance(getattr(var, name), np.ndarray)
            else str(getattr(var, name)) for name in var.ncattrs()}


def history_snapshot(path: Path) -> dict:
    with netCDF4.Dataset(path) as ds:
        times = [textrow(row) for row in ds.variables["Times"][:]]
        indices = [times.index(t) for t in EXPECTED_TIMES]
        variables = {}
        variable_attrs = {}
        for name, var in ds.variables.items():
            arr = np.ma.asarray(var[:])
            if arr.mask is not np.ma.nomask and np.any(arr.mask):
                raise RuntimeError(f"masked values in partial history {path}:{name}")
            if arr.dtype.kind in "f" and not np.isfinite(np.ma.getdata(arr)).all():
                raise RuntimeError(f"non-finite values in partial history {path}:{name}")
            axis = var.dimensions.index("Time") if "Time" in var.dimensions else None
            records = ([np.ascontiguousarray(np.ma.getdata(np.take(arr, idx, axis=axis))).tobytes().hex()
                        for idx in indices] if axis is not None else
                       [np.ascontiguousarray(np.ma.getdata(arr)).tobytes().hex()])
            variables[name] = {"axis": axis, "dtype": str(arr.dtype),
                               "dimensions": list(var.dimensions), "records": records}
            variable_attrs[name] = _attrs(var)
        return {"times": times, "dimensions": {k: len(v) for k,v in ds.dimensions.items()},
                "attrs": {name: str(getattr(ds, name)) for name in ds.ncattrs()},
                "variable_attrs": variable_attrs, "variables": variables}


def compare_partial_histories(path: Path) -> dict:
    baseline = history_snapshot(ORIGINAL_HISTORY)
    candidate = history_snapshot(path)
    if baseline["times"][:3] != EXPECTED_TIMES or candidate["times"][:3] != EXPECTED_TIMES:
        raise RuntimeError("partial history timestamps do not include 12:00/13:00/14:00")
    common = set(baseline["variables"]) & set(candidate["variables"])
    changed = [name for name in sorted(common)
               if baseline["variables"][name] != candidate["variables"][name]]
    attr_changed = [name for name in sorted(common)
                    if baseline["variable_attrs"][name] != candidate["variable_attrs"][name]]
    missing = sorted(set(baseline["variables"]) - set(candidate["variables"]))
    added = sorted(set(candidate["variables"]) - set(baseline["variables"]))
    dim_match = baseline["dimensions"] == candidate["dimensions"]
    global_attrs_equal = baseline["attrs"] == candidate["attrs"]
    return {"baseline_record_times": EXPECTED_TIMES, "candidate_record_times": EXPECTED_TIMES,
            "common_variables": len(common), "bitwise_equal_variables": len(common)-len(changed),
            "changed_variables": changed, "missing_variables": missing, "added_variables": added,
            "variable_attribute_differences": attr_changed,
            "dimensions_equal": dim_match, "global_attributes_equal": global_attrs_equal,
            "bitwise_equal": not (changed or missing or added or not dim_match)}


def child_limits():
    resource.setrlimit(resource.RLIMIT_STACK, (512 * 1024 * 1024, 512 * 1024 * 1024))


def run(case: Path, timeout_s: int) -> dict:
    capture = case / "capture"
    cu_capture = case / "cu_capture"
    capture.mkdir()
    cu_capture.mkdir()
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("WRF_RRTMGP_") or name.startswith("WRF_UDM_BOUNDARY_CAPTURE"):
            env.pop(name)
    env.update({"WRF_UDM_WINTER_CAPTURE_DIR": str(capture), "OMP_NUM_THREADS": "1",
                "OMP_DYNAMIC": "FALSE", "OMP_STACKSIZE": "512M", "OPENBLAS_NUM_THREADS": "1",
                "MPICH_INTERFACE_HOSTNAME": "127.0.0.1"})
    env["WRF_UDM_CU_CAPTURE_DIR"] = str(cu_capture)
    command = [str(MPIEXEC), "-launcher", "fork", "-iface", "lo", "-n", "4", "./wrf.exe"]
    ld_paths = [str(BUILD / "deps/netcdf/lib"),
                str(BUILD / "deps/root/usr/lib/x86_64-linux-gnu"),
                str(BUILD / "deps/mpich-sock/lib")]
    if env.get("LD_LIBRARY_PATH"):
        ld_paths.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = ":".join(ld_paths)
    start = time.time()
    rc = None
    error = None
    try:
        with (case / "launch.log").open("wb") as log:
            proc = subprocess.Popen(command, cwd=case, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, preexec_fn=child_limits)
            try:
                rc = proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                error = f"timeout after {timeout_s}s"
    except Exception:
        error = traceback.format_exc()
    logs = sorted(case.glob("rsl.error.*"))
    texts = {p.name: p.read_text(errors="replace") for p in logs}
    fatal = [(name, line.strip()) for name, text in texts.items() for line in text.splitlines()
             if "RRTMGP_INPUT_UDM_QI_NEGATIVE" in line]
    times = []
    outputs = list(case.glob("wrfout_d01_*"))
    comparison = None
    candidate_history_sha = None
    if outputs:
        candidate_history_sha = sha(outputs[0])
        if candidate_history_sha == HISTORY_SHA:
            times = list(EXPECTED_TIMES)
            comparison = {"bitwise_equal": True, "method": "whole-file SHA256 identity",
                          "common_variables": "authenticated by identical complete file bytes",
                          "baseline_sha256": HISTORY_SHA, "candidate_sha256": candidate_history_sha}
        else:
            try:
                with netCDF4.Dataset(outputs[0]) as ds:
                    times = [textrow(row) for row in ds.variables["Times"][:]]
                comparison = compare_partial_histories(outputs[0])
            except Exception as exc:
                comparison = {"bitwise_equal": False, "reader_error": repr(exc),
                              "candidate_sha256": candidate_history_sha}
    files = sorted(capture.glob("rank*.csv"))
    rad_match = []
    for p in files:
        for line in p.read_text(errors="replace").splitlines():
            fields = line.split()
            if len(fields) < 25 or fields[0] != "RAD_PRE_BUILDER":
                continue
            try:
                rank, domain, step, i, j, k = map(int, fields[2:8])
                seconds = float(fields[8])
                qi = float(fields[10])
            except ValueError:
                continue
            if (rank == int(p.stem[-4:]) and domain == 1 and i == 17 and j == 58 and k == 7
                    and abs(seconds - 10200.) < 0.01 and abs(qi - FATAL_QI) <= 1.e-20):
                rad_match.append({"rank": rank, "domain": domain, "step": step,
                                  "i": i, "j": j, "k": k, "seconds": seconds, "qi": qi,
                                  "temp_kind": fields[1]})
    matching_q = any(abs(float(m.group(1).replace("D", "E")) - FATAL_QI) <= 1.e-20
                     for _, line in fatal
                     if (m := re.search(r"value_kgkg=\s*([+-]?[0-9.eEdD+-]+)", line)))
    matching_fatal_rank = any(f"rsl.error.{row['rank']:04d}" == name
                              for row in rad_match for name, _ in fatal)
    return {"return_code": rc, "error": error, "elapsed_seconds": time.time()-start,
            "command": command, "fatal_lines": [{"log": n, "line": l} for n,l in fatal],
            "launch_environment": {k: env[k] for k in ("LD_LIBRARY_PATH", "OMP_NUM_THREADS", "OMP_DYNAMIC",
                                                          "OMP_STACKSIZE", "OPENBLAS_NUM_THREADS",
                                                          "MPICH_INTERFACE_HOSTNAME", "WRF_UDM_WINTER_CAPTURE_DIR",
                                                          "WRF_UDM_CU_CAPTURE_DIR")},
            "mpiexec_sha256": sha(MPIEXEC), "wrf_executable_sha256": sha(case / "wrf.exe"),
            "wrf_ldd": ldd_output(case / "wrf.exe"), "mpiexec_ldd": ldd_output(MPIEXEC),
            "rank_logs": {p.name: sha(p) for p in logs},
            "fatal_qi_matches_original": matching_q, "radiation_capture_matches_fatal": bool(rad_match),
            "radiation_capture_rows": rad_match, "fatal_rank_matches_radiation_capture": matching_fatal_rank,
            "history_times": times,
            "candidate_history_sha256": candidate_history_sha,
            "baseline_history_sha256": HISTORY_SHA,
            "whole_history_file_bitwise_equal": candidate_history_sha == HISTORY_SHA,
            "partial_history_comparison": comparison,
            "capture_files": [{"path": str(p), "sha256": sha(p), "rows": sum(1 for _ in p.open())} for p in files],
    "cu_capture_files": [{"path": str(p), "sha256": sha(p), "rows": sum(1 for _ in p.open())}
                                 for p in sorted(cu_capture.glob("cu_qi_adjust_rank*.csv"))],
            "expected_fatal_reproduced": bool(fatal and matching_q and rad_match and matching_fatal_rank
                                               and comparison and comparison["bitwise_equal"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=Path, required=True, help="fresh path; never reused")
    ap.add_argument("--timeout-seconds", type=int, default=600)
    ap.add_argument("--execute", action="store_true", help="run the model after staging; requires separate parent authorization")
    args = ap.parse_args()
    if args.timeout_seconds < 1 or args.timeout_seconds > 600:
        raise SystemExit("timeout must be within 1..600 seconds")
    case = args.case.resolve()
    receipt = {"status": "PREPARING", "case": str(case), "model_execution_requested": args.execute,
               "model_executed": False, "frozen_expected": {"input": INPUT_SHA, "boundary": BDY_SHA,
               "namelist": NAMELIST_SHA, "table": TABLE_SHA, "history": HISTORY_SHA,
               "fatal_log": FATAL_RANK_LOG_SHA, "executable": sha(EXECUTABLE)}}
    receipt_path = case.parent / (case.name + ".receipt.json")
    try:
        if receipt_path.exists():
            raise FileExistsError(f"refusing to overwrite replay receipt: {receipt_path}")
        receipt["pre_source_pins"] = verify_source_inputs()
        staged = stage_case(case)
        receipt["staged"] = staged
        verify_staged_case(case, staged)
        receipt["status"] = "PREFLIGHT_PASS_NOT_EXECUTED"
        if args.execute:
            receipt["model_executed"] = True
            receipt["status"] = "RUNNING"
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
            receipt["run"] = run(case, args.timeout_seconds)
            receipt["status"] = "EXPECTED_FATAL_PASS" if receipt["run"]["expected_fatal_reproduced"] else "REPLAY_DIAGNOSTIC_FAIL"
        receipt["post_source_pins"] = verify_source_inputs()
        verify_staged_case(case, staged)
        if receipt["post_source_pins"] != receipt["pre_source_pins"]:
            receipt["status"] = "PIN_DRIFT"
            raise RuntimeError("frozen source/runtime inputs changed during replay")
    except Exception as exc:
        receipt["status"] = "PREPARATION_OR_REPLAY_ERROR"
        receipt["error"] = repr(exc)
        receipt["traceback"] = traceback.format_exc()
        receipt["model_executed"] = bool(args.execute and case.exists())
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
        return 1
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "PREFLIGHT_PASS_NOT_EXECUTED" else (0 if receipt["status"] == "EXPECTED_FATAL_PASS" else 1)

if __name__ == "__main__":
    raise SystemExit(main())
