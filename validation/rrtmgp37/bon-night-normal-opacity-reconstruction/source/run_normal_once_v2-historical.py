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


PLAN_REL = Path("build/udm37-bon-night-normal-opacity-plan-v2/plan.json")
PLAN_SHA256 = "ce13701489beb602afda0bb8091339bdcb434ff555f536a2de6ab5d9add9f49f"
EXPECTED_PIN_RECORDS = 138
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
    if auth.get("schema") != "udm37-bon-night-normal-opacity-authorization-v1":
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
    """Publish complete fsynced bytes atomically, refusing existing targets."""
    temporary = path.with_name(path.name + ".partial")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    # A hard link publishes a fully written inode atomically without replacing
    # an existing artifact. Preserve any partial on failure for investigation.
    os.link(temporary, path)
    temporary.unlink()
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
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


def pfrac_context_crosscheck(plan: dict, root: Path, construction: dict, point_module) -> dict:
    """Compare applicable same-state context; do not equate different gas rosters."""
    import numpy as np
    result_rec = plan["pinned_artifacts"]["pfrac_result"]
    result_path = pin_file(root, result_rec, "pfrac context result")
    # Bind the original normal state to the pfrac's matched carrier, excluding
    # only the intentional dry-mass section. This comparison never supplies
    # numbers to the independent construction, which is already durable.
    normal = point_module.read_packet(pin_file(root, plan["pinned_artifacts"]["normal_input"], "normal input"), "LW")
    carrier = point_module.read_packet(pin_file(root, plan["pinned_artifacts"]["pfrac_input"], "pfrac held input"), "LW")
    identical_sections = ["PLAY", "PLEV", "TLAY", "GRAVITY", "MOL_WEIGHT_DRY"] + list(point_module.INPUT_SECTIONS.values())
    for name in identical_sections:
        if name not in normal or name not in carrier or not np.array_equal(normal[name], carrier[name]):
            raise ValueError("pfrac context belongs to a different physical-input section: " + name)
    context = json.loads(result_path.read_text(encoding="utf-8"))
    pfrac_plan_rec = plan["pinned_artifacts"]["pfrac_plan"]
    pfrac_plan_path = pin_file(root, pfrac_plan_rec, "pfrac plan")
    pfrac_plan = json.loads(pfrac_plan_path.read_text(encoding="utf-8"))
    if context.get("plan_sha256") != pfrac_plan_rec["sha256"]:
        raise ValueError("pfrac result does not bind the frozen pfrac plan")
    expected_input = plan["pinned_artifacts"]["pfrac_input"]
    if context.get("pins", {}).get("held_input") != expected_input or pfrac_plan.get("pinned_artifacts", {}).get("held_input") != expected_input:
        raise ValueError("pfrac plan/result/held-input ancestry mismatch")
    if context.get("status") != "PASS_SCOPED":
        raise ValueError("pfrac context receipt is not PASS_SCOPED")
    cases = construction.get("cases", [])
    if len(cases) != 1 or cases[0].get("case_id") != "normal-n2-absent":
        raise ValueError("normal N2-absent constructed case is missing")
    case = cases[0]; discrete = case["discrete_context"]
    actual_gases = case["available_gases"]
    pfrac_gases = context["reduced_gases"]
    if pfrac_gases.count("n2") != 1 or "n2" in actual_gases:
        raise ValueError("expected positive-N2 pfrac and absent-N2 normal roster")
    def semantic_ids(value, gases):
        if isinstance(value, list):
            return [semantic_ids(x, gases) for x in value]
        if not isinstance(value, int) or value < 0 or value > len(gases):
            raise ValueError("invalid reduced gas identifier in context")
        return "dry_air" if value == 0 else gases[value-1]
    exact_pairs = {
        "table_order_roster_after_removing_N2": (actual_gases, [x for x in pfrac_gases if x != "n2"]),
        "key_species_semantic_names": (semantic_ids(discrete["key_species_reduced_ids"], actual_gases), semantic_ids(context["key_species_rewritten"], pfrac_gases)),
        "flavor_semantic_names": (semantic_ids(discrete["flavors_reduced_ids"], actual_gases), semantic_ids(context["flavors_Fortran_indices"], pfrac_gases)),
        "jtemp_fortran": (discrete["jtemp_fortran"], context["jtemp_Fortran"]),
        "jpress_fortran": (discrete["jpress_fortran"], context["jpress_Fortran"]),
        "atmosphere_fortran": ([1 if x else 2 for x in discrete["tropopause_lower"]], context["atmosphere_Fortran"]),
    }
    checks = {}
    for name, (actual, expected) in exact_pairs.items():
        if actual != expected:
            raise ValueError("normal-carrier pfrac applicable context mismatch: " + name)
        checks[name] = {"exact_equal": True}
    ftemp = np.asarray([x["ftemp"] for x in discrete["layer_flavor_state"]], dtype=np.float64)
    fpress = np.asarray([x["fpress"] for x in discrete["layer_flavor_state"]], dtype=np.float64)
    ptemp = np.asarray(context["ftemp"], dtype=np.float64)
    ppress = np.asarray(context["fpress"], dtype=np.float64)
    if any(a.shape != (45,) or not np.isfinite(a).all() for a in (ftemp, fpress, ptemp, ppress)):
        raise ValueError("invalid interpolation fraction context")
    return {"schema": "udm37-bon-night-normal-opacity-pfrac-context-v1",
            "scope": "Same physical profiles with different dry-mass carriers and N2 roster. Coordinates and semantic major key/flavor identities only; no minor-roster equality or tau inputs.",
            "identical_input_sections": identical_sections,
            "pfrac_result_sha256": result_rec["sha256"], "exact_discrete_checks": checks,
            "fraction_differences_diagnostic_only": {
                "ftemp_point_minus_pfrac": (ftemp-ptemp).tolist(),
                "ftemp_max_abs_difference": float(np.max(np.abs(ftemp-ptemp))),
                "fpress_point_minus_pfrac": (fpress-ppress).tolist(),
                "fpress_max_abs_difference": float(np.max(np.abs(fpress-ppress))),
                "tolerance_or_numerical_verdict": "NONE"}}


