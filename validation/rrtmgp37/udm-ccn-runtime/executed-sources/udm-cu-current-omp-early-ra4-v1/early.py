#!/usr/bin/env python3
"""Prepare an RA4 10-minute OMP1/OMP2 diagnostic; default mode never stages or runs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONTROL = ROOT / "build/udm-cu-current-omp-ra4-control-v1/control.py"
CONTROL_SHA = "31604049a2c4356927f3aaa8d42e08dbaecc74c94097a48869ca783d34497b2d"
PARENT_HISTORY = ROOT / "build/udm-seaice-winter-validation-v3/ra4-24h-v1/case/wrfout_d01_2000-01-24_12:00:00"
START = "2000-01-24_12:00:00"
EXPECTED_TIMES = [f"2000-01-24_12:{minute:02d}:00" for minute in range(0, 11)]
EXPECTED_HISTORY = "wrfout_d01_" + START
EXPECTED_RESTART = "wrfrst_d01_2000-01-24_12:10:00"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_control():
    if sha(CONTROL) != CONTROL_SHA:
        raise RuntimeError("pinned RA4 control adapter changed")
    spec = importlib.util.spec_from_file_location("pinned_ra4_omp_control", CONTROL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if sha(CONTROL) != CONTROL_SHA:
        raise RuntimeError("RA4 control adapter changed during import")
    return module


control = load_control()
r = control.r
m = control.m
r.ARMS = {"omp1": 1, "omp2": 2}
r.TIMES = list(EXPECTED_TIMES)
BASE_NAMELIST_BUILDER = r.nml


def early_namelist(original: str) -> str:
    """Apply only the specified time-control changes to root runtime's normalized 3h namelist."""
    text = BASE_NAMELIST_BUILDER(original)
    replacements = {
        "run_hours": (r"(?im)^(\s*run_hours\s*=\s*)3(\s*,?\s*)$", r"\g<1>0\g<2>"),
        "run_minutes": (r"(?im)^(\s*run_minutes\s*=\s*)0(\s*,?\s*)$", r"\g<1>10\g<2>"),
        "end_hour": (r"(?im)^(\s*end_hour\s*=\s*)15(\s*,?\s*)$", r"\g<1>12\g<2>"),
        "history_interval": (r"(?im)^(\s*history_interval\s*=\s*)60(\s*,?\s*)$", r"\g<1>1\g<2>"),
        "restart_interval": (r"(?im)^(\s*restart_interval\s*=\s*)180(\s*,?\s*)$", r"\g<1>10\g<2>"),
    }
    for name, (pattern, replacement) in replacements.items():
        if len(re.findall(pattern, text)) != 1:
            raise ValueError(f"expected exactly one base assignment for {name}")
        text, n = re.subn(pattern, replacement, text, count=1)
        if n != 1:
            raise ValueError(f"could not set early-run namelist field {name}")
    if re.search(r"(?im)^\s*end_minute\s*=", text):
        if len(re.findall(r"(?im)^\s*end_minute\s*=", text)) != 1 or not re.search(r"(?im)^\s*end_minute\s*=\s*0\b", text):
            raise ValueError("base end_minute must occur once and equal zero")
        text, n = re.subn(r"(?im)^(\s*end_minute\s*=\s*)\d+(\s*,?\s*)$", r"\g<1>10\g<2>", text, count=1)
        if n != 1:
            raise ValueError("could not set end_minute")
    else:
        if len(re.findall(r"(?im)^\s*end_hour\s*=\s*12\s*,?\s*$", text)) != 1:
            raise ValueError("expected exactly one normalized end_hour=12")
        text, n = re.subn(r"(?im)^(\s*end_hour\s*=\s*12\s*,?\s*)$", r"\g<1>\n end_minute = 10,", text, count=1)
        if n != 1:
            raise ValueError("could not add end_minute")
    for field, value in (("run_hours", 0), ("run_minutes", 10), ("end_hour", 12),
                         ("end_minute", 10), ("history_interval", 1), ("restart_interval", 10)):
        match = re.search(r"(?im)^\s*" + field + r"\s*=\s*(\d+)", text)
        if not match or int(match.group(1)) != value:
            raise ValueError(f"normalized early namelist does not have {field}={value}")
    return text


def attr_value(value):
    if isinstance(value, str):
        return {"string": value}
    arr = np.asarray(value)
    return {"dtype": arr.dtype.str, "shape": list(arr.shape), "bytes_hex": arr.tobytes().hex()}


