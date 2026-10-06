#!/usr/bin/env python3
"""Compare frozen-optics adapter captures with independent table replay."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from compare_column_replay import compare, read_result
from test_column_replay import ReplayError, read_input

CASES = ("graupel", "hail", "mixed", "mixed_cloud", "tiny", "overlap_zero", "zero")
LW_FROZEN = {"GRAUPEL_TAU_ABS", "HAIL_TAU_ABS", "FROZEN_TAU"}
SW_FROZEN = {"GRAUPEL_TAU_EXT", "GRAUPEL_TAU_SCA", "GRAUPEL_TAU_SCA_G",
             "HAIL_TAU_EXT", "HAIL_TAU_SCA", "HAIL_TAU_SCA_G",
             "FROZEN_TAU", "FROZEN_SSA", "FROZEN_G"}


def fail(message: str) -> None:
    raise RuntimeError(message)


def run_capture(adapter: Path, data: Path, table: Path, case: str,
                capture: Path) -> subprocess.CompletedProcess[str]:
    capture.mkdir(parents=True)
    env = os.environ.copy()
    env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
    env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["OMP_DYNAMIC"] = "FALSE"
    env.pop("WRF_RRTMGP_CAPTURE_ALL", None)
    env.pop("WRF_RRTMGP_FROZEN_TABLE", None)
    return subprocess.run([str(adapter), str(data), str(table), case], env=env,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def run_reference(reference: Path, data: Path, table: Path, source: Path,
                  destination: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WRF_RRTMGP_FROZEN_TABLE"] = str(table)
    env.pop("WRF_RRTMGP_CAPTURE_DIR", None)
    env.pop("WRF_RRTMGP_CAPTURE_CALL", None)
    return subprocess.run([str(reference), str(data), str(source), str(destination)], env=env,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def verify_input(path: Path, expected_sha: str, phase: str) -> dict[str, np.ndarray]:
    parsed_phase, nc, nl, _overlap, _seed, _iceflag, records = read_input(path)
    if (parsed_phase, nc, nl) != (phase, 2, 3):
        fail(f"{path}: expected two-column three-layer {phase} input")
    version = path.read_text(encoding="ascii").splitlines()[0].strip()
    expected_versions = {"RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"} if phase == "LW" else {"RRTMGP_REPLAY_V7"}
    if version not in expected_versions:
        fail(f"{path}: frozen {phase} capture used unexpected replay format {version}")
    if phase == "LW":
        n2 = records.get("VMR_N2")
        flag = records.get("TRACE_GASES_PRESENT")
        if n2 is None or n2.shape != (nc, nl) or not np.all(n2 == 0.7808):
            fail(f"{path}: frozen LW capture lost the fixed dry-background N2 profile")
        if flag is None or flag.shape != (1, 1) or flag.item() not in (0.0, 1.0):
            fail(f"{path}: frozen LW capture has invalid CFC presence metadata")
        cfc_names = {"VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"}
        if (flag.item() == 1.0 and not cfc_names <= records.keys()) or \
                (flag.item() == 0.0 and cfc_names & records.keys()):
            fail(f"{path}: frozen LW CFC records disagree with TRACE_GASES_PRESENT")
    digest_values = records["FROZEN_TABLE_SHA256_BYTES"][:, 0]
    actual_sha = "".join(chr(int(x)) for x in digest_values)
    if actual_sha != expected_sha:
        fail(f"{path}: recorded table SHA {actual_sha} != actual bytes {expected_sha}")
    if records["FROZEN_MODE"].item() != 1.0 or records["FROZEN_OCCURRENCE"].item() != 1.0:
        fail(f"{path}: expected uniform frozen mode and one occurrence")
    for name in ("GWP", "HWP"):
        if records[name].shape != (nc, nl) or np.any(records[name] < 0.0):
            fail(f"{path}: {name} shape or value contract failed")
    for name in ("LAMBDA_G", "LAMBDA_H"):
        if records[name].shape != (nc, nl) or np.any(records[name] <= 0.0):
            fail(f"{path}: {name} shape or value contract failed")
    return records


def verify_sections(phase: str, actual: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    required = LW_FROZEN if phase == "LW" else SW_FROZEN
    missing_actual = required - actual["sections"].keys()
    missing_replay = required - replay["sections"].keys()
    if missing_actual or missing_replay:
        fail(f"{phase}: missing frozen result fields; actual={sorted(missing_actual)} replay={sorted(missing_replay)}")
    report = compare(actual, replay)
    if not report.get("passed"):
        fail(f"{phase}: adapter/reference replay mismatch in {report.get('failed_sections')}")
    for name in required:
        detail = report["max_differences"].get(name)
        if detail is None or not detail.get("passed"):
            fail(f"{phase}: raw frozen optical moment {name} was not compared successfully")
    return report


def verify_hash_mismatch_rejected(reference: Path, data: Path, table: Path,
                                  captured_input: Path, work: Path) -> None:
    mutated = work / "wrong-table-bytes.nc"
    payload = bytearray(table.read_bytes())
    if not payload:
        fail("frozen table is empty")
    payload[-1] ^= 1
    mutated.write_bytes(payload)
    env = os.environ.copy()
    env["WRF_RRTMGP_FROZEN_TABLE"] = str(mutated)
    env.pop("WRF_RRTMGP_CAPTURE_DIR", None)
    run = subprocess.run([str(reference), str(data), str(captured_input), str(work / "hash-mismatch.result")],
                         env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if run.returncode == 0 or "SHA256 does not match input" not in run.stdout:
        fail(f"reference did not reject table bytes with the wrong recorded hash: {run.stdout[-1200:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("frozen_table", type=Path)
    parser.add_argument("adapter_executable", type=Path)
    parser.add_argument("reference_executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data, table, adapter, reference = (p.resolve() for p in
                                       (args.data_directory, args.frozen_table,
                                        args.adapter_executable, args.reference_executable))
    for path in (data, table, adapter, reference):
        if not path.exists():
            parser.error(f"required path does not exist: {path}")
    expected_sha = hashlib.sha256(table.read_bytes()).hexdigest()
    summary: dict[str, Any] = {"status": "FAIL", "table_sha256": expected_sha, "cases": {}}
    with tempfile.TemporaryDirectory(prefix="rrtmgp-frozen-replay-") as temporary:
        root = Path(temporary)
        hash_check_input: Path | None = None
        for case in CASES:
            case_root = root / case
            capture = case_root / "capture"
            case_root.mkdir()
            run = run_capture(adapter, data, table, case, capture)
            if run.returncode != 0 or f"PASS: {case}" not in run.stdout:
                # The Fortran fixture uses this full banner, include a fallback
                # check for the stable diagnostic from older fixture builds.
                if run.returncode != 0 or "EXPERIMENTAL frozen adapter contract PASS" not in run.stdout:
                    fail(f"adapter case {case} failed ({run.returncode}): {run.stdout[-1800:]}")
            case_report: dict[str, Any] = {"phases": {}}
            for phase in ("LW", "SW"):
                source = capture / f"{phase.lower()}.input"
                actual_path = capture / f"{phase.lower()}.result"
                if not source.is_file() or not actual_path.is_file():
                    fail(f"{case}: missing captured {phase} input/result")
                records = verify_input(source, expected_sha, phase)
                if hash_check_input is None:
                    hash_check_input = source
                replay_path = case_root / f"{phase.lower()}.reference.result"
                reference_run = run_reference(reference, data, table, source, replay_path)
                if reference_run.returncode != 0:
                    fail(f"reference rejected {case} {phase}: {reference_run.stdout[-1800:]}")
                actual = read_result(actual_path)
                replay = read_result(replay_path)
                compared = verify_sections(phase, actual, replay)
                frozen = LW_FROZEN if phase == "LW" else SW_FROZEN
                case_report["phases"][phase] = {
                    "header": [phase, 2, 3],
                    "frozen_input_records": {name: {"shape": list(records[name].shape),
                                                       "min": float(np.min(records[name])),
                                                       "max": float(np.max(records[name]))}
                                              for name in ("GWP", "HWP", "LAMBDA_G", "LAMBDA_H")},
                    "frozen_result_fields_compared": sorted(frozen),
                    "sections_compared": compared["sections_compared"],
                    "maximum_absolute_differences": {name: compared["max_differences"][name]["max_abs"]
                                                      for name in sorted(frozen)},
                }
            summary["cases"][case] = case_report
        assert hash_check_input is not None
        verify_hash_mismatch_rejected(reference, data, table, hash_check_input, root)
        summary["wrong_table_sha_rejected"] = True
        summary["status"] = "PASS"
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ReplayError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
