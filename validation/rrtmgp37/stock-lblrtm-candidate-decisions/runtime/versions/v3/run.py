#!/usr/bin/env python3
"""One-use, externally authorized incremental build / one-case LBLRTM runner.

This preparation was not executed during creation. It never retries either child.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
STAGE = HERE / "staging"
SRC = STAGE / "source" / "LBLRTM"
BUILD_CWD = SRC / "build"
RUN = HERE / "runs" / "od-v3"
TIMEOUT_BUILD = 600
TIMEOUT_SOLVER = 7200


def sha(path: Path) -> tuple[str, int]:
    h = hashlib.sha256(); size = 0
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b: break
            size += len(b); h.update(b)
    return h.hexdigest(), size


def canonical(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def durable_new(path: Path, obj: Any) -> str:
    data = canonical(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    dfd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return hashlib.sha256(data).hexdigest()


def plan_data() -> dict[str, Any]:
    p = json.loads(PLAN.read_text())
    if p.get("schema") != "UDM37_LBLRTM_CANDIDATE_DECISION_RUN_V1":
        raise RuntimeError("unexpected plan schema")
    return p


def digest_matches(path: Path, expected: dict[str, Any]) -> None:
    h, n = sha(path)
    if h != expected["sha256"] or n != expected["size_bytes"]:
        raise RuntimeError(f"pin mismatch: {path}")


def validate_auth(auth_path: Path, action: str, p: dict[str, Any]) -> dict[str, Any]:
    if not auth_path.is_file() or auth_path.resolve().is_relative_to(HERE.resolve()):
        raise RuntimeError("authorization must be an external file")
    a = json.loads(auth_path.read_text())
    expected = {
        "schema": "UDM37_CANDIDATE_DECISION_ACTION_AUTH_V1",
        "authorized": True,
        "action": action,
        "plan_sha256": sha(PLAN)[0],
        "runner_sha256": sha(Path(__file__))[0],
        "stage_receipt_sha256": sha(STAGE / "stage-receipt.json")[0],
        "max_build_invocations": 1,
        "max_solver_invocations": 1,
    }
    for k, v in expected.items():
        if a.get(k) != v: raise RuntimeError(f"authorization mismatch: {k}")
    if action == "build" and a.get("scope") != p["authorization_scopes"]["build"]:
        raise RuntimeError("build authorization scope mismatch")
    if action == "solver" and a.get("scope") != p["authorization_scopes"]["solver"]:
        raise RuntimeError("solver authorization scope mismatch")
    return a


def controlled_env(p: dict[str, Any]) -> tuple[dict[str, str], str]:
    home = os.environ.get("HOME")
    if not home: raise RuntimeError("HOME is unset")
    env = {"HOME": home, "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
           "LD_LIBRARY_PATH": p["environment"]["LD_LIBRARY_PATH"]}
    return env, home


def terminate_and_reap(proc: subprocess.Popen[Any]) -> int:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            return proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            return proc.wait(timeout=10)
    return int(proc.returncode)


def run_child(action: str, command: list[str], cwd: Path, timeout: int,
              receipt_name: str, p: dict[str, Any]) -> int:
    receipt = HERE / receipt_name
    lock = HERE / (action + "-one-use.lock")
    if receipt.exists() or lock.exists():
        raise RuntimeError(f"{action} already attempted; no retry is permitted")
    auth_path = Path(p["authorization_files"][action]).resolve(strict=True)
    auth = validate_auth(auth_path, action, p)
    env, home = controlled_env(p)
    lock_record = {"action": action, "authorization_sha256": sha(auth_path)[0],
                   "plan_sha256": sha(PLAN)[0], "created_epoch": time.time(),
                   "one_use": True}
    durable_new(lock, lock_record)  # retained even on any failure
    stdout_path = HERE / (action + "-stdout.log")
    stderr_path = HERE / (action + "-stderr.log")
    launch_path = HERE / (action + "-launch.json")
    proc = None; start = time.time(); timed_out = False; rc = None
    try:
        if any(q.exists() for q in (stdout_path, stderr_path, launch_path)):
            raise RuntimeError(f"stale {action} outputs exist")
        with stdout_path.open("xb") as out, stderr_path.open("xb") as err:
            proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, start_new_session=True)
            durable_new(launch_path, {"action": action, "command": command, "cwd": str(cwd),
                "pid": proc.pid, "started_epoch": start, "timeout_seconds": timeout,
                "authorization_sha256": sha(auth_path)[0], "home_unchanged": True,
                "environment": {k: env[k] for k in ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH")}})
            try: rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                rc = terminate_and_reap(proc)
        # This durable child-return record is written before any log/output hashing or comparison.
        exec_record = {"schema": "UDM37_CANDIDATE_DECISION_CHILD_EXECUTION_V1",
            "action": action, "status": "TIMED_OUT" if timed_out else ("RC0" if rc == 0 else "NONZERO_RC"),
            "pid": proc.pid if proc else None, "actual_child_returncode": rc,
            "timed_out": timed_out, "started_epoch": start, "ended_epoch": time.time(),
            "timeout_seconds": timeout, "command": command, "cwd": str(cwd),
            "home_unchanged": os.environ.get("HOME") == home,
            "authorization_sha256": sha(auth_path)[0]}
        durable_new(receipt, exec_record)
    except BaseException as e:
        if proc is not None: rc = terminate_and_reap(proc)
        failure = {"schema": "UDM37_CANDIDATE_DECISION_CHILD_EXECUTION_V1",
            "action": action, "status": "RUNNER_EXCEPTION_AFTER_LAUNCH" if proc else "LAUNCH_FAILED",
            "actual_child_returncode": rc, "timed_out": timed_out,
            "pid": proc.pid if proc else None, "exception": repr(e),
            "started_epoch": start, "ended_epoch": time.time(), "timeout_seconds": timeout}
        if not receipt.exists(): durable_new(receipt, failure)
        raise
    return int(rc)


def build_once(p: dict[str, Any]) -> int:
    auth = validate_auth(Path(p["authorization_files"]["build"]).resolve(strict=True), "build", p)
    # Verify staged source/object baseline before child invocation.
    digest_matches(Path(p["stage_receipt_pin"]["path"]), p["stage_receipt_pin"])
    digest_matches(Path(p["case_stage_pin"]["path"]), p["case_stage_pin"])
    src = SRC / "src/oprop.f90"
    digest_matches(src, p["candidate_source"])
    objdir = SRC / p["object_directory"]
    before = {x["path"]: x["sha256"] for x in p["prebuild_objects"]}
    if set(before) != {str(x.relative_to(SRC)) for x in objdir.glob("*.o")}:
        raise RuntimeError("staged object roster differs from preparation receipt")
    for rel, h in before.items():
        if sha(SRC / rel)[0] != h: raise RuntimeError(f"staged object changed before build: {rel}")
    exe = SRC / p["executable_relative_path"]
    digest_matches(exe, p["prebuild_executable"])
    makefile = BUILD_CWD / "make_lblrtm"
    digest_matches(makefile, p["makefile_pin"])
    rc = run_child("build", ["/usr/bin/make", "-f", "make_lblrtm", "linuxGNUdbl"],
                   BUILD_CWD, TIMEOUT_BUILD, "build-execution.json", p)
    if rc != 0:
        durable_new(HERE / "build-postflight.json", {"status":"BUILD_CHILD_FAILED_NO_OUTPUT_COMPARISON",
            "actual_child_returncode":rc,"timeout_seconds":TIMEOUT_BUILD})
        return rc
    # Build inspection starts only after durable RC0.
    after = {x["path"]: sha(SRC / x["path"])[0] for x in p["prebuild_objects"]}
    changed = sorted(k for k in before if before[k] != after[k])
    exe_sha, exe_size = sha(exe)
    status = "BUILD_RC0_INCREMENTAL_OPROP_ONLY" if changed == [p["oprop_object_relative_path"]] and exe_sha != p["prebuild_executable"]["sha256"] else "BUILD_RC0_SCOPE_MISMATCH_PRESERVED"
    durable_new(HERE / "build-postflight.json", {"status":status,"actual_child_returncode":rc,
        "changed_objects":changed,"object_hashes_after":after,
        "executable":{"path":str(exe),"sha256":exe_sha,"size_bytes":exe_size},
        "build_execution_sha256":sha(HERE/"build-execution.json")[0],
        "authorization_sha256":sha(Path(p["authorization_files"]["build"]))[0]})
    return 0 if status == "BUILD_RC0_INCREMENTAL_OPROP_ONLY" else 3


def input_inventory(p: dict[str, Any]) -> list[dict[str, Any]]:
    rows=json.loads((RUN/"case-stage.json").read_text())["inputs"]
    for row in rows:
        q=RUN/row["path"]
        if row["kind"]=="copied_input":
            digest_matches(q,{"sha256":row["sha256"],"size_bytes":row["size_bytes"]})
        else:
            if not q.is_symlink() or str(q.resolve(strict=True)) != row["resolved_path"]:
                raise RuntimeError("staged symlink identity changed: "+row["path"])
    return rows


def solver_once(p: dict[str, Any]) -> int:
    digest_matches(Path(p["stage_receipt_pin"]["path"]), p["stage_receipt_pin"])
    digest_matches(Path(p["case_stage_pin"]["path"]), p["case_stage_pin"])
    bp=json.loads((HERE/"build-postflight.json").read_text())
    be=json.loads((HERE/"build-execution.json").read_text())
    if be.get("actual_child_returncode") != 0 or bp.get("status") != "BUILD_RC0_INCREMENTAL_OPROP_ONLY":
        raise RuntimeError("solver is gated on RC0 and exact oprop-only build postflight")
    exe=SRC/p["executable_relative_path"]
    digest_matches(exe,bp["executable"])
    input_inventory(p)
    if any(x.is_file() and not x.is_symlink() and x.name not in {"case-stage.json"} for x in RUN.rglob("*")):
        raise RuntimeError("unexpected prelaunch output in fresh solver directory")
    rc=run_child("solver",[str(exe)],RUN,TIMEOUT_SOLVER,"solver-execution.json",p)
    if rc != 0:
        durable_new(HERE/"solver-postflight.json", {"status":"CHILD_FAILED_OUTPUT_COMPARISON_NOT_RUN",
            "actual_child_returncode":rc,"execution_sha256":sha(HERE/"solver-execution.json")[0]})
        return rc
    # Only after the durable RC0 receipt may output files be opened/hashed.
    ignored={"TAPE5","case-stage.json","prepared.json","authorization.json",
             "solver-stdout.log","solver-stderr.log","solver-launch.json",
             "solver-execution.json","solver-postflight.json"}
    outputs=[]
    for q in sorted(RUN.rglob("*")):
        if q.is_symlink() or q.is_dir() or q.name in ignored: continue
        h,n=sha(q); outputs.append({"path":q.relative_to(RUN).as_posix(),"sha256":h,"size_bytes":n})
    baseline=json.loads(Path(p["baseline_output_receipt"]["path"]).read_text())
    expected={x["path"] for x in baseline["outputs"]}
    actual={x["path"] for x in outputs}
    durable_new(HERE/"solver-postflight.json", {
        "status":"RC0_OUTPUTS_INVENTORIED_COMPARISON_PENDING",
        "actual_child_returncode":rc,"execution_sha256":sha(HERE/"solver-execution.json")[0],
        "baseline_postflight_sha256":p["baseline_output_receipt"]["sha256"],
        "output_count":len(outputs),"outputs":outputs,
        "missing_baseline_output_names":sorted(expected-actual),
        "additional_output_names":sorted(actual-expected),
        "comparison_policy":"A subsequent saved-output reader may compare only after this durable RC0 receipt. No tolerance change or physical acceptance is defined here."})
    return 0


def main() -> int:
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build",action="store_true")
    g.add_argument("--solver",action="store_true")
    ap.add_argument("--authorization",type=Path,required=True)
    a=ap.parse_args(); p=plan_data()
    if a.build:
        if a.authorization.resolve()!=Path(p["authorization_files"]["build"]).resolve(): raise RuntimeError("wrong authorization path")
        return build_once(p)
    if a.solver:
        if a.authorization.resolve()!=Path(p["authorization_files"]["solver"]).resolve(): raise RuntimeError("wrong authorization path")
        return solver_once(p)
    return 2

if __name__=="__main__":
    try: raise SystemExit(main())
    except BaseException as e:
        if isinstance(e,SystemExit): raise
        print(f"runner error: {e}",file=sys.stderr); raise SystemExit(2)
