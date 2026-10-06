#!/usr/bin/env python3
"""Fail-closed, offline pre-invocation authorization check for a CF0 audit.

This does not execute the reference solver. A separate reviewed launcher must
consume the emitted receipt once, durably record its child before comparison,
and recheck pins after the child exits.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sidecar_validator", HERE / "validate_sidecar.py")
validator = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)

class GateError(ValueError):
    pass

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def require_hash(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        raise GateError(f"missing {label}: {path}")
    actual = sha(path)
    if actual != expected:
        raise GateError(f"{label} SHA256 mismatch: expected {expected}, got {actual}")
    return actual

def preflight(approval: dict, base: Path, output: Path) -> dict:
    """Validate one immutable case against a post-build exact approval JSON.

    Required keys: schema, approved, permit_id, case_id, phase, species,
    executable, source, source_manifest, build_manifest, raw, input, sidecar,
    data_files, runtime_files, argv. Each file record is {path, sha256}; paths
    are relative to the approval file.
    """
    if approval.get("schema") != "cf0-audit-invocation-approval-v1":
        raise GateError("unsupported approval schema")
    if approval.get("approved") is not True:
        raise GateError("approval is not explicitly true")
    if not all(isinstance(approval.get(k), str) and approval[k].strip()
               for k in ("permit_id", "case_id", "phase", "species")):
        raise GateError("permit/case/phase/species identity is incomplete")
    if approval["phase"] not in ("LW", "SW") or approval["species"] not in ("rain", "snow"):
        raise GateError("unsupported phase/species")
    if not isinstance(approval.get("argv"), list) or len(approval["argv"]) != 7:
        raise GateError("exact solver argv is required")
    files = {}
    for name in ("executable", "source", "source_manifest", "build_manifest", "raw", "input", "sidecar"):
        record = approval.get(name)
        if not isinstance(record, dict) or not isinstance(record.get("path"), str) or not isinstance(record.get("sha256"), str):
            raise GateError(f"missing exact {name} path/hash")
        p = (base / record["path"]).resolve()
        files[name] = (p, require_hash(p, record["sha256"], name))
    def verify_group(group_name: str, label: str, must_nonempty: bool):
        pins = approval.get(group_name)
        if not isinstance(pins, list) or (must_nonempty and not pins):
            raise GateError(f"{label} pins are required")
        checked = []
        for item in pins:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
                raise GateError(f"malformed {label} pin")
            p = (base / item["path"]).resolve()
            checked.append({"path": str(p), "sha256": require_hash(p, item["sha256"], label)})
        return checked
    data_files = verify_group("data_files", "coefficient/data file", True)
    runtime = verify_group("runtime_files", "resolved runtime library", True)
    sidecar_text = files["sidecar"][0].read_text()
    summary = validator.validate_against_raw(sidecar_text, files["raw"][0], approval["species"],
                                             int(approval.get("engine_layers", 0)), files["input"][0])
    if summary["phase"] != approval["phase"]:
        raise GateError("raw/sidecar phase differs from approved phase")
    expected_argv = [str(x) for x in approval["argv"]]
    exe = str(files["executable"][0])
    sidecar = str(files["sidecar"][0])
    # Exact argv must name the pinned executable and sidecar; no path rewriting
    # is allowed after approval.
    if expected_argv[0] != exe or expected_argv[2] != str(files["input"][0]) or expected_argv[6] != sidecar:
        raise GateError("approved argv does not bind the exact executable and sidecar paths")
    receipt = {
        "schema": "cf0-audit-preflight-receipt-v1",
        "status": "PREFLIGHT_PASS_NO_SOLVER_INVOKED",
        "permit_id": approval["permit_id"], "case_id": approval["case_id"],
        "phase": approval["phase"], "species": approval["species"],
        "argv": expected_argv,
        "files": {k: {"path": str(v[0]), "sha256": v[1]} for k, v in files.items()},
        "runtime_files": runtime,
        "sidecar_validation": summary,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "solver_invocations": 0,
        "launcher_must_recheck_after_exit": True,
    }
    if output.exists():
        raise GateError(f"refusing to overwrite preflight receipt: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt

def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "exe").write_bytes(b"exe")
        (d / "src").write_bytes(b"src")
        (d / "raw").write_text("RRTMGP_RAW_V1\nLW 3 4 2\nCF 2\n0 0\nRWP_OMITTED 2\n1 0\nSWP_OMITTED 2\n0 0\nRES 2\n20 20\nSOURCE_RE_SNOW 2\n0.00002 0.00002\nHAS_REQS 1\n1\n")
        raw = d / "raw"
        inputp = d / "input"
        inputp.write_text("RRTMGP_REPLAY_V1\nRES 1 3\n20 20 20\n")
        side = d / "side"
        side.write_text(validator.encode("LW", 1, 2, 1, 1.0, [[1.,0.]], [[0.,0.]], [[0.,0.]], 3))
        (d / "lib").write_bytes(b"lib")
        def rec(p): return {"path": p.name, "sha256": sha(p)}
        approval = {"schema":"cf0-audit-invocation-approval-v1", "approved":True,
                    "permit_id":"mock-1", "case_id":"mock-case", "phase":"LW", "species":"rain",
                    "engine_layers":3, "executable":rec(d/"exe"), "source":rec(d/"src"),
                    "source_manifest":rec(d/"src"), "build_manifest":rec(d/"src"),
                    "raw":rec(raw), "input":rec(inputp), "sidecar":rec(side),
                    "data_files":[rec(d/"lib")], "runtime_files":[rec(d/"lib")],
                    "argv":[str(d/"exe"),"data",str(inputp),"out","0","",str(side)]}
        result = preflight(approval, d, d/"receipt.json")
        assert result["status"] == "PREFLIGHT_PASS_NO_SOLVER_INVOKED"
        assert result["solver_invocations"] == 0
        bad = dict(approval); bad["approved"] = False
        try: preflight(bad, d, d/"bad.json")
        except GateError: pass
        else: raise AssertionError("unapproved preflight was accepted")
        changed = dict(approval); changed["sidecar"] = dict(approval["sidecar"], sha256="0"*64)
        try: preflight(changed, d, d/"changed.json")
        except GateError: pass
        else: raise AssertionError("sidecar hash drift was accepted")
    src = (HERE / "reference_column.proposed.f90").read_text()
    assert "audit_sidecar_path=''\n  CALL get_command_argument(6,audit_sidecar_path)" in src
    assert "USE, INTRINSIC :: iso_fortran_env, ONLY: real64,iostat_end" in src
    assert "IF(stat/=iostat_end) ERROR STOP 'I/O error checking audit sidecar end-of-file'" in src
    assert src.count("\nCONTAINS\n") == 1
    assert "SUBROUTINE read_cf0_native_section" in src

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--approval", type=Path)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()
    if args.self_test:
        self_test()
        print("invocation gate self-test PASS; solver_invocations=0")
        raise SystemExit(0)
    if not args.approval or not args.receipt:
        ap.error("use --self-test or --approval EXACT.json --receipt NEW.json")
    approval = json.loads(args.approval.read_text())
    preflight(approval, args.approval.resolve().parent, args.receipt)
    print(f"PREFLIGHT_PASS_NO_SOLVER_INVOKED: {args.receipt}")
