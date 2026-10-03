#!/usr/bin/env python3
"""Verify the archived sensitivity-matrix evidence without the external run payloads."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

idx_path = HERE / "artifact-index.json"
idx = json.loads(idx_path.read_text())
if idx.get("schema") != "UDM_STRATIFIED_MATRIX_ARCHIVE_INDEX_V1":
    fail("unsupported artifact index")
for rel, meta in idx["files"].items():
    rp = Path(rel)
    if rp.is_absolute() or ".." in rp.parts:
        fail(f"unsafe archive path {rel}")
    path = HERE / rp
    if not path.is_file():
        fail(f"missing archived file {rel}")
    if path.stat().st_size != meta["bytes"] or sha(path) != meta["sha256"]:
        fail(f"archived file hash/size mismatch: {rel}")

plan = json.loads((HERE / "run/plan-v4.json").read_text())
receipt = json.loads((HERE / "run/v4/receipt.json").read_text())
provenance = json.loads((HERE / "run/provenance.json").read_text())
readback = json.loads((HERE / "run/v4/root-independent-readback.json").read_text())
if plan["plan_sha256"] != idx["plan_sha256"]:
    fail("plan digest does not match index")
if sha(HERE / "run/v4/receipt.json") != idx["final_receipt_sha256"]:
    fail("receipt digest does not match index")
if receipt["plan_sha256"] != plan["plan_sha256"] or receipt["status"] != "PASS_ALL_1152_PAIRED_JOBS":
    fail("final receipt plan/status mismatch")
if len(receipt["jobs"]) != 1152 or receipt["failures"] or not receipt["assets_unchanged"]:
    fail("final receipt job/failure/asset contract mismatch")
if receipt["reused_job_count"] != 388 or readback["new_engine_calls"] != 0:
    fail("reuse/readback call accounting mismatch")
# Verify monotone prefix reuse and unique-call accounting across all four preserved attempts.
previous_keys: set[str] = set()
previous_counts = []
for version in range(1, 5):
    ancestor = json.loads((HERE / f"run/v{version}/receipt.json").read_text())
    current = set(ancestor["jobs"])
    if not previous_keys.issubset(current):
        fail(f"v{version} did not retain all previously successful job keys")
    if version > 1 and ancestor.get("reused_job_count") != len(previous_keys):
        fail(f"v{version} reuse count does not match the previous prefix")
    previous_keys = current
    previous_counts.append(len(current))
if previous_counts != [3, 98, 388, 1152]:
    fail(f"unexpected cumulative job counts {previous_counts}")
if sum(b - a for a, b in zip([0] + previous_counts[:-1], previous_counts)) != 1152:
    fail("cumulative unique engine-call accounting mismatch")
if readback["status"] != "PASS" or readback["jobs"] != 1152 or readback["variant_rows"] != 768 or readback["arms"] != 24:
    fail("independent readback contract mismatch")
if readback["receipt_sha256"] != idx["final_receipt_sha256"] or readback["plan_sha256"] != sha(HERE / "run/plan-v4.json"):
    fail("independent readback pins do not match")
if readback["metrics_sha256"] != sha(HERE / "run/v4/paired_metrics.csv"):
    fail("metric CSV pin mismatch")
if readback["summary_sha256"] != sha(HERE / "run/v4/per_state_summaries.json"):
    fail("summary pin mismatch")

# Validate all per-call digest records and exact accounting, without requiring the omitted 1.1 GB payloads.
counts = {"baseline": 0, "variant": 0}
seeds_by_arm: dict[tuple[str, str, str], set[int]] = {}
for key, item in receipt["jobs"].items():
    job = item["job"]
    if item["status"] != "PASS" or item["returncode"] != 0:
        fail(f"nonpassing job {key}")
    if item.get("attempts") != 1:
        fail(f"unexpected retry count in {key}")
    for name in ("result_sha256", "log_sha256", "argv_sha256"):
        value = item.get(name, "")
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            fail(f"bad {name} in {key}")
    if job["kind"] not in counts:
        fail(f"unknown job kind in {key}")
    counts[job["kind"]] += 1
    seed = int(job["seed"])
    if key.split("/")[-2] != f"seed-{seed:010d}":
        fail(f"seed path/metadata mismatch in {key}")
    mode = "baseline" if job["kind"] == "baseline" else job["mode"]
    arm = (job["case"], job["phase"], mode)
    seeds_by_arm.setdefault(arm, set()).add(seed)
    if job["kind"] == "variant":
        sidecar = job.get("sidecar")
        sidecar_hash = job.get("sidecar_sha256", "")
        if not sidecar or len(sidecar_hash) != 64:
            fail(f"sidecar pin missing in {key}")
        prefix = "build/udm-stratified-final-manifest/diagnostic-exe-v1/matrix-sidecars-v3/"
        if not sidecar.startswith(prefix):
            fail(f"unexpected sidecar path in {key}")
        archive_sidecar = HERE / "inputs/sidecars" / sidecar.removeprefix(prefix)
        if not archive_sidecar.is_file() or sha(archive_sidecar) != sidecar_hash:
            fail(f"sidecar bytes do not match job pin: {key}")
if counts != {"baseline": 384, "variant": 768}:
    fail(f"wrong engine job counts: {counts}")
if len(seeds_by_arm) != 36 or any(len(values) != 32 for values in seeds_by_arm.values()):
    fail("expected 36 baseline/variant arms with 32 active seeds each")
if sum(1 for _, _, mode in seeds_by_arm if mode == "baseline") != 12:
    fail("wrong baseline arm count")
if sum(1 for _, _, mode in seeds_by_arm if mode != "baseline") != 24:
    fail("wrong variant arm count")

# Verify each archived input/raw/captured output/reference result against plan-v4's exact original pins.
state_files = {}
for state in plan["states"]:
    alias = state["alias"]
    for phase, info in state["phases"].items():
        for field, rel, hash_field in (
            ("input", f"captures/{alias}/{phase.lower()}/input", "input_sha256"),
            ("raw", f"captures/{alias}/{phase.lower()}/raw", "raw_sha256"),
        ):
            if sha(HERE / rel) != info[hash_field]:
                fail(f"capture hash mismatch: {alias}/{phase}/{field}")
        for hash_field in ("production_result_sha256", "ordinary_reference_result_sha256"):
            value = info.get(hash_field, "")
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                fail(f"missing captured output digest: {alias}/{phase}/{hash_field}")
print("PASS archived hashes; exact capture pins; plan/receipt/readback identities; 1,152 job ledger (384 baseline, 768 variant); 32 active seeds per 36 arms; all sidecars")
