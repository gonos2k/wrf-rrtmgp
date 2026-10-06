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
PLAN = HERE / "plan-v5.json"
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
    """Install one receipt atomically without overwriting an earlier outcome."""
    data = canonical(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    with tmp.open("xb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    try:
        os.link(tmp, path)  # atomic create-if-absent; never replace a prior receipt
    finally:
        try: tmp.unlink()
        except FileNotFoundError: pass
    dfd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return hashlib.sha256(data).hexdigest()

def plan_data() -> dict[str, Any]:
    p = json.loads(PLAN.read_text())
    if p.get("schema") != "UDM37_LBLRTM_CANDIDATE_DECISION_RUN_V2":
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


def terminate_and_reap(proc: subprocess.Popen[Any]) -> dict[str, Any]:
    errors=[]; rc=proc.poll(); reaped=(rc is not None)
    if not reaped:
        try: os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError: errors.append("SIGTERM process group already absent")
        except OSError as e: errors.append("SIGTERM: "+repr(e))
        try:
            rc=proc.wait(timeout=10); reaped=True
        except subprocess.TimeoutExpired:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: errors.append("SIGKILL process group already absent")
            except OSError as e: errors.append("SIGKILL: "+repr(e))
            try: rc=proc.wait(timeout=10); reaped=True
            except subprocess.TimeoutExpired: errors.append("wait after SIGKILL timed out")
        except OSError as e: errors.append("wait after SIGTERM: "+repr(e))
    if rc is None: rc=proc.poll()
    return {"actual_child_returncode":rc,"reaped":reaped or proc.poll() is not None,
            "cleanup_errors":errors}


def run_child(action: str, command: list[str], cwd: Path, timeout: int,
              receipt_name: str, p: dict[str, Any]) -> dict[str, Any]:
    receipt=HERE/receipt_name; lock=HERE/(action+"-one-use.lock")
    if receipt.exists() or lock.exists(): raise RuntimeError(f"{action} already attempted; no retry")
    auth_path=Path(p["authorization_files"][action]).resolve(strict=True)
    validate_auth(auth_path,action,p)
    env,home=controlled_env(p)
    durable_new(lock,{"action":action,"authorization_sha256":sha(auth_path)[0],
        "plan_sha256":sha(PLAN)[0],"created_epoch":time.time(),"one_use":True})
    outpath=HERE/(action+"-stdout.log"); errpath=HERE/(action+"-stderr.log")
    launch=HERE/(action+"-launch.json"); proc=None; started=time.time(); timed_out=False
    try:
        if any(x.exists() for x in (outpath,errpath,launch)):
            raise RuntimeError(f"stale {action} output/launch receipt exists")
        with outpath.open("xb") as out,errpath.open("xb") as err:
            proc=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,
                stdout=out,stderr=err,start_new_session=True)
            durable_new(launch,{"action":action,"command":command,"cwd":str(cwd),
                "pid":proc.pid,"started_epoch":started,"timeout_seconds":timeout,
                "authorization_sha256":sha(auth_path)[0],"home_unchanged":True,
                "environment":{k:env[k] for k in ("PATH","LANG","LC_ALL","LD_LIBRARY_PATH")}})
            try: rc=proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True; reap=terminate_and_reap(proc); rc=reap["actual_child_returncode"]
        record={"schema":"UDM37_CANDIDATE_DECISION_CHILD_EXECUTION_V1",
            "action":action,"status":"TERMINAL" if not timed_out and rc is not None else ("TIMED_OUT" if timed_out else "REAP_PENDING"),
            "child_status":"CHILDRC0" if rc==0 else ("CHILD_NONZERO_RC" if rc is not None else "UNKNOWN_RC"),
            "exception":None,"pid":proc.pid if proc else None,
            "actual_child_returncode":rc,"timed_out":timed_out,
            "reaped":proc is not None and proc.poll() is not None,
            "started_epoch":started,"ended_epoch":time.time(),"timeout_seconds":timeout,
            "command":command,"cwd":str(cwd),"home_unchanged":os.environ.get("HOME")==home,
            "authorization_sha256":sha(auth_path)[0]}
        if timed_out: record["cleanup_errors"]=reap.get("cleanup_errors",[])
        durable_new(receipt,record)  # RC/status is durable before any log/output processing
        return record
    except BaseException as e:
        cleanup=terminate_and_reap(proc) if proc is not None else {"actual_child_returncode":None,"reaped":False,"cleanup_errors":[]}
        failure={"schema":"UDM37_CANDIDATE_DECISION_CHILD_EXECUTION_V1",
            "action":action,"status":"RUNNER_EXCEPTION_AFTER_LAUNCH" if proc else "LAUNCH_FAILED",
            "child_status":"CHILDRC0" if cleanup["actual_child_returncode"]==0 else "CHILD_FAILURE_OR_UNKNOWN",
            "exception":repr(e),"pid":proc.pid if proc else None,
            "actual_child_returncode":cleanup["actual_child_returncode"],
            "timed_out":timed_out,"reaped":cleanup["reaped"],"cleanup_errors":cleanup["cleanup_errors"],
            "started_epoch":started,"ended_epoch":time.time(),"timeout_seconds":timeout}
        if not receipt.exists(): durable_new(receipt,failure)
        raise

def build_once(p: dict[str, Any]) -> int:
    # Authenticate the pinned copy and ensure this path is genuinely an incremental OPROP build.
    digest_matches(Path(p["stage_receipt_pin"]["path"]),p["stage_receipt_pin"])
    digest_matches(Path(p["case_stage_pin"]["path"]),p["case_stage_pin"])
    src=SRC/"src/oprop.f90"; digest_matches(src,p["candidate_source"])
    objdir=SRC/p["object_directory"]
    before={x["path"]:x["sha256"] for x in p["prebuild_objects"]}
    if set(before)!={str(x.relative_to(SRC)) for x in objdir.glob("*.o")}: raise RuntimeError("object roster mismatch")
    for rel,h in before.items():
        if sha(SRC/rel)[0]!=h: raise RuntimeError("prebuild object changed: "+rel)
    exe=SRC/p["executable_relative_path"]; digest_matches(exe,p["prebuild_executable"])
    digest_matches(BUILD_CWD/"make_lblrtm",p["makefile_pin"])
    digest_matches(BUILD_CWD/"makefile.common",p["make_common_pin"])
    if src.stat().st_mtime_ns <= (objdir/"oprop.o").stat().st_mtime_ns:
        raise RuntimeError("candidate source is not newer than donor oprop.o")
    rec=run_child("build",["/usr/bin/make","-f","make_lblrtm","linuxGNUdbl"],BUILD_CWD,TIMEOUT_BUILD,"build-execution.json",p)
    rc=rec.get("actual_child_returncode")
    if rc!=0 or rec.get("status")!="TERMINAL" or rec.get("exception") is not None or rec.get("timed_out"):
        durable_new(HERE/"build-postflight.json",{"status":"BUILD_NOT_ACCEPTED_NO_OBJECT_COMPARISON",
            "actual_child_returncode":rc,"execution_sha256":sha(HERE/"build-execution.json")[0],
            "terminal":rec.get("status")=="TERMINAL","exception":rec.get("exception"),"timed_out":rec.get("timed_out")})
        return 124 if rec.get("timed_out") and rc==0 else (int(rc) if rc is not None else 125)
    # Hash object/executable outputs only after the actual RC0 receipt above is durable.
    after={x["path"]:sha(SRC/x["path"])[0] for x in p["prebuild_objects"]}
    changed=sorted(k for k in before if before[k]!=after[k]); exesha,exesize=sha(exe)
    status="BUILD_RC0_INCREMENTAL_OPROP_ONLY" if changed==[p["oprop_object_relative_path"]] and exesha!=p["prebuild_executable"]["sha256"] else "BUILD_RC0_SCOPE_MISMATCH_PRESERVED"
    durable_new(HERE/"build-postflight.json",{"status":status,"actual_child_returncode":rc,
        "terminal":True,"exception":None,"timed_out":False,"changed_objects":changed,
        "object_hashes_after":after,"executable":{"path":str(exe),"sha256":exesha,"size_bytes":exesize},
        "execution_sha256":sha(HERE/"build-execution.json")[0],"authorization_sha256":rec["authorization_sha256"]})
    return 0 if status=="BUILD_RC0_INCREMENTAL_OPROP_ONLY" else 3


def input_inventory(p: dict[str, Any]) -> list[dict[str, Any]]:
    rows=json.loads((RUN/"case-stage.json").read_text())["inputs"]; actual=[]
    for row in rows:
        q=RUN/row["path"]
        expected_sha=row.get("sha256",row.get("source_sha256_receipt"))
        expected_size=row.get("size_bytes",row.get("source_size_bytes_receipt"))
        if row["kind"]=="readonly_symlink_input":
            if not q.is_symlink() or str(q.resolve(strict=True))!=row["resolved_path"]:
                raise RuntimeError("staged symlink identity changed: "+row["path"])
        elif q.is_symlink(): raise RuntimeError("copied input became a symlink: "+row["path"])
        got,size=sha(q)
        if got!=expected_sha or size!=expected_size: raise RuntimeError("input bytes differ: "+row["path"])
        actual.append({"path":row["path"],"sha256":got,"size_bytes":size})
    return actual


def solver_once(p: dict[str, Any]) -> int:
    digest_matches(Path(p["stage_receipt_pin"]["path"]),p["stage_receipt_pin"])
    digest_matches(Path(p["case_stage_pin"]["path"]),p["case_stage_pin"])
    bp=json.loads((HERE/"build-postflight.json").read_text())
    if bp.get("status")!="BUILD_RC0_INCREMENTAL_OPROP_ONLY" or bp.get("actual_child_returncode")!=0 or bp.get("exception") is not None or bp.get("timed_out"):
        raise RuntimeError("solver gated on completed RC0 oprop-only build")
    exe=SRC/p["executable_relative_path"]; digest_matches(exe,bp["executable"])
    initial=input_inventory(p)
    expected_regular={r["path"] for r in json.loads((RUN/"case-stage.json").read_text())["inputs"] if r["kind"]=="copied_input"}
    expected_regular.add("case-stage.json")
    regular={q.relative_to(RUN).as_posix() for q in RUN.rglob("*") if q.is_file() and not q.is_symlink()}
    if regular!=expected_regular: raise RuntimeError(f"unexpected prelaunch regular files: {sorted(regular^expected_regular)}")
    rec=run_child("solver",[str(exe)],RUN,TIMEOUT_SOLVER,"solver-execution.json",p)
    rc=rec.get("actual_child_returncode")
    if not rec.get("reaped",False):
        durable_new(HERE/"solver-postflight.json",{"status":"REAP_PENDING_OUTPUT_COMPARISON_SKIPPED",
            "actual_child_returncode":rc,"terminal":False,"timed_out":rec.get("timed_out"),
            "exception":rec.get("exception"),"reaped":False,"input_pins_before":initial,
            "execution_sha256":sha(HERE/"solver-execution.json")[0]})
        return 125
    after_inputs=[]; input_error=None
    try: after_inputs=input_inventory(p)
    except Exception as e: input_error=repr(e)
    terminal=(rec.get("status")=="TERMINAL" and rec.get("exception") is None and not rec.get("timed_out") and rc==0)
    if not terminal:
        durable_new(HERE/"solver-postflight.json",{"status":"CHILD_FAILURE_OUTPUT_COMPARISON_SKIPPED",
            "actual_child_returncode":rc,"terminal":rec.get("status")=="TERMINAL",
            "timed_out":rec.get("timed_out"),"exception":rec.get("exception"),
            "input_pins_before":initial,"input_pins_after":after_inputs,"input_error":input_error,
            "execution_sha256":sha(HERE/"solver-execution.json")[0]})
        return 124 if rec.get("timed_out") and rc==0 else (int(rc) if rc is not None else 125)
    if input_error is not None or initial != after_inputs:
        durable_new(HERE/"solver-postflight.json",{"status":"INPUT_POST_PIN_FAILED_OUTPUT_COMPARISON_SKIPPED",
            "actual_child_returncode":rc,"terminal":True,"timed_out":False,"exception":None,
            "input_pins_before":initial,"input_pins_after":after_inputs,"input_error":input_error,
            "execution_sha256":sha(HERE/"solver-execution.json")[0]})
        return 3
    # Do not inspect output bytes until the durable terminal RC0 record exists.
    ignored={"TAPE5","case-stage.json","prepared.json","authorization.json",
        "solver-stdout.log","solver-stderr.log","solver-launch.json","solver-execution.json","solver-postflight.json"}
    outputs=[]
    for q in sorted(RUN.rglob("*")):
        if q.is_symlink() or q.is_dir() or q.relative_to(RUN).as_posix() in {r["path"] for r in json.loads((RUN/"case-stage.json").read_text())["inputs"]}: continue
        if q.name in ignored: continue
        h,n=sha(q); outputs.append({"path":q.relative_to(RUN).as_posix(),"sha256":h,"size_bytes":n})
    baseline=json.loads(Path(p["baseline_output_receipt"]["path"]).read_text())
    expected={x["path"] for x in baseline["outputs"]}; actual={x["path"] for x in outputs}
    durable_new(HERE/"solver-postflight.json",{"status":"RC0_OUTPUTS_INVENTORIED_COMPARISON_PENDING",
        "actual_child_returncode":rc,"terminal":True,"timed_out":False,"exception":None,
        "input_pins_before":initial,"input_pins_after":after_inputs,"input_error":input_error,
        "input_bytes_unchanged":initial==after_inputs and input_error is None,
        "execution_sha256":sha(HERE/"solver-execution.json")[0],
        "baseline_postflight_sha256":p["baseline_output_receipt"]["sha256"],
        "output_count":len(outputs),"outputs":outputs,
        "missing_baseline_output_names":sorted(expected-actual),"additional_output_names":sorted(actual-expected),
        "comparison_policy":"A saved-output comparison is permitted only after this terminal RC0 receipt; no tolerance/physics acceptance changes."})
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
