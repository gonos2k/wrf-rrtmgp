#!/usr/bin/env python3
"""Prepare and guard the official pristine WRF-v4.8 Jan RA4 reference.

--prepare creates a new case only. Default/--preflight never launches WRF.
--execute is kept for a separately authorized future run and will refuse any
nonfresh output directory or changed source/input/runtime pins.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

import netCDF4
import numpy as np

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP")
BUILD = ROOT / "build"
PLAN = BUILD / "pristine-jan-ra4"
CASE = PLAN / "case"
SOURCE = BUILD / "pristine-wrf-dm-sm/WRF"
MANIFEST = BUILD / "pristine-wrf-dm-sm/preflight-manifest.json"
EXECUTABLE = SOURCE / "main/wrf.exe"
CONFIGURE = SOURCE / "configure.wrf"
RA4_CASE = BUILD / "udm-alternate-jan2000-data/paired-forecast-v2/ra4"
RA4_PLAN = BUILD / "udm-alternate-jan2000-data/paired-forecast-v2/pair-plan.json"
RA4_RUNTIME = BUILD / "udm-alternate-jan2000-data/paired-forecast-v2/runtime-link-manifest.json"
REFERENCE_HISTORY = RA4_CASE / "wrfout_d01_2000-01-24_12:00:00"
CASE_HISTORY = CASE / "wrfout_d01_2000-01-24_12:00:00"
EXPECTED_TIMES = [
    "2000-01-24_12:00:00", "2000-01-24_13:00:00", "2000-01-24_14:00:00",
    "2000-01-24_15:00:00", "2000-01-24_16:00:00", "2000-01-24_17:00:00",
    "2000-01-24_18:00:00", "2000-01-24_19:00:00", "2000-01-24_20:00:00",
    "2000-01-24_21:00:00", "2000-01-24_22:00:00", "2000-01-24_23:00:00",
    "2000-01-25_00:00:00", "2000-01-25_01:00:00", "2000-01-25_02:00:00",
    "2000-01-25_03:00:00", "2000-01-25_04:00:00", "2000-01-25_05:00:00",
    "2000-01-25_06:00:00", "2000-01-25_07:00:00", "2000-01-25_08:00:00",
    "2000-01-25_09:00:00", "2000-01-25_10:00:00", "2000-01-25_11:00:00",
    "2000-01-25_12:00:00",
]
REQUIRED_HISTORY_VARIABLES = {
    "QICE", "QCLOUD", "QRAIN", "QSNOW", "QGRAUP", "QHAIL",
    "SWDOWN", "GLW", "OLR", "RTHRATEN", "RTHRATLW", "RTHRATSW",
    "SWDDIR", "SWDDIF", "GSW", "RAINC", "RAINNC",
}
PORT_ONLY_OPTIONAL_DIAGNOSTICS = {"UDM_CLDFRA", "UDM_CF_STEP", "UDM_CF_TOP"}
REMOVE_ONLY_RRTMGP_NAMELIST_KEYS = {
    "rrtmgp_udm_frozen_optics", "rrtmgp_data_path", "rrtmgp_ice_roughness",
    "rrtmgp_udm_frozen_table",
}
OMIT_FROM_CASE_RUNTIME_LINKS = {
    "wrf.exe", "ideal.exe", "input_sounding", "namelist.input",
    "namelist.input.backup.2026-10-03_06_04_11",
    "rrtmgp-clouds-lw-bnd.nc", "rrtmgp-clouds-sw-bnd.nc",
    "rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-sw-g112.nc",
}
INPUT_EXPECTED = {
    "wrfinput_d01": "0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637",
    "wrfbdy_d01": "ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4",
    "radiation_iofields.txt": "3890e55c599314f0fddb56585d64164eebaf70b2280589aa679439bc35b505c3",
    "reference_history": "edf0cfbf4efeecbbf69e979c8f4fc21a19a436f4329a3e11330a2c569ea0bcc4",
}
SOURCE_COMMIT = "06d4240ae989cc3e50af412bb472df3d9048783c"
CONFIG_SHA = "5f06ce4a1b7906dc41612d21b56771cbf762b5958fece8070b6e025209317242"
WRF_SHA = "865a687d9c1dcf67ad69488541ca459b321b0e9e0f20e755dc0a358a6aaca503"
MANIFEST_SHA = "4ce6e3374454bb23431828d4be109f3b42b948889b85cd7fa09f6a0636e780c5"
RUNTIME_MANIFEST_SHA = "69c04bfafb0338af3c13631b36b27ee9a8a57e9d515a4fc86515f67760b17b85"
RA4_PLAN_SHA = "27cd0b601366d0feca0eb4330a1a0f31981d95f8ffc5ad8b74404340eabb7b40"
RUN_RECEIPT = PLAN / "run-receipt.json"
STAGE_MANIFEST = PLAN / "stage-manifest.json"
NAMELIST_SOURCE = PLAN / "namelist.original"
NAMELIST_CLEAN = PLAN / "namelist.pristine"
NAMELIST_DIFF = PLAN / "namelist-removal.diff"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def find_exact_stock_asset(name: str, expected_sha: str) -> Path:
    candidates = []
    for p in SOURCE.rglob(name):
        if p.is_file() and sha(p) == expected_sha:
            candidates.append(p)
    require(candidates, f"official source has no exact-hash runtime asset {name}")
    candidates.sort(key=lambda p: (len(p.relative_to(SOURCE).parts), str(p)))
    return candidates[0].resolve()


def clean_namelist(raw: str) -> str:
    lines = raw.splitlines(keepends=True)
    found = {k: 0 for k in REMOVE_ONLY_RRTMGP_NAMELIST_KEYS}
    output = []
    for line in lines:
        match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=", line)
        key = match.group(1).lower() if match else None
        if key in found:
            found[key] += 1
            continue
        output.append(line)
    require(found == {k: 1 for k in REMOVE_ONLY_RRTMGP_NAMELIST_KEYS},
            f"expected exactly one assignment for each unsupported RRTMGP key: {found}")
    return "".join(output)


def validate_namelist_contract(path: Path) -> None:
    text = path.read_text()
    expected = {
        "start_year": "2000", "start_month": "01", "start_day": "24", "start_hour": "12",
        "end_year": "2000", "end_month": "01", "end_day": "25", "end_hour": "12",
        "run_hours": "24", "history_interval": "60", "restart_interval": "720",
        "mp_physics": "27", "ra_lw_physics": "4", "ra_sw_physics": "4", "radt": "10",
        "time_step": "60",
    }
    for key, value in expected.items():
        require(re.search(rf"^\s*{key}\s*=\s*{re.escape(value)}\s*,?\s*$", text,
                          flags=re.IGNORECASE | re.MULTILINE) is not None,
                f"namelist contract differs for {key}={value}")
    require("rrtmgp_" not in text.lower(), "pristine namelist still contains unknown RRTMGP keys")


def prepare() -> dict:
    require(not PLAN.exists(), f"refusing existing plan root: {PLAN}")
    source_manifest = json.loads(MANIFEST.read_text())
    current_runtime = json.loads(RA4_RUNTIME.read_text())
    pair_plan = json.loads(RA4_PLAN.read_text())
    require(source_manifest["source"]["commit"] == SOURCE_COMMIT and
            source_manifest["source"]["tracked_diff_clean"], "official source manifest mismatch")
    require(sha(MANIFEST) == MANIFEST_SHA and sha(CONFIGURE) == CONFIG_SHA and
            sha(EXECUTABLE) == WRF_SHA, "official source/config/executable pins mismatch")
    require(sha(RA4_RUNTIME) == RUNTIME_MANIFEST_SHA, "RA4 runtime manifest hash mismatch")
    require(sha(RA4_PLAN) == RA4_PLAN_SHA, "RA4 plan hash mismatch")
    require(pair_plan["arms"]["ra4"]["wrfinput_sha256"] == INPUT_EXPECTED["wrfinput_d01"] and
            pair_plan["arms"]["ra4"]["wrfbdy_sha256"] == INPUT_EXPECTED["wrfbdy_d01"],
            "RA4 input pair differs from reviewed hashes")
    PLAN.mkdir(parents=True)
    CASE.mkdir()
    records = current_runtime["arms"]["ra4"]
    staged = {}
    for rec in records:
        name = rec["name"]
        if name in OMIT_FROM_CASE_RUNTIME_LINKS:
            continue
        target = find_exact_stock_asset(name, rec["sha256"])
        (CASE / name).symlink_to(target)
        staged[name] = {"path": str(target), "sha256": sha(target), "bytes": target.stat().st_size}
    for name in ("wrfinput_d01", "wrfbdy_d01"):
        src = RA4_CASE / name
        require(src.is_file() and sha(src) == INPUT_EXPECTED[name], f"RA4 input mismatch {name}")
        (CASE / name).symlink_to(src.resolve())
    (CASE / "wrf.exe").symlink_to(EXECUTABLE.resolve())
    original = (RA4_CASE / "namelist.input").read_text()
    sanitized = clean_namelist(original)
    NAMELIST_SOURCE.write_text(original)
    NAMELIST_CLEAN.write_text(sanitized)
    (CASE / "namelist.input").write_text(sanitized)
    import difflib
    NAMELIST_DIFF.write_text("".join(difflib.unified_diff(
        original.splitlines(keepends=True), sanitized.splitlines(keepends=True),
        fromfile="paired-forecast-v2/ra4/namelist.input", tofile="pristine-jan-ra4/case/namelist.input")))
    iofields = RA4_CASE / "radiation_iofields.txt"
    require(sha(iofields) == INPUT_EXPECTED["radiation_iofields.txt"], "radiation iofields file changed")
    shutil.copyfile(iofields, CASE / "radiation_iofields.txt")
    stage = {
        "status": "PREPARED_NO_MODEL_RUN",
        "case": str(CASE), "source_commit": SOURCE_COMMIT,
        "ra4_runtime_manifest_sha256": sha(RA4_RUNTIME),
        "ra4_pair_plan_sha256": sha(RA4_PLAN),
        "official_executable_sha256": sha(EXECUTABLE), "configure_sha256": sha(CONFIGURE),
        "official_manifest_sha256": sha(MANIFEST), "source_runtime_asset_count": len(records),
        "staged_stock_runtime_asset_count": len(staged), "staged_stock_runtime_assets": staged,
        "omitted_nonrequired_or_upstreamabsent": sorted(OMIT_FROM_CASE_RUNTIME_LINKS),
        "inputs": {k: {"path": str((CASE / k).resolve()), "sha256": sha(CASE / k)}
                   for k in ("wrfinput_d01", "wrfbdy_d01")},
        "namelist_original_sha256": sha(NAMELIST_SOURCE),
        "namelist_pristine_sha256": sha(CASE / "namelist.input"),
        "namelist_diff_sha256": sha(NAMELIST_DIFF),
        "removed_namelist_keys": sorted(REMOVE_ONLY_RRTMGP_NAMELIST_KEYS),
        "radiation_iofields_sha256": sha(CASE / "radiation_iofields.txt"),
        "reference_history_sha256": sha(REFERENCE_HISTORY),
        "runtime_link_count": sum(p.is_symlink() for p in CASE.iterdir()),
        "runtime_asset_sha_checks_pass": True,
        "runtime_outputs_absent": True,
        "run_contract": {
            "mpi_ranks": 4, "omp_threads": 1, "stack_bytes": 536870912,
            "timeout_seconds": 600, "physics": {"mp_physics": 27, "ra_lw_physics": 4, "ra_sw_physics": 4},
            "period": ["2000-01-24_12:00:00", "2000-01-25_12:00:00"],
            "history_interval_minutes": 60, "restart_interval_minutes": 720,
            "command": ["mpiexec", "-launcher", "fork", "-iface", "lo", "-n", "4", "./wrf.exe"],
            "mpi_interface_env": "MPICH_INTERFACE_HOSTNAME=127.0.0.1",
            "output_iFields": ["RTHRATEN", "RTHRATLW", "RTHRATSW", "SWDDIR", "SWDDIF", "GSW"],
        },
        "comparison_contract": {
            "reference_history": str(REFERENCE_HISTORY),
            "compare_times": EXPECTED_TIMES,
            "all_common_variables_raw_bytes": True,
            "dimensions_dtype_variable_attrs_global_attrs": "exact for all common variables and global attrs",
            "asymmetric_variable_allowlist": sorted(PORT_ONLY_OPTIONAL_DIAGNOSTICS),
            "numeric_mismatch_allowlist": [],
            "no_tolerance_or_boundary_mask": True,
            "scope": "same MP27 and RA4 configuration; regression/preservation comparison, not RA37 attribution or observed truth",
        },
    }
    STAGE_MANIFEST.write_text(json.dumps(stage, indent=2, sort_keys=True) + "\n")
    (PLAN / "README.md").write_text(readme(stage))
    return stage


def read_times(ds) -> list[str]:
    raw = np.asarray(ds.variables["Times"][:])
    return [b"".join(row).decode("ascii").strip() for row in raw]


def validate_netcdf(path: Path, expected_times: list[str], required_variables=()) -> dict:
    with netCDF4.Dataset(path) as ds:
        require(set(ds.dimensions) >= {"Time", "west_east", "south_north", "bottom_top"},
                "history lacks required WRF dimensions")
        times = read_times(ds)
        require(times == expected_times, f"unexpected Times contents: {times}")
        require(set(required_variables) <= set(ds.variables),
                f"required output diagnostics missing: {sorted(set(required_variables)-set(ds.variables))}")
        numeric = 0
        fill_hits = 0
        nonfinite = 0
        shapes = {k: len(v) for k, v in ds.dimensions.items()}
        for v in ds.variables.values():
            v.set_auto_maskandscale(False)
            a = v[:]
            require(not np.ma.isMaskedArray(a) or not np.ma.getmaskarray(a).any(),
                    f"masked values in {v.name}")
            a = np.asarray(a)
            if np.issubdtype(v.dtype, np.number):
                numeric += 1
                require(np.all(np.isfinite(a)), f"nonfinite raw numeric values in {v.name}")
                for att in ("_FillValue", "missing_value"):
                    if att in v.ncattrs():
                        marker = np.asarray(v.getncattr(att)).reshape(-1)
                        for m in marker:
                            hits = np.any(np.isnan(a)) if np.issubdtype(a.dtype, np.floating) and np.isnan(m) else np.any(a == m)
                            if hits:
                                fill_hits += int(np.count_nonzero(a == m))
                scale = float(v.getncattr("scale_factor")) if "scale_factor" in v.ncattrs() else 1.0
                offset = float(v.getncattr("add_offset")) if "add_offset" in v.ncattrs() else 0.0
                decoded = a.astype(np.float64) * scale + offset
                require(np.all(np.isfinite(decoded)), f"nonfinite decoded values in {v.name}")
        require(fill_hits == 0 and nonfinite == 0, "history has fill/nonfinite values")
        return {"path": str(path), "sha256": sha(path), "times": times,
                "dimension_lengths": shapes, "variable_count": len(ds.variables),
                "numeric_variable_count": numeric, "fill_hits": fill_hits, "nonfinite": nonfinite}


def compare_histories(candidate: Path, reference: Path) -> dict:
    differences = []
    with netCDF4.Dataset(candidate) as a, netCDF4.Dataset(reference) as b:
        da, db = set(a.dimensions), set(b.dimensions)
        require(da == db, f"dimension-name sets differ: candidate-only={sorted(da-db)}, reference-only={sorted(db-da)}")
        for n in sorted(da):
            require(len(a.dimensions[n]) == len(b.dimensions[n]) and
                    a.dimensions[n].isunlimited() == b.dimensions[n].isunlimited(),
                    f"dimension differs {n}")
        va, vb = set(a.variables), set(b.variables)
        delta = va ^ vb
        require(delta <= PORT_ONLY_OPTIONAL_DIAGNOSTICS,
                f"unexpected asymmetric variable set: {sorted(delta)}")
        ga, gb = set(a.ncattrs()), set(b.ncattrs())
        require(ga == gb, f"global attribute names differ: {sorted(ga ^ gb)}")
        for n in sorted(ga):
            xa, xb = np.asarray(a.getncattr(n)), np.asarray(b.getncattr(n))
            require(xa.dtype == xb.dtype and xa.shape == xb.shape and xa.tobytes() == xb.tobytes(),
                    f"global attribute raw bytes differ: {n}")
        for n in sorted(va & vb):
            x, y = a.variables[n], b.variables[n]
            x.set_auto_maskandscale(False); y.set_auto_maskandscale(False)
            require(x.dimensions == y.dimensions and x.dtype == y.dtype, f"shape/dtype declaration differs: {n}")
            xa, ya = np.asarray(x[:]), np.asarray(y[:])
            require(xa.shape == ya.shape, f"array shape differs: {n}")
            atx, aty = set(x.ncattrs()), set(y.ncattrs())
            require(atx == aty, f"variable attribute names differ: {n}")
            for att in sorted(atx):
                ax, ay = np.asarray(x.getncattr(att)), np.asarray(y.getncattr(att))
                require(ax.dtype == ay.dtype and ax.shape == ay.shape and ax.tobytes() == ay.tobytes(),
                        f"variable attribute differs: {n}:{att}")
            if xa.dtype != ya.dtype or xa.tobytes() != ya.tobytes():
                count = int(np.count_nonzero(xa != ya))
                if np.issubdtype(xa.dtype, np.number):
                    d = np.abs(xa.astype(np.float64) - ya.astype(np.float64))
                    mx = float(d.max()) if d.size else 0.0
                else:
                    mx = None
                differences.append({"variable": n, "shape": list(xa.shape),
                                    "different_values": count, "max_abs": mx,
                                    "candidate_sha256": hashlib.sha256(xa.tobytes()).hexdigest(),
                                    "reference_sha256": hashlib.sha256(ya.tobytes()).hexdigest()})
        ta, tb = read_times(a), read_times(b)
        require(ta == tb == EXPECTED_TIMES, "candidate/reference Times mismatch")
    return {"status": "BITWISE_PASS" if not differences and not delta else "DIFFERENCES_RECORDED",
            "common_variables": len(va & vb), "asymmetric_variables": sorted(delta),
            "numeric_difference_allowlist": [], "differences": differences}


def verify_static(require_fresh: bool = True) -> dict:
    stage = json.loads(STAGE_MANIFEST.read_text())
    source_info = json.loads(MANIFEST.read_text())
    runtime_info = json.loads(RA4_RUNTIME.read_text())
    require(sha(MANIFEST) == MANIFEST_SHA and sha(CONFIGURE) == CONFIG_SHA and
            sha(EXECUTABLE) == WRF_SHA, "official executable/config/source manifest pin changed")
    require(source_info["source"]["commit"] == SOURCE_COMMIT and source_info["source"]["tracked_diff_clean"],
            "official source manifest commit/clean state changed")
    githead = subprocess.run(["git", "-C", str(SOURCE), "rev-parse", "HEAD"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.decode().strip()
    require(githead == SOURCE_COMMIT, f"official source HEAD changed: {githead}")
    tracked = subprocess.run(["git", "-C", str(SOURCE), "status", "--porcelain", "--untracked-files=no"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.decode()
    require(not tracked.strip(), f"tracked official source changes present: {tracked}")
    submodule_text = subprocess.run(["git", "-C", str(SOURCE), "submodule", "status"],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     check=True).stdout.decode()
    submodules = {}
    for line in submodule_text.splitlines():
        require(line and line[0] == " ", f"submodule is uninitialized, changed, or conflicted: {line}")
        commit, path, *_ = line[1:].split()
        submodules[path] = commit
    expected_submodules = {x["path"]: x["commit"] for x in source_info["source"]["submodules"]}
    require(submodules == expected_submodules, "official source submodule commits differ from manifest")
    require(sha(RA4_RUNTIME) == stage["ra4_runtime_manifest_sha256"] and
            sha(RA4_PLAN) == stage["ra4_pair_plan_sha256"], "RA4 source run manifests changed")
    require(sha(RA4_CASE / "wrfinput_d01") == INPUT_EXPECTED["wrfinput_d01"] and
            sha(RA4_CASE / "wrfbdy_d01") == INPUT_EXPECTED["wrfbdy_d01"] and
            sha(REFERENCE_HISTORY) == INPUT_EXPECTED["reference_history"], "pinned RA4 inputs/history changed")
    require(sha(NAMELIST_SOURCE) == stage["namelist_original_sha256"] and
            sha(CASE / "namelist.input") == stage["namelist_pristine_sha256"] and
            (CASE / "namelist.input").read_text() == clean_namelist(NAMELIST_SOURCE.read_text()),
            "sanitized namelist content changed")
    validate_namelist_contract(CASE / "namelist.input")
    require(sha(CASE / "radiation_iofields.txt") == INPUT_EXPECTED["radiation_iofields.txt"],
            "radiation iofields changed")
    require(sha(CASE / "wrfinput_d01") == INPUT_EXPECTED["wrfinput_d01"] and
            sha(CASE / "wrfbdy_d01") == INPUT_EXPECTED["wrfbdy_d01"], "case input links changed")
    for name, item in stage["staged_stock_runtime_assets"].items():
        p = CASE / name
        require(p.is_symlink() and p.resolve() == Path(item["path"]) and sha(p) == item["sha256"],
                f"runtime asset changed: {name}")
    require((CASE / "wrf.exe").is_symlink() and (CASE / "wrf.exe").resolve() == EXECUTABLE.resolve() and
            sha(CASE / "wrf.exe") == WRF_SHA, "case executable link changed")
    required = [CASE / n for n in ("wrf.exe", "namelist.input", "wrfinput_d01", "wrfbdy_d01", "radiation_iofields.txt")]
    require(all(p.exists() for p in required), "required case files missing")
    if require_fresh:
        require(not any((CASE / n).exists() for n in ("wrfout_d01_2000-01-24_12:00:00", "rsl.out.0000", "rsl.error.0000")),
                "model output exists; case is not fresh")
    ldd_env = os.environ.copy()
    ldd_env["LD_LIBRARY_PATH"] = ":".join((str(BUILD / "deps/netcdf/lib"),
                                            str(BUILD / "deps/mpich-sock/lib"),
                                            str(BUILD / "deps/root/usr/lib/x86_64-linux-gnu")))
    ldd = subprocess.run(["ldd", str(EXECUTABLE)], env=ldd_env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, check=True).stdout.decode()
    require("not found" not in ldd, f"unresolved executable dependency:\n{ldd}")
    mpiexec = BUILD / "deps/mpich-sock/bin/mpiexec"
    v = subprocess.run([str(mpiexec), "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False).stdout.decode()
    require("4.2.0" in v, f"unexpected MPICH runtime version: {v[:200]}")
    gfortran = subprocess.run(["gfortran", "--version"], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=True).stdout.decode().splitlines()[0]
    mpif90 = subprocess.run([str(BUILD / "deps/mpich-sock/bin/mpif90"), "-show"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True).stdout.decode().strip()
    require("13.3.0" in gfortran and "gfortran" in mpif90,
            f"unexpected compiler/runtime wrapper: {gfortran} / {mpif90}")
    return {"source_head": githead, "source_tracked_clean": True,
            "submodule_commits": submodules, "gfortran_version": gfortran,
            "mpif90_show": mpif90,
            "binary_sha256": sha(EXECUTABLE), "configure_sha256": sha(CONFIGURE),
            "ra4_manifest_sha256": sha(RA4_RUNTIME), "ra4_plan_sha256": sha(RA4_PLAN),
            "input_hashes": {n: sha(CASE / n) for n in ("wrfinput_d01", "wrfbdy_d01")},
            "namelist_sha256": sha(CASE / "namelist.input"),
            "radiation_iofields_sha256": sha(CASE / "radiation_iofields.txt"),
            "runtime_assets": {n: sha(CASE / n) for n in stage["staged_stock_runtime_assets"]},
            "ldd": ldd, "mpiexec_version": v}


def resource_preexec():
    n = 512 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_STACK, (n, n))


def execute() -> dict:
    require(not RUN_RECEIPT.exists(), f"refusing existing run receipt {RUN_RECEIPT}")
    baseline = verify_static()
    for n in ("wrfout_d01_2000-01-24_12:00:00", "wrfrst_d01_2000-01-25_00:00:00",
              "wrfrst_d01_2000-01-25_12:00:00", "rsl.out.0000", "rsl.error.0000"):
        require(not (CASE / n).exists(), f"refusing nonfresh case output: {n}")
    mpi = BUILD / "deps/mpich-sock/bin/mpiexec"
    command = [str(mpi), "-launcher", "fork", "-iface", "lo", "-n", "4", "./wrf.exe"]
    env = os.environ.copy()
    for k in list(env):
        if k.startswith("WRF_RRTMGP"):
            env.pop(k)
    env["OMP_NUM_THREADS"] = "1"
    env["OMP_STACKSIZE"] = "512M"
    env["OMP_DYNAMIC"] = "FALSE"
    env["OMP_PROC_BIND"] = "FALSE"
    env["MPICH_INTERFACE_HOSTNAME"] = "127.0.0.1"
    env["NETCDF"] = str(BUILD / "deps/netcdf")
    env["LD_LIBRARY_PATH"] = ":".join((str(BUILD / "deps/netcdf/lib"),
                                         str(BUILD / "deps/mpich-sock/lib"),
                                         str(BUILD / "deps/root/usr/lib/x86_64-linux-gnu")))
    status = {"status": "RUNNING", "command": command, "cwd": str(CASE),
              "pre_run_static": baseline, "start_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "timeout_seconds": 600, "environment": {k: env[k] for k in (
                  "OMP_NUM_THREADS", "OMP_STACKSIZE", "OMP_DYNAMIC", "OMP_PROC_BIND",
                  "MPICH_INTERFACE_HOSTNAME", "NETCDF", "LD_LIBRARY_PATH")}}
    RUN_RECEIPT.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    t0 = time.monotonic()
    try:
        cp = subprocess.run(command, cwd=CASE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=600, check=False, preexec_fn=resource_preexec)
        stdout = CASE / "mpiexec.stdout.log"
        stdout.write_bytes(cp.stdout)
        text = cp.stdout.decode("utf-8", "replace")
        require(cp.returncode == 0, f"mpiexec return code {cp.returncode}")
        logs = {}
        fatal_words = ("FATAL CALLED", "MPI_Abort", "SIGFPE", "Segmentation fault", "ERROR: wrf fatal")
        for rank in range(4):
            p = CASE / f"rsl.error.{rank:04d}"
            require(p.is_file(), f"missing rank error log {p.name}")
            tx = p.read_text(errors="replace")
            require("SUCCESS COMPLETE WRF" in tx, f"rank {rank} lacks SUCCESS COMPLETE WRF")
            require(not any(x in tx for x in fatal_words), f"fatal marker in rank {rank} log")
            logs[p.name] = {"sha256": sha(p), "bytes": p.stat().st_size}
        require(not any(x in text for x in fatal_words), "fatal marker in launcher stdout")
        hist = validate_netcdf(CASE_HISTORY, EXPECTED_TIMES, REQUIRED_HISTORY_VARIABLES)
        restarts = {}
        for stamp in ("2000-01-25_00:00:00", "2000-01-25_12:00:00"):
            name = f"wrfrst_d01_{stamp}"
            rp = CASE / name
            restarts[name] = validate_netcdf(rp, [stamp])
        comparison = compare_histories(CASE_HISTORY, REFERENCE_HISTORY)
        post = verify_static(require_fresh=False)
        require(post == baseline, "source, inputs, or runtime assets changed during run")
        status.update({"status": ("RUN_COMPLETE_BITWISE_PASS" if comparison["status"] == "BITWISE_PASS"
                                   else "RUN_COMPLETE_COMPARISON_DIFFERENCES_RECORDED"), "returncode": cp.returncode,
                       "elapsed_seconds": time.monotonic() - t0,
                       "launcher_stdout_sha256": sha(stdout), "rank_logs": logs,
                       "history_validation": hist, "restart_validations": restarts,
                       "full_raw_comparison": comparison,
                       "post_run_static": post})
        RUN_RECEIPT.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
        return status
    except Exception as exc:
        post_static = None
        try:
            post_static = verify_static(require_fresh=False)
        except Exception as pin_exc:
            post_static = {"status": "PIN_RECHECK_FAILED", "failure": repr(pin_exc)}
        status.update({"status": "RUN_FAILED_OR_VALIDATION_FAILED", "failure": repr(exc),
                       "elapsed_seconds": time.monotonic() - t0,
                       "post_run_static": post_static})
        if isinstance(exc, subprocess.TimeoutExpired) and exc.stdout:
            timeout_out = CASE / "mpiexec.stdout.timeout.log"
            timeout_out.write_bytes(exc.stdout)
            status["timeout_stdout"] = {"path": str(timeout_out), "sha256": sha(timeout_out)}
        RUN_RECEIPT.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
        raise


def readme(stage: dict) -> str:
    return f"""# Official pristine January 2000 RA4 comparison preflight