def _time_slice(var, index):
    if "Time" not in var.dimensions:
        return np.asarray(var[:])
    return np.take(np.asarray(var[:]), index, axis=var.dimensions.index("Time"))


def summarize_numeric(array: np.ndarray) -> dict:
    data = np.asarray(array)
    if data.dtype.kind not in "fiu":
        raise ValueError("numeric ledger received nonnumeric array")
    if data.dtype.kind == "f" and not np.isfinite(data).all():
        raise ValueError("nonfinite value in early history")
    zero = data == 0
    negative_zero = zero & np.signbit(data) if data.dtype.kind == "f" else np.zeros(data.shape, dtype=bool)
    maximum_absolute = float(np.max(np.abs(data))) if data.size else 0.0
    return {"dtype": data.dtype.str, "shape": list(data.shape),
            "raw_sha256": hashlib.sha256(data.tobytes()).hexdigest(),
            "count": int(data.size), "zero_count": int(np.count_nonzero(zero)),
            "negative_zero_count": int(np.count_nonzero(negative_zero)),
            "min": float(np.min(data)) if data.size else None,
            "max": float(np.max(data)) if data.size else None,
            "max_abs": maximum_absolute}


def history_ledger(path: Path) -> dict:
    base = m.validate_dataset(path, EXPECTED_TIMES, 4)
    fill_check = r.default_fills(path)
    if not base["passed"] or not fill_check["passed"]:
        raise ValueError("early history failed strict finite/metadata/default-fill validation")
    if base["variable_count"] != 222 or base["numeric_variable_count"] != 221:
        raise ValueError("expected exactly 222 history variables, 221 numeric")
    per_time = []
    with Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        got_times = m.times_from(ds)
        if got_times != EXPECTED_TIMES:
            raise ValueError(f"history times mismatch: {got_times}")
        if len(ds.dimensions["Time"]) != 11:
            raise ValueError("expected eleven one-minute frames")
        for index, stamp in enumerate(got_times):
            fields = {}
            for name, var in ds.variables.items():
                if np.dtype(var.dtype).kind in "fiu":
                    fields[name] = summarize_numeric(_time_slice(var, index))
            cu_positive = {}
            for name in ("QC_CU", "QI_CU"):
                if name in ds.variables:
                    vals = _time_slice(ds.variables[name], index)
                    cu_positive[name] = int(np.count_nonzero(vals > 0))
            sw_positive = {}
            for name in ("SWDOWN", "SWDNB"):
                if name in ds.variables:
                    vals = _time_slice(ds.variables[name], index)
                    sw_positive[name] = int(np.count_nonzero(vals > 0))
            per_time.append({"time": stamp, "numeric_fields": fields,
                             "cu_positive_cells": cu_positive,
                             "shortwave_positive_cells": sw_positive})
    return {"file": m.pin(path), "validation": base, "default_fill_check": fill_check,
            "frame_count": len(per_time), "per_time": per_time,
            "cu_state_note": "CU-positive counts are diagnostic only; zero is accepted during this early 10-minute window.",
            "shortwave_note": "Night/low-sun zero flux is recorded, not rejected."}


def checkpoint_ledger(path: Path) -> dict:
    base = m.validate_dataset(path, [EXPECTED_TIMES[-1]], 4)
    fill_check = r.default_fills(path)
    surface = m.checkpoint_diagnostics(path)
    if not base["passed"] or not fill_check["passed"] or not surface["passed"]:
        raise ValueError("early checkpoint failed strict numeric/default-fill/surface validation")
    if base["variable_count"] != 664 or base["numeric_variable_count"] != 663:
        raise ValueError("expected exactly 664 checkpoint variables, 663 numeric")
    diagnostics = {}
    cu_counts = {}
    with Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        for name, var in ds.variables.items():
            if np.dtype(var.dtype).kind in "fiu":
                diagnostics[name] = summarize_numeric(np.asarray(var[:]))
        for name in ("QC_CU", "QI_CU"):
            if name in ds.variables:
                cu_counts[name] = int(np.count_nonzero(np.asarray(ds.variables[name][:]) > 0))
    return {"file": m.pin(path), "validation": base, "default_fill_check": fill_check,
            "surface": surface, "numeric_fields": diagnostics, "cu_positive_cells": cu_counts,
            "cu_state_note": "A zero cloud-water/ice path count is permitted at 12:10 and is retained as an observation."}


