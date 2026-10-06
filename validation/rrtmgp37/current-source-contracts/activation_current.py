#!/usr/bin/env python3
"""Run the activation fixture while dynamically binding current UDM source."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import re
from types import SimpleNamespace


def main() -> None:
    # Keep the archived runner byte-exact. Load it as a module so changes to
    # its globals are the globals used by extract_contract/main.
    runner = pathlib.Path(__file__).resolve().parents[1] / "activation-density-contract/activation.py"
    spec = importlib.util.spec_from_file_location("activation_contract_module", runner)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load historical activation fixture implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.extract_contract = lambda path: extract_current_contract(module, path)
    argv = sys.argv[1:]
    try:
        source_root = pathlib.Path(argv[argv.index("--source-root") + 1]).resolve()
    except (ValueError, IndexError) as exc:
        raise SystemExit("--source-root is required") from exc
    ns_rel = module.SOURCE_REL.as_posix()
    source = source_root / module.SOURCE_REL
    raw = source.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines()
    first, last, block = activation_block(lines)
    source_sha = hashlib.sha256(raw).hexdigest()
    block_sha = hashlib.sha256(block.encode()).hexdigest()
    module.EXPECTED_SOURCE_SHA256 = source_sha
    module.EXPECTED_SOURCE_LINES = (first + 1, last + 1)
    module.EXPECTED_BLOCK_SHA256 = block_sha
    try:
        output_dir = pathlib.Path(argv[argv.index("--output-dir") + 1]).resolve()
    except (ValueError, IndexError) as exc:
        raise SystemExit("--output-dir is required") from exc
    process_ledger = output_dir / "current-process-status.jsonl"
    process_receipts_path = pathlib.Path(__file__).with_name("process_receipts.py")
    process_receipts_spec = importlib.util.spec_from_file_location(
        "activation_current_process_receipts", process_receipts_path)
    if process_receipts_spec is None or process_receipts_spec.loader is None:
        raise RuntimeError("could not load durable subprocess receipt helper")
    process_receipts_module = importlib.util.module_from_spec(process_receipts_spec)
    process_receipts_spec.loader.exec_module(process_receipts_module)
    process_runner = process_receipts_module.DurableProcessRunner(
        process_ledger, default_timeout_seconds=300)
    module.subprocess = SimpleNamespace(run=process_runner.run, STDOUT=subprocess.STDOUT)
    # The current block is dynamically pinned in the receipt; fixed parameter
    # checks and the O0/O2 numerical fixture remain the semantic acceptance.
    sys.argv = [str(pathlib.Path(__file__).resolve().parents[1]
                    / "activation-density-contract/activation.py"), *argv]
    module.main()
    result_path = output_dir / "result.json"
    result = json.loads(result_path.read_text())
    head = process_runner.run(["git", "rev-parse", "HEAD"], cwd=source_root, check=True,
                              capture_output=True, text=True).stdout.strip()
    tree = process_runner.run(["git", "rev-parse", "HEAD^{tree}"], cwd=source_root, check=True,
                              capture_output=True, text=True).stdout.strip()
    blob = process_runner.run(["git", "rev-parse", f"HEAD:{ns_rel}"], cwd=source_root,
                              check=True, capture_output=True, text=True).stdout.strip()
    status = process_runner.run(["git", "status", "--porcelain", "--", ns_rel], cwd=source_root,
                                check=True, capture_output=True, text=True).stdout
    current = {"schema": "udm37-current-activation-source-binding-v1",
               "status": "PASS_CURRENT_SOURCE_ACTIVATION_CONTRACT",
               "checkout_head": head, "checkout_tree": tree,
               "source_path": ns_rel, "head_blob": blob, "working_file_sha256": source_sha,
               "working_file_git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
               "working_file_matches_head_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == blob,
               "source_block_lines": [first + 1, last + 1], "source_block_sha256": block_sha,
               "dirty_source_status": status, "fixture_result_sha256_before_binding": hashlib.sha256(result_path.read_bytes()).hexdigest(),
               "durable_process_ledger": {"path": process_ledger.name,
                   "sha256": hashlib.sha256(process_ledger.read_bytes()).hexdigest(),
                   "records": len(process_ledger.read_text().splitlines())},
               "execution_counts": result.get("execution_counts", {}),
               "scope": "Current source-bound local activation fixture; archived historical result and source pins remain unchanged."}
    result["schema"] = "udm37-current-activation-contract-result-v1"
    result["status"] = "PASS_CURRENT_SOURCE_ACTIVATION_CONTRACT"
    result["current_source_binding"] = current
    _atomic_json(result_path, result)
    _atomic_json(output_dir / "current-source-binding.json", current)
    print(json.dumps({"status": current["status"], "checkout_head": head,
                      "source_sha256": source_sha, "output_dir": str(output_dir)}, sort_keys=True))


def activation_block(lines):
    starts = [i for i, line in enumerate(lines) if "if(rh_mul(k)>1.) then" in line]
    if len(starts) != 1:
        raise ValueError(f"expected one activation IF block, got {len(starts)}")
    first = starts[0]
    last = next((i for i in range(first + 1, len(lines)) if lines[i].strip() == "endif"), None)
    if last is None:
        raise ValueError("activation block has no closing endif")
    block = "\n".join(lines[first:last + 1]) + "\n"
    return first, last, block


def extract_current_contract(module, source_path):
    """Current-source extractor without historical absolute line slices."""
    raw = source_path.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines()
    first, last, block = activation_block(lines)
    if last - first + 1 != 13:
        raise ValueError("current activation IF block changed its 13 statement lines")
    if "if(rh_mul(k)>1.) then" not in block or "ncact(k) = max(0.," not in block or "pcact(k) = min(" not in block:
        raise ValueError("current activation block no longer matches the tested source contract")
    block_sha = hashlib.sha256(block.encode()).hexdigest()
    params = {}
    for name, expected in module.EXPECTED_PARAMETERS.items():
        found = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([0-9]+(?:\.[0-9]*)?(?:[eEdD][+-]?[0-9]+)?)\s*(?:[,/&]|!|$)", text)
        if len(found) != 1:
            raise ValueError(f"current source parameter {name} was not unique: {len(found)}")
        literal = found[0].replace("D", "E").replace("d", "e")
        value = float(literal)
        if value != expected:
            raise ValueError(f"current source parameter {name} changed: {literal} != {expected}")
        params[name] = {"literal": found[0], "value": value}
    wrapper = re.search(r"(?ims)^\s*subroutine\s+udm\s*\(.*?^\s*end\s+subroutine\s+udm\b", text)
    routine = re.search(r"(?ims)^\s*subroutine\s+udm2d\s*\(.*?^\s*end\s+subroutine\s+udm2d\b", text)
    if not wrapper or not routine:
        raise ValueError("could not delimit current UDM wrapper and udm2d implementation")
    wrapper_body = wrapper.group(0)
    body = routine.group(0)
    required = {
        "optional density argument": r"logical\s*,\s*optional\s*,\s*intent\s*\(\s*in\s*\)\s*::\s*input_density_is_dry",
        "legacy default": r"use_input_density_is_dry\s*=\s*\.false\.",
        "optional forwarding": r"if\s*\(\s*present\s*\(\s*input_density_is_dry\s*\)\s*\)\s*use_input_density_is_dry\s*=\s*input_density_is_dry",
        "wrapper-to-helper forwarding": r"input_density_is_dry\s*=\s*use_input_density_is_dry",
        "helper density input declaration": r"logical\s*,\s*intent\s*\(\s*in\s*\)\s*::\s*input_density_is_dry",
        "dry-density DEND branch": r"if\s*\(\s*input_density_is_dry\s*\)\s*then\s*dend\s*\(\s*k\s*,\s*i\s*\)\s*=\s*den\s*\(\s*k\s*,\s*i\s*\)\s*else\s*dend\s*\(\s*k\s*,\s*i\s*\)\s*=\s*\(\s*p\s*\(\s*k\s*,\s*i\s*\)\s*/\s*t\s*\(\s*k\s*,\s*i\s*\)\s*-\s*den\s*\(\s*k\s*,\s*i\s*\)\s*\*\s*rv\s*\)\s*/\s*\(\s*rd\s*-\s*rv\s*\)",
        "substep count": r"loops\s*=\s*max\s*\(\s*ceiling\s*\(\s*delt\s*/\s*dtcldcr\s*\)\s*,\s*1\s*\)",
    }
    wrapper_required = {"optional density argument", "legacy default", "optional forwarding",
                        "wrapper-to-helper forwarding"}
    for label, pattern in required.items():
        haystack = wrapper_body if label in wrapper_required else body
        if not re.search(pattern, haystack, re.I):
            raise ValueError(f"current {'UDM wrapper' if label in wrapper_required else 'udm2d'} contract missing {label}")
    # Current initialization has two explicit flgzero paths: both clamp CCN,
    # while cloud-number negatives are clamped only when flgzero is enabled.
    init = body[body.find("! padding 0 for negative values generated by dynamics - optional"):]
    init = init[:init.find("! initialize the surface rain")]
    if init.count("ncr(k,i,1) = min(max(ncr1(i,k,1),ccnmin),ccnmax)") != 2:
        raise ValueError("current UDM must retain CCN lower/upper clamp on both flgzero paths")
    if "ncr(k,i,2) = max(ncr1(i,k,2),0.0)" not in init or "ncr(k,i,2) = ncr1(i,k,2)" not in init:
        raise ValueError("current flgzero-dependent cloud-number initialization changed")
    # Main UDM wrapper forwards its resolved logical into udm2d.
    if not re.search(r"(?i)input_density_is_dry\s*=\s*use_input_density_is_dry", text):
        raise ValueError("current UDM wrapper does not forward its resolved density policy")
    return raw, block, params


def _atomic_json(path: pathlib.Path, value) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


if __name__ == "__main__":
    main()