def run(args) -> int:
    global CREATED_OUTPUT_DIR
    root = args.root.resolve(strict=True)
    plan_path = args.plan.resolve(strict=True)
    if plan_path != (root / PLAN_REL).resolve(strict=True):
        raise ValueError("plan path is not the frozen normal v2 plan path")
    if sha256(plan_path) != PLAN_SHA256:
        raise ValueError("frozen normal v2 plan SHA256 mismatch")
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
        "schema": "udm37-bon-night-normal-opacity-runner-preflight-v2",
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
    expected_ids = ["normal-n2-absent"]
    if not isinstance(cases, list) or [x.get("case_id") for x in cases] != expected_ids:
        raise ValueError("point source returned unexpected case roster/order")
    # This durable construction artifact and its SHA precede any captured-target read.
    construction_sha = durable_json(out / "construction.json", construction)
    durable_json(out / "construction-receipt.json", {
        "schema": "udm37-bon-night-normal-opacity-construction-receipt-v2",
        "status": "NORMAL_POINT_ARRAY_DURABLY_WRITTEN_BEFORE_TARGET_READ",
        "construction_file": "construction.json",
        "construction_sha256": construction_sha,
        "case_ids": expected_ids,
        "shape_each_case": [45, 128],
    })

    # Cross-check previously published positive-N2 interpolation context only
    # after the point arrays are durable and still before reading tau targets.
    pfrac_crosscheck = pfrac_context_crosscheck(plan, root, construction, module)
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
        "schema": "udm37-bon-night-normal-opacity-diagnostic-v2",
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
    durable_json(out / "normal-target-comparison.json", report)
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