def early_outputs(entry) -> dict:
    case = Path(entry["case_path"])
    histories = sorted(case.glob("wrfout_d01_*"))
    checkpoints = sorted(case.glob("wrfrst_d01_*"))
    if [p.name for p in histories] != [EXPECTED_HISTORY]:
        raise ValueError(f"expected one minute-cadence history file: {[p.name for p in histories]}")
    if [p.name for p in checkpoints] != [EXPECTED_RESTART]:
        raise ValueError(f"expected one 12:10 checkpoint: {[p.name for p in checkpoints]}")
    history = history_ledger(histories[0])
    checkpoint = checkpoint_ledger(checkpoints[0])
    return {"history": history, "checkpoint": checkpoint, "passed": True}


def compare_frame_ledgers(left: list[dict], right: list[dict]) -> dict:
    if len(left) != 11 or len(right) != 11:
        raise ValueError("comparison requires exactly 11 history frames per arm")
    diffs_by_time = []
    for frame_a, frame_b in zip(left, right, strict=True):
        if frame_a.get("time") != frame_b.get("time"):
            raise ValueError("history frame timestamps are misaligned")
        vars_a = frame_a.get("numeric_fields", {})
        vars_b = frame_b.get("numeric_fields", {})
        differences = []
        for name in sorted(set(vars_a) | set(vars_b)):
            a, b = vars_a.get(name), vars_b.get(name)
            if a is None or b is None:
                differences.append({"variable": name, "difference": "variable absent from one arm"})
            elif (a.get("dtype"), a.get("shape"), a.get("raw_sha256")) != (b.get("dtype"), b.get("shape"), b.get("raw_sha256")):
                differences.append({"variable": name, "left": {k: a.get(k) for k in ("dtype", "shape", "raw_sha256", "min", "max", "max_abs", "zero_count", "negative_zero_count")},
                                    "right": {k: b.get(k) for k in ("dtype", "shape", "raw_sha256", "min", "max", "max_abs", "zero_count", "negative_zero_count")}})
        diffs_by_time.append({"time": frame_a["time"], "different_numeric_fields": len(differences), "fields": differences})
    first = next((x["time"] for x in diffs_by_time if x["different_numeric_fields"]), None)
    return {"status": "BITWISE_EQUAL" if first is None else "DIFFERENCES_RECORDED",
            "first_differing_time": first,
            "per_time": diffs_by_time}


def compare_early(root: Path, stage_sha: str) -> dict:
    executions = {}
    for arm in r.ARMS:
        r.invariants(root, stage_sha, arm)
        path = root / arm / "execution.json"
        entry = json.loads(path.read_text())
        if entry.get("status") != "PASS" or entry.get("actual_model_invocations") != 1:
            raise ValueError(f"arm {arm} is not a validated terminal run")
        if not entry.get("before_pins_valid") or not entry.get("after_pins_valid"):
            raise ValueError(f"arm {arm} pin checks failed")
        if entry.get("control_adapter") != m.pin(CONTROL) or entry.get("early_adapter") != m.pin(Path(__file__)):
            raise ValueError(f"arm {arm} adapter hashes differ")
        m.check_pin(entry["runner"])
        for field in ("history", "checkpoint"):
            m.check_pin(entry["outputs"][field]["file"])
        executions[arm] = entry
    left, right = executions["omp1"], executions["omp2"]
    history_file = r.compare_file(Path(left["outputs"]["history"]["file"]["path"]),
                                  Path(right["outputs"]["history"]["file"]["path"]))
    checkpoint_file = r.compare_file(Path(left["outputs"]["checkpoint"]["file"]["path"]),
                                     Path(right["outputs"]["checkpoint"]["file"]["path"]))
    frames = compare_frame_ledgers(left["outputs"]["history"]["per_time"], right["outputs"]["history"]["per_time"])
    metadata_ok = history_file["metadata_equal"] and checkpoint_file["metadata_equal"]
    arrays_equal = (all(item["equal"] for item in history_file["ledger"]) and
                    all(item["equal"] for item in checkpoint_file["ledger"]))
    if not metadata_ok:
        status = "FAIL_METADATA_MISMATCH_PRESERVED"
    elif arrays_equal and frames["status"] == "BITWISE_EQUAL":
        status = "BITWISE_EQUAL"
    else:
        status = "DIFFERENCES_RECORDED"
    result = {"schema": "UDM_RA4_EARLY_OMP_COMPARISON_V1", "status": status,
              "early_adapter": m.pin(Path(__file__)), "base_control_adapter": m.pin(CONTROL),
              "stage": m.pin(root / "stage.json"),
              "executions": {arm: m.pin(root / arm / "execution.json") for arm in r.ARMS},
              "history_file_comparison": history_file,
              "checkpoint_file_comparison": checkpoint_file,
              "frame_comparison": frames,
              "scope": "RA4 12:00–12:10 threadcount control; field differences locate earliest recorded output time only."}
    m.collision(root / "comparison.json")
    m.write_json(root / "comparison.json", result)
    return result


