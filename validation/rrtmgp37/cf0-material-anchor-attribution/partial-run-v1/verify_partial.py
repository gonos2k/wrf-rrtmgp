#!/usr/bin/env python3
"""Verify the preserved two-call partial-run bundle; performs no solver calls."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def verify_pin(record: dict, path: Path) -> bytes:
    data = path.read_bytes()
    assert len(data) == record["size_bytes"], f"size mismatch: {path}"
    assert sha(data) == record["sha256"], f"SHA256 mismatch: {path}"
    return data

def main() -> None:
    manifest = json.loads((HERE / "partial-execution-v1.json").read_text())
    assert manifest["status"] == "PARTIAL_TWO_CALLS_ONLY_SIX_PENDING"
    assert manifest["actual_counts"] == {
        "standalone_solver_calls": 2,
        "calls_returned_zero": 2,
        "not_started": 6,
        "WRF": 0,
        "REAL": 0,
        "build": 0,
        "numerical_retries": 0,
    }

    receipt = json.loads((HERE / "execution.json").read_text())
    terminal = json.loads((HERE / "root-terminal-receipt.json").read_text())
    assert receipt["status"] == "FAILED_STOPPED"
    assert receipt["solver_invocations"] == 2
    assert terminal["actual_reference_executable_calls"] == 2
    assert terminal["actual_WRF_calls"] == terminal["actual_build_calls"] == 0
    started = [c for c in receipt["calls"] if c.get("returncode") is not None]
    pending = [c for c in receipt["calls"] if c.get("status") == "NOT_STARTED"]
    assert len(started) == 2 and len(pending) == 6
    assert all(c["returncode"] == 0 for c in started)

    result_by_id = {r["call_id"]: r for r in manifest["launched_calls"]}
    assert set(result_by_id) == {c["call_id"] for c in started}
    for call in started:
        record = result_by_id[call["call_id"]]
        gzpath = HERE.parent / record["compressed"]["path"]
        compressed = gzpath.read_bytes()
        assert len(compressed) == record["compressed"]["size_bytes"]
        assert sha(compressed) == record["compressed"]["sha256"]
        original = gzip.decompress(compressed)
        assert len(original) == record["original"]["size_bytes"]
        assert sha(original) == record["original"]["sha256"]
        assert call["output_pin"]["sha256"] == record["original"]["sha256"]
        assert call["output_pin"]["size_bytes"] == record["original"]["size_bytes"]

    for rec in manifest["logs"]:
        logdata = (HERE.parent / rec["package_path"]).read_bytes()
        assert len(logdata) == rec["package_size_bytes"]
        assert sha(logdata) == rec["package_sha256"]
    assert manifest["failure"].startswith("The first execution stopped during parsing")
    print("PASS: preserved partial bundle integrity (2 completed calls; 6 not started; no solver rerun)")

if __name__ == "__main__":
    main()
