#!/usr/bin/env python3
"""Exercise all three SW delta compositions on a V4 replay input."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from compare_column_replay import compare, read_result
from test_column_replay import read_input


def write_variant(source: Path, destination: Path, updates: dict[str, np.ndarray]) -> None:
    lines = source.read_text(encoding="ascii").splitlines()
    out = lines[:2]
    pos = 2
    while pos < len(lines):
        header = lines[pos].split()
        if len(header) != 3:
            raise ValueError(f"{source}:{pos + 1}: invalid input section header")
        name = header[0].upper()
        rows, cols = int(header[1]), int(header[2])
        pos += 1
        values: list[str] = []
        while sum(len(line.split()) for line in values) < rows * cols and pos < len(lines):
            values.append(lines[pos])
            pos += 1
        if name not in updates:
            out.append(" ".join(header))
            out.extend(values)
            continue
        arr = np.asarray(updates[name], dtype=np.float64)
        if arr.shape != (rows, cols) or not np.isfinite(arr).all():
            raise ValueError(f"replacement {name} has invalid shape or values")
        out.append(f"{name} {rows} {cols}")
        out.extend(f"{x:.16E}" for x in arr.flatten(order="F"))
    destination.write_text("\n".join(out) + "\n", encoding="ascii")


def run_reference(exe: Path, data: Path, source: Path, output: Path, policy: int | None) -> None:
    command = [str(exe), str(data), str(source), str(output)]
    if policy is not None:
        command.append(str(policy))
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"reference policy {policy} failed: {result.stdout[-1600:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("adapter_executable", type=Path)
    parser.add_argument("reference_executable", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data, adapter, reference = (p.resolve() for p in
                                (args.data_directory, args.adapter_executable, args.reference_executable))
    for path in (data, adapter, reference):
        if not path.exists():
            parser.error(f"required path does not exist: {path}")

    with tempfile.TemporaryDirectory(prefix="rrtmgp-sw-delta-replay-") as temp:
        root = Path(temp)
        capture = root / "capture"
        capture.mkdir()
        env = os.environ.copy()
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
        env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
        result = subprocess.run([str(adapter), str(data)], cwd=root, env=env,
                                text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            raise RuntimeError(f"V4 adapter fixture failed: {result.stdout[-1600:]}")
        source = capture / "sw.input"
        production = capture / "sw.result"
        phase, nc, nl, overlap, seed, iceflag, records = read_input(source)
        if (phase, nc) != ("SW", 1) or source.read_text().splitlines()[0].strip() not in {"RRTMGP_REPLAY_V4", "RRTMGP_REPLAY_V5", "RRTMGP_REPLAY_V6"}:
            raise RuntimeError("adapter did not capture one-column V4/V5/V6 SW input")
        # Add liquid and ice paths so all policies compare the composition
        # step with active cloud and captured rain/snow optics.
        variant = root / "sw-cloudy.input"
        updates = {
            "LWP": np.tile(np.asarray([[100., 40., 8.]]), (nc, 1)),
            "IWP": np.tile(np.asarray([[30., 18., 4.]]), (nc, 1)),
        }
        write_variant(source, variant, updates)
        _, _, _, _, _, _, variant_records = read_input(variant)
        if not np.array_equal(variant_records["CF"], records["CF"]):
            raise RuntimeError("V4 cloud-path fixture unexpectedly changed cloud fraction")

        default_out = root / "default.result"
        run_reference(reference, data, variant, default_out, None)
        outputs: dict[int, dict] = {}
        max_policy_differences: dict[str, float] = {}
        for policy in (1, 2, 3):
            out = root / f"policy-{policy}.result"
            run_reference(reference, data, variant, out, policy)
            outputs[policy] = read_result(out)
        default_report = compare(read_result(default_out), outputs[1])
        if not default_report.get("passed"):
            raise RuntimeError("explicit policy 1 changed the default V4 result")
        sections = outputs[1]["sections"]
        for policy in (2, 3):
            other = outputs[policy]["sections"]
            delta = float(np.max(np.abs(sections["PREPARED_TAU"] - other["PREPARED_TAU"])))
            max_policy_differences[str(policy)] = delta
            if delta <= 1.e-8:
                raise RuntimeError(f"policy {policy} did not change prepared cloud optics")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "status": "PASS",
            "input": "actual adapter-generated V4 SW replay with liquid/ice paths added for controlled composition comparison",
            "default_equals_explicit_policy_1": True,
            "policy_1_vs_policy_2_or_3_max_abs_prepared_tau": max_policy_differences,
            "policy_1_sections": default_report["sections_compared"],
            "policies": {"1": "D(C)+D(P)", "2": "C+D(P)", "3": "D(C+P)"},
        }
        args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote V4 SW policy replay summary to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
