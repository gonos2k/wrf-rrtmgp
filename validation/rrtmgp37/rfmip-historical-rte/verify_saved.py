#!/usr/bin/env python3
"""Verify the closed evidence package and reproduce its saved-only analysis."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    manifest_path = HERE / "package-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    expected = manifest.get("files")
    if manifest.get("schema") != "UDM37_RFMIP_HISTORICAL_RTE_EVIDENCE_PACKAGE_V1" or not isinstance(expected, dict):
        raise ValueError("package manifest schema/roster invalid")
    actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and p != manifest_path}
    if actual != set(expected):
        raise ValueError(f"package file roster mismatch; extra={sorted(actual-set(expected))}, missing={sorted(set(expected)-actual)}")
    for rel, pin in expected.items():
        p = HERE / rel
        if not p.is_file() or p.is_symlink() or p.stat().st_size != pin["size_bytes"] or sha(p) != pin["sha256"]:
            raise ValueError(f"package file pin mismatch: {rel}")
    analysis = HERE / "two_by_two_analysis.json"
    result = subprocess.run([sys.executable, "-B", str(HERE / "analyze_historical_rte.py")],
                            check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"saved-only analysis failed: {result.stderr[-2000:]}")
    if sha(analysis) != expected["two_by_two_analysis.json"]["sha256"] or analysis.stat().st_size != expected["two_by_two_analysis.json"]["size_bytes"]:
        raise ValueError("recomputed analysis differs from the packaged result")
    report = json.loads(analysis.read_text())
    if report.get("status") != "PASS_SCOPED_HISTORICAL_REPLAY_AND_COMPONENT_DECOMPOSITION_NOT_GLOBAL_STRICT_PASS":
        raise ValueError("analysis scope/status changed")
    print(json.dumps({"status": "PASS_SAVED_PACKAGE_AND_ANALYSIS", "files": len(expected),
                      "analysis_sha256": sha(analysis), "rte_calls": 40,
                      "strict_global_gate_changed": False, "scientific_execution": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
