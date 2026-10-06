#!/usr/bin/env python3
"""Exercise V5 capture, V4 default replay, legacy V1/V2, and strict V3 SW contract."""
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


def fail(message: str) -> None:
    raise RuntimeError(message)


def rewrite_input(source: Path, destination: Path, magic: str,
                  remove: set[str] = frozenset(), replacements: dict[str, str] | None = None) -> None:
    """Rewrite one replay file while preserving each row/column record exactly."""
    lines = source.read_text(encoding="ascii").splitlines()
    if len(lines) < 2:
        fail(f"{source}: truncated replay input")
    output = [magic, lines[1]]
    replacements = replacements or {}
    pos = 2
    while pos < len(lines):
        header_line = lines[pos]
        fields = header_line.split()
        if not fields:
            pos += 1
            continue
        if len(fields) != 3:
            fail(f"{source}:{pos+1}: invalid input record header")
        name = fields[0].upper()
        try:
            count = int(fields[1]) * int(fields[2])
        except ValueError as exc:
            raise RuntimeError(f"{source}:{pos+1}: invalid record dimensions") from exc
        if count < 1:
            fail(f"{source}:{pos+1}: nonpositive record dimensions")
        record = [header_line]
        pos += 1
        found = 0
        while found < count and pos < len(lines):
            record.append(lines[pos])
            found += len(lines[pos].split())
            pos += 1
        if found != count:
            fail(f"{source}: truncated values for {name}")
        if name in remove:
            continue
        if name in replacements:
            if count != 1:
                fail(f"{source}: replacement requested for nonscalar {name}")
            record[1] = replacements[name]
        output.extend(record)
    destination.write_text("\n".join(output) + "\n", encoding="ascii")


def rewrite_default_v5_as_v4(source: Path, destination: Path) -> None:
    """Drop V5 constants and add a zero-rain V4 section to test legacy defaults."""
    lines = source.read_text(encoding="ascii").splitlines()
    header = lines[1].split()
    if len(header) != 6:
        fail(f"{source}: invalid replay header")
    nc, nl = int(header[1]), int(header[2])
    records: list[list[str]] = []
    pos = 2
    while pos < len(lines):
        fields = lines[pos].split()
        if len(fields) != 3:
            fail(f"{source}:{pos+1}: invalid input record header")
        name = fields[0].upper()
        count = int(fields[1]) * int(fields[2])
        record = [lines[pos]]
        pos += 1
        values = 0
        while values < count and pos < len(lines):
            row = lines[pos]
            record.append(row)
            values += len(row.split())
            pos += 1
        if values != count:
            fail(f"{source}: truncated values for {name}")
        if name not in {"GRAVITY", "CP_DRY", "MOL_WEIGHT_DRY"}:
            records.append(record)
    records.extend([
        ["PRECIPITATION_OPTICS 1 1", "1.0000000000000000E+000"],
        [f"RWP {nc} {nl}", *("0.0000000000000000E+000" for _ in range(nc * nl))],
    ])
    output = ["RRTMGP_REPLAY_V4", lines[1]]
    for record in records:
        output.extend(record)
    destination.write_text("\n".join(output) + "\n", encoding="ascii")


def run_reference(executable: Path, data_dir: Path, input_path: Path,
                  output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(executable), str(data_dir), str(input_path), str(output_path)],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def assert_result_match(actual: Path, expected: Path, label: str) -> dict[str, Any]:
    report = compare(read_result(actual), read_result(expected))
    if not report.get("passed"):
        fail(f"{label}: replay mismatch in {report.get('failed_sections')}")
    return report


