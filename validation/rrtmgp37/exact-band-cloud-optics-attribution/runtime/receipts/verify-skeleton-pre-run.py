#!/usr/bin/env python3
"""Read-only verification of the exact-band package skeleton; no solver calls."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sys


def digest(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
            size += len(block)
    return h.hexdigest(), size


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> None:
    root = Path(__file__).resolve().parent
    plan = json.loads((root / "plan-not-run.json").read_text())
    if plan.get("status") != "NOT_RUN" or plan.get("runtime_calls_executed") != 0:
        fail("skeleton status is not NOT_RUN/zero calls")
    calls = plan.get("calls", [])
    if len(calls) != 2 or any(c.get("status") != "NOT_RUN" for c in calls):
        fail("expected exactly two planned, not-run calls")

    checked = []
    for group in ("prepared_assets", "reused_evidence"):
        for name, item in plan[group].items():
            path = (root / item["path"]).resolve()
            if not path.is_file():
                fail(f"missing {group}.{name}: {path}")
            got_sha, got_size = digest(path)
            if got_sha != item["sha256"]:
                fail(f"SHA mismatch {group}.{name}: {got_sha}")
            if "size_bytes" in item and got_size != item["size_bytes"]:
                fail(f"size mismatch {group}.{name}: {got_size}")
            checked.append(f"{group}.{name}")
    gz = (root / plan["reused_evidence"]["baseline_result_gzip"]["path"]).resolve()
    h = hashlib.sha256()
    size = 0
    with gzip.open(gz, "rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
            size += len(block)
    baseline = plan["reused_evidence"]["baseline_result_gzip"]
    if h.hexdigest() != baseline["decompressed_sha256"] or size != baseline["decompressed_size_bytes"]:
        fail("decompressed baseline result pin mismatch")

    for call in calls:
        for key in ("output", "log"):
            target = root / call[key]
            if target.exists() or target.is_symlink():
                fail(f"runtime {key} already exists: {target}")
    print(json.dumps({"status": "PREPARATION_SKELETON_VERIFIED_NOT_RUN",
                      "runtime_calls": 0, "checked_pins": checked,
                      "baseline_decompressed_sha256": h.hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
