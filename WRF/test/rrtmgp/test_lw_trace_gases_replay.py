#!/usr/bin/env python3
"""Synthetic N2/CFC input contract and independent replay regression for LW."""
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

from test_column_replay import ReplayError, read_input


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
    # The adapter retains GAS_TAU and exposes the same raw optical record.
    # V12/V13 add N2 provenance without reinterpreting any V1-V11 input.
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


def rewrite_section(source: Path, destination: Path, name: str, *,
                    header: str | None = None, values: list[str] | None = None,
                    remove: bool = False) -> None:
    """Rewrite one numeric section while preserving the rest of the fixture."""
    lines = source.read_text(encoding="ascii").splitlines()
    out = lines[:2]
    pos = 2
    found = False
    while pos < len(lines):
        fields = lines[pos].split()
        if len(fields) != 3:
            raise ValueError(f"{source}:{pos+1}: malformed input section")
        section = fields[0].upper()
        count = int(fields[1]) * int(fields[2])
        end = pos + 1
        tokens = 0
        while tokens < count and end < len(lines):
            tokens += len(lines[end].split())
            end += 1
        if tokens != count:
            raise ValueError(f"{source}: truncated {section}")
        if section == name.upper():
            if found:
                raise ValueError(f"{source}: duplicate {section}")
            found = True
            if not remove:
                out.append(header or lines[pos])
                out.extend(values if values is not None else lines[pos+1:end])
        else:
            out.extend(lines[pos:end])
        pos = end
    if not found and not remove:
        raise ValueError(f"{source}: missing {name}")
    destination.write_text("\n".join(out) + "\n", encoding="ascii")


def reject_bad_replay(reference: Path, data: Path, source: Path, work: Path,
                      label: str, *, name: str, header: str | None = None,
                      values: list[str] | None = None, remove: bool = False) -> None:
    invalid = work / f"invalid-{label}.input"
    rewrite_section(source, invalid, name, header=header, values=values, remove=remove)
    try:
        read_input(invalid)
    except ReplayError:
        pass
    else:
        raise AssertionError(f"Python reader accepted malformed N2 replay {label}")
    output = work / f"invalid-{label}.result"
    proc = subprocess.run([str(reference), str(data), str(invalid), str(output)],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode == 0:
        raise AssertionError(f"reference accepted malformed N2 replay {label}")


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
            if magic != "RRTMGP_REPLAY_V12":
                raise AssertionError(f"LW trace without CU should use V12, got {magic}")
            if "VMR_N2" not in inp or inp["VMR_N2"].shape != dims or \
                    not np.all(inp["VMR_N2"] == 0.7808):
                raise AssertionError("V12 did not retain the exact fixed WP N2 profile")
            if "TRACE_GASES_PRESENT" not in inp or inp["TRACE_GASES_PRESENT"].shape != (1, 1):
                raise AssertionError("V12 omitted explicit CFC-presence metadata")
            if "GAS_TAU_RAW" not in out or not np.array_equal(out["GAS_TAU"], out["GAS_TAU_RAW"]):
                raise AssertionError("V12 result omitted or changed GAS_TAU_RAW")
            expected_flag = 0.0 if mode == "absent" else 1.0
            if inp["TRACE_GASES_PRESENT"].item() != expected_flag:
                raise AssertionError(f"V12 trace-gas presence flag is wrong for {mode}")
            for species, section in INPUT_NAMES.items():
                if expected_flag:
                    if section not in inp:
                        raise AssertionError(f"V12 trace omitted {section}")
                    # CFC arguments come from the host's default REAL API.
                    expected = float(np.float32(EXPECTED[species])) if mode in {species, "all"} else 0.0
                    if not np.all(inp[section] == expected):
                        raise AssertionError(f"{section} does not match synthetic fixture for {mode}")
                elif section in inp:
                    raise AssertionError(f"V12 should omit {section} when TRACE_GASES_PRESENT=0")
            report["modes"][mode]["_input"] = str(input_path)
            report["modes"][mode]["_result"] = str(result_path)

        # Reject malformed fixed-N2 metadata in both the independent Python
        # reader and compiled reference, including missing, malformed-shape,
        # nonfinite, and out-of-range inputs.
        valid_n2_input = Path(report["modes"]["absent"]["_input"])
        nl = report["modes"]["absent"]["dimensions"][1]
        reject_bad_replay(args.reference.resolve(), args.data_dir.resolve(), valid_n2_input, work,
                          "n2-missing", name="VMR_N2", remove=True)
        reject_bad_replay(args.reference.resolve(), args.data_dir.resolve(), valid_n2_input, work,
                          "n2-shape", name="VMR_N2", header="VMR_N2 1 1", values=["0.7808"])
        reject_bad_replay(args.reference.resolve(), args.data_dir.resolve(), valid_n2_input, work,
                          "n2-nonfinite", name="VMR_N2", values=["NaN"] + ["0.7808"] * (nl - 1))
        reject_bad_replay(args.reference.resolve(), args.data_dir.resolve(), valid_n2_input, work,
                          "n2-range", name="VMR_N2", values=["1.01"] + ["0.7808"] * (nl - 1))
        reject_bad_replay(args.reference.resolve(), args.data_dir.resolve(), valid_n2_input, work,
                          "trace-flag-range", name="TRACE_GASES_PRESENT", values=["2.0"])
        reject_bad_replay(args.reference.resolve(), args.data_dir.resolve(), valid_n2_input, work,
                          "trace-flag-missing", name="TRACE_GASES_PRESENT", remove=True)
        report["invalid_inputs"].update({
            "n2_missing": True, "n2_shape": True, "n2_nonfinite": True,
            "n2_out_of_range": True, "trace_flag_out_of_range": True,
            "trace_flag_missing": True,
        })

        # Verify omitted and explicitly-zero CFC inputs preserve the fixed
        # N2 background path exactly at trace and public-output precision.
        _, _, absent = parse_records(Path(report["modes"]["absent"]["_result"]), result=True)
        _, _, zero = parse_records(Path(report["modes"]["zero"]["_result"]), result=True)
        for name in ("GAS_TAU", "TOTAL_TAU", "UP", "DN", "HR", "UPC", "DNC", "HRC"):
            if name not in absent or name not in zero or not np.array_equal(absent[name], zero[name]):
                raise AssertionError(f"omitted and all-zero CFC paths differ in {name}")
        report["absent_equals_explicit_zero_with_fixed_n2"] = True

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