def assert_default_v4_match(actual: Path, expected: Path, phase: str) -> dict[str, Any]:
    """Compare physical/common V5 outputs against V4's exact default constants."""
    production = read_result(actual)
    reference = read_result(expected)
    prod_names,ref_names=set(production["sections"]),set(reference["sections"])
    asymmetric=prod_names ^ ref_names
    precip_sections={"PRECIP_TAU", "PRECIP_SSA", "PRECIP_G"}
    if not asymmetric <= precip_sections:
        fail(f"V5/V4 {phase}: unexpected section-set difference {sorted(asymmetric)}")
    excluded={"DS_USED"} | asymmetric
    common = prod_names & ref_names
    required = {"GAS_TAU", "CLOUD_TAU", "PREPARED_TAU", "UP", "DN", "HR", "UPC", "DNC", "HRC"}
    if phase == "SW":
        required.update({"GAS_SSA", "GAS_G", "DIRECT", "DIFFUSE", "DIRECTC", "VISDIR",
                         "VISDIF", "NIRDIR", "NIRDIF"})
    if not required <= common:
        fail(f"V5/V4 {phase}: required common physical sections missing: {sorted(required-common)}")
    keep = common - excluded
    production["sections"] = {name: production["sections"][name] for name in keep}
    reference["sections"] = {name: reference["sections"][name] for name in keep}
    report = compare(production, reference)
    report["excluded_v4_protocol_sections"] = sorted(excluded)
    if not report.get("passed"):
        fail(f"V5 exact defaults versus V4 {phase}: mismatch in {report.get('failed_sections')}")
    return report


def must_reject_python(path: Path, label: str) -> None:
    try:
        read_input(path)
    except ReplayError:
        return
    fail(f"Python input reader accepted invalid {label}")


def must_reject_reference(executable: Path, data_dir: Path, path: Path,
                          output_path: Path, label: str) -> None:
    run = run_reference(executable, data_dir, path, output_path)
    if run.returncode == 0:
        fail(f"reference_column accepted invalid {label}")
    if label != "missing" and "SW_BAND_PARTITION" not in run.stdout:
        fail(f"reference_column rejected {label} without a partition diagnostic: {run.stdout[-1200:]}")


