#!/usr/bin/env python3
"""Verify packaged SURFRAD evidence hashes and internal provenance links."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", nargs="?", type=Path, default=Path(__file__).with_name("manifest.json"))
    args = ap.parse_args()
    manifest_path = args.manifest.resolve()
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    failures = []
    for item in manifest["files"]:
        rel = Path(item["path"])
        path = (root / rel).resolve()
        if root not in path.parents:
            failures.append(f"path escapes evidence root: {rel}")
        elif not path.is_file():
            failures.append(f"missing file: {rel}")
        elif path.stat().st_size != item["size_bytes"] or sha(path) != item["sha256"]:
            failures.append(f"size/hash mismatch: {rel}")

    scorer = root / "score_surfrad.py"
    report_path = root / "results/metrics.json"
    run_path = root / "results/run-receipt.json"
    metrics = json.loads(report_path.read_text())
    run = json.loads(run_path.read_text())
    if metrics.get("status") != "METRICS_COMPUTED":
        failures.append("metrics report does not have METRICS_COMPUTED status")
    if metrics.get("scoring_script", {}).get("sha256") != sha(scorer):
        failures.append("metrics scoring-script hash does not match packaged scorer")
    immutability = metrics.get("input_immutability", {})
    if not (immutability.get("all_unchanged") is True and immutability.get("history_file_count") == 50
            and immutability.get("sha256_before") == immutability.get("sha256_after")):
        failures.append("input immutability evidence is incomplete or failed")
    if run.get("return_code") != 0 or run.get("status") != "PASS":
        failures.append("recorded command receipt is not PASS/zero status")
    for station, filenames in {"FPK": ("fpk10162.dat", "fpk10163.dat"), "DRA": ("dra10162.dat", "dra10163.dat")}.items():
        expected = metrics.get("observation_file_hashes", {}).get(station, {})
        for label, filename in zip(("day", "next_day"), filenames):
            packaged = root / "surfrad" / filename
            if not packaged.is_file() or sha(packaged) != expected.get(label, {}).get("sha256"):
                failures.append(f"{station} {label} observation hash mismatch")
    for item in manifest["files"]:
        if item["path"] == "plot_surfrad_metrics.py":
            if run.get("plotter", {}).get("sha256") != item["sha256"]:
                failures.append("run receipt plotter hash differs from packaged plotter")
    if failures:
        print(json.dumps({"status": "FAIL", "failures": failures}, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "verified_files": len(manifest["files"]), "metric_status": metrics["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
