#!/usr/bin/env python3
"""Compare independent RRTMGP reference output with a production replay."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np


MAGIC = "RRTMGP_RESULT_V1"
OPTICAL_SECTIONS = {
    "GAS_TAU", "GAS_TAU_RAW", "GAS_SSA", "GAS_G", "GAS_COL_DRY", "CLOUD_TAU", "CLOUD_SSA", "CLOUD_G",
    "PREPARED_TAU", "PREPARED_SSA", "PREPARED_G", "TOTAL_TAU", "TOTAL_SSA",
    "TOTAL_G", "RL_USED", "DI_USED", "DS_USED", "PRECIP_TAU", "PRECIP_SSA", "PRECIP_G",
    "GRAUPEL_TAU_ABS", "HAIL_TAU_ABS", "GRAUPEL_TAU_EXT", "GRAUPEL_TAU_SCA", "GRAUPEL_TAU_SCA_G",
    "HAIL_TAU_EXT", "HAIL_TAU_SCA", "HAIL_TAU_SCA_G", "FROZEN_TAU", "FROZEN_SSA", "FROZEN_G",
    "NATIVE_CLOUD_TAU", "CU_CLOUD_TAU", "NATIVE_CLOUD_SSA", "NATIVE_CLOUD_G",
    "CU_CLOUD_SSA", "CU_CLOUD_G", "CU_RL_USED", "CU_DI_USED",
    "AUDIT_EXTRA_PRECIP_TAU", "AUDIT_EXTRA_PRECIP_TAU_RAW",
    "AUDIT_EXTRA_PRECIP_SSA", "AUDIT_EXTRA_PRECIP_G",
}
MASK_SECTION = "MASK"
FLOAT_OUTPUT_SECTIONS = {
    "UP", "DN", "HR", "UPC", "DNC", "HRC", "DIRECT", "DIFFUSE", "DIRECTC",
    "VISDIR", "VISDIF", "NIRDIR", "NIRDIF",
    "DIRECT_PREDELTA", "DIRECTC_PREDELTA", "VISDIR_PREDELTA", "NIRDIR_PREDELTA",
    "AUDIT_DIRECT_PREDELTA",
}
INTERFACE_SECTIONS = {"UP", "DN", "UPC", "DNC", "DIRECT", "DIFFUSE", "DIRECTC",
                      "VISDIR", "VISDIF", "NIRDIR", "NIRDIF", "DIRECT_PREDELTA",
                      "DIRECTC_PREDELTA", "VISDIR_PREDELTA", "NIRDIR_PREDELTA",
                      "AUDIT_DIRECT_PREDELTA"}
LAYER_SCALAR_SECTIONS = {"RL_USED", "DI_USED", "DS_USED", "HR", "HRC"}
RADIATION_SECTIONS = (OPTICAL_SECTIONS | FLOAT_OUTPUT_SECTIONS | INTERFACE_SECTIONS |
                      LAYER_SCALAR_SECTIONS | {MASK_SECTION})
WRF_SURFACE_SECTIONS = {"WRF_GLW", "WRF_OLR", "WRF_GSW", "WRF_SWDDIR", "WRF_SWDDIF"}
REQUIRED_SECTIONS = {
    "GAS_TAU", "CLOUD_TAU", "PREPARED_TAU", "MASK", "TOTAL_TAU", "RL_USED", "DI_USED",
    "DS_USED", "UP", "DN", "HR", "UPC", "DNC", "HRC",
}
FLOAT32_EPS = np.finfo(np.float32).eps


class ReplayFormatError(ValueError):
    pass


def _parse_numbers(tokens: list[str], path: Path, line_no: int) -> list[float]:
    values: list[float] = []
    for token in tokens:
        try:
            value = float(token.replace("D", "E").replace("d", "e"))
        except ValueError as exc:
            raise ReplayFormatError(f"{path}:{line_no}: invalid numeric value {token!r}") from exc
        if not math.isfinite(value):
            raise ReplayFormatError(f"{path}:{line_no}: non-finite value {token!r}")
        values.append(value)
    return values


def read_result(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2 or lines[0].strip() != MAGIC:
        raise ReplayFormatError(f"{path}: expected {MAGIC} header")
    header = lines[1].split()
    if len(header) != 3:
        raise ReplayFormatError(f"{path}: expected phase, nc, nl on line 2")
    phase = header[0].upper()
    if phase not in {"LW", "SW"}:
        raise ReplayFormatError(f"{path}: invalid phase {phase!r}")
    try:
        nc, nl = int(header[1]), int(header[2])
    except ValueError as exc:
        raise ReplayFormatError(f"{path}: invalid nc/nl dimensions") from exc
    if nc < 1 or nl < 1:
        raise ReplayFormatError(f"{path}: nc and nl must be positive")

    sections: dict[str, np.ndarray] = {}
    line_index = 2
    while line_index < len(lines):
        if not lines[line_index].strip():
            line_index += 1
            continue
        section_line = line_index + 1
        fields = lines[line_index].split()
        line_index += 1
        if len(fields) != 4:
            raise ReplayFormatError(f"{path}:{section_line}: expected section name and 3 dimensions")
        name = fields[0].upper()
        if name in sections:
            raise ReplayFormatError(f"{path}:{section_line}: duplicate section {name}")
        try:
            shape = tuple(int(value) for value in fields[1:])
        except ValueError as exc:
            raise ReplayFormatError(f"{path}:{section_line}: invalid shape for {name}") from exc
        if any(size < 1 for size in shape):
            raise ReplayFormatError(f"{path}:{section_line}: non-positive shape for {name}")
        count = math.prod(shape)
        values: list[float] = []
        while len(values) < count and line_index < len(lines):
            value_line = lines[line_index]
            line_index += 1
            if not value_line.strip():
                continue
            values.extend(_parse_numbers(value_line.split(), path, line_index))
            if len(values) > count:
                raise ReplayFormatError(f"{path}:{line_index}: too many values in {name}")
        if len(values) != count:
            raise ReplayFormatError(f"{path}: {name} expected {count} values, found {len(values)}")
        array = np.asarray(values, dtype=np.float64).reshape(shape, order="F")
        if not np.isfinite(array).all():
            raise ReplayFormatError(f"{path}: {name} contains non-finite values")
        if name in INTERFACE_SECTIONS and shape != (nc, nl + 1, 1):
            raise ReplayFormatError(f"{path}:{section_line}: {name} must have shape {(nc, nl + 1, 1)}")
        if name in LAYER_SCALAR_SECTIONS and shape != (nc, nl, 1):
            raise ReplayFormatError(f"{path}:{section_line}: {name} must have shape {(nc, nl, 1)}")
        if name in RADIATION_SECTIONS - INTERFACE_SECTIONS - LAYER_SCALAR_SECTIONS:
            if shape[0:2] != (nc, nl):
                raise ReplayFormatError(f"{path}:{section_line}: {name} must start with shape {(nc, nl)}")
        if name.startswith("WRF_"):
            if name in WRF_SURFACE_SECTIONS:
                expected_shape = (nc, 1, 1)
                if shape != expected_shape:
                    raise ReplayFormatError(f"{path}:{section_line}: {name} must have shape {expected_shape}")
            elif name == "WRF_THETA_HR":
                if shape[0] != nc or shape[2] != 1 or not 1 <= shape[1] <= nl:
                    raise ReplayFormatError(
                        f"{path}:{section_line}: {name} must have shape (nc, model_nl, 1) with 1 <= model_nl <= {nl}"
                    )
            elif shape[0] != nc or shape[2] != 1 or not 1 <= shape[1] <= nl + 1:
                raise ReplayFormatError(
                    f"{path}:{section_line}: {name} must have shape (nc, positive_levels<=nl+1, 1)"
                )
        elif name not in RADIATION_SECTIONS:
            raise ReplayFormatError(f"{path}:{section_line}: unsupported section {name}")
        sections[name] = array
    if not sections:
        raise ReplayFormatError(f"{path}: no result sections")
    required = set(REQUIRED_SECTIONS)
    if phase == "SW":
        required.update({"GAS_SSA", "GAS_G", "CLOUD_SSA", "CLOUD_G", "PREPARED_SSA", "PREPARED_G",
                         "TOTAL_SSA", "TOTAL_G", "DIRECT", "DIFFUSE", "DIRECTC", "VISDIR", "VISDIF",
                         "NIRDIR", "NIRDIF"})
    missing = sorted(required - set(sections))
    if missing:
        raise ReplayFormatError(f"{path}: missing required sections: {', '.join(missing)}")
    predelta = {"DIRECT_PREDELTA", "DIRECTC_PREDELTA", "VISDIR_PREDELTA", "NIRDIR_PREDELTA"} & sections.keys()
    if predelta and predelta != {"DIRECT_PREDELTA", "DIRECTC_PREDELTA", "VISDIR_PREDELTA", "NIRDIR_PREDELTA"}:
        raise ReplayFormatError(f"{path}: V9 direct-diagnostic result sections must be all present or all absent")
    if predelta and phase != "SW":
        raise ReplayFormatError(f"{path}: pre-delta direct-diagnostic sections are SW-only")
    audit_names = {"AUDIT_EXTRA_PRECIP_TAU", "AUDIT_EXTRA_PRECIP_TAU_RAW",
                   "AUDIT_EXTRA_PRECIP_SSA", "AUDIT_EXTRA_PRECIP_G", "AUDIT_DIRECT_PREDELTA"}
    audit = audit_names & sections.keys()
    expected_audit = {"AUDIT_EXTRA_PRECIP_TAU"} if phase == "LW" else audit_names
    if audit and audit != expected_audit:
        raise ReplayFormatError(f"{path}: incomplete or wrong-phase CF0 audit sections")
    if audit and phase == "SW" and not predelta:
        raise ReplayFormatError(f"{path}: SW CF0 audit requires baseline pre-delta diagnostics")
    cu_lw = {"NATIVE_CLOUD_TAU", "CU_CLOUD_TAU"} & sections.keys()
    cu_sw_names = {"NATIVE_CLOUD_TAU", "CU_CLOUD_TAU", "NATIVE_CLOUD_SSA", "NATIVE_CLOUD_G",
                   "CU_CLOUD_SSA", "CU_CLOUD_G"}
    cu_sw = cu_sw_names & sections.keys()
    cu_radii = {"CU_RL_USED", "CU_DI_USED"} & sections.keys()
    if phase == "LW" and cu_lw and cu_lw != {"NATIVE_CLOUD_TAU", "CU_CLOUD_TAU"}:
        raise ReplayFormatError(f"{path}: LW CU component optics must be present together")
    if phase == "SW" and cu_sw and cu_sw != cu_sw_names:
        raise ReplayFormatError(f"{path}: SW native/CU tau, SSA, and g components must be present together")
    if bool(cu_lw or cu_sw) != (cu_radii == {"CU_RL_USED", "CU_DI_USED"}):
        raise ReplayFormatError(f"{path}: CU component optics require both CU radius records")
    return {"phase": phase, "nc": nc, "nl": nl, "sections": sections}


def compare(production: dict, reference: dict) -> dict:
    report = {
        "production_phase": production["phase"],
        "reference_phase": reference["phase"],
        "nc": production["nc"],
        "nl": production["nl"],
        "sections_compared": 0,
        "max_differences": {},
        "failed_sections": [],
        "missing_sections": [],
    }
    if (production["phase"], production["nc"], production["nl"]) != (
        reference["phase"], reference["nc"], reference["nl"]
    ):
        report["failed_sections"].append("HEADER")
        report["header_error"] = "phase or dimensions differ"

    actual_sections = production["sections"]
    for name, expected in reference["sections"].items():
        if name not in actual_sections:
            report["missing_sections"].append(name)
            report["failed_sections"].append(name)
            continue
        actual = actual_sections[name]
        if actual.shape != expected.shape:
            report["failed_sections"].append(name)
            report["max_differences"][name] = {
                "shape_mismatch": {"production": list(actual.shape), "reference": list(expected.shape)}
            }
            continue
        report["sections_compared"] += 1
        difference = np.abs(actual - expected)
        max_abs = float(np.max(difference)) if difference.size else 0.0
        detail = {"max_abs": max_abs}
        if name == MASK_SECTION:
            passed = np.array_equal(actual, expected)
            detail["tolerance"] = "exact"
        elif name in FLOAT_OUTPUT_SECTIONS:
            ulp = np.abs(np.spacing(expected.astype(np.float32)).astype(np.float64))
            tolerance = 4.0 * ulp + 1.0e-6
            passed = bool(np.all(difference <= tolerance))
            detail["max_tolerance"] = float(np.max(tolerance))
            detail["tolerance"] = "4 float32 ULP + 1e-6"
        elif name in OPTICAL_SECTIONS:
            tolerance = 2.0e-13 + 2.0e-12 * np.abs(expected)
            passed = bool(np.all(difference <= tolerance))
            detail["max_tolerance"] = float(np.max(tolerance))
            detail["tolerance"] = "2e-13 absolute + 2e-12 relative"
        else:
            # Unknown auxiliary sections are compared conservatively as optical data.
            tolerance = 2.0e-13 + 2.0e-12 * np.abs(expected)
            passed = bool(np.all(difference <= tolerance))
            detail["max_tolerance"] = float(np.max(tolerance))
            detail["tolerance"] = "2e-13 absolute + 2e-12 relative (default)"
        detail["passed"] = passed
        report["max_differences"][name] = detail
        if not passed:
            report["failed_sections"].append(name)
    report["passed"] = not report["failed_sections"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production_result", type=Path)
    parser.add_argument("reference_result", type=Path)
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args()
    try:
        production = read_result(args.production_result)
        reference = read_result(args.reference_result)
        report = compare(production, reference)
    except (OSError, ReplayFormatError) as exc:
        report = {"passed": False, "error": str(exc), "failed_sections": ["FORMAT"]}
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report.get("passed", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