# Patch the pinned RA4 adapter in memory only; all source artifacts remain untouched.
r.nml = early_namelist
r.outputs = early_outputs
r.compare = compare_early
base_invariants = r.invariants


def early_invariants(root: Path, stage_sha: str, arm: str):
    stage, entry, runargs = base_invariants(root, stage_sha, arm)
    if stage.get("early_adapter") != m.pin(Path(__file__)):
        raise ValueError("early diagnostic adapter changed")
    return stage, entry, runargs


r.invariants = early_invariants


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("preflight", "prepare", "run", "compare"), nargs="?", default="preflight")
    ap.add_argument("--root", type=Path, default=HERE / "cases/ra4-early-10m-v1")
    ap.add_argument("--prepare-go", action="store_true", help="stage only; separate operator approval required")
    ap.add_argument("--stage-sha")
    ap.add_argument("--arm", choices=r.ARMS)
    ap.add_argument("--execute", action="store_true", help="launch model; not authorized by this preparation task")
    args = ap.parse_args()
    root = args.root.absolute()
    if args.mode == "preflight":
        parent, stage, runargs = control.parent4()
        original = Path(stage["case"]["case_path"]) / "namelist.input"
        generated = early_namelist(original.read_text())
        result = {"schema": "UDM_RA4_EARLY_OMP_PREFLIGHT_V1", "status": "READY_NOT_STAGED",
                  "model_invocations": 0, "source_adapter": m.pin(Path(__file__)),
                  "base_control_adapter": m.pin(CONTROL), "root_runtime": m.pin(control.RUNTIME),
                  "parent_ra4_receipt": m.pin(r.PARENT), "parent_case_stage": m.pin(Path(parent["stage_receipt"]["path"])),
                  "source_namelist_sha256": sha(original),
                  "proposed_namelist_sha256": hashlib.sha256(generated.encode()).hexdigest(),
                  "proposed_namelist": generated, "root": str(root),
                  "arms": r.ARMS, "times": EXPECTED_TIMES,
                  "expected_history_file": EXPECTED_HISTORY, "expected_restart_file": EXPECTED_RESTART,
                  "required_outputs": ["all 11 one-minute Times records", "all numeric fields finite/unmasked/non-fill/default-fill-free",
                                       "per-variable per-time raw hashes, min/max/max-abs, zero and negative-zero counts",
                                       "12:10 checkpoint with 663 numeric valuesets and USTM/QZ0 validation",
                                       "record QC_CU/QI_CU counts, allow zero", "record SWDOWN/SWDNB counts, allow zero"],
                  "runtime": {"mpiexec": str(runargs.mpiexec), "ld_library_path": runargs.ld_library_path,
                              "timeout_seconds": runargs.timeout, "omp_arms": r.ARMS},
                  "action_note": "Preflight only. This task authorizes neither case staging nor model execution."}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.mode == "prepare":
        result = r.prepare(root, args.prepare_go)
        if args.prepare_go:
            result["control_adapter"] = m.pin(CONTROL)
            result["root_runtime"] = m.pin(control.RUNTIME)
            result["early_adapter"] = m.pin(Path(__file__))
            result["scope"] = "RA4 10-minute early-time threadcount control; not forecast-accuracy evidence"
            m.write_json(root / "stage.json", result)
    elif args.mode == "run":
        result = r.run(root, args.stage_sha, args.arm, args.execute)
        if args.execute:
            result["control_adapter"] = m.pin(CONTROL)
            result["early_adapter"] = m.pin(Path(__file__))
            m.write_json(root / args.arm / "execution.json", result)
    else:
        result = r.compare(root, args.stage_sha)
    print(json.dumps({"status": result["status"], "actual_model_invocations": result.get("actual_model_invocations", 0)}))
    return 0 if result["status"].startswith(("PASS", "READY", "STAGED")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
