#!/usr/bin/env python3
"""Locked one-point diagnostic runner. No work occurs without root authorization."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import traceback


PLAN_REL = Path("build/udm37-bon-night-opacity-independent-plan-v1/v3/plan.json")
PLAN_SHA256 = "21edb10d1af8cbc6b12f44e305572d49fa688d822644c49acb946246aa62d01e"
EXPECTED_PIN_RECORDS = 51
CREATED_OUTPUT_DIR: Path | None = None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pin_file(root: Path, rec: dict, label: str) -> Path:
    path = Path(rec["path"])
    if not path.is_absolute():
        path = root / path
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label}: expected regular non-symlink file: {path}")
    actual_size = path.stat().st_size
    actual_hash = sha256(path)
    if actual_size != int(rec["size_bytes"]) or actual_hash != rec["sha256"]:
        raise ValueError(f"{label}: pin mismatch: {path}")
    return path.resolve()


def collect_pin_records(value, pointer=""):
    records = []
    if isinstance(value, dict):
        if {"path", "sha256", "size_bytes"}.issubset(value):
            records.append({
                "json_pointer": pointer or "/",
                "path": value["path"],
                "sha256": value["sha256"],
                "size_bytes": int(value["size_bytes"]),
            })
        for key, child in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            records.extend(collect_pin_records(child, pointer + "/" + escaped))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            records.extend(collect_pin_records(child, pointer + "/" + str(index)))
    return records


def canonical_records(records):
    return sorted(records, key=lambda x: (x["json_pointer"], x["path"]))


def verify_authorization(root: Path, plan_path: Path, plan: dict,
                         point_source: Path, auth_path: Path) -> dict:
    auth_bytes = auth_path.read_bytes()
    auth = json.loads(auth_bytes)
    if auth.get("schema") != "udm37-bon-night-opacity-execution-authorization-v1":
        raise ValueError("authorization schema mismatch")
    if auth.get("status") != "AUTHORIZED_DIAGNOSTIC_ONLY":
        raise ValueError("authorization is not explicitly authorized")
    if auth.get("plan_sha256") != PLAN_SHA256 or sha256(plan_path) != PLAN_SHA256:
        raise ValueError("frozen plan identity mismatch")

    source_rec = auth.get("point_source")
    review_rec = auth.get("source_review")
    if not isinstance(source_rec, dict) or not isinstance(review_rec, dict):
        raise ValueError("authorization must pin point_source and source_review")
    if pin_file(root, source_rec, "authorized point source") != point_source.resolve():
        raise ValueError("CLI point source differs from authorized point source")
    pin_file(root, review_rec, "independent source review")

    plan_records = canonical_records(collect_pin_records(plan))
    if len(plan_records) != EXPECTED_PIN_RECORDS:
        raise ValueError(f"frozen artifact-pin roster changed: {len(plan_records)}")
    auth_records = auth.get("artifact_pins")
    if not isinstance(auth_records, list) or canonical_records(auth_records) != plan_records:
        raise ValueError("authorization artifact_pins do not exactly bind plan pins")
    for item in plan_records:
        pin_file(root, item, "plan artifact " + item["json_pointer"])

    # Keep the review pin and source pin distinct from the plan artifact roster.
    if not auth.get("source_review_status", "").startswith("PASS_SCOPED"):
        raise ValueError("source review status is not PASS_SCOPED")
    return auth


def write_new(path: Path, data: bytes) -> str:
    """Create one durable file without replacing prior evidence."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o644)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    return hashlib.sha256(data).hexdigest()


def durable_json(path: Path, value) -> str:
    return write_new(path, (json.dumps(value, indent=2, sort_keys=True,
                                       allow_nan=False) + "\n").encode("utf-8"))


def ordered_ulp_delta(a, b) -> int:
    """Signed distance in monotonically ordered IEEE-754 binary64 encodings."""
    import struct
    def key(x):
        bits = struct.unpack(">Q", struct.pack(">d", float(x)))[0]
        return ((~bits) & ((1 << 64) - 1)) if bits >> 63 else (bits | (1 << 63))
    return key(a) - key(b)


