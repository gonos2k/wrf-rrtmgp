#!/usr/bin/env python3
"""Verify the small, checked-in residual-attribution evidence bundle."""
from __future__ import annotations

import hashlib
import json
import gzip
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_stream(stream) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        h.update(block)
        size += len(block)
    return h.hexdigest(), size


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> int:
    manifest = load_json(MANIFEST)
    if manifest.get("schema") != "udm37-residual-attribution-evidence-v1":
        fail("unexpected manifest schema")
    if manifest.get("verifier_sha256") != sha256(Path(__file__)):
        fail("verifier hash mismatch")

    declared = {item["path"] for item in manifest["files"]}
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual != declared:
        fail(f"package roster mismatch: missing={sorted(declared-actual)} extra={sorted(actual-declared)}")

    checked = 0
    for item in manifest["files"]:
        rel = Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts:
            fail(f"unsafe package path: {rel}")
        path = ROOT / rel
        if not path.is_file():
            fail(f"missing package file: {rel}")
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            fail(f"package hash/size mismatch: {rel}")
        checked += 1

    # The held CF0 raw logs are stored as gzip in the already-published PR71
    # evidence bundle; verify those bytes and their original-log identities.
    repo = ROOT.parents[2]
    bundle_manifest = repo / "validation/rrtmgp37/matthew-dt60-timestep-evidence/evidence-manifest.json"
    expected_bundle_manifest_sha = manifest["reused_evidence"]["dt60_evidence_manifest_sha256"]
    if sha256(bundle_manifest) != expected_bundle_manifest_sha:
        fail("reused timestep evidence manifest hash mismatch")
    bm = load_json(bundle_manifest)
    cf_audit = load_json(ROOT / "cf0/audit-final-v2.json")
    for row in cf_audit["run"]["unique_rank_logs"]:
        original = row["path"]
        suffix = f"dt60-48-hour/ra37/rsl.error.{row['rank']:04d}.gz"
        candidates = [x for x in bm["bundle_artifacts"] if x["bundle_path"].endswith(suffix)]
        if len(candidates) != 1:
            fail(f"expected one archived raw log for rank {row['rank']}")
        entry = candidates[0]
        gz = repo / "validation/rrtmgp37/matthew-dt60-timestep-evidence" / entry["bundle_path"]
        if not gz.is_file() or gz.stat().st_size != entry["bundle_size_bytes"] or sha256(gz) != entry["bundle_sha256"]:
            fail(f"archived rank log hash mismatch: {entry['bundle_path']}")
        with gzip.open(gz, "rb") as stream:
            raw_sha, raw_size = sha256_stream(stream)
        expected_suffix = f"build/udm37-matthew-dt60-paired-48h-v1/ra37/rsl.error.{row['rank']:04d}"
        if raw_sha != row["sha256"] or raw_size != row["size_bytes"]:
            fail(f"decompressed original-log hash/size mismatch: rank {row['rank']}")
        if not entry["original_path"].endswith(expected_suffix) or not original.endswith(expected_suffix) or entry["original_sha256"] != row["sha256"] or entry["original_size_bytes"] != row["size_bytes"]:
            fail(f"archived/raw log identity mismatch: rank {row['rank']}")
        checked += 1

    # Compact contract checks keep the narrative attached to measured records.
    if cf_audit["by_band_and_phase"]["LW"]["RAIN"]["omitted_to_native_path_ratio_over_all_logged_native_paths"] != "0.2818130495330095537711645540":
        fail("CF0 LW rain ratio differs from retained audit")
    if cf_audit["by_band_and_phase"]["SW"]["RAIN"]["omitted_to_native_path_ratio_over_all_logged_native_paths"] != "0.2666622438009969176055481300":
        fail("CF0 SW rain ratio differs from retained audit")

    rfmip = load_json(ROOT / "rfmip/summary.json")
    if rfmip["execution"]["sha256"] != manifest["external_pins"]["rfmip_execution_receipt_sha256"]:
        fail("RFMIP receipt pin mismatch")
    if rfmip["execution"]["standalone_sw_solver_calls"] != 2 or rfmip["execution"]["wrf_or_real_forecasts"] != 0:
        fail("RFMIP invocation scope mismatch")
    if rfmip["strict_comparison"]["published_atol"] != 1e-5 or rfmip["strict_comparison"]["rtol"] != 0:
        fail("RFMIP strict threshold mismatch")
    if rfmip["arms"]["old_solar"]["prewrite_outside_target_float32_rounding_interval"] != 155:
        fail("RFMIP old-solar rounding-interval count mismatch")
    if rfmip["arms"]["old_solar"]["selected_prewrite_values_over_1e-5"] != 99:
        fail("RFMIP old-solar prewrite threshold count mismatch")
    if rfmip["cross_arm"]["captured_gas_optics_bitwise_equal_all_profiles"] is not True:
        fail("RFMIP solar-only gas-optics control failed")
    terminal_review = load_json(ROOT / "rfmip/terminal-review.json")
    if terminal_review.get("status") != "PASS_SCOPED_DIAGNOSTIC_RECOMPUTATION_STRICT_REFERENCE_FAIL_PRESERVED":
        fail("RFMIP terminal review status mismatch")
    if terminal_review.get("original_receipt_unchanged") is not True:
        fail("RFMIP terminal review did not preserve original receipt")
    terminal_manifest = load_json(ROOT / "rfmip/terminal-review-manifest.json")
    review_map = {
        "README.md": "terminal-review-README.md",
        "metric-readback.json": "terminal-review-metric-readback.json",
        "review-command.log": "terminal-review-command.log",
        "review.json": "terminal-review.json",
        "review.py": "terminal-review.py",
    }
    for entry in terminal_manifest["files"]:
        package_name = review_map.get(entry["path"])
        if package_name is None:
            fail(f"unexpected terminal review artifact: {entry['path']}")
        p = ROOT / "rfmip" / package_name
        if not p.is_file() or p.stat().st_size != entry["size_bytes"] or sha256(p) != entry["sha256"]:
            fail(f"terminal review artifact mismatch: {entry['path']}")

    print(f"PASS: {checked} file/log hashes and scoped evidence contracts verified")
    print("External binaries, coefficient/input NetCDFs, and raw RFMIP captures are hash-pinned but intentionally not packaged.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # report a concise failure in offline CI/use
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
