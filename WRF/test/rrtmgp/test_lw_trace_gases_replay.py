#!/usr/bin/env python3
"""Synthetic CFC input contract and independent replay regression for LW."""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


EXPECTED = {
    "cfc11": 2.51e-10,
    "cfc12": 5.38e-10,
    "cfc22": 1.69e-10,
    "ccl4": 9.30e-11,
}
INPUT_NAMES = {
    "cfc11": "VMR_CFC11",
    "cfc12": "VMR_CFC12",
    "cfc22": "VMR_CFC22",
    "ccl4": "VMR_CCL4",
}
BAD_CASES = {
    "partial": "RRTMGP_LW_TRACE_GAS_PARTIAL_INPUTS",
    "shape": "RRTMGP_LW_TRACE_GAS_SHAPE_MISMATCH",
    "nan": "RRTMGP_LW_TRACE_GAS_NOT_FINITE_NONNEGATIVE",
    "negative": "RRTMGP_LW_TRACE_GAS_NOT_FINITE_NONNEGATIVE",
}


def parse_records(path: Path, result: bool) -> tuple[str, tuple[int, int], dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    expected_magic = "RRTMGP_RESULT_V1" if result else None
    if not lines:
        raise ValueError(f"{path}: empty capture")
    magic = lines[0].strip()
    if result and magic != expected_magic:
        raise ValueError(f"{path}: expected {expected_magic}, got {magic}")
    header = lines[1].split()
    expected_header_len = 3 if result else 6
    if len(header) != expected_header_len:
        raise ValueError(f"{path}: malformed capture header {header}")
    phase = header[0].upper()
    nc, nl = int(header[1]), int(header[2])
    if phase != "LW" or nc < 1 or nl < 1:
        raise ValueError(f"{path}: unexpected replay dimensions/phase {header}")
    records: dict[str, np.ndarray] = {}
    idx = 2
    while idx < len(lines):
        if not lines[idx].strip():
            idx += 1
            continue
        fields = lines[idx].split()
        idx += 1
        if len(fields) != (4 if result else 3):
            raise ValueError(f"{path}: malformed record header {fields}")
        name = fields[0].upper()
        shape = tuple(map(int, fields[1:]))
        count = math.prod(shape)
        vals: list[float] = []
        while len(vals) < count and idx < len(lines):
            vals.extend(float(s.replace("D", "E").replace("d", "e")) for s in lines[idx].split())
            idx += 1
        if len(vals) != count or name in records:
            raise ValueError(f"{path}: invalid/duplicate data for {name}")
        arr = np.asarray(vals, dtype=np.float64).reshape(shape, order="F")
        if not np.isfinite(arr).all():
            raise ValueError(f"{path}: {name} contains non-finite data")
        records[name] = arr
    return magic, (nc, nl), records


def run(exe: Path, data: Path, mode: str, capture_dir: Path) -> subprocess.CompletedProcess[str]:
    capture_dir.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture_dir)
    env.pop("WRF_RRTMGP_CAPTURE_ALL", None)
    return subprocess.run([str(exe), str(data), mode], env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def compare_reference(ref: Path, data: Path, input_file: Path, output_file: Path) -> dict:
    proc = subprocess.run([str(ref), str(data), str(input_file), str(output_file)],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode:
        raise RuntimeError(f"reference replay failed ({proc.returncode}):\n{proc.stdout}")
    _, _, actual = parse_records(output_file, result=True)
    _, _, expected = parse_records(input_file.with_suffix(".result"), result=True)
    # The adapter stores public outputs in default REAL; reference values are wp.
    output_names = ("UP", "DN", "HR", "UPC", "DNC", "HRC")
    maxima: dict[str, float] = {}
    for name in output_names:
        if name not in actual or name not in expected:
            raise ValueError(f"missing {name} in independent replay")
        delta = np.abs(actual[name] - expected[name])
        maxima[name] = float(delta.max())
        tol = 4.0 * np.finfo(np.float32).eps * np.abs(expected[name]) + 1.e-6
        if np.any(delta > tol):
            raise AssertionError(f"{name} differs from independent replay: max={maxima[name]:.9g}")
    # GAS_TAU is emitted at adapter/default-REAL precision, while the reference
    # writer preserves wp precision. Compare with float32 rounding allowance.
    # The adapter keeps GAS_TAU for legacy consumers and adds RAW only in V8.
    # V8 reference support is being tested as part of this contract.
    gas_key = "GAS_TAU_RAW" if "GAS_TAU_RAW" in actual else "GAS_TAU"
    ref_key = "GAS_TAU_RAW" if "GAS_TAU_RAW" in expected else "GAS_TAU"
    if gas_key not in actual or ref_key not in expected:
        raise ValueError("GAS_TAU_RAW section missing from adapter/reference")
    delta = np.abs(actual[gas_key] - expected[ref_key])
    maxima["GAS_TAU_RAW"] = float(delta.max())
    tol = 4.0 * np.finfo(np.float32).eps * np.abs(expected[ref_key]) + 2.e-7
    if np.any(delta > tol):
        raise AssertionError(f"GAS_TAU_RAW differs from independent replay: max={maxima['GAS_TAU_RAW']:.9g}")
    return maxima


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("adapter", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    for p in (args.adapter, args.reference, args.data_dir):
        if not p.exists():
            parser.error(f"path does not exist: {p}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="lw-trace-gases-", dir=args.output.parent))
    report: dict = {
        "status": "FAIL",
        "fixture_scope": "synthetic clear-sky input; VMRs are legacy WRF GHG_INPUT=0 fallback constants, not observed SCM values",
        "modes": {},
        "invalid_inputs": {},
    }
    try:
        for mode in ("absent", "zero", "cfc11", "cfc12", "cfc22", "ccl4", "all"):
            cap = work / mode
            proc = run(args.adapter.resolve(), args.data_dir.resolve(), mode, cap)
            if proc.returncode:
                raise RuntimeError(f"adapter {mode} failed ({proc.returncode}):\n{proc.stdout}")
            input_path, result_path = cap / "lw.input", cap / "lw.result"
            if not input_path.is_file() or not result_path.is_file():
                raise RuntimeError(f"adapter {mode} did not emit LW trace captures")
            magic, dims, inp = parse_records(input_path, result=False)
            _, _, out = parse_records(result_path, result=True)
            report["modes"][mode] = {"magic": magic, "dimensions": dims, "metrics": {}}
            if mode == "absent":
                if magic not in {"RRTMGP_REPLAY_V5", "RRTMGP_REPLAY_V6", "RRTMGP_REPLAY_V7"}:
                    raise AssertionError(f"legacy omitted-CFC path unexpectedly wrote {magic}")
            else:
                if magic != "RRTMGP_REPLAY_V8":
                    raise AssertionError(f"explicit CFC path should write V8, got {magic}")
                if "GAS_TAU_RAW" not in out:
                    raise AssertionError("V8 result omitted GAS_TAU_RAW")
                if not np.array_equal(out["GAS_TAU"], out["GAS_TAU_RAW"]):
                    raise AssertionError("GAS_TAU_RAW is not identical to retained GAS_TAU")
                for species, section in INPUT_NAMES.items():
                    if section not in inp:
                        raise AssertionError(f"V8 trace omitted {section}")
                    # Wrapper API is default REAL; trace serializes the exact
                    # binary32 argument widened to text, not the Python source
                    # decimal. Compare that representable fixture value.
                    expected = float(np.float32(EXPECTED[species])) if mode in {species, "all"} else 0.0
                    if not np.all(inp[section] == expected):
                        raise AssertionError(f"{section} does not match synthetic fixture for {mode}")
            report["modes"][mode]["_input"] = str(input_path)
            report["modes"][mode]["_result"] = str(result_path)

        # Verify absent and explicitly-zero inputs preserve the former six-gas
        # behavior exactly at both the adapter's trace and public outputs.
        _, _, absent = parse_records(Path(report["modes"]["absent"]["_result"]), result=True)
        _, _, zero = parse_records(Path(report["modes"]["zero"]["_result"]), result=True)
        for name in ("GAS_TAU", "TOTAL_TAU", "UP", "DN", "HR", "UPC", "DNC", "HRC"):
            if name not in absent or name not in zero or not np.array_equal(absent[name], zero[name]):
                raise AssertionError(f"omitted and all-zero CFC paths differ in {name}")
        report["absent_equals_explicit_zero"] = True

        # Independent direct-core replay must reproduce each synthetic case,
        # proving the captured optional V8 VMR fields are consumed in order.
        for mode, item in report["modes"].items():
            output_path = work / f"{mode}.reference.result"
            maxima = compare_reference(args.reference.resolve(), args.data_dir.resolve(),
                                       Path(item["_input"]), output_path)
            item["metrics"] = {"max_abs_diff_adapter_vs_reference": maxima}
            del item["_input"]
            del item["_result"]

        # Each species must affect optical depth, and the combined fixture must
        # change at least one radiative output. These tests are structural;
        # magnitudes are recorded without claiming model validation.
        if "GAS_TAU_RAW" not in zero:
            raise AssertionError("explicit-zero V8 result omitted GAS_TAU_RAW")
        base_gas = zero["GAS_TAU_RAW"]
        for species in EXPECTED:
            _, _, case = parse_records(Path(work / species / "lw.result"), result=True)
            delta = np.abs(case["GAS_TAU_RAW"] - base_gas)
            if not np.any(delta > 0.):
                raise AssertionError(f"{species} did not affect traced gas optical depth")
            output_deltas = {
                name: float(np.max(np.abs(case[name] - zero[name])))
                for name in ("UP", "DN", "HR", "UPC", "DNC", "HRC")
            }
            if not any(value > 0. for value in output_deltas.values()):
                raise AssertionError(f"{species} changed optical depth but no public LW output")
            report["modes"][species]["metrics"].update({
                "max_abs_delta_gas_tau_vs_zero": float(delta.max()),
                "max_abs_delta_outputs_vs_zero": output_deltas,
            })
        _, _, combined = parse_records(Path(work / "all" / "lw.result"), result=True)
        flux_deltas = {}
        for name in ("UP", "DN", "HR", "UPC", "DNC", "HRC"):
            flux_deltas[name] = float(np.max(np.abs(combined[name] - zero[name])))
        if not any(v > 0. for v in flux_deltas.values()):
            raise AssertionError("combined CFC fixture changed no public LW flux/heating output")
        report["modes"]["all"]["metrics"]["max_abs_delta_outputs_vs_zero"] = flux_deltas

        for mode, diagnostic in BAD_CASES.items():
            cap = work / f"invalid-{mode}"
            proc = run(args.adapter.resolve(), args.data_dir.resolve(), mode, cap)
            if proc.returncode == 0 or diagnostic not in proc.stdout:
                raise AssertionError(f"invalid case {mode} expected {diagnostic}; rc={proc.returncode}\n{proc.stdout}")
            report["invalid_inputs"][mode] = {"diagnostic": diagnostic, "rejected": True}
        report["status"] = "PASS"
    except Exception as exc:
        report["error"] = str(exc)
        report["work_directory"] = str(work)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report["error"], file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