def summarize_pair(candidate, target):
    import numpy as np
    c = np.asarray(candidate, dtype=np.float64)
    t = np.asarray(target, dtype=np.float64)
    if c.shape != (45, 128) or t.shape != (45, 128):
        raise ValueError(f"tau shape mismatch: candidate={c.shape}, target={t.shape}")
    if not np.isfinite(c).all() or not np.isfinite(t).all():
        raise ValueError("nonfinite candidate or captured tau")
    signed = c - t
    absolute = np.abs(signed)
    relative = np.divide(signed, t, out=np.full_like(signed, np.nan), where=t != 0.0)
    ulp = np.empty(c.shape, dtype=object)
    for idx in np.ndindex(c.shape):
        ulp[idx] = ordered_ulp_delta(c[idx], t[idx])
    flat_ulp = [int(x) for x in ulp.flat]
    return {
        "candidate_tau": c.tolist(),
        "target_tau": t.tolist(),
        "signed_residual": signed.tolist(),
        "absolute_residual": absolute.tolist(),
        "relative_residual_signed_target_denominator_null_at_zero": [
            [None if not math.isfinite(float(x)) else float(x) for x in row]
            for row in relative.tolist()
        ],
        "signed_ordered_binary64_ulp_delta": [[int(x) for x in row] for row in ulp.tolist()],
        "summary": {
            "cells": int(c.size),
            "target_zero_cells": int(np.count_nonzero(t == 0.0)),
            "max_absolute_residual": float(absolute.max()),
            "rms_residual": float(np.sqrt(np.mean(signed * signed))),
            "max_absolute_relative_residual_nonzero_target": (
                float(np.max(np.abs(relative[t != 0.0]))) if np.any(t != 0.0) else None
            ),
            "max_absolute_ordered_ulp_delta": max(abs(x) for x in flat_ulp),
            "numerical_gate": "NONE_DIAGNOSTIC_ONLY",
        },
    }


def summarize_dry_column(candidate, target):
    import numpy as np
    c = np.asarray(candidate, dtype=np.float64)
    t = np.asarray(target, dtype=np.float64)
    if c.shape != (45,) or t.shape != (45,):
        raise ValueError(f"dry-column shape mismatch: candidate={c.shape}, target={t.shape}")
    if not np.isfinite(c).all() or not np.isfinite(t).all():
        raise ValueError("nonfinite reconstructed or saved GAS_COL_DRY")
    delta = c - t
    rel = np.divide(delta, t, out=np.full_like(delta, np.nan), where=t != 0.0)
    return {
        "reconstructed_molecule_cm2": c.tolist(),
        "saved_GAS_COL_DRY_molecule_cm2": t.tolist(),
        "signed_residual": delta.tolist(),
        "absolute_residual": np.abs(delta).tolist(),
        "relative_residual_signed_saved_denominator_null_at_zero": [
            None if not math.isfinite(float(x)) else float(x) for x in rel
        ],
        "summary": {
            "layers": int(c.size),
            "saved_zero_layers": int(np.count_nonzero(t == 0.0)),
            "max_absolute_residual": float(np.max(np.abs(delta))),
            "rms_residual": float(np.sqrt(np.mean(delta * delta))),
            "max_absolute_relative_residual_nonzero_saved": (
                float(np.max(np.abs(rel[t != 0.0]))) if np.any(t != 0.0) else None
            ),
            "numerical_gate": "NONE_DIAGNOSTIC_ONLY",
        },
    }


