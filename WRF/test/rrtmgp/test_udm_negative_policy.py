#!/usr/bin/env python3
"""Compile the actual UDM builder and verify its optional negative-q contract."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
WRF_ROOT = HERE.parents[1]
INPUT_SOURCE = WRF_ROOT / "phys" / "module_ra_rrtmgp_input.F"
FATAL_STUB = HERE / "standalone_wrf_error.f90"
FORTRAN_FIXTURE = HERE / "test_udm_negative_policy.f90"
sys.path.insert(0, str(HERE))
from test_column_replay import ReplayError, corrected_hydrometeor


def fail(message: str) -> None:
    raise RuntimeError(message)


def compile_fixture(build: Path) -> Path:
    compiler = shutil.which("gfortran")
    if not compiler:
        fail("gfortran is required for the isolated UDM builder test")
    executable = build / "test_udm_negative_policy"
    command = [compiler, "-ffree-form", "-ffree-line-length-none", "-fcheck=all",
               "-fbacktrace", "-J", str(build), "-I", str(build),
               str(INPUT_SOURCE), str(FORTRAN_FIXTURE), str(FATAL_STUB), "-o", str(executable)]
    result = subprocess.run(command, cwd=build, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        fail(f"compile actual module_ra_rrtmgp_input.F failed:\n{result.stdout[-2200:]}")
    return executable


def run_success(executable: Path, mode: str, cwd: Path) -> None:
    result = subprocess.run([str(executable), mode], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    marker = f"NEGATIVE_POLICY_FIXTURE_PASS {mode}"
    if result.returncode or marker not in result.stdout:
        fail(f"{mode}: expected successful fixture, rc={result.returncode}\n{result.stdout[-1400:]}")


def run_fatal(executable: Path, mode: str, pattern: str, cwd: Path) -> None:
    result = subprocess.run([str(executable), mode], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode == 0 or re.search(pattern, result.stdout) is None:
        fail(f"{mode}: expected fatal matching {pattern!r}, rc={result.returncode}\n{result.stdout[-1600:]}")


def raw_case(q: np.ndarray, limit: float, clipped: np.ndarray,
             correction: np.ndarray, dp_hpa: np.ndarray | None = None) -> dict[str, np.ndarray]:
    return {
        "SOURCE_QC": np.asarray(q, dtype=np.float64),
        "DP_HPA": np.asarray(dp_hpa if dp_hpa is not None else [1000.0, 500.0], dtype=np.float64),
        "GRAVITY": np.asarray([10.0], dtype=np.float64),
        "NEGATIVE_Q_LIMITS": np.asarray([limit, 0.0625, 0.25, 0.5, 0.25, 0.0625], dtype=np.float64),
        "NUMERIC_CLIPPED_QC": np.asarray(clipped, dtype=np.float64),
        "NEGATIVE_GRID_CORRECTION_LWP": np.asarray(correction, dtype=np.float64),
    }


def expect_python_failure(raw: dict[str, np.ndarray], message: str) -> None:
    try:
        corrected_hydrometeor(raw, "SOURCE_QC", "LWP", len(raw["SOURCE_QC"]))
    except ReplayError as exc:
        if message not in str(exc):
            fail(f"raw-record validation failed for the wrong reason: {exc}")
    else:
        fail(f"raw-record validation accepted invalid evidence: expected {message}")


def check_raw_record_validation() -> None:
    # New positive captures still require explicit, all-zero correction records.
    positive = raw_case(np.asarray([0.0, 0.125]), 0.125, [0.0, 0.0], [0.0, 0.0])
    if not np.array_equal(corrected_hydrometeor(positive, "SOURCE_QC", "LWP", 2),
                          positive["SOURCE_QC"]):
        fail("positive raw q was changed by the Python raw-record validator")
    missing_positive = positive.copy()
    del missing_positive["NEGATIVE_GRID_CORRECTION_LWP"]
    expect_python_failure(missing_positive, "missing, wrong shape, or nonfinite correction record")
    legacy_positive = {key: value for key, value in positive.items()
                       if key not in {"NEGATIVE_Q_LIMITS", "NUMERIC_CLIPPED_QC",
                                      "NEGATIVE_GRID_CORRECTION_LWP"}}
    if not np.array_equal(corrected_hydrometeor(legacy_positive, "SOURCE_QC", "LWP", 2),
                          legacy_positive["SOURCE_QC"]):
        fail("legacy positive-only record was not accepted unchanged")

    q = np.asarray([-0.0625, 0.125])
    dp = np.asarray([1000.0, 500.0])
    correction = np.asarray([625000.0, 0.0])
    accepted = raw_case(q, 0.125, [-0.0625, 0.0], correction, dp)
    sanitized = corrected_hydrometeor(accepted, "SOURCE_QC", "LWP", 2)
    if not np.array_equal(sanitized, np.asarray([0.0, 0.125])):
        fail("accepted raw negative did not reconstruct the sanitized q series")
    raw_path = q * dp * 100.0 / accepted["GRAVITY"][0] * 1000.0
    if not np.array_equal(raw_path + correction, sanitized * dp * 100.0 /
                          accepted["GRAVITY"][0] * 1000.0):
        fail("raw signed path plus correction differs from sanitized path")

    boundary = raw_case([-0.125, 0.0], 0.125, [-0.125, 0.0],
                        [1250000.0, 0.0])
    expect_python_failure(boundary, "accepted raw negative exceeds its strict bound")
    no_correction = raw_case(q, 0.125, [-0.0625, 0.0], [625000.0, 0.0])
    del no_correction["NEGATIVE_GRID_CORRECTION_LWP"]
    expect_python_failure(no_correction, "missing, wrong shape, or nonfinite correction record")
    tampered = raw_case(q, 0.125, [-0.0625, 0.0], [625001.0, 0.0])
    expect_python_failure(tampered, "mismatch")
    tampered_clip = raw_case(q, 0.125, [0.0, 0.0], correction)
    expect_python_failure(tampered_clip, "mismatch")

    # A float32-quantum negative remains visible in the clipped-q record even
    # though its water-path correction rounds to default-real zero.
    tiny_negative = -float(np.nextafter(np.float32(0.0), np.float32(1.0)))
    underflow = raw_case([tiny_negative, 0.0], 1.0e-40,
                         [tiny_negative, 0.0], [0.0, 0.0], [1.0e-38, 500.0])
    sanitized_tiny = corrected_hydrometeor(underflow, "SOURCE_QC", "LWP", 2)
    if underflow["NUMERIC_CLIPPED_QC"][0] != tiny_negative or sanitized_tiny[0] != 0.0:
        fail("underflow lost the accepted raw negative count or failed to clip it")


def main() -> int:
    # Some supported workspaces mount /tmp with noexec. Keep the compiled
    # fixture on the checkout filesystem, creating the scratch parent on a
    # fresh checkout rather than assuming a preceding CMake build.
    scratch_parent = WRF_ROOT.parent / "build"
    scratch_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rrtmgp-negative-policy-", dir=scratch_parent) as temporary:
        root = Path(temporary)
        executable = compile_fixture(root)
        for mode in ("mixed", "positive", "hail_tiny", "underflow"):
            run_success(executable, mode, root)
        run_fatal(executable, "strict_default",
                  r"column=d01:i=19:j=8 RRTMGP_INPUT_UDM_QG_NEGATIVE "
                  r"value_kgkg=-1\.250000000000000E-001 layer=2", root)
        run_fatal(executable, "boundary_equal",
                  r"column=d01:i=19:j=8 RRTMGP_INPUT_UDM_QC_NEGATIVE "
                  r"value_kgkg=-1\.250000000000000E-001 limit_kgkg=\s*1\.250000000000000E-001 layer=1", root)
        run_fatal(executable, "large_negative",
                  r"column=d01:i=19:j=8 RRTMGP_INPUT_UDM_QH_NEGATIVE "
                  r"value_kgkg=-1\.250000000000000E-001 limit_kgkg=\s*6\.250000000000000E-002 layer=2", root)
        run_fatal(executable, "limit_shape", r"RRTMGP_INPUT_SHAPE_MISMATCH in UDM negative_q_limits", root)
        run_fatal(executable, "limit_nan", r"RRTMGP_INPUT_UDM_NEGATIVE_LIMIT_INVALID", root)
        run_fatal(executable, "limit_inf", r"RRTMGP_INPUT_UDM_NEGATIVE_LIMIT_INVALID", root)
        run_fatal(executable, "limit_negative", r"RRTMGP_INPUT_UDM_NEGATIVE_LIMIT_INVALID", root)
        run_fatal(executable, "clipped_shape", r"RRTMGP_INPUT_SHAPE_MISMATCH in UDM clipped_negative_q", root)
        run_fatal(executable, "correction_shape", r"RRTMGP_INPUT_SHAPE_MISMATCH in UDM negative_grid_correction", root)
        run_fatal(executable, "nonfinite_q", r"RRTMGP_INPUT_UDM_QI_NOT_FINITE.*layer=2", root)
        check_raw_record_validation()
    print("PASS: strict/bounded negative-q policy, conservation outputs, bitwise inputs, "
          "underflow, atomic hail refusal, fatal diagnostics, and Python raw-capture evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
