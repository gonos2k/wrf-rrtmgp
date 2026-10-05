#!/usr/bin/env python3
"""Locked, one-condition saved-point reconstruction runner.

This runner performs one Python opacity construction only after a root-authored
packet binds the exact plan, runner and point source. It never invokes WRF,
REAL, RTE, a compiler, or another solver.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import traceback

SCHEMA = "udm37-bon-night-normal-positive-n2-point-runner-v2"
ROOT_DEFAULT = Path(__file__).resolve().parents[2]
PLAN_DEFAULT = ROOT_DEFAULT / "build/udm37-bon-night-normal-positive-n2-plan-v3/plan.json"
AUTH_DEFAULT = ROOT_DEFAULT / "build/udm37-bon-night-normal-positive-n2-math-v1/root-authorization.json"
OUT_DEFAULT = ROOT_DEFAULT / "build/udm37-bon-night-normal-positive-n2-math-v1/run-v1"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def durable_json(path: Path, obj: dict) -> None:
    """Durable mutable state snapshot; output directory is exclusively owned."""
    tmp = path.with_name(path.name + ".tmp")
    data = (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with tmp.open("xb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path); fsync_dir(path.parent)


def write_once(path: Path, data: bytes) -> None:
    """Publish an immutable artifact without replacing any prior bytes."""
    with path.open("xb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    fsync_dir(path.parent)


def resolve(root: Path, rec: dict) -> Path:
    p = Path(rec["path"])
    return p if p.is_absolute() else root / p


def walk_pins(x, where="plan"):
    if isinstance(x, dict):
        if {"path", "sha256", "size_bytes"}.issubset(x.keys()):
            yield where, x
        for k, v in x.items():
            yield from walk_pins(v, f"{where}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x): yield from walk_pins(v, f"{where}[{i}]")


def verify_pin(root: Path, where: str, rec: dict) -> dict:
    p = resolve(root, rec)
    if not p.exists() or not p.is_file():
        raise ValueError(f"pinned artifact target is not a regular file: {where}: {p}")
    resolved = p.resolve(strict=True)
    size = resolved.stat().st_size
    digest = sha(resolved)
    if size != int(rec["size_bytes"]) or digest != rec["sha256"]:
        raise ValueError(f"pinned artifact changed: {where}: {p}")
    return {"name": where, "path": str(resolved), "size_bytes": size, "sha256": digest}


def np_shape(value):
    if not isinstance(value, list): return []
    if not value: return [0]
    return [len(value)] + np_shape(value[0])

def ordered_u64(v: float) -> int:
    bits = struct.unpack(">Q", struct.pack(">d", float(v)))[0]
    return (~bits & ((1 << 64)-1)) if bits >> 63 else (bits | (1 << 63))


def summary(candidate, target, start: int, stop: int) -> dict:
    import numpy as np
    a = np.asarray(candidate, dtype=np.float64)[start:stop, :]
    b = np.asarray(target, dtype=np.float64)[start:stop, :]
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("comparison arrays must have matching finite shapes")
    d = b - a
    rel = np.divide(d, a, out=np.full_like(d, np.nan), where=(a != 0.0))
    ulps = [abs(ordered_u64(x) - ordered_u64(y)) for x, y in zip(a.ravel(), b.ravel())]
    return {"shape": list(a.shape), "elements": int(a.size),
            "signed_target_minus_construction": {"min": float(np.min(d)), "max": float(np.max(d)), "mean": float(np.mean(d))},
            "absolute": {"max": float(np.max(np.abs(d))), "rms": float(np.sqrt(np.mean(d*d)))},
            "relative_to_construction": {"max_abs_nonzero_denominator": float(np.nanmax(np.abs(rel))) if np.any(np.isfinite(rel)) else None,
                                         "zero_denominator_count": int(np.count_nonzero(a == 0.0))},
            "ordered_binary64_ulp": {"max": int(max(ulps)), "nonzero_count": int(sum(x != 0 for x in ulps))}}


def read_result(path: Path) -> dict:
    """Strictly parse a saved RRTMGP_RESULT_V1 packet after construction is durable."""
    import numpy as np
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RESULT_V1":
        raise ValueError("saved target is not RRTMGP_RESULT_V1")
    h = lines[1].split()
    if len(h) != 3 or h[0].upper() != "LW" or tuple(map(int, h[1:])) != (1, 45):
        raise ValueError("saved target header is not LW, 1 column, 45 layers")
    out, i = {}, 2
    while i < len(lines):
        if not lines[i].strip(): i += 1; continue
        fields = lines[i].split(); i += 1
        if len(fields) != 4: raise ValueError("malformed result section header")
        name = fields[0].upper()
        shape = tuple(int(x) for x in fields[1:])
        if name in out or len(shape) != 3 or any(x <= 0 for x in shape):
            raise ValueError(f"duplicate or invalid result section {name}")
        n = math.prod(shape); vals = []
        while len(vals) < n and i < len(lines):
            if lines[i].strip(): vals.extend(float(x.replace("D", "E").replace("d", "e")) for x in lines[i].split())
            i += 1
        if len(vals) != n: raise ValueError(f"truncated result section {name}")
        arr = np.asarray(vals, dtype=np.float64).reshape(shape, order="F")
        if not np.isfinite(arr).all(): raise ValueError(f"nonfinite result section {name}")
        out[name] = arr
    for name in ("GAS_TAU", "GAS_TAU_RAW", "GAS_COL_DRY"):
        if name not in out: raise ValueError(f"saved target lacks required {name}")
    for name in ("GAS_TAU", "GAS_TAU_RAW"):
        if out[name].shape != (1, 45, 128): raise ValueError(f"unexpected {name} dimensions {out[name].shape}")
    if out["GAS_COL_DRY"].shape != (1,45,1):
        raise ValueError(f"unexpected GAS_COL_DRY dimensions {out['GAS_COL_DRY'].shape}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="requires an exact root authorization packet")
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    ap.add_argument("--plan", type=Path, default=PLAN_DEFAULT)
    ap.add_argument("--authorization", type=Path, default=AUTH_DEFAULT)
    ap.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    root = args.root.resolve(); plan_path = args.plan.resolve(); auth_path = args.authorization.resolve(); out = args.output.resolve()
    if not args.execute:
        print("LOCKED: no reconstruction performed; pass --execute only with matching root authorization and independent review.")
        return 3
    plan_bytes = plan_path.read_bytes(); plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    runner_hash = sha(Path(__file__).resolve())
    plan = json.loads(plan_bytes)
    auth = json.loads(auth_path.read_text())
    req = plan["authorization"]["required_fields"]
    expected = {"schema": req["schema"], "authorized": True, "plan_sha256": plan_hash,
                "runner_sha256": runner_hash,
                "point_source_sha256": plan["pinned_artifacts"]["point_source"]["sha256"],
                "source_review_sha256": plan["pinned_artifacts"]["normal_positive_n2_source_review"]["sha256"],
                "precondition_receipt_sha256": plan["pinned_artifacts"]["input_precondition_pass"]["sha256"],
                "max_point_invocations": 1}
    for k, v in expected.items():
        if auth.get(k) != v: raise SystemExit(f"authorization mismatch for {k}")
    review_pin = auth.get("plan_runner_review")
    if not isinstance(review_pin, dict) or not {"path", "sha256", "size_bytes"}.issubset(review_pin):
        raise SystemExit("authorization lacks independent plan/runner review pin")
    review_path = resolve(root, review_pin)
    if review_path.is_symlink() or not review_path.is_file() or review_path.stat().st_size != int(review_pin["size_bytes"]) or sha(review_path) != review_pin["sha256"]:
        raise SystemExit("independent plan/runner review bytes do not match authorization")
    review_doc = json.loads(review_path.read_text())
    if review_doc.get("status") != "PASS_SCOPED_PLAN_AND_RUNNER_REVIEW":
        raise SystemExit("independent review status is not PASS_SCOPED_PLAN_AND_RUNNER_REVIEW")
    reviewed_plan = review_doc.get("reviewed_plan", {})
    reviewed_runner = review_doc.get("reviewed_runner", {})
    if reviewed_plan.get("sha256") != plan_hash or reviewed_runner.get("sha256") != runner_hash:
        raise SystemExit("independent review does not bind exact plan and runner hashes")
    if plan.get("schema") != "udm37-bon-night-normal-positive-n2-opacity-plan-v3":
        raise SystemExit("unexpected plan schema")
    pins_seen = [verify_pin(root, n, p) for n,p in walk_pins(plan)]
    review = json.loads(resolve(root, plan["pinned_artifacts"]["normal_positive_n2_source_review"]).read_text())
    pre = json.loads(resolve(root, plan["pinned_artifacts"]["input_precondition_pass"]).read_text())
    if review.get("status") != plan["source_review_gate"]["required_status"]:
        raise SystemExit("source review receipt status is not accepted")
    if pre.get("status") != plan["source_review_gate"]["precondition_required_status"] or pre.get("process_rc") != 0:
        raise SystemExit("positive-N2 input precondition receipt is not PASS")
    if pre.get("input", {}).get("sha256") != plan["pinned_artifacts"]["normal_input"]["sha256"]:
        raise SystemExit("input precondition receipt does not bind selected input")
    if plan.get("status") != "LOCKED_UNRUN_WAITING_ROOT_AUTHORIZATION_AND_PLAN_REVIEW":
        raise SystemExit("plan is not in locked state")
    expected_out = (root / plan["output_policy"]["output_dir"]).resolve()
    if out != expected_out:
        raise SystemExit(f"output path differs from frozen one-use plan: {out} != {expected_out}")
    if plan["output_policy"].get("must_be_absent") is not True or plan["output_policy"].get("no_overwrite") is not True or plan["output_policy"].get("retries") != 0:
        raise SystemExit("plan does not enforce the one-use absent-output contract")
    if out.exists(): raise SystemExit(f"refusing existing output directory: {out}")
    out.mkdir(parents=True, exist_ok=False); fsync_dir(out.parent)
    started = time.time()
    state = {"schema": SCHEMA, "status": "RUNNING_ONE_POINT", "plan_sha256":plan_hash,
             "runner_sha256":runner_hash, "authorization_sha256":sha(auth_path),
             "point_source_sha256":expected["point_source_sha256"], "started_unix":started,
             "verified_pin_count":len(pins_seen), "verified_pins_sha256":hashlib.sha256(json.dumps(pins_seen,sort_keys=True).encode()).hexdigest(),
             "point_invocations":0, "target_reads":0}
    durable_json(out/"execution-state.json",state)
    try:
        point_path = resolve(root, plan["pinned_artifacts"]["point_source"])
        sys.dont_write_bytecode = True
        spec=importlib.util.spec_from_file_location("locked_positive_n2_point", point_path)
        if spec is None or spec.loader is None: raise RuntimeError("cannot load locked point source")
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        state["point_invocations"] = 1
        durable_json(out/"execution-state.json",state)
        construction=module.reconstruct_point(plan,root)
        # The construction artifact is committed and hashed before opening the saved target.
        raw=(json.dumps(construction,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
        artifact=out/"construction.json.gz"
        with artifact.open("xb") as f:
            with gzip.GzipFile(fileobj=f,mode="wb",mtime=0,filename="") as gz: gz.write(raw)
            f.flush(); os.fsync(f.fileno())
        fsync_dir(out)
        art_rec={"path":artifact.name,"size_bytes":artifact.stat().st_size,"sha256":sha(artifact),"uncompressed_size_bytes":len(raw),"uncompressed_sha256":hashlib.sha256(raw).hexdigest()}
        receipt={"schema":"udm37-bon-night-normal-positive-n2-construction-receipt-v1","status":"CONSTRUCTION_DURABLE_TARGET_NOT_YET_READ","plan_sha256":plan_hash,"runner_sha256":runner_hash,"artifact":art_rec,"point_invocations":1}
        write_once(out/"construction-receipt.json", (json.dumps(receipt,sort_keys=True,indent=2,allow_nan=False)+"\n").encode())
        # Re-open only the construction artifact; verify it is complete before target parsing.
        if sha(artifact)!=art_rec["sha256"]: raise RuntimeError("construction gzip changed before target read")
        with gzip.open(artifact,"rb") as f: saved=f.read()
        if hashlib.sha256(saved).hexdigest()!=art_rec["uncompressed_sha256"]: raise RuntimeError("construction artifact failed readback")
        saved_obj=json.loads(saved)
        if len(saved_obj.get("cases", [])) != 1 or saved_obj["cases"][0].get("case_id") != "normal-positive-n2-captured-input":
            raise RuntimeError("construction must contain exactly the authorized positive-N2 case")
        saved_case=saved_obj["cases"][0]
        if len(saved_case.get("n2_vmr_values", [])) != 45 or len(saved_case.get("dry_column_molecule_cm2", [])) != 45 or np_shape(saved_case.get("tau_point")) != [45,128]:
            raise RuntimeError("construction case arrays do not satisfy the frozen 45x128 profile contract")
        import numpy as np
        if not all(math.isfinite(float(x)) for x in saved_case["n2_vmr_values"]):
            raise RuntimeError("construction N2 profile is nonfinite")
        target_path=resolve(root,plan["pinned_artifacts"]["actual_result"])
        target=read_result(target_path); state["target_reads"]=1; durable_json(out/"execution-state.json",state)
        case=saved_obj["cases"][0]
        candidate=np.asarray(case["tau_point"],dtype=np.float64)
        rawtau=target["GAS_TAU_RAW"][0]
        efftau=target["GAS_TAU"][0]
        if candidate.shape != (45,128): raise ValueError("constructed tau shape mismatch")
        dry=np.asarray(case["dry_column_molecule_cm2"],dtype=np.float64)
        targetdry=target["GAS_COL_DRY"][0,:,0]
        report={"schema":"udm37-bon-night-normal-positive-n2-point-comparison-v1","status":"DESCRIPTIVE_COMPARISON_COMPLETE_NO_ACCEPTANCE_THRESHOLD","plan_sha256":plan_hash,"construction_receipt_sha256":sha(out/"construction-receipt.json"),"target_result_sha256":plan["pinned_artifacts"]["actual_result"]["sha256"],"case_id":case["case_id"],"n2_profile":{"count":len(case["n2_vmr_values"]),"min":min(case["n2_vmr_values"]),"max":max(case["n2_vmr_values"]),"copied_from_input":True},"scope":{"layers":45,"native_prefix_layers":32,"pressure_extension_layers":13,"gpoints":128},"comparisons":{}}
        for name, c, t in (("GAS_COL_DRY",dry[:,None],targetdry[:,None]),("GAS_TAU_RAW",candidate,rawtau),("GAS_TAU",candidate,efftau)):
            report["comparisons"][name]={"all45":summary(c,t,0,45),"native32":summary(c,t,0,32),"pressure_extensions13":summary(c,t,32,45)}
        report["interpretation_limits"]=["This is one source-ordered Python binary64 reconstruction against one saved WRF call.","No threshold or fitted tolerance is applied; summaries are descriptive, not pass/fail accuracy gates.","The captured positive N2 values are input data, not proof of composition or unit validity.","No coefficient-generation, spectroscopy, physical accuracy, or broader radiative-residual cause is established."]
        write_once(out/"comparison.json", (json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+"\n").encode())
        state.update(status="COMPLETE_DESCRIPTIVE_ONLY",completed_unix=time.time(),actual_return_code=0,point_invocations=1,target_reads=1,construction_receipt_sha256=sha(out/"construction-receipt.json"),comparison_sha256=sha(out/"comparison.json"))
        durable_json(out/"execution-state.json",state)
        return 0
    except BaseException as e:
        state.update(status="FAILED_PRESERVED",completed_unix=time.time(),actual_return_code=1,error=repr(e),traceback=traceback.format_exc())
        # Save the failure receipt while preserving any durable construction artifact.
        durable_json(out/"execution-state.json",state)
        return 1

if __name__ == "__main__":
    sys.exit(main())
