#!/usr/bin/env python3
"""One-use runner for the three-arm serial Matthew wrapper audit.

This file only runs when a separate root-authorization JSON binds its exact
bytes, stage pins, executable, runtime closure, loader coefficients and expiry.
There is no retry or automatic extension. Do not edit after authorization.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP")
PLAN = HERE / "plan.json"
MANIFEST = HERE / "stage-manifest.json"
READBACK = HERE / "stage-readback-v1.json"
IDENTITY = HERE / "runtime-build-identity-v1.json"
AUTH = HERE / "root-authorization.json"
LOCK = HERE / ".one-use.lock"
RECEIPT = HERE / "execution-receipt.json"
ARMS = ("OFF", "ON_native4_0", "ON_native4_1")
HISTORY_TIMES = ("2016-10-07_12:00:00", "2016-10-07_13:00:00")
END_TIME = "2016-10-07_13:00:00"
CHECKPOINT_INPUT = "wrfrst_d01_2016-10-07_12:00:00"
FATAL_MARKERS = ("FATAL CALLED FROM FILE", "APPLICATION CALLED MPI_ABORT",
                 "ERROR: FATAL", "RRTMGP_FATAL", "RRtmgp_fatal", "RRTMGP_TRACE_")
AUDIT_COLUMNS = {"phase", "domain", "step", "source_seconds", "i", "j", "metric",
                 "value37", "value4", "sample_count", "mean37", "sd37", "mean4",
                 "sd4", "sd_delta", "radius_mode", "scope"}
INPUT_NAMES = {"wrfinput_d01", "wrfbdy_d01", CHECKPOINT_INPUT, "radiation_iofields.txt"}


def sha(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pin(path: Path | str) -> dict:
    p = Path(path)
    return {"path": str(p.resolve()), "size_bytes": p.stat().st_size, "sha256": sha(p)}


def atomic(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_text() -> str:
    return utc_now().isoformat()


def check_pin(record: dict, label: str) -> None:
    path = Path(record["path"])
    if not path.is_file():
        raise RuntimeError(f"{label}: pinned file is absent: {path}")
    if path.stat().st_size != record["size_bytes"] or sha(path) != record["sha256"]:
        raise RuntimeError(f"{label}: pinned bytes changed: {path}")


def verify_manifest_sources(identity: dict) -> dict:
    """Rehash every tracked source file listed by the accepted fresh-build manifest."""
    manifest_pin = identity["build"]["source_manifest"]
    check_pin(manifest_pin, "source manifest")
    manifest = json.loads(Path(manifest_pin["path"]).read_text())
    if manifest["tracked_file_count"] != len(manifest["tracked_files"]):
        raise RuntimeError("source manifest tracked-file count is inconsistent")
    source_root = Path(identity["build"]["source_root"])
    bad = []
    for item in manifest["tracked_files"]:
        path = source_root / item["path"]
        if item["git_mode"] == "120000":
            raw = os.readlink(path).encode() if path.is_symlink() else b""
        else:
            raw = path.read_bytes() if path.is_file() and not path.is_symlink() else b""
        if len(raw) != item["size_bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            bad.append(item["path"])
            if len(bad) >= 10:
                break
    if bad:
        raise RuntimeError(f"tracked source drift: {bad}")
    return {"manifest_sha256": manifest_pin["sha256"],
            "tracked_file_count": len(manifest["tracked_files"]), "all_tracked_bytes_match": True}


def ldd_map(executable: Path, ld_library_path: str) -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin", "LD_LIBRARY_PATH": ld_library_path,
           "LC_ALL": "C", "LANG": "C"}
    proc = subprocess.run(["/usr/bin/ldd", str(executable)], env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode:
        raise RuntimeError(f"ldd failed: {proc.stdout[-2000:]}")
    resolved: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        parts = line.strip().split()
        path = None
        if "=>" in parts:
            idx = parts.index("=>")
            if idx + 1 < len(parts) and parts[idx + 1].startswith("/"):
                path = parts[idx + 1]
        elif parts and parts[0].startswith("/"):
            path = parts[0]
        if path:
            p = Path(path).resolve(strict=True)
            if p.name in resolved and resolved[p.name] != str(p):
                raise RuntimeError(f"duplicate soname basename in ldd closure: {p.name}")
            resolved[p.name] = str(p)
    return resolved


def verify_runtime(plan: dict, identity: dict, auth: dict) -> dict:
    exe = Path(plan["executable"]["path"])
    check_pin(plan["executable"], "WRF executable")
    if plan["executable"]["sha256"] != identity["executable"]["sha256"]:
        raise RuntimeError("plan and runtime identity executable disagree")
    for label, key in (("build receipt", "receipt"), ("build log", "log"),
                       ("source manifest", "source_manifest"),
                       ("toolchain inventory", "toolchain_dependency_inventory"),
                       ("analysis helper", "analysis_tool"),
                       ("radius comparator", "radius_comparator")):
        record = identity[key] if key in ("analysis_tool", "radius_comparator") else identity["build"][key]
        check_pin(record, label)
    check_pin(identity["build"]["postbuild_readback"], "independent postbuild readback")
    postbuild = json.loads(Path(identity["build"]["postbuild_readback"]["path"]).read_text())
    if postbuild.get("status") != "POSTBUILD_PASS":
        raise RuntimeError("independent postbuild readback is not PASS")
    if postbuild.get("executables", {}).get("wrf.exe", {}).get("sha256") != identity["executable"]["sha256"]:
        raise RuntimeError("postbuild readback executable differs from the stage executable")
    build_receipt = json.loads(Path(identity["build"]["receipt"]["path"]).read_text())
    if build_receipt.get("status") != "BUILD_PASS" or build_receipt.get("returncode") != 0:
        raise RuntimeError("fresh serial build receipt is not BUILD_PASS")
    if build_receipt.get("model_invocations") != 0:
        raise RuntimeError("build receipt unexpectedly records model calls")
    if build_receipt["executables"]["wrf.exe"]["sha256"] != sha(exe):
        raise RuntimeError("build receipt executable hash mismatch")
    libs = identity["executable"]["runtime_libraries"]
    if len(libs) != 48 or identity["executable"]["runtime_library_count"] != 48:
        raise RuntimeError("unexpected shared-library closure length")
    for rec in libs:
        check_pin(rec, f"runtime library {rec['path']}")
    dep_path = Path(identity["build"]["toolchain_dependency_inventory"]["path"])
    dep = json.loads(dep_path.read_text())
    runtime_env = dep["runtime_environment"]
    resolved = ldd_map(exe, runtime_env["LD_LIBRARY_PATH"])
    if resolved != identity["executable"]["resolved_ldd_map"]:
        raise RuntimeError("live ldd resolved-library map differs from the build receipt")
    expected_map = {Path(x["path"]).name: str(Path(x["path"]).resolve()) for x in libs}
    if resolved != expected_map:
        raise RuntimeError("runtime closure map is inconsistent with pinned library files")
    checked_source = verify_manifest_sources(identity)
    for rec in identity["actual_rrtmgp_loader_files"]["files"]:
        check_pin(rec, "fresh RRTMGP coefficient loader input")
    check_pin(identity["frozen_table"], "expanded frozen Planck table")
    if auth.get("executable_sha256") != sha(exe):
        raise RuntimeError("authorization executable hash does not match")
    return {"executable": pin(exe), "runtime_library_count": len(libs),
            "runtime_libraries": libs,
            "ldd_map": resolved,
            "fresh_loader_files": identity["actual_rrtmgp_loader_files"]["files"],
            "frozen_table": identity["frozen_table"], "source_readback": checked_source}


def verify_stage(plan: dict, manifest: dict, readback: dict, identity: dict, empty_arm: str | None = None) -> dict:
    if plan.get("status") != "STAGED_WAITING_FOR_ROOT_AUTHORIZATION":
        raise RuntimeError("stage plan is not in pending-authorization state")
    if manifest.get("plan_sha256") != sha(PLAN):
        raise RuntimeError("stage manifest does not bind current plan")
    if readback.get("stage_plan_sha256") != sha(PLAN) or readback.get("stage_manifest_sha256") != sha(MANIFEST):
        raise RuntimeError("stage readback hashes do not match current plan/manifest")
    ipin = plan["runtime_build_identity"]
    if ipin["path"] != str(IDENTITY) or ipin["sha256"] != sha(IDENTITY):
        raise RuntimeError("plan does not bind the frozen runtime identity")
    if readback.get("runtime_build_identity") != ipin or manifest.get("runtime_build_identity") != ipin:
        raise RuntimeError("plan/manifest/readback runtime identity pins disagree")
    runner_pin = plan.get("execution_runner")
    if not runner_pin or runner_pin.get("path") != str(Path(__file__).resolve()) or runner_pin.get("sha256") != sha(Path(__file__)):
        raise RuntimeError("plan does not bind these runner bytes")
    if manifest.get("execution_runner") != runner_pin or readback.get("execution_runner") != runner_pin:
        raise RuntimeError("runner pins disagree across plan/manifest/readback")
    arm_summary = {}
    for arm in ARMS:
        case = Path(plan["arms"][arm]["case_path"])
        rows = manifest["arms"][arm]["entries"]
        if len(rows) != 104 or plan["arms"][arm]["staged_entry_count"] != 104:
            raise RuntimeError(f"{arm}: expected 104 staged entries")
        for rec in rows:
            p = case / rec["name"]
            if rec["kind"] == "symlink":
                if not p.is_symlink() or os.readlink(p) != rec["link_text"]:
                    raise RuntimeError(f"{arm}/{rec['name']}: symlink identity changed")
                target = p.resolve(strict=True)
                if str(target) != rec["target_path"]:
                    raise RuntimeError(f"{arm}/{rec['name']}: symlink target changed")
                got = pin(target)
            else:
                if not p.is_file() or p.is_symlink():
                    raise RuntimeError(f"{arm}/{rec['name']}: expected regular staged file")
                got = pin(p)
            if got["sha256"] != rec["sha256"] or got["size_bytes"] != rec["bytes"]:
                raise RuntimeError(f"{arm}/{rec['name']}: staged content changed")
        if sha(case / "namelist.input") != plan["arms"][arm]["namelist_sha256"]:
            raise RuntimeError(f"{arm}: namelist changed")
        nml = (case / "namelist.input").read_text()
        expected = {"run_days": "0", "run_hours": "1", "run_minutes": "0", "run_seconds": "0",
                    "start_year": "2016", "start_month": "10", "start_day": "07", "start_hour": "12",
                    "end_year": "2016", "end_month": "10", "end_day": "07", "end_hour": "13",
                    "ra_lw_physics": "37", "ra_sw_physics": "37", "mp_physics": "27",
                    "use_mp_re": "1", "cu_physics": "1", "cudt": "5", "time_step": "60",
                    "numtiles": "1", "history_interval": "60", "frames_per_outfile": "1",
                    "restart_interval": "60", "restart": ".true.", "override_restart_timers": ".true.",
                    "write_hist_at_0h_rst": ".true.", "radt": "10", "rrtmgp_udm_frozen_optics": "1",
                    "rrtmgp_ice_roughness": "1",
                    "rrtmgp_data_path": f"'{identity['actual_rrtmgp_loader_files']['root']}'",
                    "rrtmgp_udm_frozen_table": f"'{identity['frozen_table']['path']}'"}
        for key, value in expected.items():
            vals = re.findall(rf"(?im)^\s*{re.escape(key)}\s*=\s*([^,\n]+)", nml)
            if vals != [value] and key not in {"radt"}:
                raise RuntimeError(f"{arm}: namelist {key} differs from reviewed value: {vals}")
            if key == "radt" and vals != [value + ".0"] and vals != [value]:
                raise RuntimeError(f"{arm}: namelist {key} differs from reviewed value: {vals}")
        if empty_arm == "ALL" or empty_arm == arm:
            actual_files = {p.name for p in case.iterdir() if p.is_file() or p.is_symlink()}
            if actual_files != {x["name"] for x in rows}:
                raise RuntimeError(f"{arm}: file roster differs from stage manifest")
            forbidden = []
            for pattern in ("wrf.exe", "wrf.stdout.log", "rsl.*", "wrfout_d01_*", "wrfrst_d01_*"):
                forbidden += [p.name for p in case.glob(pattern)
                              if p.name != CHECKPOINT_INPUT and not p.is_dir()]
            if forbidden:
                raise RuntimeError(f"{arm}: staged output/executable artifacts already exist: {forbidden[:6]}")
            for dirname in ("trace", "audit"):
                q = case / dirname
                if q.exists() and any(q.iterdir()):
                    raise RuntimeError(f"{arm}/{dirname}: trace/audit directory is not empty before run")
        arm_summary[arm] = {"staged_entry_count": len(rows), "namelist_sha256": sha(case / "namelist.input"),
                            "input_sha256": {name: sha(case / name) for name in sorted(INPUT_NAMES)}}
    if len({v["namelist_sha256"] for v in arm_summary.values()}) != 1:
        raise RuntimeError("reviewed physics/restart namelists are not byte-identical")
    return {"arms": arm_summary, "plan_sha256": sha(PLAN), "manifest_sha256": sha(MANIFEST),
            "readback_sha256": sha(READBACK), "identity_sha256": sha(IDENTITY)}


def clean_environment(identity: dict, arm: str) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if (key.startswith(("WRF_RRTMGP_", "GOMP_", "KMP_", "OMP_")) or
                key in {"WRF_UDM_BOUNDARY_CAPTURE", "LD_PRELOAD", "LD_AUDIT"}):
            env.pop(key, None)
    dep = json.loads(Path(identity["build"]["toolchain_dependency_inventory"]["path"]).read_text())
    env["LD_LIBRARY_PATH"] = dep["runtime_environment"]["LD_LIBRARY_PATH"]
    env["OMP_NUM_THREADS"] = "1"
    env["WRF_RRTMGP_BATCH_SIZE"] = "1"
    env["WRF_RRTMGP_COLUMN_I"] = "24"
    env["WRF_RRTMGP_COLUMN_J"] = "55"
    env["WRF_RRTMGP_CAPTURE_DIR"] = str(Path(PLAN.parent / arm / "trace"))
    env["WRF_RRTMGP_CAPTURE_ALL"] = "1"
    if arm != "OFF":
        env["WRF_RRTMGP_AUDIT_DIR"] = str(Path(PLAN.parent / arm / "audit"))
        env["WRF_RRTMGP_AUDIT_SEEDS"] = "128"
        env["WRF_RRTMGP_AUDIT_NATIVE4"] = "0" if arm.endswith("_0") else "1"
    return env


def raw_key(path: Path) -> tuple[str, int, float]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RAW_V1":
        raise RuntimeError(f"{path}: unsupported raw trace format")
    h = lines[1].split()
    if len(h) != 4 or h[0].upper() not in {"LW", "SW"} or int(h[1]) != 24 or int(h[2]) != 55:
        raise RuntimeError(f"{path}: unexpected selected-column raw header {h}")
    records: dict[str, list[float]] = {}
    pos = 2
    while pos < len(lines):
        if not lines[pos].strip():
            pos += 1; continue
        header = lines[pos].split(); pos += 1
        if len(header) != 2:
            raise RuntimeError(f"{path}: malformed record header")
        name, count = header[0].upper(), int(header[1])
        vals: list[float] = []
        while len(vals) < count and pos < len(lines):
            vals.extend(float(x.replace("D", "E").replace("d", "e")) for x in lines[pos].split())
            pos += 1
        if len(vals) != count or name in records or not np.isfinite(vals).all():
            raise RuntimeError(f"{path}: invalid/nonfinite raw record {name}")
        records[name] = vals
    if "RADIATION_STEP" not in records or "SOURCE_TIME_SECONDS" not in records:
        raise RuntimeError(f"{path}: missing radiation step/time identity")
    step = records["RADIATION_STEP"]
    seconds = records["SOURCE_TIME_SECONDS"]
    if len(step) != 1 or len(seconds) != 1 or step[0] != int(step[0]):
        raise RuntimeError(f"{path}: malformed step/time identity")
    return h[0].upper(), int(step[0]), float(seconds[0])


def capture_groups(case: Path) -> list[dict]:
    folder = case / "trace"
    groups: dict[tuple[str, int, float], dict[str, str]] = {}
    raws = sorted(folder.glob("*.raw"))
    if not raws:
        raise RuntimeError(f"{case}: no production raw captures")
    for raw in raws:
        stem = raw.with_suffix("")
        files = {suffix: stem.with_suffix("." + suffix) for suffix in ("raw", "input", "result")}
        for suffix, path in files.items():
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"{case}: incomplete capture group {stem.name}, missing {suffix}")
        key = raw_key(raw)
        if key in groups:
            raise RuntimeError(f"{case}: duplicate actual scheduler key {key}")
        groups[key] = {suffix: sha(path) for suffix, path in files.items()}
    return [{"phase": key[0], "radiation_step": key[1], "source_seconds": key[2],
             "files_sha256": groups[key]} for key in sorted(groups)]


def capture_map(records: list[dict]) -> dict[tuple[str, int, float], dict[str, str]]:
    result = {}
    for rec in records:
        key = (rec["phase"], int(rec["radiation_step"]), float(rec["source_seconds"]))
        if key in result:
            raise RuntimeError(f"duplicate capture key in receipt: {key}")
        result[key] = rec["files_sha256"]
    return result


def audit_roster(case: Path, arm: str) -> dict:
    csv_path = case / "audit" / "same_state.csv"
    if not csv_path.is_file():
        raise RuntimeError(f"{arm}: expected same_state.csv is absent")
    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not AUDIT_COLUMNS <= set(reader.fieldnames):
            raise RuntimeError(f"{arm}: audit CSV header is incomplete")
        rows = list(reader)
    if not rows:
        raise RuntimeError(f"{arm}: audit CSV contains no rows")
    for row in rows:
        for col in ("phase", "domain", "step", "source_seconds", "i", "j", "value37", "value4", "sample_count",
                    "mean37", "sd37", "mean4", "sd4", "sd_delta"):
            if col not in row:
                raise RuntimeError(f"{arm}: audit row lacks {col}")
            if col not in ("phase", "domain") and not np.isfinite(float(row[col])):
                raise RuntimeError(f"{arm}: audit {col} contains a nonfinite value")
        if int(float(row["sample_count"])) != 128 or float(row["sample_count"]) != 128.0:
            raise RuntimeError(f"{arm}: audit sample_count must be exactly 128, got {row['sample_count']}")
        if float(row["sd37"]) < 0.0 or float(row["sd4"]) < 0.0:
            raise RuntimeError(f"{arm}: audit standard deviations must be nonnegative")
        if row["scope"] != "selected_column":
            raise RuntimeError(f"{arm}: unexpected audit scope {row['scope']}")
    cell_rows = [r for r in rows if int(r["i"]) == 24 and int(r["j"]) == 55]
    if not cell_rows:
        raise RuntimeError(f"{arm}: no CSV rows for selected global point i=24,j=55")
    by_phase: dict[str, set[tuple[int, float]]] = {"LW": set(), "SW": set()}
    for row in cell_rows:
        phase = row["phase"].upper()
        if phase not in by_phase:
            raise RuntimeError(f"{arm}: unexpected phase {phase}")
        by_phase[phase].add((int(row["step"]), float(row["source_seconds"])))
        expected_mode = 1 if arm.endswith("_1") else 0
        if int(row["radius_mode"]) != expected_mode:
            raise RuntimeError(f"{arm}: radius_mode {row['radius_mode']} != {expected_mode}")
    keys = sorted((phase, step, seconds) for phase, pairs in by_phase.items() for step, seconds in pairs)
    if len(keys) != len(set(keys)) or not keys:
        raise RuntimeError(f"{arm}: invalid scheduler call roster")
    return {"csv": pin(csv_path), "row_count": len(rows), "selected_point_call_keys": keys,
            "phase_call_counts": {k: len(v) for k, v in by_phase.items()},
            "scope": "all-sky selected-column CSV only; no paired clear-sky CSV"}


def verify_history(path: Path, expected_time: str) -> dict:
    result = {"file": pin(path), "times": [], "variables": 0, "numeric_values_checked": 0}
    with Dataset(path, "r") as ds:
        if "Times" not in ds.variables:
            raise RuntimeError(f"{path}: missing Times")
        result["times"] = ["".join(x.decode() if isinstance(x, bytes) else str(x) for x in row).strip()
                           for row in ds["Times"][:]]
        if result["times"] != [expected_time]:
            raise RuntimeError(f"{path}: Times {result['times']} != {[expected_time]}")
        result["dimensions"] = {k: {"size": len(v), "unlimited": bool(v.isunlimited())}
                                for k, v in ds.dimensions.items()}
        for name, var in ds.variables.items():
            result["variables"] += 1
            var.set_auto_maskandscale(False)
            raw = np.asarray(var[:])
            if raw.dtype.kind in "fci":
                if not np.isfinite(raw).all():
                    raise RuntimeError(f"{path}:{name} has nonfinite raw values")
                for attr in ("_FillValue", "missing_value"):
                    if attr in var.ncattrs():
                        fill = np.asarray(var.getncattr(attr))
                        if np.any(raw == fill):
                            raise RuntimeError(f"{path}:{name} contains {attr}")
                result["numeric_values_checked"] += raw.size
            var.set_auto_maskandscale(True)
            decoded = var[:]
            if np.ma.isMaskedArray(decoded) and np.ma.getmaskarray(decoded).any():
                raise RuntimeError(f"{path}:{name} contains decoded masked values")
            decoded_data = np.asarray(decoded.data if np.ma.isMaskedArray(decoded) else decoded)
            if decoded_data.dtype.kind in "fci" and not np.isfinite(decoded_data).all():
                raise RuntimeError(f"{path}:{name} contains nonfinite decoded values")
        result["global_attributes"] = {k: attr_value(ds.getncattr(k)) for k in ds.ncattrs()}
    return result


def attr_value(value):
    if isinstance(value, np.ndarray):
        def clean(item):
            if isinstance(item, bytes):
                return item.decode("utf-8", errors="replace")
            if isinstance(item, np.generic):
                return clean(item.item())
            if isinstance(item, list):
                return [clean(x) for x in item]
            return item
        return {"dtype": str(value.dtype), "shape": list(value.shape), "values": clean(value.tolist())}
    if isinstance(value, bytes):
        return {"type": "bytes", "value": value.decode("utf-8", errors="replace")}
    if isinstance(value, np.generic):
        return {"dtype": str(value.dtype), "value": attr_value(value.item())}
    return {"type": type(value).__name__, "value": value}


def compare_netcdf(left: Path, right: Path) -> dict:
    out = {"left": pin(left), "right": pin(right), "status": "PASS_EXACT", "mismatches": []}
    with Dataset(left, "r") as a, Dataset(right, "r") as b:
        if a.data_model != b.data_model:
            out["mismatches"].append({"data_model": [a.data_model, b.data_model]})
        da = {k: (len(v), bool(v.isunlimited())) for k, v in a.dimensions.items()}
        db = {k: (len(v), bool(v.isunlimited())) for k, v in b.dimensions.items()}
        if da != db: out["mismatches"].append({"dimensions": [da, db]})
        if set(a.variables) != set(b.variables):
            out["mismatches"].append({"variable_set": {"left_only": sorted(set(a.variables)-set(b.variables), key=str),
                                                          "right_only": sorted(set(b.variables)-set(a.variables), key=str)}})
        for name in sorted(set(a.variables) & set(b.variables), key=str):
            x, y = a[name], b[name]
            schema = (x.dimensions, x.shape, str(x.dtype))
            if schema != (y.dimensions, y.shape, str(y.dtype)):
                out["mismatches"].append({"variable_schema": name}); continue
            x.set_auto_maskandscale(False); y.set_auto_maskandscale(False)
            if np.asarray(x[:]).tobytes(order="C") != np.asarray(y[:]).tobytes(order="C"):
                out["mismatches"].append({"variable_bytes": name})
            if {k: attr_value(x.getncattr(k)) for k in x.ncattrs()} != {k: attr_value(y.getncattr(k)) for k in y.ncattrs()}:
                out["mismatches"].append({"variable_attributes": name})
        if {k: attr_value(a.getncattr(k)) for k in a.ncattrs()} != {k: attr_value(b.getncattr(k)) for k in b.ncattrs()}:
            out["mismatches"].append({"global_attributes": True})
    if out["mismatches"]: out["status"] = "FAIL_DIFFERENCE"
    return out


def read_auth(plan: dict, manifest: dict, readback: dict, identity: dict) -> dict:
    if not AUTH.is_file():
        raise RuntimeError("root-authorization.json is absent; no model launch is permitted")
    auth = json.loads(AUTH.read_text())
    if auth.get("schema") != "UDM37_CURRENT_MATTHEW_SERIAL_AUDIT_AUTH_V1" or auth.get("status") != "AUTHORIZED_ONCE":
        raise RuntimeError("authorization schema/status is invalid")
    expected = {"runner_sha256": sha(Path(__file__)), "plan_sha256": sha(PLAN),
                "manifest_sha256": sha(MANIFEST), "readback_sha256": sha(READBACK),
                "runtime_identity_sha256": sha(IDENTITY),
                "executable_sha256": identity["executable"]["sha256"]}
    for key, value in expected.items():
        if auth.get(key) != value:
            raise RuntimeError(f"authorization {key} does not bind reviewed bytes")
    if auth.get("max_forecasts") != 3 or auth.get("per_arm_timeout_seconds") != 600:
        raise RuntimeError("authorization must permit exactly three arms and 600 s per arm")
    if int(auth.get("model_invocation_budget", -1)) != 3:
        raise RuntimeError("authorization does not bind the three-call budget")
    now = utc_now()
    issued = dt.datetime.fromisoformat(auth["issued_utc"].replace("Z", "+00:00"))
    expires = dt.datetime.fromisoformat(auth["expires_utc"].replace("Z", "+00:00"))
    if issued > now or expires <= now or (expires - issued).total_seconds() > 3600:
        raise RuntimeError("authorization is not currently valid or exceeds one hour")
    if auth.get("expected_arm_order") != list(ARMS):
        raise RuntimeError("authorization arm order differs from reviewed order")
    return auth


def check_empty_once() -> None:
    if LOCK.exists() or RECEIPT.exists() or (HERE / "radius-arm-comparison.json").exists():
        raise RuntimeError("one-use lock or execution receipt already exists; refusing any rerun")


def scan_logs(case: Path) -> dict:
    rank_success = set()
    fatal = []
    scanned = []
    for pattern in ("rsl.out.*", "rsl.error.*", "wrf.stdout.log"):
        for path in sorted(case.glob(pattern)):
            if not path.is_file(): continue
            scanned.append(pin(path))
            text = path.read_text(encoding="utf-8", errors="replace")
            if "wrf: success complete wrf" in text.lower():
                m = re.search(r"\.(\d+)$", path.name)
                rank_success.add(int(m.group(1)) if m else 0)
            for no, line in enumerate(text.splitlines(), 1):
                if any(marker.lower() in line.lower() for marker in FATAL_MARKERS):
                    fatal.append({"file": path.name, "line": no, "text": line[:1000]})
    return {"success_ranks": sorted(rank_success), "fatal_markers": fatal, "logs": scanned}


def run_arm(arm: str, plan: dict, identity: dict, receipt: dict, auth: dict) -> None:
    case = Path(plan["arms"][arm]["case_path"])
    exe = Path(plan["executable"]["path"])
    # All immutable source/runtime/input pins are checked immediately before Popen.
    runtime = verify_runtime(plan, identity, auth)
    stage = verify_stage(plan, json.loads(MANIFEST.read_text()), json.loads(READBACK.read_text()), identity,
                         empty_arm=arm)
    stdout = case / "wrf.stdout.log"
    if stdout.exists():
        raise RuntimeError(f"{arm}: stdout log already exists")
    arm_rec = {"status": "PREPARED", "cwd": str(case), "started_utc": utc_text(),
               "command": [str(exe)], "process_id": None, "model_invocations": 0,
               "returncode": None, "timed_out": False, "runtime_prelaunch": runtime,
               "stage_prelaunch": stage}
    receipt["arms"][arm] = arm_rec
    atomic(RECEIPT, receipt)
    env = clean_environment(identity, arm)
    proc = None
    rc = None
    timed_out = False
    try:
        # Recheck authorization window and binary directly at launch boundary.
        if utc_now() >= dt.datetime.fromisoformat(auth["expires_utc"].replace("Z", "+00:00")):
            raise RuntimeError("authorization expired immediately before launch")
        if sha(Path(__file__)) != auth["runner_sha256"] or sha(PLAN) != auth["plan_sha256"]:
            raise RuntimeError("runner/plan changed immediately before launch")
        if sha(AUTH) != receipt["authorization_sha256"]:
            raise RuntimeError("root authorization changed immediately before launch")
        if sha(exe) != auth["executable_sha256"]:
            raise RuntimeError("executable changed immediately before launch")
        with stdout.open("xb") as log:
            proc = subprocess.Popen([str(exe)], cwd=case, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            arm_rec["process_id"] = proc.pid
            arm_rec["model_invocations"] = 1
            receipt["model_invocations"] += 1
            arm_rec["status"] = "RUNNING"
            atomic(RECEIPT, receipt)
            try:
                rc = proc.wait(timeout=600)
            except subprocess.TimeoutExpired:
                timed_out = True
                try: os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: rc = proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    rc = proc.wait()
    except BaseException as exc:
        arm_rec["launch_or_wait_error"] = repr(exc)
        if proc is not None and proc.poll() is None:
            try: os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: rc = proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                rc = proc.wait()
    # Actual child return code is durable before any log/output inspection.
    arm_rec["returncode"] = rc
    arm_rec["timed_out"] = timed_out
    arm_rec["ended_utc"] = utc_text()
    arm_rec["process_status"] = "PROCESS_COMPLETE" if proc is not None else "NOT_LAUNCHED"
    atomic(RECEIPT, receipt)
    if proc is None or rc is None:
        arm_rec["status"] = "FAIL_PRESERVED"
        arm_rec["reason"] = arm_rec.get("launch_or_wait_error", "child process did not launch/complete")
        atomic(RECEIPT, receipt)
        raise RuntimeError(f"{arm}: process did not complete")
    # Revalidate immutable source, build closure, fresh loader inputs, stage inputs,
    # and table after the child exits and before log/output inspection.
    arm_rec["runtime_postprocess"] = verify_runtime(plan, identity, auth)
    arm_rec["stage_postprocess"] = verify_stage(plan, json.loads(MANIFEST.read_text()),
                                                json.loads(READBACK.read_text()), identity)
    atomic(RECEIPT, receipt)
    log_info = scan_logs(case)
    arm_rec["log_scan"] = log_info
    if rc != 0 or timed_out or log_info["fatal_markers"] or log_info["success_ranks"] != [0]:
        arm_rec["status"] = "FAIL_PRESERVED"
        arm_rec["reason"] = "nonzero return, timeout, fatal marker, or missing unique serial success"
        atomic(RECEIPT, receipt)
        raise RuntimeError(f"{arm}: model process/WRF success gate failed")
    arm_rec["status"] = "MODEL_SUCCESS_POSTFLIGHT_PENDING"
    arm_rec["quality"] = []
    histories = sorted(case.glob("wrfout_d01_20*"))
    actual_times = []
    for f in histories:
        quality = verify_history(f, f.name.removeprefix("wrfout_d01_"))
        actual_times.extend(quality["times"])
        arm_rec["quality"].append(quality)
    if len(histories) != len(HISTORY_TIMES) or tuple(actual_times) != HISTORY_TIMES:
        raise RuntimeError(f"{arm}: expected one history file at each endpoint {HISTORY_TIMES}, got {actual_times}")
    restart_outputs = sorted(p for p in case.glob("wrfrst_d01_*") if p.name != CHECKPOINT_INPUT)
    required_restart = f"wrfrst_d01_{END_TIME}"
    if [p.name for p in restart_outputs] != [required_restart]:
        raise RuntimeError(f"{arm}: expected exactly final restart {required_restart}; got {[p.name for p in restart_outputs]}")
    arm_rec["restart_outputs"] = []
    for checkpoint in restart_outputs:
        stamp = checkpoint.name.removeprefix("wrfrst_d01_")
        arm_rec["restart_outputs"].append(verify_history(checkpoint, stamp))
    arm_rec["history_filenames"] = [p.name for p in histories]
    arm_rec["restart_filenames"] = [p.name for p in restart_outputs]
    arm_rec["capture_groups"] = capture_groups(case)
    if arm == "OFF":
        if (case / "audit" / "same_state.csv").exists():
            raise RuntimeError("OFF arm unexpectedly generated an audit CSV")
    else:
        roster = audit_roster(case, arm)
        groups = capture_map(arm_rec["capture_groups"])
        rawkeys = sorted(groups)
        csvkeys = sorted((phase, step, seconds) for phase, step, seconds in roster["selected_point_call_keys"])
        if rawkeys != csvkeys:
            raise RuntimeError(f"{arm}: actual raw step/time keys do not align with audit CSV")
        arm_rec["audit_roster"] = roster
        analysis = case / "audit" / "analysis.json"
        analyzer = Path(identity["analysis_tool"]["path"]).with_name("analyse_udm_physics_audit.py")
        if not analyzer.is_file():
            raise RuntimeError("pinned audit analyzer is absent")
        proc2 = subprocess.run([sys.executable, "-B", str(analyzer), "--csv",
                                str(case / "audit" / "same_state.csv"), "--raw",
                                str(case / "trace"), "--output", str(analysis)],
                               cwd=case, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, check=False)
        arm_rec["analysis_process"] = {"returncode": proc2.returncode, "stdout": proc2.stdout[-4000:]}
        if proc2.returncode != 0 or not analysis.is_file():
            raise RuntimeError(f"{arm}: read-only audit analyzer failed")
        arm_rec["audit_analysis"] = pin(analysis)
    arm_rec["runtime_final_postflight"] = verify_runtime(plan, identity, auth)
    arm_rec["stage_final_postflight"] = verify_stage(
        plan, json.loads(MANIFEST.read_text()), json.loads(READBACK.read_text()), identity)
    arm_rec["status"] = "PASS_MODEL_OUTPUTS"
    atomic(RECEIPT, receipt)


def compare_all_arms(receipt: dict) -> None:
    comparisons = []
    expected_history = {f"wrfout_d01_{t}" for t in HISTORY_TIMES}
    output_names = {}
    for arm in ARMS:
        case = HERE / arm
        names = sorted(p.name for pattern in ("wrfout_d01_*", "wrfrst_d01_*") for p in case.glob(pattern)
                       if p.is_file() and p.name != CHECKPOINT_INPUT)
        if not expected_history <= set(names):
            raise RuntimeError(f"{arm}: one or more hourly history files are missing")
        output_names[arm] = names
    if len({tuple(v) for v in output_names.values()}) != 1:
        raise RuntimeError(f"three arms produced different output file sets: {output_names}")
    for filename in output_names["OFF"]:
        paths = {arm: HERE / arm / filename for arm in ARMS}
        base = paths["OFF"]
        for arm in ARMS[1:]:
            check = compare_netcdf(base, paths[arm])
            if check["status"] != "PASS_EXACT":
                raise RuntimeError(f"instrumentation changed {filename} for {arm}: {check['mismatches'][:3]}")
            comparisons.append({"arm": arm, "file": filename, **check})
    groups = {arm: capture_map(receipt["arms"][arm]["capture_groups"]) for arm in ARMS}
    common = sorted(set(groups["OFF"]) & set(groups["ON_native4_0"]) & set(groups["ON_native4_1"]))
    if any(set(groups[a]) != set(common) for a in ARMS):
        raise RuntimeError("production capture scheduler roster differs between arms")
    trace_checks = []
    for key in common:
        for suffix in ("raw", "input", "result"):
            values = {arm: groups[arm][key][suffix] for arm in ARMS}
            if len(set(values.values())) != 1:
                raise RuntimeError(f"actual wrapper capture differs across audit settings {key}/{suffix}")
            trace_checks.append({"key": key, "suffix": suffix, "sha256": values["OFF"]})
    receipt["output_comparisons"] = comparisons
    receipt["capture_comparisons"] = trace_checks
    receipt["actual_call_roster"] = [{"phase": k[0], "radiation_step": k[1], "source_seconds": k[2]} for k in common]
    receipt["all_sky_only"] = True
    receipt["clear_sky_csv_available"] = False
    comparison_tool = Path(receipt["radius_comparator"]["path"])
    out = HERE / "radius-arm-comparison.json"
    proc = subprocess.run([sys.executable, "-B", str(comparison_tool),
                           "--generic", str(HERE / "ON_native4_0" / "audit" / "same_state.csv"),
                           "--native", str(HERE / "ON_native4_1" / "audit" / "same_state.csv"),
                           "--output", str(out)], cwd=HERE, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, check=False)
    receipt["radius_comparison_process"] = {"returncode": proc.returncode, "stdout": proc.stdout[-3000:]}
    if proc.returncode or not out.is_file():
        raise RuntimeError("matched generic/native4 audit comparison failed")
    check_pin(receipt["radius_comparator"], "radius-arm comparator after analysis")
    receipt["radius_comparison"] = pin(out)
    for arm in ARMS:
        receipt["arms"][arm]["status"] = "PASS_ARM"


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "--execute":
        print("This runner accepts only --execute and requires root-authorization.json.", file=sys.stderr)
        return 2
    if LOCK.exists() or RECEIPT.exists():
        print("Refusing rerun: one-use lock/receipt already exists.", file=sys.stderr)
        return 2
    plan = json.loads(PLAN.read_text())
    manifest = json.loads(MANIFEST.read_text())
    readback = json.loads(READBACK.read_text())
    identity = json.loads(IDENTITY.read_text())
    receipt = {"schema": "udm37-current-matthew-serial-audit-execution-v1",
               "status": "PREFLIGHT_RUNNING", "model_invocations": 0,
               "started_utc": utc_text(), "arms": {}, "counts": {"REAL": 0, "compile": 0, "model": 0}}
    locked = False
    try:
        # Static authorization and runtime/source closure checks before consuming one use.
        stage_state = verify_stage(plan, manifest, readback, identity, empty_arm="ALL")
        auth = read_auth(plan, manifest, readback, identity)
        runtime = verify_runtime(plan, identity, auth)
        radius_tool = identity["radius_comparator"]
        check_pin(radius_tool, "radius-arm comparator")
        receipt["radius_comparator"] = radius_tool
        receipt.update({"authorization_sha256": sha(AUTH), "stage_preflight": stage_state,
                       "runtime_preflight": runtime, "status": "PREFLIGHT_PASS"})
        fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as lock:
            lock.write(json.dumps({"started_utc": utc_text(), "authorization_sha256": sha(AUTH),
                                   "pid": os.getpid()}, sort_keys=True) + "\n")
            lock.flush(); os.fsync(lock.fileno())
        locked = True
        atomic(RECEIPT, receipt)
        for arm in ARMS:
            run_arm(arm, plan, identity, receipt, auth)
        compare_all_arms(receipt)
        receipt["campaign_final_identity"] = {
            "runtime": verify_runtime(plan, identity, auth),
            "stage": verify_stage(plan, json.loads(MANIFEST.read_text()),
                                  json.loads(READBACK.read_text()), identity),
            "radius_comparator": pin(Path(identity["radius_comparator"]["path"]))}
        receipt["status"] = "PASS_SERIAL_AUDIT_OUTPUTS_AND_CAPTURE_PARITY"
        receipt["ended_utc"] = utc_text()
        receipt["model_invocations"] = 3
        receipt["counts"]["model"] = 3
        atomic(RECEIPT, receipt)
        return 0
    except BaseException as exc:
        receipt["status"] = "FAIL_PRESERVED" if locked else "FAIL_PREFLIGHT_NO_MODEL"
        receipt["error"] = repr(exc)
        receipt["ended_utc"] = utc_text()
        for arm_rec in receipt.get("arms", {}).values():
            if arm_rec.get("status") in {"PREPARED", "RUNNING", "MODEL_SUCCESS_POSTFLIGHT_PENDING"}:
                arm_rec["status"] = "FAIL_PRESERVED"
                arm_rec["postflight_error"] = repr(exc)
        # Preserve the invocation count and actual per-arm child return codes.
        receipt["counts"]["model"] = receipt.get("model_invocations", 0)
        try:
            if locked:
                atomic(RECEIPT, receipt)
        except BaseException as write_error:
            print(f"receipt write failure: {write_error!r}", file=sys.stderr)
        print(f"{receipt['status']}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
