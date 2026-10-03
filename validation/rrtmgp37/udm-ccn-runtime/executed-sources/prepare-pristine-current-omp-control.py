#!/usr/bin/env python3
"""Stage an official pristine Jan OMP1/OMP2 control; execute only explicitly.

The two cases use the existing official WRF-v4.8 Jan RA4 inputs and stock
runtime assets. By default it only preflights; case staging and WRF launch need
explicit flags. Run with --self-test for offline contract checks.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

import numpy as np
from netCDF4 import Dataset, default_fillvals

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP")
BUILD = ROOT / "build"
SOURCE = BUILD / "pristine-wrf-dm-sm/WRF"
EXECUTABLE = SOURCE / "main/wrf.exe"
CONFIGURE = SOURCE / "configure.wrf"
SOURCE_MANIFEST = BUILD / "pristine-wrf-dm-sm/preflight-manifest.json"
OFFICIAL_PLAN = BUILD / "pristine-jan-ra4"
OFFICIAL_CASE = OFFICIAL_PLAN / "case"
OFFICIAL_STAGE = OFFICIAL_PLAN / "stage-manifest.json"
OFFICIAL_POSTHOC = OFFICIAL_PLAN / "posthoc-comparison.json"
OFFICIAL_RUN_RECEIPT = OFFICIAL_PLAN / "run-receipt.json"
MPICH = BUILD / "deps/mpich-sock"
NETCDF = BUILD / "deps/netcdf"
ROOT_LIBS = BUILD / "deps/root/usr/lib/x86_64-linux-gnu"

SOURCE_COMMIT = "06d4240ae989cc3e50af412bb472df3d9048783c"
WRF_SHA = "865a687d9c1dcf67ad69488541ca459b321b0e9e0f20e755dc0a358a6aaca503"
CONFIG_SHA = "5f06ce4a1b7906dc41612d21b56771cbf762b5958fece8070b6e025209317242"
MANIFEST_SHA = "4ce6e3374454bb23431828d4be109f3b42b948889b85cd7fa09f6a0636e780c5"
OFFICIAL_POSTHOC_SHA = "0d2df7446b8abd78962ea773ce6d5a7e3418117d5fba999408ec8461a9068c16"
OFFICIAL_RUN_RECEIPT_SHA = "56d4d5dd291465c7fbaf6f19aa98dbb4bd1f12d8136ce8760b9bd89920904302"
COMMON_HELPER = BUILD / "udm-seaice-winter-validation-v1/winter_validation_v1.py"
COMMON_HELPER_SHA = "6f66046e785fc5ef69f317daa3ca63a09a4cfab0839a67bea9703ce21691a4e8"
INPUT_HASHES = {
    "wrfinput_d01": "0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637",
    "wrfbdy_d01": "ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4",
    "radiation_iofields.txt": "3890e55c599314f0fddb56585d64164eebaf70b2280589aa679439bc35b505c3",
    "reference_history": "edf0cfbf4efeecbbf69e979c8f4fc21a19a436f4329a3e11330a2c569ea0bcc4",
}
ARMS = {"omp1": 1, "omp2": 2}
EXPECTED_TIMES = [f"2000-01-24_{h:02d}:00:00" for h in range(12, 16)]
REMOVE = {"rrtmgp_udm_frozen_optics", "rrtmgp_data_path",
          "rrtmgp_ice_roughness", "rrtmgp_udm_frozen_table"}
OMIT = {
    "wrf.exe", "ideal.exe", "input_sounding",
    "namelist.input", "namelist.input.backup.2026-10-03_06_04_11",
    "rrtmgp-clouds-lw-bnd.nc", "rrtmgp-clouds-sw-bnd.nc",
    "rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-sw-g112.nc",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_runtime_helper():
    need(sha(COMMON_HELPER) == COMMON_HELPER_SHA, "pinned process-group runtime helper changed")
    spec = importlib.util.spec_from_file_location("pinned_pristine_omp_runtime", COMMON_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned runtime helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    need(sha(COMMON_HELPER) == COMMON_HELPER_SHA, "runtime helper changed while loading")
    module.TIMEOUT = 1200
    return module


def need(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def run(command: list[str], *, env=None) -> str:
    cp = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        check=True, env=env, text=True)
    return cp.stdout


def official_namelist(text: str) -> str:
    """Change only end time, run length, restart interval, and OMP tile count."""
    out = []
    seen = {k: 0 for k in ("run_hours", "end_day", "end_hour", "restart_interval")}
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(\s*)([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*?)(\s*)$", line.rstrip("\r\n"))
        if not m:
            out.append(line)
            continue
        key = m.group(2).lower()
        expected = {"run_hours": ("24", "3"), "end_day": ("25", "24"),
                    "end_hour": ("12", "15"), "restart_interval": ("720", "180")}
        if key in expected:
            seen[key] += 1
            old, new = expected[key]
            value = m.group(3)
            if not re.fullmatch(re.escape(old) + r"\s*,?", value):
                raise ValueError(f"unexpected pristine {key} value: {value!r}")
            ending = "\n" if line.endswith("\n") else ""
            out.append(f"{m.group(1)}{m.group(2)} = {new},{m.group(4)}{ending}")
        else:
            out.append(line)
    if seen != {k: 1 for k in seen}:
        raise ValueError(f"expected one each run-control key, found {seen}")
    result = "".join(out)
    if re.search(r"(?im)^\s*numtiles\s*=", result):
        raise ValueError("unexpected numtiles in pristine base namelist")
    result, n = re.subn(r"(?im)^(\s*max_dom\s*=\s*1\s*,?\s*)$",
                        lambda m: m.group(1) + "\n numtiles = 2,", result)
    if n != 1:
        raise ValueError(f"expected one max_dom=1 line, found {n}")
    return result


def normalized_ldd() -> list[dict]:
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join(map(str, (NETCDF / "lib", MPICH / "lib", ROOT_LIBS)))
    text = run(["ldd", str(EXECUTABLE)], env=env)
    if "not found" in text:
        raise RuntimeError("unresolved official executable library")
    records = []
    for line in text.splitlines():
        m = re.match(r"\s*(?:(\S+)\s+=>\s+(\S+)|(\S+))\s+\(0x[0-9a-fA-F]+\)\s*$", line)
        if not m:
            raise RuntimeError(f"cannot parse ldd row {line!r}")
        name = m.group(1) or m.group(3)
        path = m.group(2) or m.group(3)
        if path.startswith("/") and Path(path).is_file():
            resolved = Path(path).resolve()
            records.append({"name": name, "reported_path": path,
                            "resolved_path": str(resolved), "sha256": sha(resolved)})
        else:
            records.append({"name": name, "reported_path": path,
                            "resolved_path": None, "sha256": None})
    return sorted(records, key=lambda r: r["name"])


def source_pins() -> dict:
    need(sha(EXECUTABLE) == WRF_SHA and sha(CONFIGURE) == CONFIG_SHA,
         "official binary/config pin mismatch")
    need(sha(SOURCE_MANIFEST) == MANIFEST_SHA, "official source manifest changed")
    manifest = json.loads(SOURCE_MANIFEST.read_text())
    head = run(["git", "-C", str(SOURCE), "rev-parse", "HEAD"]).strip()
    tracked = run(["git", "-C", str(SOURCE), "status", "--porcelain", "--untracked-files=no"])
    need(head == SOURCE_COMMIT and not tracked.strip(), "official pristine source tree changed")
    need(manifest["source"]["commit"] == SOURCE_COMMIT and manifest["source"]["tracked_diff_clean"],
         "official source manifest commit/clean status mismatch")
    submodule_text = run(["git", "-C", str(SOURCE), "submodule", "status"])
    submodules = {}
    for line in submodule_text.splitlines():
        need(line.startswith(" "), f"invalid submodule status: {line}")
        commit, path, *_ = line[1:].split()
        submodules[path] = commit
    expected = {entry["path"]: entry["commit"] for entry in manifest["source"]["submodules"]}
    need(submodules == expected, "official submodule commits changed")
    return {"commit": head, "tracked_worktree_clean": True, "submodules": submodules,
            "tree": run(["git", "-C", str(SOURCE), "rev-parse", "HEAD^{tree}"]).strip(),
            "manifest_sha256": sha(SOURCE_MANIFEST), "binary_sha256": sha(EXECUTABLE),
            "configure_sha256": sha(CONFIGURE)}


def runtime_pins() -> dict:
    stage = json.loads(OFFICIAL_STAGE.read_text())
    assets = {}
    for name, rec in sorted(stage["staged_stock_runtime_assets"].items()):
        path = Path(rec["path"])
        need(path.is_file() and sha(path) == rec["sha256"], f"official runtime asset changed: {name}")
        assets[name] = {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha(path)}
    need(len(assets) == 85, f"expected 85 stock runtime assets, found {len(assets)}")
    deps = normalized_ldd()
    return {"official_stage_sha256": sha(OFFICIAL_STAGE), "assets": assets,
            "asset_count": len(assets), "ldd_dependencies": deps,
            "ldd_dependency_count": len(deps),
            "netcdf_root": str(NETCDF), "mpich_root": str(MPICH)}


def verify_base() -> dict:
    source = source_pins()
    need(sha(OFFICIAL_POSTHOC) == OFFICIAL_POSTHOC_SHA, "official posthoc receipt changed")
    need(sha(OFFICIAL_RUN_RECEIPT) == OFFICIAL_RUN_RECEIPT_SHA, "official run receipt changed")
    post = json.loads(OFFICIAL_POSTHOC.read_text())
    need(post["status"] == "POSTHOC_RUNTIME_AND_RAW_COMPARISON_COMPLETE", "official run posthoc not accepted")
    need(post["history_validation"]["sha256"] == INPUT_HASHES["reference_history"] and
         sha(OFFICIAL_CASE / "wrfout_d01_2000-01-24_12:00:00") == INPUT_HASHES["reference_history"],
         "official OMP1 history prefix reference changed")
    runtime = runtime_pins()
    for name, digest in INPUT_HASHES.items():
        path = (OFFICIAL_CASE / "wrfout_d01_2000-01-24_12:00:00"
                if name == "reference_history" else OFFICIAL_CASE / name)
        need(path.is_file() and sha(path) == digest, f"official base input changed: {name}")
    base_nml = (OFFICIAL_CASE / "namelist.input").read_text()
    need(re.search(r"(?im)^\s*run_hours\s*=\s*24\s*,?\s*$", base_nml) is not None and
         re.search(r"(?im)^\s*restart_interval\s*=\s*720\s*,?\s*$", base_nml) is not None,
         "official sanitized namelist is not expected base")
    return {"source": source, "runtime": runtime,
            "base_case": str(OFFICIAL_CASE.resolve()),
            "official_history_sha256": post["history_validation"]["sha256"],
            "official_run_receipt_sha256": sha(OFFICIAL_RUN_RECEIPT),
            "official_posthoc_sha256": sha(OFFICIAL_POSTHOC),
            "input_hashes": INPUT_HASHES,
            "radiation_iofields_sha256": sha(OFFICIAL_CASE / "radiation_iofields.txt")}


def prepare(root: Path) -> dict:
    need(root.is_absolute(), "--root must be absolute")
    need(not root.exists() and not root.is_symlink(), f"strict fresh-root refusal: {root}")
    pins = verify_base()
    base_nml = (OFFICIAL_CASE / "namelist.input").read_text()
    changed_nml = official_namelist(base_nml)
    root.mkdir(parents=True)
    arms = {}
    try:
        official_stage = json.loads(OFFICIAL_STAGE.read_text())
        stock = official_stage["staged_stock_runtime_assets"]
        for arm, threads in ARMS.items():
            case = root / arm
            case.mkdir()
            assets = {}
            for name, rec in sorted(stock.items()):
                src = Path(rec["path"]).resolve(strict=True)
                need(sha(src) == rec["sha256"], f"stock runtime asset changed during staging: {name}")
                (case / name).symlink_to(src)
                assets[name] = {"path": str(src), "sha256": rec["sha256"], "bytes": src.stat().st_size}
            for name in ("wrfinput_d01", "wrfbdy_d01"):
                src = (OFFICIAL_CASE / name).resolve(strict=True)
                need(sha(src) == INPUT_HASHES[name], f"input changed while staging: {name}")
                (case / name).symlink_to(src)
            (case / "wrf.exe").symlink_to(EXECUTABLE.resolve(strict=True))
            (case / "radiation_iofields.txt").write_bytes((OFFICIAL_CASE / "radiation_iofields.txt").read_bytes())
            (case / "namelist.input").write_text(changed_nml)
            outputs = [p.name for p in case.iterdir() if p.name.startswith(("wrfout_", "wrfrst_", "rsl."))]
            need(not outputs, f"fresh case unexpectedly contains model outputs: {outputs}")
            arms[arm] = {"threads": threads, "case_path": str(case),
                         "namelist_sha256": sha(case / "namelist.input"),
                         "namelist_bytes": (case / "namelist.input").stat().st_size,
                         "runtime_assets": assets,
                         "input_hashes": {n: sha(case / n) for n in INPUT_HASHES
                                          if n not in ("radiation_iofields.txt", "reference_history")},
                         "radiation_iofields_sha256": sha(case / "radiation_iofields.txt"),
                         "output_paths_absent": True}
        need(arms["omp1"]["namelist_sha256"] == arms["omp2"]["namelist_sha256"],
             "OMP arms do not share exact namelist bytes")
        need(arms["omp1"]["input_hashes"] == arms["omp2"]["input_hashes"],
             "OMP arms do not share exact input hashes")
        base_nml = (OFFICIAL_CASE / "namelist.input").read_text()
        diff_path = root / "namelist-change.diff"
        diff_path.write_text("".join(difflib.unified_diff(
            base_nml.splitlines(keepends=True), changed_nml.splitlines(keepends=True),
            fromfile="official-pristine-24h/namelist.input",
            tofile="pristine-current-omp-3h/namelist.input")))
        stage = {
            "status": "STAGED_NOT_RUN",
            "actual_model_invocations": 0,
            "runner": {"path": str(Path(__file__).resolve()), "sha256": sha(Path(__file__))},
            "runtime_helper": {"path": str(COMMON_HELPER.resolve()), "sha256": sha(COMMON_HELPER)},
            "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "scope": "Official upstream RA4 same-input OMP1 versus OMP2 decomposition/control, not RA37 or forecast accuracy.",
            "pins": pins,
            "period": [EXPECTED_TIMES[0], EXPECTED_TIMES[-1]],
            "expected_history_times": EXPECTED_TIMES,
            "mpi": {"ranks": 4, "layout": "2x2"},
            "tiles": {"numtiles": 2},
            "arms": arms,
            "run_contract_for_later_review_only": {
                "threads": {"omp1": 1, "omp2": 2},
                "timeout_seconds": 1200,
                "stack_bytes": 536870912,
                "environment": {"OMP_DYNAMIC": "FALSE", "OMP_PROC_BIND": "FALSE",
                                 "OMP_MAX_ACTIVE_LEVELS": "1", "OMP_NESTED": "FALSE",
                                 "OMP_STACKSIZE": "512M", "OPENBLAS_NUM_THREADS": "1",
                                 "MPICH_INTERFACE_HOSTNAME": "127.0.0.1"},
                "history": {"times": EXPECTED_TIMES, "variables": 222,
                            "numeric_variables": 221, "raw_and_decoded_finite": True,
                            "no_default_fill_or_masked_values": True},
                "restart": {"time": EXPECTED_TIMES[-1], "variables": 664,
                            "numeric_variables": 663, "raw_and_decoded_finite": True,
                            "no_default_fill_or_masked_values": True},
                "physics_checks": ["QC_CU positive", "QI_CU positive",
                                   "QZ0 finite/no-fill with full distribution reported",
                                   "USTM nonnegative"],
                "comparison": "Compare both arms against official OMP1 24h prefix and each other; raw bytes, dimensions, dtypes, attrs and global metadata. No tolerance or hidden boundary mask.",
            },
            "namelist_change_policy": "Only run_hours/end_day/end_hour/restart_interval and addition numtiles=2 differ from official pristine Jan RA4 namelist.",
            "namelist_diff": {"path": str(diff_path), "sha256": sha(diff_path)},
            "official_omp1_prefix_reference": {
                "path": str(OFFICIAL_CASE / "wrfout_d01_2000-01-24_12:00:00"),
                "sha256": INPUT_HASHES["reference_history"], "records_compared": 4,
            },
            "model_execution_supported_only_with_explicit_execute_flag": True,
        }
        (root / "stage.json").write_text(json.dumps(stage, indent=2, sort_keys=True) + "\n")
        (root / "README.md").write_text(readme(stage))
        return stage
    except Exception as exc:
        (root / "stage-failure.json").write_text(json.dumps({
            "status": "STAGE_FAILED_PRESERVED", "actual_model_invocations": 0,
            "error": repr(exc), "pins": pins,
        }, indent=2, sort_keys=True) + "\n")
        raise


def default_fill_check(path: Path) -> dict:
    hits = {}
    with Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        for name, var in ds.variables.items():
            dtype = np.dtype(var.dtype)
            if dtype.kind not in "iuf":
                continue
            key = dtype.kind + str(dtype.itemsize)
            if key not in default_fillvals:
                continue
            marker = np.asarray(default_fillvals[key], dtype=dtype)
            count = int(np.count_nonzero(np.asarray(var[:]) == marker))
            if count:
                hits[name] = count
    return {"hits": hits, "passed": not hits}


def validate_outputs(entry: dict) -> dict:
    """Validate history/checkpoint counts, values, fills and stock CU diagnostics."""
    m = load_runtime_helper()
    case = Path(entry["case_path"])
    histories = sorted(case.glob("wrfout_d01_*"))
    checkpoints = sorted(case.glob("wrfrst_d01_*"))
    expected_hist = ["wrfout_d01_2000-01-24_12:00:00"]
    expected_rst = ["wrfrst_d01_2000-01-24_15:00:00"]
    need([p.name for p in histories] == expected_hist, f"wrong history outputs: {[p.name for p in histories]}")
    need([p.name for p in checkpoints] == expected_rst, f"wrong restart outputs: {[p.name for p in checkpoints]}")
    history = m.validate_dataset(histories[0], EXPECTED_TIMES, 4)
    checkpoint = m.validate_dataset(checkpoints[0], [EXPECTED_TIMES[-1]], 4)
    history["default_fill_check"] = default_fill_check(histories[0])
    checkpoint["default_fill_check"] = default_fill_check(checkpoints[0])
    diagnostics = stock_checkpoint_diagnostics(checkpoints[0])
    checkpoint["stock_diagnostics"] = diagnostics["variables"]
    checkpoint["stock_diagnostics_passed"] = diagnostics["passed"]
    history["expected_variable_count"] = 222
    history["expected_numeric_variable_count"] = 221
    checkpoint["expected_variable_count"] = 664
    checkpoint["expected_numeric_variable_count"] = 663
    good = (history["passed"] and checkpoint["passed"] and
            history["variable_count"] == 222 and history["numeric_variable_count"] == 221 and
            checkpoint["variable_count"] == 664 and checkpoint["numeric_variable_count"] == 663 and
            history["default_fill_check"]["passed"] and checkpoint["default_fill_check"]["passed"] and
            checkpoint["stock_diagnostics_passed"])
    return {"history": history, "checkpoint": checkpoint, "passed": bool(good)}


def stock_checkpoint_diagnostics(path: Path) -> dict:
    diagnostics = {}
    with Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        for name in ("QC_CU", "QI_CU", "QZ0", "USTM"):
            need(name in ds.variables, f"checkpoint missing required diagnostic {name}")
            raw = np.asarray(ds.variables[name][:])
            need(raw.size > 0, f"empty checkpoint diagnostic {name}")
            finite = raw[np.isfinite(raw)]
            diagnostics[name] = {
                "dtype": raw.dtype.str, "shape": list(raw.shape),
                "total_count": int(raw.size),
                "finite_count": int(finite.size), "nonfinite_count": int(raw.size - finite.size),
                "minimum_finite": float(np.min(finite)) if finite.size else None,
                "maximum_finite": float(np.max(finite)) if finite.size else None,
                "positive_count": int(np.count_nonzero(raw > 0)),
                "negative_count": int(np.count_nonzero(raw < 0)),
                "zero_count": int(np.count_nonzero(raw == 0)),
            }
        diagnostics["QC_CU"]["passed"] = (diagnostics["QC_CU"]["nonfinite_count"] == 0 and
                                           diagnostics["QC_CU"]["positive_count"] > 0)
        diagnostics["QI_CU"]["passed"] = (diagnostics["QI_CU"]["nonfinite_count"] == 0 and
                                           diagnostics["QI_CU"]["positive_count"] > 0)
        diagnostics["QZ0"]["passed"] = diagnostics["QZ0"]["nonfinite_count"] == 0
        diagnostics["USTM"]["passed"] = (diagnostics["USTM"]["nonfinite_count"] == 0 and
                                          diagnostics["USTM"]["negative_count"] == 0)
    return {"variables": diagnostics, "passed": all(x["passed"] for x in diagnostics.values())}


def compare_history_prefix(candidate: Path, reference: Path) -> dict:
    """Compare every shared variable/attribute against first four official records."""
    differs = []
    metadata_differences = []
    with Dataset(candidate) as a, Dataset(reference) as b:
        ta, tb = dataset_times(a), dataset_times(b)
        times_pass = ta == EXPECTED_TIMES and tb[:len(EXPECTED_TIMES)] == EXPECTED_TIMES
        if not times_pass:
            metadata_differences.append({"kind": "Times", "candidate": ta,
                                         "reference_prefix": tb[:len(EXPECTED_TIMES)]})
        if a.data_model != b.data_model:
            metadata_differences.append({"kind": "data_model", "candidate": a.data_model,
                                         "reference": b.data_model})
        da, db = set(a.dimensions), set(b.dimensions)
        if da != db:
            metadata_differences.append({"kind": "dimension_names", "candidate_only": sorted(da-db),
                                         "reference_only": sorted(db-da)})
        for name in sorted(da & db):
            ad, bd = a.dimensions[name], b.dimensions[name]
            if ad.isunlimited() != bd.isunlimited() or (name != "Time" and len(ad) != len(bd)):
                metadata_differences.append({"kind": "dimension", "name": name,
                                             "candidate": [len(ad), ad.isunlimited()],
                                             "reference": [len(bd), bd.isunlimited()]})
        ga, gb = set(a.ncattrs()), set(b.ncattrs())
        if ga != gb:
            metadata_differences.append({"kind": "global_attribute_names",
                                         "candidate_only": sorted(ga-gb), "reference_only": sorted(gb-ga)})
        for name in sorted(ga & gb):
            aa, bb = _raw_meta_value(a.getncattr(name)), _raw_meta_value(b.getncattr(name))
            if aa != bb:
                metadata_differences.append({"kind": "global_attribute", "name": name,
                                             "candidate": aa, "reference": bb})
        va, vb = set(a.variables), set(b.variables)
        if va != vb:
            metadata_differences.append({"kind": "variable_names", "candidate_only": sorted(va-vb),
                                         "reference_only": sorted(vb-va)})
        for name in sorted(va & vb):
            av, bv = a.variables[name], b.variables[name]
            if av.dimensions != bv.dimensions or np.dtype(av.dtype) != np.dtype(bv.dtype):
                metadata_differences.append({"kind": "variable_declaration", "name": name,
                                             "candidate_dimensions": list(av.dimensions),
                                             "reference_dimensions": list(bv.dimensions),
                                             "candidate_dtype": np.dtype(av.dtype).str,
                                             "reference_dtype": np.dtype(bv.dtype).str})
            aa, ba = {n: _raw_meta_value(av.getncattr(n)) for n in av.ncattrs()}, {n: _raw_meta_value(bv.getncattr(n)) for n in bv.ncattrs()}
            if aa != ba:
                metadata_differences.append({"kind": "variable_attributes", "name": name,
                                             "candidate": aa, "reference": ba})
            av.set_auto_maskandscale(False); bv.set_auto_maskandscale(False)
            aa = np.asarray(av[:])
            bb = np.asarray(bv[:])
            if "Time" in bv.dimensions:
                axis = bv.dimensions.index("Time")
                bb = np.take(bb, np.arange(len(EXPECTED_TIMES)), axis=axis)
            same = aa.dtype == bb.dtype and aa.shape == bb.shape and aa.tobytes() == bb.tobytes()
            if not same:
                numeric = np.issubdtype(aa.dtype, np.number) and np.issubdtype(bb.dtype, np.number)
                max_abs = float(np.max(np.abs(aa.astype(np.float64) - bb.astype(np.float64)))) if numeric and aa.shape == bb.shape else None
                differs.append({"variable": name, "candidate_dtype": aa.dtype.str,
                                "reference_dtype": bb.dtype.str, "candidate_shape": list(aa.shape),
                                "reference_shape": list(bb.shape), "max_abs": max_abs,
                                "candidate_raw_sha256": hashlib.sha256(aa.tobytes()).hexdigest(),
                                "reference_prefix_raw_sha256": hashlib.sha256(bb.tobytes()).hexdigest()})
    return {"candidate": {"path": str(candidate), "sha256": sha(candidate)},
            "reference": {"path": str(reference), "sha256": sha(reference)},
            "expected_prefix_times": EXPECTED_TIMES, "times_pass": times_pass,
            "metadata_difference_count": len(metadata_differences),
            "metadata_differences": metadata_differences,
            "raw_difference_count": len(differs), "differences": differs,
            "bitwise_pass": times_pass and not metadata_differences and not differs}


def m_metadata(ds, dimensions_ignore_time_length=False) -> dict:
    dims = {}
    for name, dim in ds.dimensions.items():
        dims[name] = {"size": None if dimensions_ignore_time_length and name == "Time" else len(dim),
                      "unlimited": dim.isunlimited()}
    attrs = {name: _raw_meta_value(ds.getncattr(name)) for name in ds.ncattrs()}
    variables = {}
    for name, var in ds.variables.items():
        variables[name] = {"dtype": np.dtype(var.dtype).str,
                           "dimensions": list(var.dimensions),
                           "shape": [None if dimensions_ignore_time_length and d == "Time" else n
                                     for d, n in zip(var.dimensions, var.shape)],
                           "attributes": {a: _raw_meta_value(var.getncattr(a)) for a in var.ncattrs()}}
    return {"data_model": ds.data_model, "dimensions": dims, "attributes": attrs, "variables": variables}


def _raw_meta_value(value):
    if isinstance(value, str):
        return {"string": value}
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    arr = np.asarray(value)
    if arr.dtype.kind in "OUS":
        def encode(x):
            if isinstance(x, bytes):
                return {"bytes_hex": x.hex()}
            if isinstance(x, str):
                return {"string": x}
            if isinstance(x, np.bytes_):
                return {"bytes_hex": bytes(x).hex()}
            if isinstance(x, np.str_):
                return {"string": str(x)}
            return {"repr": repr(x)}
        return {"dtype": arr.dtype.str, "shape": list(arr.shape),
                "values": [encode(x) for x in arr.reshape(-1)]}
    return {"dtype": arr.dtype.str, "shape": list(arr.shape), "bytes_hex": arr.tobytes().hex()}


def dataset_times(ds) -> list[str]:
    if "Times" not in ds.variables:
        return []
    var = ds.variables["Times"]
    var.set_auto_maskandscale(False)
    rows = np.asarray(var[:])
    return [(b"".join(row).decode("ascii") if rows.dtype.kind == "S" else "".join(row)).strip()
            for row in rows]


def validate_stage(root: Path, stage_sha: str, arm: str, allow_outputs: bool = False) -> tuple[dict, dict]:
    stage_path = root / "stage.json"
    need(sha(stage_path) == stage_sha, "stage receipt hash changed")
    stage = json.loads(stage_path.read_text())
    need(stage["status"] == "STAGED_NOT_RUN" and stage["actual_model_invocations"] == 0,
         "stage receipt is not fresh/unrun")
    need(stage["runner"]["sha256"] == sha(Path(__file__) ) and
         stage["runtime_helper"]["sha256"] == sha(COMMON_HELPER), "runner/helper changed")
    live = verify_base()
    need(live == stage["pins"], "official source/runtime/input pins changed after staging")
    entry = stage["arms"][arm]
    case = Path(entry["case_path"])
    need(entry["threads"] == ARMS[arm], "wrong OMP arm contract")
    need(sha(case / "namelist.input") == entry["namelist_sha256"], "namelist changed")
    for name, rec in entry["runtime_assets"].items():
        path = case / name
        need(path.is_symlink() and path.resolve(strict=True) == Path(rec["path"]) and sha(path) == rec["sha256"],
             f"runtime asset/link changed: {name}")
    for name, expected in entry["input_hashes"].items():
        need((case / name).is_symlink() and sha(case / name) == expected, f"input changed: {name}")
    need((case / "wrf.exe").is_symlink() and sha(case / "wrf.exe") == WRF_SHA,
         "executable link changed")
    need(sha(case / "radiation_iofields.txt") == INPUT_HASHES["radiation_iofields.txt"],
         "radiation iofields changed")
    if not allow_outputs:
        need(not any(case.glob("wrfout_d01_*")) and not any(case.glob("wrfrst_d01_*")) and
             not any(case.glob("rsl.*")) and not (case / "runner.stdout.log").exists() and
             not (case / "run-progress.json").exists(), "case already has runtime outputs")
    return stage, entry


def run_arm(root: Path, stage_sha: str, arm: str, execute: bool) -> dict:
    m = load_runtime_helper()
    stage, entry = validate_stage(root, stage_sha, arm)
    output = root / f"{arm}-execution.json"
    if output.exists():
        raise FileExistsError(f"preserving prior execution receipt: {output}")
    if not execute:
        return {"status": "READY_NOT_RUN", "actual_model_invocations": 0,
                "arm": arm, "stage_sha256": stage_sha}
    e = {"case_path": entry["case_path"], "arm": arm,
         "link_names": list(entry["runtime_assets"]) + ["wrfinput_d01", "wrfbdy_d01", "wrf.exe"]}
    m.unused_case(e)
    result = {"status": "RUNNING", "actual_model_invocations": 0,
              "stage": {"path": str(root / "stage.json"), "sha256": stage_sha},
              "runner_sha256": sha(Path(__file__)), "arm": arm,
              "pre_run_pins": verify_base()}
    with output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    original_clean = m.clean_run_env

    def clean_arm_env(mpiexec, ld_path):
        env, cleared = original_clean(mpiexec, ld_path)
        additional = [k for k in env if k.startswith(("WRF_", "OMP_", "GOMP_", "KMP_")) or
                      k in ("LD_PRELOAD", "LD_AUDIT", "NETCDF", "OPENBLAS_NUM_THREADS")]
        for key in additional:
            env.pop(key, None)
        env.update({"OMP_NUM_THREADS": str(ARMS[arm]), "OMP_DYNAMIC": "FALSE",
                    "OMP_PROC_BIND": "FALSE", "OMP_STACKSIZE": "512M",
                    "OMP_MAX_ACTIVE_LEVELS": "1", "OMP_NESTED": "FALSE",
                    "OPENBLAS_NUM_THREADS": "1",
                    "MPICH_INTERFACE_HOSTNAME": "127.0.0.1", "NETCDF": str(NETCDF),
                    "LD_LIBRARY_PATH": ":".join(map(str, (NETCDF / "lib", MPICH / "lib", ROOT_LIBS)))})
        result["runtime_environment"] = {
            k: env[k] for k in ("OMP_NUM_THREADS", "OMP_DYNAMIC", "OMP_PROC_BIND", "OMP_STACKSIZE",
                                "OMP_MAX_ACTIVE_LEVELS", "OMP_NESTED", "OPENBLAS_NUM_THREADS",
                                "MPICH_INTERFACE_HOSTNAME", "NETCDF", "LD_LIBRARY_PATH")}
        result["cleared_inherited_runtime_environment_names"] = sorted(set(cleared + additional))
        return env, sorted(set(cleared + additional))

    try:
        m.clean_run_env = clean_arm_env
        def launched(pid):
            result["actual_model_invocations"] = 1
            result["process_group_pid"] = pid
            output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        args = type("RunArgs", (), {"mpiexec": m.MPIEXEC,
                                    "ld_library_path": ":".join(map(str, (NETCDF / "lib", MPICH / "lib", ROOT_LIBS)))})()
        result["model"] = m.run_one(e, args, on_launch=launched)
        result["outputs"] = validate_outputs(entry)
        result["official_omp1_history_prefix"] = compare_history_prefix(
            Path(entry["case_path"]) / "wrfout_d01_2000-01-24_12:00:00",
            OFFICIAL_CASE / "wrfout_d01_2000-01-24_12:00:00")
        result["status"] = ("PASS_ARM" if result["model"]["model_completed"] and
                            result["outputs"]["passed"] else "FAIL_PRESERVED")
    except Exception as exc:
        result["status"] = "FAIL_PRESERVED"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        m.clean_run_env = original_clean
        try:
            result["post_run_pins"] = verify_base()
            validate_stage(root, stage_sha, arm, allow_outputs=True)
            result["after_pins_valid"] = result["post_run_pins"] == result["pre_run_pins"]
            if not result["after_pins_valid"]:
                result["status"] = "FAIL_PRESERVED"
        except Exception as exc:
            result["after_pins_valid"] = False
            result["after_pin_error"] = f"{type(exc).__name__}: {exc}"
            result["status"] = "FAIL_PRESERVED"
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def compare_arms(root: Path, stage_sha: str) -> dict:
    stage = json.loads((root / "stage.json").read_text())
    need(sha(root / "stage.json") == stage_sha, "stage hash changed")
    entries = {}
    for arm in ARMS:
        validate_stage(root, stage_sha, arm, allow_outputs=True)
        recpath = root / f"{arm}-execution.json"
        need(recpath.is_file(), f"missing execution receipt {arm}")
        rec = json.loads(recpath.read_text())
        need(rec["status"] == "PASS_ARM" and rec["actual_model_invocations"] == 1 and
             rec["after_pins_valid"], f"arm did not pass: {arm}")
        entries[arm] = rec
    cmp_hist = compare_history_prefix(
        Path(entries["omp1"]["outputs"]["history"]["file"]["path"]),
        Path(entries["omp2"]["outputs"]["history"]["file"]["path"]))
    # Compare the single 15:00 checkpoints including full schema and raw arrays.
    m = load_runtime_helper()
    a = Path(entries["omp1"]["outputs"]["checkpoint"]["file"]["path"])
    b = Path(entries["omp2"]["outputs"]["checkpoint"]["file"]["path"])
    cmp_rst = m.compare_datasets(a, b)
    official_prefixes = {arm: entries[arm]["official_omp1_history_prefix"] for arm in ARMS}
    all_official_prefixes_pass = all(rec["bitwise_pass"] for rec in official_prefixes.values())
    result = {"status": "PASS" if cmp_hist["bitwise_pass"] and cmp_rst["passed"] and all_official_prefixes_pass else "DIFFERENCES_RECORDED",
              "stage_sha256": stage_sha,
              "omp1": str(root / "omp1-execution.json"), "omp2": str(root / "omp2-execution.json"),
              "official_omp1_history_prefix_checks": official_prefixes,
              "omp1_vs_omp2_history": cmp_hist, "omp1_vs_omp2_checkpoint": cmp_rst,
              "scope": "Pristine RA4 thread-count control only; no RA37 comparison or accuracy claim."}
    out = root / "comparison.json"
    if out.exists():
        raise FileExistsError(f"preserving prior comparison: {out}")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def readme(stage: dict) -> str:
    return f"""# Pristine current-case OMP control (staged only)

