#!/usr/bin/env python3
"""Capture and independently replay CU optics fixtures for V13/V11 and legacy formats."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from compare_column_replay import compare, read_result
from test_column_replay import read_input


CASES = {
    "capture": (True, 1),
    "overlap_zero": (True, 0),
    "no_precip": (True, 1),
    "capture_zero": (True, 1),
    "capture_absent": (False, 1),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_pin(path: Path) -> dict[str, Any]:
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def provenance(args: argparse.Namespace) -> dict[str, Any]:
    generator = args.generator.resolve(strict=True)
    reference = args.reference.resolve(strict=True)
    data = args.data.resolve(strict=True)
    table = args.table.resolve(strict=True)
    here = Path(__file__).resolve().parent
    sources = [here / "reference_column.f90", here / "test_column_replay.py",
               here / "compare_column_replay.py", here / "test_cu_population_optics_replay.py",
               here / "test_cu_population_optics.f90"]
    coefficients = [data / name for name in ("rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-sw-g112.nc",
                    "rrtmgp-clouds-lw-bnd.nc", "rrtmgp-clouds-sw-bnd.nc")]
    return {"executables": {"generator": file_pin(generator), "reference": file_pin(reference)},
            "table": file_pin(table), "coefficient_data": [file_pin(p) for p in coefficients],
            "sources": [file_pin(p) for p in sources]}


def run(command: list[str], cwd: Path, env: dict[str, str], log: Path,
        timeout: float = 180.0) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, timeout=timeout, check=False)
        output = completed.stdout
        rc = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        rc = None
        timed_out = True
    log.write_text(output, encoding="utf-8")
    return {"command": command, "cwd": str(cwd), "returncode": rc, "timed_out": timed_out,
            "elapsed_seconds": time.monotonic() - started, "log": str(log),
            "log_sha256": sha256(log)}


def execute(args: argparse.Namespace) -> dict[str, Any]:
    generator = args.generator.resolve(strict=True)
    reference = args.reference.resolve(strict=True)
    data = args.data.resolve(strict=True)
    table = args.table.resolve(strict=True)
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output directory already exists: {out}")
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("WRF_RRTMGP_"):
            env.pop(name, None)
    env["OMP_NUM_THREADS"] = "1"
    env["OMP_DYNAMIC"] = "FALSE"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["WRF_RRTMGP_FROZEN_TABLE"] = str(table)
    versions = {"capture": {"LW": "RRTMGP_REPLAY_V13", "SW": "RRTMGP_REPLAY_V11"},
                "overlap_zero": {"LW": "RRTMGP_REPLAY_V13", "SW": "RRTMGP_REPLAY_V11"},
                "no_precip": {"LW": "RRTMGP_REPLAY_V13", "SW": "RRTMGP_REPLAY_V11"},
                "capture_zero": {"LW": "RRTMGP_REPLAY_V13", "SW": "RRTMGP_REPLAY_V11"},
                "capture_absent": {"LW": "RRTMGP_REPLAY_V12", "SW": "RRTMGP_REPLAY_V9"}}
    receipt: dict[str, Any] = {
        "status": "RUNNING", "cases": [],
        "pins": {"generator": {"path": str(generator), "sha256": sha256(generator)},
                 "reference": {"path": str(reference), "sha256": sha256(reference)},
                 "data_dir": str(data), "table": {"path": str(table), "sha256": sha256(table)},
                 "harness": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())}},
        "scope": "small synthetic independent CU adapter/reference fixtures; no forecast claim",
    }
    for frozen in (0, 1):
        for mode, (expects_cu, expected_overlap) in CASES.items():
            case_dir = out / f"{mode}-frozen{frozen}"
            capture = case_dir / "capture"
            capture.mkdir(parents=True)
            case_env = env.copy()
            case_env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
            case_env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
            item: dict[str, Any] = {"mode": mode, "frozen_mode": frozen, "expects_cu": expects_cu,
                                    "overlap": expected_overlap, "phases": {}}
            launch = run([str(generator), str(data), mode, str(table), str(frozen)], case_dir,
                         case_env, case_dir / "fixture.log")
            item["fixture"] = launch
            if launch["returncode"] != 0 or launch["timed_out"]:
                item["status"] = "FAIL_FIXTURE"
                receipt["cases"].append(item)
                receipt["status"] = "FAIL"
                return receipt
            for phase in ("LW", "SW"):
                stem = phase.lower()
                input_path = capture / f"{stem}.input"
                actual_path = capture / f"{stem}.result"
                input_version = input_path.read_text(encoding="ascii").splitlines()[0].strip()
                phase_tag, nc, nl, overlap, seed, iceflag, adapter = read_input(input_path)
                expected_version = versions[mode][phase]
                if input_version != expected_version or phase_tag != phase or \
                        overlap != expected_overlap or (nc, nl) != (2, 3):
                    raise ValueError(f"{input_path}: unexpected header/version {input_version} {nc}x{nl} overlap={overlap}")
                if phase == "LW":
                    n2 = adapter.get("VMR_N2")
                    flag = adapter.get("TRACE_GASES_PRESENT")
                    if n2 is None or n2.shape != (nc, nl) or not np.isfinite(n2).all() or \
                            not np.all(n2 == 0.7808):
                        raise ValueError(f"{input_path}: LW N2 background trace is missing or not exactly 0.7808")
                    if flag is None or flag.shape != (1, 1) or flag.item() not in (0.0, 1.0):
                        raise ValueError(f"{input_path}: LW CFC presence flag is missing/invalid")
                    cfc_names = {"VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"}
                    cfc_present = cfc_names & adapter.keys()
                    if (flag.item() == 1.0 and cfc_present != cfc_names) or (flag.item() == 0.0 and cfc_present):
                        raise ValueError(f"{input_path}: LW CFC arrays disagree with explicit trace-gas flag")
                cu_names = {"CU_POPULATION_POLICY", "CU_RADIUS_POLICY", "CU_OCCURRENCE_POLICY",
                            "CU_LWP", "CU_IWP", "CU_REL", "CU_REI"}
                cu_records = cu_names & adapter.keys()
                if expects_cu and cu_records != cu_names:
                    raise ValueError(f"{input_path}: CU policy/profiles are incomplete")
                if not expects_cu and cu_records:
                    raise ValueError(f"{input_path}: absent-bundle fixture serialized CU records")
                reference_path = capture / f"{stem}.reference.result"
                ref_env = env.copy()
                command = [str(reference), str(data), str(input_path), str(reference_path)]
                replay = run(command, case_dir, ref_env, case_dir / f"reference-{stem}.log")
                if replay["returncode"] != 0 or replay["timed_out"]:
                    item["phases"][phase] = {"status": "FAIL_REFERENCE", "reference": replay}
                    receipt["cases"].append(item)
                    receipt["status"] = "FAIL"
                    return receipt
                compared = compare(read_result(actual_path), read_result(reference_path))
                if not compared.get("passed"):
                    item["phases"][phase] = {"status": "FAIL_COMPARE", "reference": replay,
                                             "comparison": compared}
                    receipt["cases"].append(item)
                    receipt["status"] = "FAIL"
                    return receipt
                result_sections = read_result(actual_path)["sections"]
                if expects_cu:
                    required = {"NATIVE_CLOUD_TAU", "CU_CLOUD_TAU", "CU_RL_USED", "CU_DI_USED"}
                    if phase == "SW":
                        required |= {"NATIVE_CLOUD_SSA", "NATIVE_CLOUD_G", "CU_CLOUD_SSA", "CU_CLOUD_G"}
                    absent = required - result_sections.keys()
                    if absent:
                        raise ValueError(f"{actual_path}: missing CU result components {sorted(absent)}")
                elif any(name.startswith("CU_CLOUD_") or name.startswith("NATIVE_CLOUD_")
                         for name in result_sections):
                    raise ValueError(f"{actual_path}: legacy absent-bundle result has new CU component records")
                item["phases"][phase] = {
                    "status": "PASS", "version": input_version, "seed": seed, "iceflag": iceflag,
                    "section_count": compared["sections_compared"],
                    "compared_max_differences": compared["max_differences"],
                    "input_sha256": sha256(input_path), "production_result_sha256": sha256(actual_path),
                    "reference_result_sha256": sha256(reference_path), "reference": replay,
                }
            item["status"] = "PASS"
            receipt["cases"].append(item)
    receipt["status"] = "PASS"
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--table", type=Path, required=True)
    outputs = parser.add_mutually_exclusive_group(required=True)
    outputs.add_argument("--output-dir", type=Path)
    outputs.add_argument("--ctest-output-root", type=Path,
                          help="create a unique retained run directory under this root")
    args = parser.parse_args()
    if args.ctest_output_root is not None:
        root = args.ctest_output_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        args.output_dir = Path(tempfile.mkdtemp(prefix="cu-population-replay-", dir=root))
    else:
        args.output_dir = args.output_dir.resolve()
        if args.output_dir.exists():
            print(json.dumps({"status": "OUTPUT_COLLISION", "output": str(args.output_dir)}))
            return 2
    out = args.output_dir.resolve()
    try:
        before = provenance(args)
    except Exception as exc:
        receipt = {"status": "FAIL_SETUP_OR_VALIDATION", "error": f"{type(exc).__name__}: {exc}"}
        out.mkdir(parents=True, exist_ok=True)
        (out / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "receipt": str(out / "receipt.json")}, sort_keys=True))
        return 1
    try:
        receipt = execute(args)
    except Exception as exc:
        receipt = {"status": "FAIL_SETUP_OR_VALIDATION", "error": f"{type(exc).__name__}: {exc}"}
    try:
        after = provenance(args)
        receipt["asset_integrity"] = {"before": before, "after": after, "unchanged": before == after}
        if before != after:
            receipt["status"] = "FAIL_ASSET_CHANGED"
    except Exception as exc:
        receipt["asset_integrity"] = {"before": before, "after_error": f"{type(exc).__name__}: {exc}",
                                      "unchanged": False}
        receipt["status"] = "FAIL_ASSET_POSTCHECK"
    out.mkdir(parents=True, exist_ok=True)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "receipt": str(out / "receipt.json")}, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
