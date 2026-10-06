#!/usr/bin/env python3
"""Exercise V5 capture, V4 default replay, legacy V1/V2, and strict V3 SW contract."""
from __future__ import annotations

import argparse
import hashlib
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


def make_v7_from_legacy_capture(source: Path, destination: Path,
                                digest: str | None = None) -> str:
    """Build a schema-valid V7 input for reader/rejection checks (not optics)."""
    lines = source.read_text(encoding="ascii").splitlines()
    header = lines[1].split()
    nc, nl = int(header[1]), int(header[2])
    records: list[list[str]] = []
    pos = 2
    while pos < len(lines):
        fields = lines[pos].split()
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
            fail(f"{source}: truncated {name}")
        records.append(record)

    constants = {"GRAVITY", "CP_DRY", "MOL_WEIGHT_DRY"}
    common = [record for record in records if record[0].split()[0].upper() not in constants]
    host = [record for record in records if record[0].split()[0].upper() in constants]
    digest = digest or ("0123456789abcdef" * 4)

    def numeric_record(name: str, rows: int, cols: int, values: np.ndarray) -> list[str]:
        result = [f"{name} {rows} {cols}"]
        result.extend(f"{float(value):.16E}" for value in np.asarray(values).reshape(-1, order="F"))
        return result

    output = ["RRTMGP_REPLAY_V7", lines[1]]
    for record in common:
        output.extend(record)
    output.extend(numeric_record("GWP", nc, nl, np.ones((nc, nl))))
    output.extend(numeric_record("HWP", nc, nl, np.zeros((nc, nl))))
    output.extend(numeric_record("LAMBDA_G", nc, nl, np.full((nc, nl), 1.0e4)))
    output.extend(numeric_record("LAMBDA_H", nc, nl, np.full((nc, nl), 1.0e4)))
    output.extend(host[0])
    output.extend(host[1])
    output.extend(host[2])
    output.extend(numeric_record("FROZEN_MODE", 1, 1, np.array([[1.0]])))
    output.extend(numeric_record("FROZEN_OCCURRENCE", 1, 1, np.array([[1.0]])))
    output.extend(numeric_record("FROZEN_TABLE_SHA256_BYTES", 64, 1,
                                 np.array([ord(char) for char in digest])))
    destination.write_text("\n".join(output) + "\n", encoding="ascii")
    return digest


def make_v8_from_v5_capture(source: Path, destination: Path,
                            vmr_values: dict[str, np.ndarray] | None = None) -> None:
    """Add explicit LW trace-gas profiles immediately after the six base gases."""
    lines = source.read_text(encoding="ascii").splitlines()
    header = lines[1].split()
    nc, nl = int(header[1]), int(header[2])
    values = vmr_values or {
        "VMR_CFC11": np.full((nc, nl), 1.0e-10),
        "VMR_CFC12": np.full((nc, nl), 2.0e-10),
        "VMR_CFC22": np.full((nc, nl), 3.0e-10),
        "VMR_CCL4": np.full((nc, nl), 4.0e-10),
    }
    records: list[list[str]] = []
    pos = 2
    inserted = False
    while pos < len(lines):
        fields = lines[pos].split()
        if len(fields) != 3:
            fail(f"{source}:{pos+1}: invalid record header")
        name = fields[0].upper()
        count = int(fields[1]) * int(fields[2])
        record = [lines[pos]]
        pos += 1
        nvalues = 0
        while nvalues < count and pos < len(lines):
            record.append(lines[pos])
            nvalues += len(lines[pos].split())
            pos += 1
        if nvalues != count:
            fail(f"{source}: truncated {name}")
        records.append(record)
        if name == "O2":
            for gas_name in ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"):
                array = np.asarray(values[gas_name], dtype=np.float64)
                if array.shape != (nc, nl):
                    fail(f"{gas_name}: fixture shape {array.shape} != {(nc, nl)}")
                section = [f"{gas_name} {nc} {nl}"]
                section.extend(f"{float(x):.16E}" for x in array.reshape(-1, order="F"))
                records.append(section)
            inserted = True
    if not inserted:
        fail(f"{source}: O2 section not found")
    output = ["RRTMGP_REPLAY_V8", lines[1]]
    for record in records:
        output.extend(record)
    destination.write_text("\n".join(output) + "\n", encoding="ascii")


