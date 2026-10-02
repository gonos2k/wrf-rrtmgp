#!/usr/bin/env python3
"""Test native dry-mass gas columns in the real adapter and replay formats.

Standalone mode runs the Fortran solver fixture, validates its V6 captures,
replays them through the independent reference executable, and probes invalid
native-mass inputs. Capture mode accepts current V6/V7/V8 production captures
and validates them with the same independent mass and pressure-derived-
extension formulas. V8 must contain all four LW trace-gas profiles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


AVOGADRO = 6.02214076e23
M_H2O_KG_MOL = 0.018016
SHAPE_ERROR = "RRTMGP_INPUT_NATIVE_DRY_MASS_SHAPE"
VALUE_ERROR = "RRTMGP_INPUT_NATIVE_DRY_MASS_NOT_POSITIVE_FINITE"
REFERENCE_VALUE_ERROR = "V6 native dry layer mass must be finite and positive"
SUPPORTED_INPUT_MAGICS = {"RRTMGP_REPLAY_V6", "RRTMGP_REPLAY_V7", "RRTMGP_REPLAY_V8"}
PHASES = ("LW", "SW")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_trace(path: Path, magic_expected: str, section_dimensions: int) -> tuple[list[str], dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2:
        raise ValueError(f"{path}: incomplete trace")
    magic = lines[0].strip()
    if magic != magic_expected:
        raise ValueError(f"{path}: expected {magic_expected}, got {magic}")
    header = lines[1].split()
    if len(header) != 3:
        raise ValueError(f"{path}: malformed result header {header}")
    sections: dict[str, np.ndarray] = {}
    cursor = 2
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        record_header = lines[cursor].split()
        cursor += 1
        if len(record_header) != section_dimensions:
            raise ValueError(f"{path}: malformed section header {record_header}")
        name = record_header[0].upper()
        shape = tuple(int(x) for x in record_header[1:])
        if name in sections or any(x < 1 for x in shape):
            raise ValueError(f"{path}: duplicate/empty section {name}")
        count = math.prod(shape)
        values: list[float] = []
        while len(values) < count and cursor < len(lines):
            try:
                values.extend(float(token.replace("D", "E").replace("d", "e"))
                              for token in lines[cursor].split())
            except ValueError as exc:
                raise ValueError(f"{path}: invalid value in {name}") from exc
            cursor += 1
            if len(values) > count:
                raise ValueError(f"{path}: too many values in {name}")
        if len(values) != count:
            raise ValueError(f"{path}: truncated {name}")
        arr = np.asarray(values, dtype=np.float64).reshape(shape, order="F")
        if not np.isfinite(arr).all():
            raise ValueError(f"{path}: non-finite values in {name}")
        sections[name] = arr
    return header, sections


def read_input(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0].strip() not in SUPPORTED_INPUT_MAGICS:
        raise ValueError(f"{path}: expected one of {', '.join(sorted(SUPPORTED_INPUT_MAGICS))}")
    h = lines[1].split()
    if len(h) != 6:
        raise ValueError(f"{path}: malformed replay header")
    phase, nc, nl, overlap, seed, iceflag = h[0], *(int(x) for x in h[1:])
    # Use the shared strict replay parser so V8 cannot silently pass with a
    # missing/invalid CFC profile and V7/V8 frozen metadata keeps its contract.
    from test_column_replay import read_input as read_strict_replay_input
    try:
        strict_phase, strict_nc, strict_nl, strict_overlap, strict_seed, strict_iceflag, sections = \
            read_strict_replay_input(path)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    if (phase.upper(), nc, nl, overlap, seed, iceflag) != \
       (strict_phase, strict_nc, strict_nl, strict_overlap, strict_seed, strict_iceflag):
        raise ValueError(f"{path}: replay header changed during strict validation")
    native = sections.get("NATIVE_DRY_LAYER_MASS_KG_M2")
    if native is None or native.shape[0] != nc or not 1 <= native.shape[1] <= nl:
        raise ValueError(f"{path}: invalid native dry-mass shape")
    if not np.isfinite(native).all() or np.any(native <= 0):
        raise ValueError(f"{path}: native dry mass must be finite and positive")
    for key in ("PLEV", "H2O", "GRAVITY", "CP_DRY", "MOL_WEIGHT_DRY"):
        if key not in sections:
            raise ValueError(f"{path}: missing {key}")
    if sections["PLEV"].shape != (nc, nl + 1) or sections["H2O"].shape != (nc, nl):
        raise ValueError(f"{path}: pressure/vapor dimensions do not match header")
    if any(sections[key].shape != (1, 1) for key in ("GRAVITY", "CP_DRY", "MOL_WEIGHT_DRY")):
        raise ValueError(f"{path}: constants metadata must be scalar")
    return {"phase": strict_phase, "nc": nc, "nl": nl, "overlap": overlap,
            "seed": seed, "iceflag": iceflag, "magic": lines[0].strip()}, sections


def reject_missing_v8_cfc(path: Path) -> bool:
    """Prove the strict parser rejects a V8 capture missing one required gas."""
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines or lines[0].strip() != "RRTMGP_REPLAY_V8":
        return False
    output: list[str] = []
    cursor = 0
    removed = False
    while cursor < len(lines):
        fields = lines[cursor].split()
        if len(fields) == 3 and fields[0].upper() == "VMR_CCL4":
            count = int(fields[1]) * int(fields[2])
            cursor += 1
            consumed = 0
            while cursor < len(lines) and consumed < count:
                consumed += len(lines[cursor].split())
                cursor += 1
            if consumed != count:
                raise ValueError(f"{path}: malformed VMR_CCL4 fixture while testing rejection")
            removed = True
            continue
        output.append(lines[cursor])
        cursor += 1
    if not removed:
        raise ValueError(f"{path}: V8 capture lacks VMR_CCL4 to exercise missing-gas rejection")
    with tempfile.TemporaryDirectory(prefix="native-gas-v8-missing-") as scratch:
        corrupted = Path(scratch) / "missing-ccl4.input"
        corrupted.write_text("\n".join(output) + "\n", encoding="ascii")
        try:
            read_input(corrupted)
        except ValueError as exc:
            if "V8 missing required LW gas records" not in str(exc):
                raise
            return True
        raise RuntimeError("strict parser accepted V8 replay missing VMR_CCL4")


def parse_trace_records(lines: list[str], path: Path) -> tuple[None, dict[str, np.ndarray]]:
    sections: dict[str, np.ndarray] = {}
    cursor = 0
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        line_no = cursor + 3
        fields = lines[cursor].split()
        cursor += 1
        if len(fields) != 3:
            raise ValueError(f"{path}:{line_no}: expected NAME rows columns")
        name = fields[0].upper()
        rows, cols = int(fields[1]), int(fields[2])
        if name in sections or rows < 1 or cols < 1:
            raise ValueError(f"{path}:{line_no}: duplicate or invalid section {name}")
        count = rows * cols
        values: list[float] = []
        while len(values) < count and cursor < len(lines):
            try:
                values.extend(float(token.replace("D", "E").replace("d", "e"))
                              for token in lines[cursor].split())
            except ValueError as exc:
                raise ValueError(f"{path}:{cursor+2}: invalid {name} value") from exc
            cursor += 1
            if len(values) > count:
                raise ValueError(f"{path}: too many values in {name}")
        if len(values) != count:
            raise ValueError(f"{path}: truncated {name}")
        sections[name] = np.asarray(values, dtype=np.float64).reshape((rows, cols), order="F")
    return None, sections


def read_result(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RESULT_V1":
        raise ValueError(f"{path}: expected RRTMGP_RESULT_V1")
    h = lines[1].split()
    if len(h) != 3:
        raise ValueError(f"{path}: malformed result header")
    phase, nc, nl = h[0].upper(), int(h[1]), int(h[2])
    _, sections = parse_trace(path, "RRTMGP_RESULT_V1", 4)
    if "GAS_COL_DRY" not in sections:
        raise ValueError(f"{path}: missing GAS_COL_DRY diagnostic")
    return {"phase": phase, "nc": nc, "nl": nl}, sections


def read_raw(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RAW_V1":
        raise ValueError(f"{path}: expected RRTMGP_RAW_V1")
    h = lines[1].split()
    if len(h) != 4:
        raise ValueError(f"{path}: malformed raw header")
    phase, i, j, nl = h[0].upper(), *(int(x) for x in h[1:])
    _, sections = parse_raw_records(lines[2:], path)
    return {"phase": phase, "i": i, "j": j, "nl": nl}, sections


def parse_raw_records(lines: list[str], path: Path) -> tuple[None, dict[str, np.ndarray]]:
    sections: dict[str, np.ndarray] = {}
    cursor = 0
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        fields = lines[cursor].split()
        line_no = cursor + 3
        cursor += 1
        if len(fields) != 2:
            raise ValueError(f"{path}:{line_no}: expected NAME count")
        name, count = fields[0].upper(), int(fields[1])
        if name in sections or count < 1:
            raise ValueError(f"{path}:{line_no}: duplicate/invalid raw field {name}")
        values: list[float] = []
        while len(values) < count and cursor < len(lines):
            values.extend(float(token.replace("D", "E").replace("d", "e"))
                          for token in lines[cursor].split())
            cursor += 1
            if len(values) > count:
                raise ValueError(f"{path}: too many raw values in {name}")
        if len(values) != count:
            raise ValueError(f"{path}: truncated raw field {name}")
        arr = np.asarray(values, dtype=np.float64)
        if not np.isfinite(arr).all():
            raise ValueError(f"{path}: non-finite raw field {name}")
        sections[name] = arr
    return None, sections


def expected_columns(input_records: dict[str, np.ndarray], nc: int, nl: int) -> tuple[np.ndarray, int]:
    mass = input_records["NATIVE_DRY_LAYER_MASS_KG_M2"]
    n_native = mass.shape[1]
    mol_weight = float(input_records["MOL_WEIGHT_DRY"].item())
    gravity = float(input_records["GRAVITY"].item())
    plev_pa = input_records["PLEV"] * 100.0
    h2o = input_records["H2O"]
    expected = np.empty((nc, nl), dtype=np.float64)
    expected[:, :n_native] = mass * AVOGADRO / (mol_weight * 10000.0)
    delta = np.abs(np.diff(plev_pa, axis=1))
    fact = 1.0 / (1.0 + h2o)
    moist_molar_mass = (mol_weight + M_H2O_KG_MOL * h2o) * fact
    expected[:, n_native:] = (10.0 * delta[:, n_native:] * AVOGADRO * fact[:, n_native:] /
                              (1000.0 * moist_molar_mass[:, n_native:] * 100.0 * gravity))
    return expected, n_native


def validate_pair(capture: Path, phase: str, *, require_raw: bool) -> dict[str, Any]:
    inp_path, result_path = capture / f"{phase.lower()}.input", capture / f"{phase.lower()}.result"
    meta, inputs = read_input(inp_path)
    missing_v8_cfc_rejected = reject_missing_v8_cfc(inp_path) if meta["magic"] == "RRTMGP_REPLAY_V8" else None
    result_meta, result = read_result(result_path)
    if (meta["phase"], meta["nc"], meta["nl"]) != (phase, result_meta["nc"], result_meta["nl"]):
        raise ValueError(f"{capture}: {phase} input/result headers differ")
    if result_meta["phase"] != phase:
        raise ValueError(f"{result_path}: result phase {result_meta['phase']} does not match {phase}")
    gas_col_raw = result["GAS_COL_DRY"]
    if gas_col_raw.shape != (meta["nc"], meta["nl"], 1):
        raise ValueError(f"{result_path}: unexpected GAS_COL_DRY shape {gas_col_raw.shape}")
    gas_col = gas_col_raw[:, :, 0]
    expected, n_native = expected_columns(inputs, meta["nc"], meta["nl"])
    np.testing.assert_allclose(gas_col, expected, rtol=3.0e-14, atol=0.0,
                               err_msg=f"{phase} gas dry-column mass formula")
    native_exact = None
    raw_path = capture / f"{phase.lower()}.raw"
    if raw_path.exists():
        raw_meta, raw = read_raw(raw_path)
        if raw_meta["phase"] != phase:
            raise ValueError(f"{raw_path}: phase mismatch")
        raw_mass = raw.get("DRY_LAYER_MASS_KG_M2")
        if raw_mass is None or raw_mass.shape != (raw_meta["nl"],):
            raise ValueError(f"{raw_path}: missing native dry layer mass")
        if meta["nc"] != 1 or n_native != raw_meta["nl"]:
            raise ValueError(f"{capture}: captured raw/input native extents disagree")
        native_exact = np.array_equal(inputs["NATIVE_DRY_LAYER_MASS_KG_M2"][0], raw_mass)
        if not native_exact:
            raise ValueError(f"{capture}: trace native mass differs from raw WRF mass")
        if not require_raw:
            raise ValueError(f"{capture}: raw fields unexpectedly present for standalone fixture")
    elif require_raw:
        raise ValueError(f"{capture}: missing actual SCM raw trace {raw_path.name}")
    return {"phase": phase, "nc": meta["nc"], "nl": meta["nl"], "native_layers": n_native,
            "magic": meta["magic"], "missing_v8_cfc_rejected": missing_v8_cfc_rejected,
            "native_mass_exact_raw_match": native_exact,
            "gas_col_dry_max_abs_error": float(np.max(np.abs(gas_col - expected))),
            "gas_col_dry_relative_max_error": float(np.max(np.abs(gas_col - expected) /
                                                              np.maximum(np.abs(expected), 1.0))),
            "native_mass_sha256": hashlib.sha256(inputs["NATIVE_DRY_LAYER_MASS_KG_M2"].tobytes(order="F")).hexdigest(),
            "input_sha256": digest(inp_path), "result_sha256": digest(result_path)}


def expect_failure(command: list[str], substring: str, label: str,
                   env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, check=False, env=env)
    if proc.returncode == 0 or substring not in proc.stdout:
        raise RuntimeError(f"{label}: expected nonzero status and {substring!r}; got {proc.returncode}:\n{proc.stdout}")
    return {"case": label, "returncode": proc.returncode, "diagnostic": substring}


def mutate_native_section(source: Path, output: Path, mutation: str) -> None:
    lines = source.read_text(encoding="ascii").splitlines()
    start = next((i for i, line in enumerate(lines) if line.split() and
                  line.split()[0].upper() == "NATIVE_DRY_LAYER_MASS_KG_M2"), None)
    if start is None:
        raise ValueError(f"{source}: native mass section missing")
    header = lines[start].split()
    nrow, ncol = int(header[1]), int(header[2])
    count = nrow * ncol
    end = start + 1
    while end < len(lines) and end <= start + 1 + count and sum(len(x.split()) for x in lines[start + 1:end]) < count:
        end += 1
    value_lines = lines[start + 1:end]
    values = [token for row in value_lines for token in row.split()]
    if len(values) != count:
        raise ValueError(f"{source}: invalid native mass fixture section")
    if mutation == "zero":
        values[0] = "0.0"
    elif mutation == "negative":
        values[0] = "-1.0"
    elif mutation == "nan":
        values[0] = "NaN"
    elif mutation == "inf":
        values[0] = "Infinity"
    elif mutation == "empty":
        header[2] = "0"
        values = []
    elif mutation == "too_wide":
        header[2] = str(int(lines[1].split()[2]) + 1)
        values.append("1.0")
    elif mutation == "row_shape":
        header[1] = str(int(header[1]) + 1)
        values.append("1.0")
    else:
        raise ValueError(f"unknown reference-input mutation {mutation}")
    replacement = [" ".join(header)]
    if values:
        replacement.extend(" ".join(values[i:i + 4]) for i in range(0, len(values), 4))
    lines[start:end] = replacement
    output.write_text("\n".join(lines) + "\n", encoding="ascii")


def mutate_gas_result_shape(source: Path, output: Path) -> None:
    lines = source.read_text(encoding="ascii").splitlines()
    record = next((i for i, line in enumerate(lines) if line.split() and
                   line.split()[0].upper() == "GAS_COL_DRY"), None)
    if record is None:
        raise ValueError(f"{source}: GAS_COL_DRY record missing")
    fields = lines[record].split()
    if len(fields) != 4 or int(fields[1]) < 2:
        raise ValueError(f"{source}: fixture cannot test alternate GAS_COL_DRY shape")
    fields[1], fields[3] = "1", str(int(fields[1]) * int(fields[3]))
    lines[record] = " ".join(fields)
    output.write_text("\n".join(lines) + "\n", encoding="ascii")


def run_standalone(args: argparse.Namespace) -> dict[str, Any]:
    executable, reference, data_dir = args.executable.resolve(), args.reference.resolve(), args.data_dir.resolve()
    scratch_parent = args.output_dir.resolve()
    if not executable.is_file() or not reference.is_file() or not data_dir.is_dir():
        raise RuntimeError("standalone executable, reference executable, or coefficient directory missing")
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native-gas-columns-", dir=scratch_parent) as scratch:
        return _run_standalone_in_directory(args, executable, reference, data_dir, Path(scratch))


def _run_standalone_in_directory(args: argparse.Namespace, executable: Path, reference: Path,
                                 data_dir: Path, out: Path) -> dict[str, Any]:
    capture = out / "capture"
    capture.mkdir()
    env = os.environ.copy()
    for key in ("WRF_RRTMGP_CAPTURE_DIR", "WRF_RRTMGP_CAPTURE_CALL", "WRF_RRTMGP_CAPTURE_ALL",
                "WRF_RRTMGP_AUDIT_DIR", "WRF_RRTMGP_HYDRO_DIAG_DIR"):
        env.pop(key, None)
    env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
    env["WRF_RRTMGP_CAPTURE_ALL"] = "1"
    exe_sha = digest(executable)
    run = subprocess.run([str(executable), str(data_dir), "positive"], cwd=out, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if run.returncode != 0 or "NATIVE_GAS_COLUMNS_FIXTURE_PASS" not in run.stdout:
        raise RuntimeError(f"positive Fortran solver fixture failed ({run.returncode}):\n{run.stdout}")
    if digest(executable) != exe_sha:
        raise RuntimeError("adapter test executable changed during run")

    phase_results = []
    replay_results = []
    for phase in PHASES:
        pairs = []
        for call in (1, 2):
            cap = capture / f"{phase}_{call:06d}"
            cap.mkdir()
            for extension in ("input", "result"):
                shutil.copy2(capture / f"{phase.lower()}_{call:06d}.{extension}",
                             cap / f"{phase.lower()}.{extension}")
            validated = validate_pair(cap, phase, require_raw=False)
            pairs.append((cap, validated))
            phase_results.append({"call": call, **validated})
            ref_out = out / f"{phase.lower()}_{call:06d}.reference.result"
            proc = subprocess.run([str(reference), str(data_dir), str(cap / f"{phase.lower()}.input"),
                                  str(ref_out)], cwd=out, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, check=False)
            if proc.returncode != 0:
                raise RuntimeError(f"V6 reference replay failed for {phase} call {call}:\n{proc.stdout}")
            from compare_column_replay import compare as compare_replay, read_result as read_compare_result
            adapter_result = read_compare_result(cap / f"{phase.lower()}.result")
            reference_result = read_compare_result(ref_out)
            comparison = compare_replay(adapter_result, reference_result)
            if not comparison["passed"]:
                raise RuntimeError(f"adapter/reference sections differ for {phase} call {call}: {comparison}")
            replay_results.append({"phase": phase, "call": call, "passed": True,
                                  "sections_compared": comparison["sections_compared"],
                                  "gas_col_dry_max_abs": comparison["max_differences"]["GAS_COL_DRY"]["max_abs"]})
        inputs1 = read_input(pairs[0][0] / f"{phase.lower()}.input")[1]
        inputs2 = read_input(pairs[1][0] / f"{phase.lower()}.input")[1]
        gas1 = read_result(pairs[0][0] / f"{phase.lower()}.result")[1]["GAS_COL_DRY"]
        gas2 = read_result(pairs[1][0] / f"{phase.lower()}.result")[1]["GAS_COL_DRY"]
        n_native = inputs1["NATIVE_DRY_LAYER_MASS_KG_M2"].shape[1]
        gas1 = gas1.reshape((inputs1["PLAY"].shape[0], gas1.shape[1], gas1.shape[2]), order="F")[:, :, 0]
        gas2 = gas2.reshape((inputs2["PLAY"].shape[0], gas2.shape[1], gas2.shape[2]), order="F")[:, :, 0]
        if not np.array_equal(gas1[:, :n_native], gas2[:, :n_native]):
            raise RuntimeError(f"{phase}: native gas columns changed when pressure/H2O changed at fixed mass")
        if np.array_equal(gas1[:, n_native:], gas2[:, n_native:]):
            raise RuntimeError(f"{phase}: pressure-derived extension did not respond to pressure/H2O perturbation")
        if np.array_equal(inputs1["PLEV"], inputs2["PLEV"]) or np.array_equal(inputs1["H2O"], inputs2["H2O"]):
            raise RuntimeError(f"{phase}: test fixture failed to change both pressure and H2O")

    bad_result_dir = out / "bad-result-shape"
    bad_result_dir.mkdir()
    good_capture = capture / "LW_000001"
    shutil.copy2(good_capture / "lw.input", bad_result_dir / "lw.input")
    mutate_gas_result_shape(good_capture / "lw.result", bad_result_dir / "lw.result")
    try:
        validate_pair(bad_result_dir, "LW", require_raw=False)
    except ValueError as exc:
        if "unexpected GAS_COL_DRY shape" not in str(exc):
            raise
    else:
        raise RuntimeError("malformed GAS_COL_DRY rank/shape was accepted")

    invalid_results = []
    for case, diagnostic in (("shape", SHAPE_ERROR), ("empty", SHAPE_ERROR),
                             ("too_wide", SHAPE_ERROR), ("zero", VALUE_ERROR),
                             ("negative", VALUE_ERROR), ("nan", VALUE_ERROR), ("inf", VALUE_ERROR)):
        for phase in ("LW", "SW", "SW_NIGHT"):
            invalid_results.append(expect_failure([str(executable), str(data_dir), case, phase], diagnostic,
                                                  f"adapter_{phase}_{case}"))

    corruption_results = []
    source_input = capture / "lw_000001.input"
    ref_diags = {"zero": REFERENCE_VALUE_ERROR, "negative": REFERENCE_VALUE_ERROR,
                 "nan": REFERENCE_VALUE_ERROR, "inf": REFERENCE_VALUE_ERROR,
                 "empty": "replay section name or shape mismatch",
                 "too_wide": "replay section name or shape mismatch",
                 "row_shape": "replay section name or shape mismatch"}
    for mutation, diagnostic in ref_diags.items():
        mutated = out / f"mutated-{mutation}.input"
        mutate_native_section(source_input, mutated, mutation)
        try:
            read_input(mutated)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"input validator accepted native mass corruption {mutation}")
        proc = subprocess.run([str(reference), str(data_dir), str(mutated), str(out / f"mutated-{mutation}.result")],
                              cwd=out, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, check=False)
        if proc.returncode == 0 or diagnostic not in proc.stdout:
            raise RuntimeError(f"reference corruption {mutation} was not rejected as expected: {proc.stdout}")
        corruption_results.append({"mutation": mutation, "returncode": proc.returncode,
                                   "diagnostic": diagnostic, "python_validator_rejected": True})

    return {"status": "PASS", "scope": "direct two-column LW/SW adapter calls plus independent V6 replay",
            "physics_checks": ["native-prefix GAS_COL_DRY equals Avogadro/dry-molecular-weight conversion",
                               "upper extended layers equal pressure/H2O helper formula",
                               "native prefix is invariant to pressure/H2O changes at fixed supplied mass",
                               "upper helper extension responds to pressure/H2O changes",
                               "all traced adapter results agree with independent reference solver"],
            "executable": str(executable), "executable_sha256": exe_sha,
            "reference": str(reference), "reference_sha256": digest(reference),
            "coefficient_directory": str(data_dir), "phases": phase_results,
            "reference_replays": replay_results, "adapter_invalid_cases": invalid_results,
            "reference_corruption_probes": corruption_results,
            "malformed_result_shape_rejected": True,
            "surface_albedos": {"avdir": [0.15, 0.20], "avdif": [0.10, 0.12],
                                "andir": [0.25, 0.30], "andif": [0.20, 0.22]},
            "capture_directory": str(capture)}


def run_capture_validation(capture: Path) -> dict[str, Any]:
    found = []
    for phase in PHASES:
        for input_path in capture.rglob(f"{phase.lower()}.input"):
            phase_dir = input_path.parent
            if not all((phase_dir / f"{phase.lower()}.{ext}").is_file() for ext in ("raw", "input", "result")):
                raise RuntimeError(f"{phase_dir}: incomplete {phase} raw/input/result capture set")
            found.append(validate_pair(phase_dir, phase, require_raw=True))
    if not found:
        raise RuntimeError(f"{capture}: no complete LW or SW capture found")
    return {"status": "PASS", "scope": "actual WRF capture native-mass and full gas-column formula validation",
            "capture_directory": str(capture.resolve()), "phases": found,
            "checks": ["trace NATIVE_DRY_LAYER_MASS_KG_M2 bitwise-equals raw DRY_LAYER_MASS_KG_M2",
                       "native GAS_COL_DRY equals Avogadro/(M_dry*10000) times dry mass",
                       "extended GAS_COL_DRY equals the pinned pressure/H2O helper calculation"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture-dir", type=Path,
                       help="validate an actual WRF capture containing phase .raw/.input/.result files")
    group.add_argument("--executable", type=Path, help="compiled test_rrtmgp_native_gas_columns executable")
    parser.add_argument("--reference", type=Path, help="compiled independent reference_column executable")
    parser.add_argument("--data-dir", type=Path, help="RRTMGP production coefficient directory")
    parser.add_argument("--output-dir", type=Path, help="parent directory for an automatically cleaned scratch run")
    parser.add_argument("--output", type=Path, help="write validation JSON (required with --capture-dir)")
    args = parser.parse_args()
    try:
        if args.capture_dir is not None:
            if args.output is None:
                parser.error("--capture-dir requires --output JSON")
            report = run_capture_validation(args.capture_dir.resolve())
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            if args.reference is None or args.data_dir is None or args.output_dir is None:
                parser.error("--executable requires --reference, --data-dir, and --output-dir")
            report = run_standalone(args)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "phases": report["phases"]}, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, AssertionError, subprocess.SubprocessError) as exc:
        print(f"native gas-column test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
