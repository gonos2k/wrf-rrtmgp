#!/usr/bin/env python3
"""Offline tests for the early-run namelist and per-frame metric ledger."""
from __future__ import annotations

import importlib.util
import json
import re
import tempfile
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("early_ra4_omp", HERE / "early.py")
early = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(early)


def assignment_map(text: str) -> dict[str, str]:
    return {name.lower(): value.strip().rstrip(",") for name, value in re.findall(
        r"(?im)^\s*([a-z][a-z0-9_]*)\s*=\s*([^!\n]+)", text)}


def main() -> None:
    control_case = early.ROOT / "build/udm-seaice-winter-validation-v3/ra4-24h-v1/case"
    source = (control_case / "namelist.input").read_text()
    base = early.BASE_NAMELIST_BUILDER(source)
    short = early.early_namelist(source)
    before, after = assignment_map(base), assignment_map(short)
    expected = {"run_hours": ("3", "0"), "run_minutes": ("0", "10"),
                "end_hour": ("15", "12"), "history_interval": ("60", "1"),
                "restart_interval": ("180", "10"), "end_minute": (None, "10")}
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    assert changed == set(expected), f"unexpected namelist keys changed: {changed ^ set(expected)}"
    for key, (old, new) in expected.items():
        assert before.get(key) == old and after.get(key) == new, (key, before.get(key), after.get(key))
    summary = early.summarize_numeric(np.asarray([0.0, -0.0, -2.0, 1.0], dtype=np.float32))
    assert summary["zero_count"] == 2
    assert summary["negative_zero_count"] == 1
    assert summary["min"] == -2.0 and summary["max"] == 1.0 and summary["max_abs"] == 2.0
    assert summary["count"] == 4 and len(summary["raw_sha256"]) == 64
    assert len(early.EXPECTED_TIMES) == 11 and early.EXPECTED_TIMES[0] == "2000-01-24_12:00:00" and early.EXPECTED_TIMES[-1] == "2000-01-24_12:10:00"
    try:
        early.summarize_numeric(np.asarray([1.0, np.nan], dtype=np.float32))
    except ValueError:
        pass
    else:
        raise AssertionError("nonfinite field passed ledger summary")
    compare_fixture()
    print("EARLY_RA4_HARNESS_OFFLINE_TESTS_PASS")


def netcdf(path: Path, values: np.ndarray) -> None:
    with Dataset(path, "w") as ds:
        ds.createDimension("Time", len(values))
        ds.createDimension("x", 1)
        ds.setncattr("MP_PHYSICS", 27)
        var = ds.createVariable("sample", "f4", ("Time", "x"))
        var.setncattr("units", "K")
        var[:, 0] = values


def frames(values: np.ndarray) -> list[dict]:
    out = []
    for stamp, value in zip(early.EXPECTED_TIMES, values, strict=True):
        item = early.summarize_numeric(np.asarray([value], dtype=np.float32))
        out.append({"time": stamp, "numeric_fields": {"sample": item}})
    return out


def compare_fixture() -> None:
    with tempfile.TemporaryDirectory(prefix="early-ra4-compare-test-") as tmp:
        root = Path(tmp)
        (root / "stage.json").write_text(json.dumps({"status": "STAGED_NOT_RUN"}))
        arms = {"omp1": np.ones(11, dtype=np.float32), "omp2": np.ones(11, dtype=np.float32)}
        arms["omp2"][7] = np.float32(2.0)
        entries = {}
        for arm, values in arms.items():
            d = root / arm
            d.mkdir()
            history = d / "history.nc"
            checkpoint = d / "restart.nc"
            netcdf(history, values)
            netcdf(checkpoint, np.asarray([3.0], dtype=np.float32))
            entries[arm] = {"status": "PASS", "actual_model_invocations": 1,
                            "before_pins_valid": True, "after_pins_valid": True,
                            "runner": early.m.pin(early.control.RUNTIME),
                            "control_adapter": early.m.pin(early.CONTROL),
                            "early_adapter": early.m.pin(HERE / "early.py"),
                            "outputs": {"history": {"file": early.m.pin(history), "per_time": frames(values)},
                                        "checkpoint": {"file": early.m.pin(checkpoint)}}}
            (d / "execution.json").write_text(json.dumps(entries[arm]))
        original = early.r.invariants
        early.r.invariants = lambda *_args: ({}, {}, {})
        try:
            result = early.compare_early(root, "test-stage-sha")
        finally:
            early.r.invariants = original
        assert result["status"] == "DIFFERENCES_RECORDED"
        assert result["frame_comparison"]["first_differing_time"] == "2000-01-24_12:07:00"
        at_first = next(x for x in result["frame_comparison"]["per_time"] if x["time"] == "2000-01-24_12:07:00")
        assert at_first["different_numeric_fields"] == 1
        assert at_first["fields"][0]["variable"] == "sample"


if __name__ == "__main__":
    main()