def replace_record_value(path: Path, name: str, value: str) -> None:
    lines = path.read_text(encoding="ascii").splitlines()
    for pos, line in enumerate(lines[:-1]):
        if line.split() and line.split()[0].upper() == name:
            lines[pos + 1] = value
            path.write_text("\n".join(lines) + "\n", encoding="ascii")
            return
    fail(f"{path}: record {name} not found")


def run_reference(executable: Path, data_dir: Path, input_path: Path,
                  output_path: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(executable), str(data_dir), str(input_path), str(output_path)],
                          env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


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


def must_reject_v7_reference(executable: Path, data_dir: Path, path: Path,
                             output_path: Path, expected: str, env: dict[str, str]) -> None:
    run = run_reference(executable, data_dir, path, output_path, env=env)
    if run.returncode == 0 or expected not in run.stdout:
        fail(f"reference_column V7 rejection expected {expected!r}, got rc={run.returncode}: {run.stdout[-1200:]}")


def must_reject_v8_reference(executable: Path, data_dir: Path, path: Path,
                             output_path: Path, expected: str,
                             env: dict[str, str] | None = None) -> None:
    run = run_reference(executable, data_dir, path, output_path, env=env)
    if run.returncode == 0 or expected not in run.stdout:
        fail(f"reference_column V8 rejection expected {expected!r}, got rc={run.returncode}: {run.stdout[-1200:]}")


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

    summary: dict[str, Any] = {"status": "FAIL", "phases": {}, "invalid_v3_rejections": [],
                               "invalid_v7_rejections": []}
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
                fail(f"column driver did not capture {phase} input and result")
            parsed_phase, nc, nl, overlap, seed, iceflag, records = read_input(v3_input)
            if (parsed_phase, nc, nl) != (phase, 1, 3):
                fail(f"unexpected replay {phase} header {(parsed_phase, nc, nl)}")
            if phase == "LW":
                if v3_input.read_text(encoding="ascii").splitlines()[0].strip() != "RRTMGP_REPLAY_V12":
                    fail("current LW adapter capture must use N2-explicit V12")
                if "VMR_N2" not in records or not np.all(records["VMR_N2"] == 0.7808):
                    fail("current LW adapter capture lost the fixed dry-background N2 profile")
                invalid_old_n2 = root / "lw.v10.with-new-n2-fields.input"
                rewrite_input(v3_input, invalid_old_n2, "RRTMGP_REPLAY_V10")
                must_reject_python(invalid_old_n2, "N2 fields under legacy V10 magic")
            if phase == "SW":
                policy = records.get("SW_BAND_PARTITION")
                if policy is None or policy.shape != (1, 1) or policy.item() != 1.0:
                    fail("captured SW must carry scalar SW_BAND_PARTITION=1")
            elif "SW_BAND_PARTITION" in records:
                fail("LW input must not carry SW_BAND_PARTITION")

            v3_reference = root / f"{phase.lower()}.current.reference.result"
            ref_run = run_reference(reference_exe, data_dir, v3_input, v3_reference)
            if ref_run.returncode != 0:
                fail(f"reference rejected captured {phase}: {ref_run.stdout[-1600:]}")
            report = assert_result_match(v3_output, v3_reference, f"captured current {phase}")
            summary["phases"][phase] = {"header": [phase, nc, nl, overlap, seed, iceflag],
                                         "current_sections_compared": report["sections_compared"]}

            # Legacy formats intentionally retain the historical ten-gas LW
            # closure. Strip the explicitly new background N2 metadata before
            # constructing those compatibility inputs; never relabel N2 data
            # as an old V1-V11 stream.
            legacy_v5 = v3_input
            if phase == "LW":
                legacy_v5 = root / "lw.v5.legacy-ten-gas.input"
                rewrite_input(v3_input, legacy_v5, "RRTMGP_REPLAY_V5",
                              remove={"VMR_N2", "TRACE_GASES_PRESENT"})
            legacy_v5_output = root / f"{phase.lower()}.v5.legacy-ten-gas.result"
            legacy_v5_run = run_reference(reference_exe, data_dir, legacy_v5, legacy_v5_output)
            if legacy_v5_run.returncode != 0:
                fail(f"reference rejected legacy ten-gas V5 {phase}: {legacy_v5_run.stdout[-1600:]}")
            summary["phases"][phase]["legacy_ten_gas_v5_sections"] = \
                len(read_result(legacy_v5_output)["sections"])

            # Legacy V4 has no constants metadata. Its independent solver must
            # retain the same exact upstream defaults as no-argument adapter init.
            v4_input = root / f"{phase.lower()}.v4.default.input"
            v4_output = root / f"{phase.lower()}.v4.default.result"
            rewrite_default_v5_as_v4(legacy_v5, v4_input)
            v4_run = run_reference(reference_exe, data_dir, v4_input, v4_output)
            if v4_run.returncode != 0:
                fail(f"reference rejected default-constant V4 {phase}: {v4_run.stdout[-1600:]}")
            legacy_current = legacy_v5_output if phase == "LW" else v3_output
            v4_report = assert_default_v4_match(legacy_current, v4_output, phase)
            summary["phases"][phase]["default_v5_vs_v4_sections_compared"] = v4_report["sections_compared"]

            v2_input = root / f"{phase.lower()}.v2.input"
            v1_input = root / f"{phase.lower()}.v1.input"
            remove_v2 = {"SW_BAND_PARTITION"} if phase == "SW" else set()
            remove_v1 = {"ICE_ROUGHNESS"} | remove_v2
            rewrite_input(legacy_v5, v2_input, "RRTMGP_REPLAY_V2", remove=remove_v2)
            rewrite_input(legacy_v5, v1_input, "RRTMGP_REPLAY_V1", remove=remove_v1)
            for version, legacy_input in (("V2", v2_input), ("V1", v1_input)):
                legacy_output = root / f"{phase.lower()}.{version.lower()}.result"
                legacy_run = run_reference(reference_exe, data_dir, legacy_input, legacy_output)
                if legacy_run.returncode != 0:
                    fail(f"reference rejected legacy {version} {phase}: {legacy_run.stdout[-1600:]}")
                results[version][phase] = legacy_output
            results["V3"][phase] = legacy_current
            inputs[phase] = legacy_v5

        # V7 is a required new semantics boundary. Validate the complete
        # record set, then prove malformed V7 inputs reject before environment
        # lookup instead of falling through to legacy replay behavior.
        v7_input = root / "lw.v7.input"
        v7_digest = make_v7_from_legacy_capture(inputs["LW"], v7_input)
        parsed = read_input(v7_input)
        if parsed[-1]["FROZEN_MODE"].item() != 1.0 or len(v7_digest) != 64:
            fail("Python V7 parser did not retain frozen metadata")
        no_frozen_env = os.environ.copy()
        no_frozen_env.pop("WRF_RRTMGP_FROZEN_TABLE", None)
        valid_no_env = run_reference(reference_exe, data_dir, v7_input,
                                     root / "lw.v7.no-table.result", env=no_frozen_env)
        if valid_no_env.returncode == 0 or "WRF_RRTMGP_FROZEN_TABLE" not in valid_no_env.stdout:
            fail(f"V7 did not require its table path: {valid_no_env.stdout[-1200:]}")
        summary["invalid_v7_rejections"].append("missing_table_path")

        invalid_mode = root / "lw.v7.invalid-mode.input"
        rewrite_input(v7_input, invalid_mode, "RRTMGP_REPLAY_V7",
                      replacements={"FROZEN_MODE": "0.0000000000000000E+000"})
        must_reject_python(invalid_mode, "V7 frozen mode zero")
        must_reject_v7_reference(reference_exe, data_dir, invalid_mode,
                                 root / "lw.v7.invalid-mode.result", "FROZEN_MODE must equal one", no_frozen_env)
        summary["invalid_v7_rejections"].append("frozen_mode_zero")

        missing_gwp = root / "lw.v7.missing-gwp.input"
        rewrite_input(v7_input, missing_gwp, "RRTMGP_REPLAY_V7", remove={"GWP"})
        must_reject_python(missing_gwp, "V7 missing GWP")
        must_reject_v7_reference(reference_exe, data_dir, missing_gwp,
                                 root / "lw.v7.missing-gwp.result", "section name or shape mismatch", no_frozen_env)
        summary["invalid_v7_rejections"].append("missing_gwp")

        invalid_hash = root / "lw.v7.invalid-hash-byte.input"
        rewrite_input(v7_input, invalid_hash, "RRTMGP_REPLAY_V7")
        replace_record_value(invalid_hash, "FROZEN_TABLE_SHA256_BYTES", "4.8500000000000000E+001")
        must_reject_python(invalid_hash, "V7 noninteger hash byte")
        must_reject_v7_reference(reference_exe, data_dir, invalid_hash,
                                 root / "lw.v7.invalid-hash-byte.result", "integer ASCII", no_frozen_env)
        summary["invalid_v7_rejections"].append("noninteger_hash_byte")

        nonfinite_hash = root / "lw.v7.nonfinite-hash-byte.input"
        rewrite_input(v7_input, nonfinite_hash, "RRTMGP_REPLAY_V7")
        replace_record_value(nonfinite_hash, "FROZEN_TABLE_SHA256_BYTES", "NaN")
        must_reject_python(nonfinite_hash, "V7 nonfinite hash byte")
        must_reject_v7_reference(reference_exe, data_dir, nonfinite_hash,
                                 root / "lw.v7.nonfinite-hash-byte.result", "SHA bytes must be finite", no_frozen_env)
        summary["invalid_v7_rejections"].append("nonfinite_hash_byte")

        # V8 carries the four per-layer LW minor-gas profiles explicitly.
        v8_input = root / "lw.v8.input"
        zero_cfc = {name: np.zeros((1, 3), dtype=np.float64) for name in
                    ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4")}
        make_v8_from_v5_capture(inputs["LW"], v8_input, zero_cfc)
        v8_parsed = read_input(v8_input)
        for gas_name in ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"):
            if v8_parsed[-1][gas_name].shape != (1, 3):
                fail(f"V8 parser lost {gas_name}")

        v8_zero_output = root / "lw.v8.zero.result"
        v8_zero_run = run_reference(reference_exe, data_dir, v8_input, v8_zero_output)
        if v8_zero_run.returncode != 0:
            fail(f"reference rejected valid zero-CFC V8: {v8_zero_run.stdout[-1600:]}")
        v8_zero_comparison = compare(read_result(v8_zero_output), read_result(root / "lw.v5.legacy-ten-gas.result"))
        if not v8_zero_comparison.get("passed"):
            fail(f"V8 zero-CFC versus V5 common LW sections differ: {v8_zero_comparison.get('failed_sections')}")
        v8_zero_sections = read_result(v8_zero_output)["sections"]
        if not np.array_equal(v8_zero_sections["GAS_TAU_RAW"], v8_zero_sections["GAS_TAU"]):
            fail("V8 GAS_TAU_RAW must equal GAS_TAU for zero-CFC replay")

        v8_frozen = root / "lw.v8.frozen.input"
        repo_root = Path(__file__).resolve().parents[3]
        frozen_table = repo_root / "validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc"
        if not frozen_table.is_file():
            fail(f"V8 frozen replay fixture missing frozen LUT {frozen_table}")
        frozen_digest = hashlib.sha256(frozen_table.read_bytes()).hexdigest()
        real_v7 = root / "lw.v7.real-table.input"
        make_v7_from_legacy_capture(inputs["LW"], real_v7, frozen_digest)
        make_v8_from_v5_capture(real_v7, v8_frozen, zero_cfc)
        v8_frozen_records = read_input(v8_frozen)[-1]
        if v8_frozen_records["FROZEN_MODE"].item() != 1.0:
            fail("V8 parser did not retain optional frozen-optics group")
        recorded_digest = "".join(chr(int(x)) for x in v8_frozen_records["FROZEN_TABLE_SHA256_BYTES"][:, 0])
        if recorded_digest != frozen_digest:
            fail("V8 frozen replay fixture does not use the actual frozen-table SHA256")
        table_env = os.environ.copy()
        table_env["WRF_RRTMGP_FROZEN_TABLE"] = str(frozen_table)
        v7_frozen_output = root / "lw.v7.real-table.result"
        v7_frozen_run = run_reference(reference_exe, data_dir, real_v7, v7_frozen_output, env=table_env)
        if v7_frozen_run.returncode != 0:
            fail(f"reference rejected valid V7 frozen fixture: {v7_frozen_run.stdout[-1600:]}")
        v8_frozen_output = root / "lw.v8.frozen.result"
        v8_frozen_run = run_reference(reference_exe, data_dir, v8_frozen, v8_frozen_output, env=table_env)
        if v8_frozen_run.returncode != 0:
            fail(f"reference rejected valid V8 frozen fixture: {v8_frozen_run.stdout[-1600:]}")
        frozen_pair = compare(read_result(v8_frozen_output), read_result(v7_frozen_output))
        if not frozen_pair.get("passed"):
            fail(f"V8 zero-CFC frozen replay differs from same-input V7: {frozen_pair.get('failed_sections')}")
        v8_frozen_sections = read_result(v8_frozen_output)["sections"]
        if not np.array_equal(v8_frozen_sections["GAS_TAU_RAW"], v8_frozen_sections["GAS_TAU"]):
            fail("V8 frozen GAS_TAU_RAW must equal GAS_TAU")

        invalid_v8_negative = root / "lw.v8.negative.input"
        rewrite_input(v8_input, invalid_v8_negative, "RRTMGP_REPLAY_V8")
        replace_record_value(invalid_v8_negative, "VMR_CFC22", "-1.0E-20")
        must_reject_python(invalid_v8_negative, "negative V8 CFC22")
        must_reject_v8_reference(reference_exe, data_dir, invalid_v8_negative,
                                 root / "lw.v8.negative.result", "VMR_CFC22 must be finite/nonnegative")

        invalid_v8_nan = root / "lw.v8.nan.input"
        rewrite_input(v8_input, invalid_v8_nan, "RRTMGP_REPLAY_V8")
        replace_record_value(invalid_v8_nan, "VMR_CFC11", "NaN")
        must_reject_python(invalid_v8_nan, "nonfinite V8 CFC11")
        must_reject_v8_reference(reference_exe, data_dir, invalid_v8_nan,
                                 root / "lw.v8.nan.result", "VMR_CFC11 must be finite/nonnegative")

        invalid_v8_missing = root / "lw.v8.missing-ccl4.input"
        rewrite_input(v8_input, invalid_v8_missing, "RRTMGP_REPLAY_V8", remove={"VMR_CCL4"})
        must_reject_python(invalid_v8_missing, "missing V8 CCL4")
        must_reject_v8_reference(reference_exe, data_dir, invalid_v8_missing,
                                 root / "lw.v8.missing-ccl4.result", "replay section name or shape mismatch")

        invalid_v8_shape = root / "lw.v8.bad-shape.input"
        rewrite_input(v8_input, invalid_v8_shape, "RRTMGP_REPLAY_V8")
        shape_lines = invalid_v8_shape.read_text(encoding="ascii").splitlines()
        for line_index, line in enumerate(shape_lines):
            if line.split() and line.split()[0].upper() == "VMR_CFC12":
                shape_lines[line_index] = f"VMR_CFC12 2 {int(line.split()[2])}"
                break
        else:
            fail("V8 CFC12 header not found for shape mutation")
        invalid_v8_shape.write_text("\n".join(shape_lines) + "\n", encoding="ascii")
        must_reject_python(invalid_v8_shape, "wrong-shaped V8 CFC12")
        must_reject_v8_reference(reference_exe, data_dir, invalid_v8_shape,
                                 root / "lw.v8.bad-shape.result", "replay section name or shape mismatch")

        invalid_v8_old_magic = root / "lw.v7.with-v8-gases.input"
        rewrite_input(v8_input, invalid_v8_old_magic, "RRTMGP_REPLAY_V7")
        must_reject_python(invalid_v8_old_magic, "V8 gas records under V7 magic")
        must_reject_v8_reference(reference_exe, data_dir, invalid_v8_old_magic,
                                 root / "lw.v8.old-magic.result", "replay section name or shape mismatch")

        invalid_v8_partial_frozen = root / "lw.v8.partial-frozen.input"
        rewrite_input(v8_frozen, invalid_v8_partial_frozen, "RRTMGP_REPLAY_V8",
                      remove={"FROZEN_TABLE_SHA256_BYTES"})
        must_reject_python(invalid_v8_partial_frozen, "partial V8 frozen metadata")
        must_reject_v8_reference(reference_exe, data_dir, invalid_v8_partial_frozen,
                                 root / "lw.v8.partial-frozen.result", "failed to read replay section header")
        summary["v8_parser_contract"] = {
            "valid_four_gases": True,
            "valid_zero_gases_executable_replay": True,
            "valid_frozen_executable_replay": True,
            "valid_frozen_combination": True,
            "rejections": ["negative", "nonfinite", "missing", "wrong_shape", "v7_magic", "partial_frozen"],
        }

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
