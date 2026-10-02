#!/usr/bin/env python3
"""Exercise the V9 SW pre-delta direct trace and independent replay."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from compare_column_replay import compare, read_result
from test_column_replay import read_input


def run_case(data: Path, adapter: Path, reference: Path, case: str,
             table: Path | None, with_precip: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="sw-predelta-replay-") as temporary:
        root = Path(temporary) / case
        root.mkdir()
        capture = root / "capture"
        capture.mkdir()
        env = os.environ.copy()
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
        env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
        env["OMP_NUM_THREADS"] = "1"
        run_case_name = ("capture_frozen_overlap_zero" if table is not None else
                         "capture_precip" if with_precip else "capture")
        result = subprocess.run([str(adapter), str(data), run_case_name, str(table or "")], env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode != 0 or f"SW pre-delta direct contract PASS: {run_case_name}" not in result.stdout:
            raise RuntimeError(f"adapter trace failed ({result.returncode}):\n{result.stdout}")
        source, actual_path = capture / "sw.input", capture / "sw.result"
        if not source.is_file() or not actual_path.is_file():
            raise RuntimeError("adapter did not write a complete SW trace")
        phase, nc, nl, overlap, _seed, _iceflag, records = read_input(source)
        if (phase, nc, nl) != ("SW", 2, 3):
            raise RuntimeError("captured V9 fixture header differs from expected two-column SW input")
        expected_overlap = 1 if table is None else 0
        if overlap != expected_overlap:
            raise RuntimeError("captured V9 overlap mode differs from the selected fixture")
        if source.read_text(encoding="ascii").splitlines()[0].strip() != "RRTMGP_REPLAY_V9":
            raise RuntimeError("optional direct diagnostics did not select replay V9")
        required = {"SW_DIRECT_PREDELTA_POLICY", "RAW_GAS_TAU", "RAW_CLOUD_TAU",
                    "RAW_PRECIP_TAU", "RAW_GRAUPEL_TAU_EXT", "RAW_HAIL_TAU_EXT",
                    "MCICA_MASK", "VISIBLE_WEIGHT"}
        if not required.issubset(records):
            raise RuntimeError(f"V9 trace missing {sorted(required - records.keys())}")
        if table is not None:
            if "GWP" not in records or "HWP" not in records:
                raise RuntimeError("frozen V9 capture omitted graupel/hail inputs")
            if np.any(records["MCICA_MASK"] != 0.0):
                raise RuntimeError("overlap-zero case unexpectedly sampled native-cloud mask")
            if not np.any(records["RAW_GRAUPEL_TAU_EXT"] > 0.0) or not np.any(records["RAW_HAIL_TAU_EXT"] > 0.0):
                raise RuntimeError("frozen paths were not retained outside the MCICA mask")
        if table is None and not with_precip:
            if np.any(records["MCICA_MASK"][1] != 0.0):
                raise RuntimeError("clear second column unexpectedly sampled a cloud mask")
            if np.any(records["RAW_CLOUD_TAU"][1] != 0.0):
                raise RuntimeError("clear second column has nonzero cloud optical depth")
        if with_precip:
            if "RWP" not in records or not np.any(records["RWP"] > 0.0):
                raise RuntimeError("precipitation V9 fixture did not capture a positive rain path")
            if not np.any(records["RAW_PRECIP_TAU"] > 0.0):
                raise RuntimeError("precipitation V9 fixture did not capture raw precipitation extinction")
        expected_path = root / "reference.result"
        if table is not None:
            env["WRF_RRTMGP_FROZEN_TABLE"] = str(table)
        replay = subprocess.run([str(reference), str(data), str(source), str(expected_path)],
                                env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        if replay.returncode != 0:
            raise RuntimeError(f"independent V9 replay failed ({replay.returncode}):\n{replay.stdout}")
        actual = read_result(actual_path)
        expected = read_result(expected_path)
        report = compare(actual, expected)
        if not report.get("passed"):
            raise RuntimeError(f"V9 adapter/reference mismatch: {report['failed_sections']}")
        sections = actual["sections"]
        for key in ("DIRECT_PREDELTA", "DIRECTC_PREDELTA", "VISDIR_PREDELTA", "NIRDIR_PREDELTA"):
            if key not in sections:
                raise RuntimeError(f"missing {key} in V9 result")
        if np.array_equal(sections["DIRECT_PREDELTA"], sections["DIRECT"]):
            raise RuntimeError("cloud fixture did not distinguish pre-delta from solver direct")
        direct = sections["DIRECT_PREDELTA"][:, :, 0]
        clear_direct = sections["DIRECTC_PREDELTA"][:, :, 0]
        if np.max(np.abs(direct[1] - clear_direct[1])) > 1.0e-5:
            raise RuntimeError("clear second column direct beam differs from its gas-only control")


def main() -> int:
    if len(sys.argv) not in (4, 5):
        raise SystemExit("usage: test_sw_predelta_replay.py DATA ADAPTER REFERENCE [FROZEN_TABLE]")
    data, adapter, reference = (Path(x).resolve() for x in sys.argv[1:4])
    table = Path(sys.argv[4]).resolve() if len(sys.argv) == 5 else None
    run_case(data, adapter, reference, "cloud", None)
    run_case(data, adapter, reference, "precip", None, with_precip=True)
    if table is not None:
        run_case(data, adapter, reference, "frozen-overlap-zero", table)
    print("SW pre-delta V9 independent replay PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
