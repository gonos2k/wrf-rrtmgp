#!/usr/bin/env python3
"""Validate UDM precipitation adapter captures against the V4 column replay."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from compare_column_replay import compare, read_result
from test_column_replay import ReplayError, read_input
from test_replay_formats import rewrite_input


def fail(message: str) -> None:
    raise RuntimeError(message)


def run_reference(executable: Path, data_dir: Path, input_path: Path,
                  output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(executable), str(data_dir), str(input_path), str(output_path)],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("adapter_executable", type=Path)
    parser.add_argument("reference_executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data_dir = args.data_directory.resolve()
    adapter = args.adapter_executable.resolve()
    reference = args.reference_executable.resolve()
    for required in (data_dir, adapter, reference):
        if not required.exists():
            parser.error(f"required path does not exist: {required}")

    summary: dict[str, Any] = {"status": "FAIL", "phases": {}, "invalid_v4_rejections": []}
    with tempfile.TemporaryDirectory(prefix="rrtmgp-udm-replay-") as temporary:
        root = Path(temporary)
        capture = root / "capture"
        capture.mkdir()
        env = os.environ.copy()
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
        env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
        run = subprocess.run([str(adapter), str(data_dir)], cwd=root, env=env,
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if run.returncode != 0:
            fail(f"UDM adapter test failed ({run.returncode}): {run.stdout[-2400:]}")

        for phase in ("LW", "SW"):
            replay = capture / f"{phase.lower()}.input"
            production_path = capture / f"{phase.lower()}.result"
            if not replay.is_file() or not production_path.is_file():
                fail(f"adapter did not capture V4 {phase} input/result")
            parsed_phase, nc, nl, overlap, seed, iceflag, records = read_input(replay)
            if (parsed_phase, nc, nl) != (phase, 1, 3):
                fail(f"unexpected V4 {phase} input header {(parsed_phase, nc, nl)}")
            if replay.read_text(encoding="ascii").splitlines()[0].strip() != "RRTMGP_REPLAY_V4":
                fail(f"{phase} capture did not use replay V4")
            rwp = records.get("RWP")
            if rwp is None or rwp.shape != (nc, nl) or not np.any(rwp > 0.0):
                fail(f"{phase} V4 must retain positive in-cloud rain paths")
            res = records["RES"]
            if not np.array_equal(res[0], np.asarray([25.0, 300.0, 999.0])):
                fail(f"{phase} test did not preserve native snow radii")

            reference_path = root / f"{phase.lower()}.reference.result"
            ref_run = run_reference(reference, data_dir, replay, reference_path)
            if ref_run.returncode != 0:
                fail(f"reference rejected V4 {phase}: {ref_run.stdout[-1600:]}")
            report = compare(read_result(production_path), read_result(reference_path))
            if not report.get("passed"):
                fail(f"V4 {phase} adapter/reference mismatch: {report.get('failed_sections')}")
            production = read_result(production_path)["sections"]
            expected_radii = production["DS_USED"][:, :, 0]
            if not np.array_equal(expected_radii, res):
                fail(f"{phase} DS_USED must equal native RES, with no ice-LUT conversion/clipping")
            precip = production.get("PRECIP_TAU")
            if precip is None or not np.any(precip > 0.0):
                fail(f"{phase} precipitation optical depth must be present and positive")
            summary["phases"][phase] = {
                "header": [phase, nc, nl, overlap, seed, iceflag],
                "sections_compared": report["sections_compared"],
                "max_differences": report["max_differences"],
                "native_snow_radius_preserved": True,
                "positive_precip_optics": True,
            }

            for label, remove, replacements in (
                ("missing_rwp", {"RWP"}, {}),
                ("bad_policy", set(), {"PRECIPITATION_OPTICS": "2"}),
            ):
                invalid = root / f"{phase.lower()}.{label}.input"
                rewrite_input(replay, invalid, "RRTMGP_REPLAY_V4", remove=remove, replacements=replacements)
                try:
                    read_input(invalid)
                except ReplayError:
                    pass
                else:
                    fail(f"Python replay reader accepted invalid {phase} V4 case {label}")
                invalid_run = run_reference(reference, data_dir, invalid, root / f"{phase.lower()}.{label}.result")
                if invalid_run.returncode == 0:
                    fail(f"reference accepted invalid {phase} V4 case {label}")
                summary["invalid_v4_rejections"].append(f"{phase}:{label}")

        summary["status"] = "PASS"

    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