def pfrac_context_crosscheck(plan: dict, root: Path, construction: dict) -> dict:
    """Cross-check discrete interpolation metadata only; never supply tau inputs."""
    import numpy as np
    result_path = pin_file(root, plan["pinned_artifacts"]["pfrac_result"], "pfrac context result")
    context = json.loads(result_path.read_text(encoding="utf-8"))
    if context.get("status") != "PASS_SCOPED":
        raise ValueError("pfrac context receipt is not PASS_SCOPED")
    case = next((x for x in construction["cases"] if x["case_id"] == "n2-0p7808"), None)
    if case is None:
        raise ValueError("positive-N2 constructed case is missing")
    discrete = case["discrete_context"]
    exact_pairs = {
        "available_gases_vs_pfrac_reduced_gases": (case["available_gases"], context["reduced_gases"]),
        "key_species_rewritten": (discrete["key_species_reduced_ids"], context["key_species_rewritten"]),
        "flavors_fortran_indices": (discrete["flavors_reduced_ids"], context["flavors_Fortran_indices"]),
        "jtemp_fortran": (discrete["jtemp_fortran"], context["jtemp_Fortran"]),
        "jpress_fortran": (discrete["jpress_fortran"], context["jpress_Fortran"]),
        "atmosphere_fortran": ([1 if x else 2 for x in discrete["tropopause_lower"]],
                                context["atmosphere_Fortran"]),
    }
    checks = {}
    for name, (actual, expected) in exact_pairs.items():
        if actual != expected:
            raise ValueError(f"positive-N2 pfrac discrete context mismatch: {name}")
        checks[name] = {"exact_equal": True}

    ftemp = np.asarray([x["ftemp"] for x in discrete["layer_flavor_state"]], dtype=np.float64)
    fpress = np.asarray([x["fpress"] for x in discrete["layer_flavor_state"]], dtype=np.float64)
    ptemp = np.asarray(context["ftemp"], dtype=np.float64)
    ppress = np.asarray(context["fpress"], dtype=np.float64)
    if ftemp.shape != (45,) or fpress.shape != (45,) or ptemp.shape != (45,) or ppress.shape != (45,):
        raise ValueError("pfrac fraction context shape mismatch")
    if not all(np.isfinite(x).all() for x in (ftemp, fpress, ptemp, ppress)):
        raise ValueError("nonfinite interpolation fractions")
    return {
        "schema": "udm37-bon-night-opacity-pfrac-context-crosscheck-v1",
        "scope": "positive-N2 discrete cross-check only; pfrac values are not used to construct tau",
        "pfrac_result_sha256": plan["pinned_artifacts"]["pfrac_result"]["sha256"],
        "exact_discrete_checks": checks,
        "fraction_differences_diagnostic_only": {
            "ftemp_point_minus_pfrac": (ftemp - ptemp).tolist(),
            "ftemp_max_abs_difference": float(np.max(np.abs(ftemp - ptemp))),
            "fpress_point_minus_pfrac": (fpress - ppress).tolist(),
            "fpress_max_abs_difference": float(np.max(np.abs(fpress - ppress))),
            "tolerance_or_numerical_verdict": "NONE",
        },
    }