This package stages two fresh stock WRF-v4.8.0 RA4 cases using the existing Jan
24 12:00 initial/boundary data. It has not run WRF. The source is official commit `{SOURCE_COMMIT}` with binary
`{WRF_SHA}` and configure `{CONFIG_SHA}`. Each case uses MPI4 in a 2x2 layout,
`numtiles=2`, and differs only by the later runtime environment's
`OMP_NUM_THREADS=1` or `2`.

The only namelist changes from the official 24-hour case are end time 15:00,
`run_hours=3`, `restart_interval=180`, and `numtiles=2`. Both cases share the
same exact namelist, wrfinput, wrfbdy, radiation iofields, and 85 SHA-pinned
official runtime assets. The unchanged official OMP1 24-hour output provides
an independent three-hour prefix comparator. Expected history records are
`{EXPECTED_TIMES[0]}` through `{EXPECTED_TIMES[-1]}`; comparisons inspect all
222 history and 664 checkpoint variables, raw and decoded finiteness, fill/mask
conditions, CU QC/QI positivity, finite/no-fill QZ0 distribution, and USTM
nonnegativity stated in `stage.json`.

Model launches require `--run --execute`; that flag has not been used. Preparation status: `{stage['status']}`. Actual model invocations: 0.
"""


def self_test() -> None:
    text = (OFFICIAL_CASE / "namelist.input").read_text()
    changed = official_namelist(text)
    def projection(nml):
        return "".join(line for line in nml.splitlines(keepends=True)
                       if not re.match(r"(?im)^\s*(run_hours|end_day|end_hour|restart_interval|numtiles)\s*=", line))
    unchanged = projection(text) == projection(changed)
    try:
        official_namelist(re.sub(r"(?im)^(\s*run_hours\s*=\s*)24", r"\g<1>23", text, count=1))
        bad_base_rejected = False
    except ValueError:
        bad_base_rejected = True
    old_checkpoint = OFFICIAL_CASE / "wrfrst_d01_2000-01-25_12:00:00"
    old_history = OFFICIAL_CASE / "wrfout_d01_2000-01-24_12:00:00"
    no_fills = default_fill_check(old_checkpoint)["passed"] and default_fill_check(old_history)["passed"]
    old_diag = stock_checkpoint_diagnostics(old_checkpoint)
    with tempfile.TemporaryDirectory(prefix="pristine-omp-prefix-test-") as td:
        fixture = Path(td) / "history-prefix.nc"
        make_history_prefix_fixture(old_history, fixture)
        comparator_pass = compare_history_prefix(fixture, old_history)["bitwise_pass"]
        with Dataset(fixture, "r+") as ds:
            raw = np.asarray(ds.variables["SWDOWN"][0, :, :]).copy()
            raw.flat[0] = raw.flat[0] + np.asarray(1, dtype=raw.dtype)
            ds.variables["SWDOWN"][0, :, :] = raw
        changed = compare_history_prefix(fixture, old_history)
        comparator_detects_raw_difference = (not changed["bitwise_pass"] and
                                              any(item["variable"] == "SWDOWN" for item in changed["differences"]))
    checks = {
        "three_hour": bool(re.search(r"(?im)^\s*run_hours\s*=\s*3\s*,?\s*$", changed)),
        "end_day_24": bool(re.search(r"(?im)^\s*end_day\s*=\s*24\s*,?\s*$", changed)),
        "end_hour_15": bool(re.search(r"(?im)^\s*end_hour\s*=\s*15\s*,?\s*$", changed)),
        "restart_180": bool(re.search(r"(?im)^\s*restart_interval\s*=\s*180\s*,?\s*$", changed)),
        "numtiles_2": bool(re.search(r"(?im)^\s*numtiles\s*=\s*2\s*,?\s*$", changed)),
        "expected_times_4": len(EXPECTED_TIMES) == 4 and EXPECTED_TIMES[-1] == "2000-01-24_15:00:00",
        "unrelated_namelist_lines_identical": unchanged,
        "wrong_base_rejected": bad_base_rejected,
        "existing_official_history_checkpoint_no_default_fill": no_fills,
        "official_omp1_checkpoint_cu_ustm_sanity": all(old_diag["variables"][n]["passed"] for n in ("QC_CU", "QI_CU", "USTM")),
        "qz0_finite_no_fill_contract": old_diag["variables"]["QZ0"]["passed"] and no_fills,
        "four_record_full_schema_prefix_comparator_passes": comparator_pass,
        "prefix_comparator_detects_raw_change": comparator_detects_raw_difference,
    }
    if not all(checks.values()):
        raise RuntimeError(f"offline contract self-test failed: {checks}")
    print(json.dumps({"status": "SELF_TEST_PASS_NO_STAGE_NO_MODEL", "checks": checks}, sort_keys=True))


def make_history_prefix_fixture(source: Path, target: Path) -> None:
    """Copy first four raw records, retaining complete official schema/attrs."""
    with Dataset(source) as src, Dataset(target, "w", format="NETCDF4") as dst:
        for name, dim in src.dimensions.items():
            dst.createDimension(name, None if dim.isunlimited() else len(dim))
        for name in src.ncattrs():
            dst.setncattr(name, src.getncattr(name))
        for name, var in src.variables.items():
            fill = var.getncattr("_FillValue") if "_FillValue" in var.ncattrs() else False
            out = dst.createVariable(name, var.dtype, var.dimensions, fill_value=fill)
            for attr in var.ncattrs():
                if attr != "_FillValue":
                    out.setncattr(attr, var.getncattr(attr))
            var.set_auto_maskandscale(False)
            values = np.asarray(var[:])
            if "Time" in var.dimensions:
                axis = var.dimensions.index("Time")
                values = np.take(values, np.arange(4), axis=axis)
            out[:] = values


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--run", action="store_true", help="inspect an arm; launch only with --execute")
    mode.add_argument("--compare", action="store_true", help="compare both completed arms")
    ap.add_argument("--root", type=Path)
    ap.add_argument("--arm", choices=tuple(ARMS))
    ap.add_argument("--stage-sha")
    ap.add_argument("--execute", action="store_true", help="explicitly authorize a model launch")
    a = ap.parse_args()
    need(not a.execute or a.run, "--execute is accepted only together with --run")
    if a.self_test:
        need(not a.execute, "--self-test cannot execute WRF")
        self_test()
        return 0
    if a.preflight:
        need(not a.execute, "--preflight cannot execute WRF")
        pins = verify_base()
        print(json.dumps({"status": "PREFLIGHT_PASS_NO_STAGE_NO_MODEL", "pins": pins}, indent=2, sort_keys=True))
        return 0
    if a.run:
        need(a.root is not None and a.stage_sha and a.arm, "--run requires --root, --stage-sha and --arm")
        r = run_arm(a.root.absolute(), a.stage_sha, a.arm, a.execute)
        print(json.dumps({"status": r["status"], "actual_model_invocations": r.get("actual_model_invocations", 0)}, sort_keys=True))
        return 0 if r["status"].startswith(("READY_", "PASS_")) else 1
    if a.compare:
        need(a.root is not None and a.stage_sha, "--compare requires --root and --stage-sha")
        r = compare_arms(a.root.absolute(), a.stage_sha)
        print(json.dumps({"status": r["status"], "comparison": str(a.root / "comparison.json")}, sort_keys=True))
        return 0 if r["status"] == "PASS" else 1
    need(not a.execute, "--prepare stages cases only and never launches WRF")
    if a.root is None:
        ap.error("--prepare requires --root NEW_ABSOLUTE_PATH")
    stage = prepare(a.root)
    print(json.dumps({"status": stage["status"], "root": str(a.root),
                      "actual_model_invocations": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