def old_policy_differences(new_result: Path, old_result: Path) -> dict[str, float]:
    new = read_result(new_result)["sections"]
    old = read_result(old_result)["sections"]
    required = {"UP", "VISDIR", "NIRDIR"}
    if not required <= new.keys() or not required <= old.keys():
        fail("SW result is missing surface or VIS/NIR diagnostics")
    differences = {
        "surface_up_w_m2": float(abs(new["UP"][0, 0, 0] - old["UP"][0, 0, 0])),
        "visible_direct_max_w_m2": float(np.max(np.abs(new["VISDIR"] - old["VISDIR"]))),
        "near_ir_direct_max_w_m2": float(np.max(np.abs(new["NIRDIR"] - old["NIRDIR"]))),
    }
    if differences["surface_up_w_m2"] < 1.0e-3:
        fail("V3 half-transition did not change reflected surface-up flux versus legacy full-VIS")
    if max(differences["visible_direct_max_w_m2"], differences["near_ir_direct_max_w_m2"]) < 1.0e-3:
        fail("V3 half-transition did not change VIS/NIR direct diagnostics versus legacy full-VIS")
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("columns_executable", type=Path)
    parser.add_argument("reference_executable", type=Path)
    parser.add_argument("--output", type=Path, help="optional JSON summary path")
    args = parser.parse_args()
    data_dir = args.data_directory.resolve()
    columns_exe = args.columns_executable.resolve()
    reference_exe = args.reference_executable.resolve()
    for path in (data_dir, columns_exe, reference_exe):
        if not path.exists():
            parser.error(f"required path does not exist: {path}")

    summary: dict[str, Any] = {"status": "FAIL", "phases": {}, "invalid_v3_rejections": []}
    with tempfile.TemporaryDirectory(prefix="rrtmgp-replay-formats-") as temporary:
        root = Path(temporary)
        capture = root / "capture"
        capture.mkdir()
        env = os.environ.copy()
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
        env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
        run = subprocess.run([str(columns_exe), str(data_dir)], cwd=root, env=env,
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if run.returncode != 0:
            fail(f"test_rrtmgp_columns failed ({run.returncode}): {run.stdout[-2000:]}")

        results: dict[str, dict[str, Path]] = {"V1": {}, "V2": {}, "V3": {}}
        inputs: dict[str, Path] = {}
        for phase in ("LW", "SW"):
            v3_input = capture / f"{phase.lower()}.input"
            v3_output = capture / f"{phase.lower()}.result"
            if not v3_input.is_file() or not v3_output.is_file():
                fail(f"column driver did not capture V5 {phase} input and result")
            parsed_phase, nc, nl, overlap, seed, iceflag, records = read_input(v3_input)
            if (parsed_phase, nc, nl) != (phase, 1, 3):
                fail(f"unexpected V5 {phase} header {(parsed_phase, nc, nl)}")
            if phase == "SW":
                policy = records.get("SW_BAND_PARTITION")
                if policy is None or policy.shape != (1, 1) or policy.item() != 1.0:
                    fail("captured SW must carry scalar SW_BAND_PARTITION=1")
            elif "SW_BAND_PARTITION" in records:
                fail("LW input must not carry SW_BAND_PARTITION")

            v3_reference = root / f"{phase.lower()}.v5.reference.result"
            ref_run = run_reference(reference_exe, data_dir, v3_input, v3_reference)
            if ref_run.returncode != 0:
                fail(f"reference rejected captured V5 {phase}: {ref_run.stdout[-1600:]}")
            report = assert_result_match(v3_output, v3_reference, f"captured V5 {phase}")
            summary["phases"][phase] = {"header": [phase, nc, nl, overlap, seed, iceflag],
                                         "v5_sections_compared": report["sections_compared"]}

            # Legacy V4 has no constants metadata. Its independent solver must
            # retain the same exact upstream defaults as no-argument adapter init.
            v4_input = root / f"{phase.lower()}.v4.default.input"
            v4_output = root / f"{phase.lower()}.v4.default.result"
            rewrite_default_v5_as_v4(v3_input, v4_input)
            v4_run = run_reference(reference_exe, data_dir, v4_input, v4_output)
            if v4_run.returncode != 0:
                fail(f"reference rejected default-constant V4 {phase}: {v4_run.stdout[-1600:]}")
            v4_report = assert_default_v4_match(v3_output, v4_output, phase)
            summary["phases"][phase]["default_v5_vs_v4_sections_compared"] = v4_report["sections_compared"]

            v2_input = root / f"{phase.lower()}.v2.input"
            v1_input = root / f"{phase.lower()}.v1.input"
            remove_v2 = {"SW_BAND_PARTITION"} if phase == "SW" else set()
            remove_v1 = {"ICE_ROUGHNESS"} | remove_v2
            rewrite_input(v3_input, v2_input, "RRTMGP_REPLAY_V2", remove=remove_v2)
            rewrite_input(v3_input, v1_input, "RRTMGP_REPLAY_V1", remove=remove_v1)
            for version, legacy_input in (("V2", v2_input), ("V1", v1_input)):
                legacy_output = root / f"{phase.lower()}.{version.lower()}.result"
                legacy_run = run_reference(reference_exe, data_dir, legacy_input, legacy_output)
                if legacy_run.returncode != 0:
                    fail(f"reference rejected legacy {version} {phase}: {legacy_run.stdout[-1600:]}")
                results[version][phase] = legacy_output
            results["V3"][phase] = v3_output
            inputs[phase] = v3_input

        for phase in ("LW", "SW"):
            legacy_comparison = compare(read_result(results["V1"][phase]), read_result(results["V2"][phase]))
            if not legacy_comparison.get("passed"):
                fail(f"legacy V1 and V2 {phase} results differ: {legacy_comparison.get('failed_sections')}")
        summary["legacy_v1_v2_results_match"] = True
        summary["sw_v3_vs_legacy"] = old_policy_differences(results["V3"]["SW"], results["V2"]["SW"])

        sw_input = inputs["SW"]
        for label, remove, replacement in (
            ("missing", {"SW_BAND_PARTITION"}, None),
            ("zero", set(), "0"),
            ("two", set(), "2"),
        ):
            invalid = root / f"sw.v3.invalid-{label}.input"
            replacements = {} if replacement is None else {"SW_BAND_PARTITION": replacement}
            rewrite_input(sw_input, invalid, "RRTMGP_REPLAY_V3", remove=remove, replacements=replacements)
            must_reject_python(invalid, label)
            must_reject_reference(reference_exe, data_dir, invalid,
                                  root / f"sw.invalid-{label}.result", label)
            summary["invalid_v3_rejections"].append(label)
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
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