def run(args) -> int:
    global CREATED_OUTPUT_DIR
    root = args.root.resolve(strict=True)
    plan_path = args.plan.resolve(strict=True)
    if plan_path != (root / PLAN_REL).resolve(strict=True):
        raise ValueError("plan path is not the frozen v3 plan path")
    if sha256(plan_path) != PLAN_SHA256:
        raise ValueError("frozen v3 plan SHA256 mismatch")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    point_source = args.point_source.resolve(strict=True)
    auth_path = args.authorization.resolve(strict=True)

    # All authorization and input/source pin checks precede module import.
    auth = verify_authorization(root, plan_path, plan, point_source, auth_path)
    out = args.out.absolute()
    out.parent.mkdir(parents=True, exist_ok=True)
    os.mkdir(out)  # refuses any pre-existing output directory
    CREATED_OUTPUT_DIR = out
    preflight = {
        "schema": "udm37-bon-night-opacity-point-runner-preflight-v2",
        "status": "AUTHORIZED_PINS_VERIFIED",
        "plan_sha256": PLAN_SHA256,
        "point_source_sha256": sha256(point_source),
        "authorization_sha256": sha256(auth_path),
        "source_review_sha256": auth["source_review"]["sha256"],
        "plan_artifact_pin_records": EXPECTED_PIN_RECORDS,
        "solver_calls": 0,
        "model_calls": 0,
    }
    durable_json(out / "preflight.json", preflight)
    durable_json(out / "execution-state.json", {"status": "POINT_RECONSTRUCTION_STARTED",
                                                   "actual_process_return_code": "RECORDED_BY_PARENT"})

    # Import only after the authorization packet and every pinned artifact passed.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("authorized_point_reconstruction", point_source)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load authorized point source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "reconstruct_point", None)):
        raise ValueError("point source lacks reconstruct_point(plan, root)")

    # Contract: reconstruct_point must construct all cases without opening targets.
    construction = module.reconstruct_point(plan, root)
    if construction.get("status") != "POINT_ARRAYS_CONSTRUCTED_TARGETS_NOT_OPENED":
        raise ValueError("point source did not return the pre-target construction status")
    cases = construction.get("cases")
    expected_ids = ["n2-absent-baseline", "n2-explicit-zero", "n2-0p7808"]
    if not isinstance(cases, list) or [x.get("case_id") for x in cases] != expected_ids:
        raise ValueError("point source returned unexpected case roster/order")
    # This durable construction artifact and its SHA precede any captured-target read.
    construction_sha = durable_json(out / "construction.json", construction)
    durable_json(out / "construction-receipt.json", {
        "schema": "udm37-bon-night-opacity-construction-receipt-v2",
        "status": "ALL_THREE_POINT_ARRAYS_DURABLY_WRITTEN_BEFORE_TARGET_READ",
        "construction_file": "construction.json",
        "construction_sha256": construction_sha,
        "case_ids": expected_ids,
        "shape_each_case": [45, 128],
    })

    # Cross-check previously published positive-N2 interpolation context only
    # after the point arrays are durable and still before reading tau targets.
    pfrac_crosscheck = pfrac_context_crosscheck(plan, root, construction)
    durable_json(out / "pfrac-context-crosscheck.json", pfrac_crosscheck)

    # Target parser is intentionally imported/opened only after construction is durable.
    comparator_rec = plan["pinned_artifacts"]["column_comparator"]
    comparator_path = pin_file(root, comparator_rec, "result comparator")
    sys.path.insert(0, str(comparator_path.parent))
    from compare_column_replay import read_result

    comparisons = []
    dry_comparisons = []
    for case in cases:
        target_pin_name = case["result_target_pin_name"]
        target_path = pin_file(root, plan["pinned_artifacts"][target_pin_name], target_pin_name)
        target_packet = read_result(target_path)
        if (target_packet["phase"], target_packet["nc"], target_packet["nl"]) != ("LW", 1, 45):
            raise ValueError(f"unexpected target result header for {case['case_id']}")
        sections = target_packet["sections"]
        if "GAS_TAU_RAW" not in sections or "GAS_TAU" not in sections or "GAS_COL_DRY" not in sections:
            raise ValueError(f"target lacks required gas tau/dry sections for {case['case_id']}")
        dry_target = sections["GAS_COL_DRY"]
        if dry_target.shape != (1, 45, 1):
            raise ValueError(f"target GAS_COL_DRY shape mismatch for {case['case_id']}: {dry_target.shape}")
        dry_comparisons.append({
            "case_id": case["case_id"],
            "target_path": str(target_path.relative_to(root)),
            "target_sha256": plan["pinned_artifacts"][target_pin_name]["sha256"],
            **summarize_dry_column(case["dry_column_molecule_cm2"], dry_target[0, :, 0]),
        })
        reconstructed = case["tau_point"]
        for section in ("GAS_TAU_RAW", "GAS_TAU"):
            t = sections[section]
            if t.shape != (1, 45, 128):
                raise ValueError(f"target {section} shape mismatch for {case['case_id']}")
            comparisons.append({
                "case_id": case["case_id"], "target_section": section,
                "target_path": str(target_path.relative_to(root)),
                "target_sha256": plan["pinned_artifacts"][target_pin_name]["sha256"],
                **summarize_pair(reconstructed, t[0]),
            })
    report = {
        "schema": "udm37-bon-night-opacity-point-diagnostic-v2",
        "status": "DIAGNOSTIC_COMPLETE_NO_NUMERICAL_VERDICT",
        "plan_sha256": PLAN_SHA256,
        "point_source_sha256": sha256(point_source),
        "authorization_sha256": sha256(auth_path),
        "construction_sha256": construction_sha,
        "pfrac_context_crosscheck_file": "pfrac-context-crosscheck.json",
        "dry_column_crosschecks": dry_comparisons,
        "comparisons": comparisons,
        "interpretation": "Residual and ULP statistics only. No tolerance or PASS/FAIL threshold is applied; same-table agreement cannot establish coefficient-generation or physical accuracy.",
    }
    durable_json(out / "diagnostic.json", report)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--point-source", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="new, nonexistent output directory")
    parser.add_argument("--execute", action="store_true",
                        help="required in addition to a valid root authorization packet")
    args = parser.parse_args()
    if not args.execute:
        parser.error("LOCKED: --execute and a valid execution-authorization packet are required")
    try:
        return run(args)
    except BaseException as exc:
        # Do not overwrite earlier evidence; if output was created, leave a durable failure.
        out = CREATED_OUTPUT_DIR
        if out is not None and out.is_dir() and not (out / "terminal-failure.json").exists():
            try:
                durable_json(out / "terminal-failure.json", {
                    "schema": "udm37-bon-night-opacity-point-runner-failure-v2",
                    "status": "FAILED_PRESERVED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                })
            except BaseException:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