This is a fresh case directory for a later official-pristine WRF v4.8.0 RA4
regression comparison. **No model run has been launched.** The case uses
official commit `{SOURCE_COMMIT}`, GNU Fortran 13.3 / MPICH 4.2 / NetCDF 4.5.4,
GNU dm+sm configuration (`35`, `1`), MPI4 and OMP1. The exact executable SHA256
is `{WRF_SHA}` and configure SHA256 is `{CONFIG_SHA}`.

The initial and boundary files are the existing paired-forecast RA4 files:

- `wrfinput_d01`: `{INPUT_EXPECTED['wrfinput_d01']}`
- `wrfbdy_d01`: `{INPUT_EXPECTED['wrfbdy_d01']}`

The namelist is copied byte-for-byte except for the four unrecognized RRTMGP
keys listed in `namelist-removal.diff`; all remaining RA4, MP27, 24-hour end
time, 60-minute history, 720-minute restart, and 2x2 MPI layout settings remain.
`radiation_iofields.txt` is copied unchanged. The 85 linked stock runtime assets
were matched by full SHA against the RA4 run manifest; RRTMGP coefficients,
build executables, input_sounding, and a historical backup namelist are omitted
because pristine RA4 does not require them.

The guarded runner defaults to static preflight only. `--execute` is present
for a separately authorized later run and enforces a fresh output directory,
4 successful rank logs, no fatal marker, exact 25 `Times` records, all raw and
decoded numeric data finite/unmasked/no-fill, pre/post source/input/runtime
pins, and a full same-layout comparison with every shared raw variable and
attribute. No numerical mismatch is allowed. The only asymmetric-variable
allowlist is `{sorted(PORT_ONLY_OPTIONAL_DIAGNOSTICS)}`, the three explicitly
registered port-only UDM cloud-fraction diagnostics; they are compared normally
if present in both files. The current paired RA4 history is the reference at
`{REFERENCE_HISTORY}` (SHA `{INPUT_EXPECTED['reference_history']}`).

This is an official-vs-patched **RA4 preservation** check for one shared winter
case. It cannot identify the cause of the separate RA37 QI fatal or be treated
as a same-trajectory RA4-vs-RA37 physics comparison.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--prepare", action="store_true", help="create fresh case and pins; does not run WRF")
    g.add_argument("--execute", action="store_true", help="run MPI4/OMP1 case (requires separate authorization)")
    args = ap.parse_args()
    if args.prepare:
        stage = prepare()
        print(json.dumps({"status": stage["status"], "case": stage["case"],
                          "staged_stock_runtime_asset_count": stage["staged_stock_runtime_asset_count"]}, indent=2))
        return 0
    if not PLAN.is_dir() or not STAGE_MANIFEST.is_file():
        raise RuntimeError("prepared case not found; use --prepare after checking path")
    verified = verify_static()
    if args.execute:
        r = execute()
        print(json.dumps({"status": r["status"], "receipt": str(RUN_RECEIPT)}, indent=2))
    else:
        print(json.dumps({"status": "PREFLIGHT_PASS_NO_MODEL_RUN", "case": str(CASE),
                          "verified": verified, "run_receipt_absent": not RUN_RECEIPT.exists()}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
