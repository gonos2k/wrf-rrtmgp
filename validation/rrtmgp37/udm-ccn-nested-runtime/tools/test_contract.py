#!/usr/bin/env python3
"""Focused negative controls for the read-only restart attribution comparator."""
from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "compare_restart.py"
SPEC = importlib.util.spec_from_file_location("delayed_nest_compare_restart", MODULE_PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def write_file(path, *, phase, timestamp, values=None, extra_global=None, alarms=False, variable_unit="kg kg-1", shape=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    values = values or {}
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", 1)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("x", shape)
        tv = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        tv[:] = np.asarray([list(timestamp)], dtype="S1")
        q = ds.createVariable("Q", "f4", ("Time", "x"))
        q.units = variable_unit
        q[:] = np.asarray([values.get("Q", [1.0] * shape)], dtype="f4")
        if timestamp == "2010-06-11_01:10:00":
            for name in ("UDM_CLDFRA", "UDM_CF_TOP", "UDM_CF_STEP"):
                v = ds.createVariable(name, "f4" if name == "UDM_CLDFRA" else "i4", ("Time", "x"))
                v[:] = np.asarray([values.get(name, [0.25, 0.5] if phase == "continuous" else [-1, -1])], dtype=v.dtype)
        ds.START_DATE = "2010-06-11_00:00:00" if phase == "continuous" else "2010-06-11_01:10:00"
        if extra_global:
            for name, value in extra_global.items(): ds.setncattr(name, value)
        if alarms:
            if timestamp == "2010-06-11_02:00:00":
                ds.setncattr(MOD.ALARM51, 600 if phase == "continuous" else 3000)
                ds.setncattr("WRF_ALARM_ISRINGING_51", 1)
                ds.setncattr(MOD.ALARM55, -7200 if phase == "continuous" else -3000)
                ds.setncattr("WRF_ALARM_ISRINGING_55", 0)
            else:
                ds.setncattr(MOD.ALARM55, -4800 if phase == "continuous" else -600)
                ds.setncattr("WRF_ALARM_ISRINGING_55", 0)


def run_case(root, name, *, timestamp="2010-06-11_01:20:00", checkpoint=False,
             continuous=None, restart=None, extra_c=None, extra_r=None, alarms=False, unit_r="kg kg-1", shape_r=2,
             need_fail=False, expected_substring=None):
    ca = root / name / "continuous.nc"
    rb = root / name / "restart.nc"
    write_file(ca, phase="continuous", timestamp=timestamp, values=continuous, extra_global=extra_c, alarms=alarms)
    write_file(rb, phase="restart", timestamp=timestamp, values=restart, extra_global=extra_r,
               alarms=alarms, variable_unit=unit_r, shape=shape_r)
    try:
        got = MOD.compare_datasets(ca, rb, 1, timestamp, checkpoint=checkpoint)
    except (AssertionError, KeyError, ValueError) as e:
        if not need_fail: raise
        if expected_substring and expected_substring not in str(e):
            raise AssertionError(f"wrong rejection: expected {expected_substring!r}, got {e!r}") from e
        return {"name": name, "rejected": True, "diagnostic": str(e)}
    if need_fail: raise AssertionError(f"mutation unexpectedly passed: {name}")
    return {"name": name, "rejected": False, "exact_variables": got["exact_variable_count"],
            "reset_variables": got["initial_reset_variable_count"]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="restart-compare-contract-") as tmp:
        root = Path(tmp)
        cases = []
        cases.append(run_case(root, "clean-history"))
        cases.append(run_case(root, "valid-initial-diagnostic-reset", timestamp="2010-06-11_01:10:00"))
        cases.append(run_case(root, "history-alarm55-added", extra_c={MOD.ALARM55: -4800, "WRF_ALARM_ISRINGING_55": 0},
                              extra_r={MOD.ALARM55: -600, "WRF_ALARM_ISRINGING_55": 0}, need_fail=True,
                              expected_substring="unexpected global attribute differences"))
        cases.append(run_case(root, "valid-final-checkpoint", timestamp="2010-06-11_02:00:00", checkpoint=True, alarms=True))
        for name, attr, value, text in (
            ("final51-wrong-seconds", MOD.ALARM51, 3001, "alarm51 final exception invalid"),
            ("final51-wrong-ring", "WRF_ALARM_ISRINGING_51", 0, "alarm51 final exception invalid"),
            ("final55-wrong-elapsed", MOD.ALARM55, -2999, "alarm55 elapsed anchor mismatch"),
        ):
            case_dir = root / name
            ca, rb = case_dir / "continuous.nc", case_dir / "restart.nc"
            write_file(ca, phase="continuous", timestamp="2010-06-11_02:00:00", alarms=True)
            write_file(rb, phase="restart", timestamp="2010-06-11_02:00:00", alarms=True)
            if name == "final51-wrong-ring":
                with Dataset(ca, "r+") as ds: ds.setncattr(attr, value)
            with Dataset(rb, "r+") as ds: ds.setncattr(attr, value)
            try: MOD.compare_datasets(ca, rb, 1, "2010-06-11_02:00:00", checkpoint=True)
            except AssertionError as e:
                if text not in str(e): raise
            else: raise AssertionError(f"invalid {attr} mutation passed")
            cases.append({"name": name, "rejected": True, "diagnostic": text})
        cases.append(run_case(root, "extra-global", extra_r={"UNEXPECTED_GLOBAL": 1}, need_fail=True,
                              expected_substring="unexpected global attribute differences"))
        cases.append(run_case(root, "other-variable-data", restart={"Q": [1.0, 2.0]}, need_fail=True,
                              expected_substring="unexpected raw field mismatch"))
        cases.append(run_case(root, "variable-attribute", unit_r="unexpected", need_fail=True,
                              expected_substring="variable attribute mismatch"))
        cases.append(run_case(root, "variable-shape", shape_r=3, need_fail=True,
                              expected_substring="dimension sizes differ"))
        cases.append(run_case(root, "initial-other-field", timestamp="2010-06-11_01:10:00",
                              continuous={"Q": [1.0, 1.0]}, restart={"Q": [1.0, 2.0]}, need_fail=True,
                              expected_substring="unexpected raw field mismatch"))
        cases.append(run_case(root, "initial-reset-not-minus-one", timestamp="2010-06-11_01:10:00",
                              restart={"UDM_CF_STEP": [0, -1]}, need_fail=True,
                              expected_substring="initial restart diagnostic not reset to -1"))
    result = {"status": "PASS", "scope": "comparator negative controls only; manufactured tiny NetCDF files, no model or source execution",
              "cases": cases}
    if args.output:
        out = args.output.resolve()
        if out.exists(): raise SystemExit(f"refusing to overwrite {out}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "case_count": len(cases)}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
