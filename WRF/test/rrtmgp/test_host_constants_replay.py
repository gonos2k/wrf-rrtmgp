#!/usr/bin/env python3
"""Verify V5 replay reproduces columns initialized with non-default host constants."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from compare_column_replay import compare, read_result


def run(command: list[str], env: dict[str, str], label: str) -> None:
    proc = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)
    if proc.returncode:
        raise RuntimeError(f"{label} failed ({proc.returncode}): {proc.stdout[-2000:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("host_constants_executable", type=Path)
    parser.add_argument("reference_executable", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.data_directory.resolve()
    host_exe = args.host_constants_executable.resolve()
    ref_exe = args.reference_executable.resolve()
    for path in (data, host_exe, ref_exe):
        if not path.exists():
            parser.error(f"required path does not exist: {path}")

    reports = {}
    with tempfile.TemporaryDirectory(prefix="rrtmgp-host-constants-replay-") as tmp:
        root = Path(tmp)
        captures = root / "captures"
        captures.mkdir()
        env = os.environ.copy()
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(captures)
        env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
        run([str(host_exe), str(data)], env, "host-constant adapter")
        for phase in ("lw", "sw"):
            input_path = captures / f"{phase}.input"
            actual_path = captures / f"{phase}.result"
            if not input_path.exists() or not actual_path.exists():
                raise RuntimeError(f"missing {phase.upper()} replay capture")
            lines = input_path.read_text(encoding="ascii").splitlines()
            if not lines or lines[0].strip() != "RRTMGP_REPLAY_V5":
                raise RuntimeError(f"{phase.upper()} capture did not use replay V5")
            records = {line.split()[0].upper(): idx for idx, line in enumerate(lines[2:], start=2)
                       if line.split() and line.split()[0].upper() in {"GRAVITY", "CP_DRY", "MOL_WEIGHT_DRY"}}
            for name, expected in (("GRAVITY", 9.81), ("CP_DRY", 1004.5), ("MOL_WEIGHT_DRY", .028966)):
                if name not in records or len(lines[records[name]].split()) != 3:
                    raise RuntimeError(f"{phase.upper()} V5 missing scalar {name}")
                if abs(float(lines[records[name] + 1].split()[0]) - expected) > max(1.e-9, abs(expected) * 2.e-7):
                    raise RuntimeError(f"{phase.upper()} V5 {name} does not preserve host initialization")
            reference_path = root / f"{phase}.reference.result"
            run([str(ref_exe), str(data), str(input_path), str(reference_path)], env,
                f"{phase.upper()} independent replay")
            report = compare(read_result(actual_path), read_result(reference_path))
            if not report.get("passed"):
                raise RuntimeError(f"{phase.upper()} replay mismatch: {report.get('failed_sections')}")
            reports[phase.upper()] = report

    summary = {"status": "PASS", "constants": {"gravity_m_s2": 9.81,
               "cp_dry_j_kg_k": 1004.5, "mol_weight_dry_kg_mol": .028966},
               "phases": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
