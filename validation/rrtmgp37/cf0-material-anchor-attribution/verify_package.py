#!/usr/bin/env python3
"""Verify the closed, portable CF0 material-anchor evidence bundle."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "artifact-manifest-v1.json"

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def main() -> None:
    m = json.loads(MANIFEST.read_text())
    if m.get("schema") != "CF0_MATERIAL_ANCHOR_CLOSED_ARTIFACT_MANIFEST_V1":
        raise SystemExit("unexpected manifest schema")
    expected = m["files"]
    actual = sorted(p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and p != MANIFEST and "__pycache__" not in p.parts)
    if actual != sorted(expected):
        raise SystemExit(f"closed-roster mismatch: missing={sorted(set(expected)-set(actual))}, extra={sorted(set(actual)-set(expected))}")
    for rel, pin in expected.items():
        p = HERE / rel
        if p.stat().st_size != pin["size_bytes"] or digest(p) != pin["sha256"]:
            raise SystemExit(f"artifact pin mismatch: {rel}")
    ledger = json.loads((HERE / "eight-call-ledger-v2.json").read_text())
    calls = ledger["calls"]
    if len(calls) != 8 or len({c["call_id"] for c in calls}) != 8 or len({c["pid"] for c in calls}) != 8:
        raise SystemExit("expected eight distinct call IDs and PIDs")
    if any(c["returncode"] != 0 for c in calls) or ledger["actual_reference_solver_calls"] != 8 or ledger["wrf_forecasts"] != 0:
        raise SystemExit("call accounting or return-code contract failed")
    if sum(c["attempt"] == "first_attempt" for c in calls) != 2 or sum(c["attempt"] == "continuation" for c in calls) != 6:
        raise SystemExit("expected exactly two historical calls and six continuation calls")
    if ledger["first_attempt"]["status"] != "FAILED_STOPPED; two launched children returned 0; the old parser rejected AUDIT_EXTRA_PRECIP_TAU; six calls were not started." or ledger["continuation"]["status"] != "ALL_SIX_NEW_CALLS_VALIDATED":
        raise SystemExit("historical failure/continuation states do not match the preserved record")
    for c in calls:
        compressed = HERE / c["package_output"]["path"]
        raw = gzip.decompress(compressed.read_bytes())
        if hashlib.sha256(raw).hexdigest() != c["source_output_sha256"]:
            raise SystemExit(f"compressed result does not match original output: {c['call_id']}")
    review = json.loads((HERE / ledger["independent_terminal_review"]["path"]).read_text())
    if review.get("status") != "PASS_SCOPED_INDEPENDENT_OPTICS_DIRECT_HEATING_AND_HELD_FIELDS":
        raise SystemExit("independent terminal review is not the expected scoped pass")
    if review.get("builds") != 0 or review.get("forecasts") != 0:
        raise SystemExit("unexpected build/forecast count in terminal review")
    print(f"PASS: {len(expected)} pinned files; 8 unique reference calls; compressed outputs match original bytes")

if __name__ == "__main__":
    main()
