#!/usr/bin/env python3
"""One-use standalone natural cloud-top-shrink retention fixture; no WRF forecast."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

HELPER_SHA256 = "b287ddb29ac58fb9abda16077c6b38c0b22baef5b691bd64bd22bf54daae94ea"
UDM_SHA256 = "18bac4328061b828c1a57fcbead77986eb71bf5b6a56985fbed0672647bc7d4d"
PARENT_REVISION = "e3b9e52c2a20811830a27d34420721ca89b62e59"
PARENT_UDM_SHA256 = "7998df8f1f6a3b9f63f285a60016447cbbcf4802b7a31a711442c90b8c59a8fc"
STRICT = ["-g", "-ffree-form", "-ffree-line-length-none", "-fcheck=all",
          "-finit-real=snan", "-ffpe-trap=invalid,zero,overflow", "-fbacktrace", "-fno-fast-math"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "size_bytes": len(data), "sha256": sha(data)}


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def run_one(argv: list[str], cwd: Path, log: Path, record: dict[str, object], receipt: Path,
            records: list[dict[str, object]], timeout: int = 180) -> None:
    record.update(argv=argv, cwd=str(cwd), log_path=str(log), timeout_seconds=timeout, status="PREPARED")
    records.append(record); atomic(receipt, STATE)
    proc = None
    try:
        with log.open("xb") as out:
            proc = subprocess.Popen(argv, cwd=cwd, stdout=out, stderr=subprocess.STDOUT,
                                    start_new_session=True, env={**os.environ, "LC_ALL":"C", "OMP_NUM_THREADS":"1"})
            record.update(pid=proc.pid, status="RUNNING", started_unix=time.time())
            atomic(receipt, STATE)
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                os.killpg(proc.pid, signal.SIGKILL)
                rc = proc.wait()
            except BaseException:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                rc = proc.wait()
                record.update(actual_returncode=rc, ended_unix=time.time(), status="INTERRUPTED")
                out.flush(); os.fsync(out.fileno()); atomic(receipt, STATE)
                raise
            out.flush(); os.fsync(out.fileno())
        record.update(actual_returncode=rc, ended_unix=time.time(), timed_out=bool(record.get("timed_out", False)), status="PROCESS_COMPLETE")
        # Persist the child's actual status before reading/classifying any output.
        atomic(receipt, STATE)
        record["log_sha256"] = sha(log.read_bytes())
        if record["timed_out"]: raise RuntimeError(f"timeout: {record['role']}")
        if rc != 0: raise RuntimeError(f"nonzero child rc={rc}: {record['role']}")
        record["status"] = "PASS_RC0"
        atomic(receipt, STATE)
    except BaseException:
        if proc is None:
            record.update(status="NOT_LAUNCHED", ended_unix=time.time())
            atomic(receipt, STATE)
        raise


def validate_traces(traces: list[dict[str, object]]) -> dict[str, object]:
    groups: dict[tuple[int,int], dict[tuple[int,int], dict[str,object]]] = {}
    for row in traces:
        key=(int(row["branch"]),int(row["mode"]))
        slot=(int(row["site"]),int(row["phase"]))
        if slot in groups.setdefault(key, {}): raise ValueError(f"duplicate slope marker {key}/{slot}")
        groups[key][slot]=row
    expected={(b,m) for b in (1,2,3) for m in (0,1,2)}
    if set(groups)!=expected: raise ValueError(f"wrong branch/mode trace roster: {sorted(groups)}")
    result=[]
    for key, rows in sorted(groups.items()):
        if set(rows)!={(1,0),(1,1),(2,0),(2,1)}: raise ValueError(f"incomplete marker quartet {key}")
        first0,first1,second0,second1=(rows[k] for k in ((1,0),(1,1),(2,0),(2,1)))
        if [int(x["cloud_top"]) for x in (first0,first1,second0,second1)] != [5,5,4,4]:
            raise ValueError(f"unexpected top sequence at {key}: {[x['cloud_top'] for x in (first0,first1,second0,second1)]}")
        vals=[x["rslopec2"] for x in (first0,first1,second0,second1)]
        if not all(len(x)==7 and all(math.isfinite(float(v)) for v in x) for x in vals):
            raise ValueError(f"nonfinite or malformed slope vector {key}")
        init, computed, pre2, post2=(float(x[4]) for x in vals)
        if not (computed != init and computed == pre2 == post2):
            raise ValueError(f"k5 value not computed then exactly retained at {key}: {(init,computed,pre2,post2)}")
        result.append({"branch":key[0],"density_mode":key[1],"first_top":5,"second_top":4,
                       "k5_initializer":init,"k5_first_call_post":computed,
                       "k5_second_call_pre_post":pre2,"retained_exactly":True})
    return {"all_nine_records_pass":True,"records":result}


STATE: dict[str, object]

def main() -> int:
    global STATE
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("wrf_root",type=Path)
    ap.add_argument("--workdir",type=Path,required=True)
    ap.add_argument("--compiler",default=shutil.which("gfortran") or "gfortran")
    args=ap.parse_args()
    wrf=args.wrf_root.resolve(strict=True); work=args.workdir.resolve()
    if work.exists(): raise FileExistsError(f"refusing existing experiment root: {work}")
    work.mkdir(parents=True,exist_ok=False)
    here=Path(__file__).resolve(); driver=here.with_suffix(".f90")
    helper=wrf/"test/rrtmgp/test_udm_rain_only_slopes.py"
    if sha(helper.read_bytes())!=HELPER_SHA256: raise ValueError("corrected shared helper pin mismatch")
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location("rain_slope_helper",helper)
    h=importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
    source=wrf/"phys/module_mp_udm.F"
    deps=[wrf/"phys/module_mp_radar.F",wrf/"phys/module_gfs_machine.F"]
    compiler=Path(shutil.which(args.compiler) or args.compiler).resolve(strict=True)
    repo=wrf.parent
    baseline=subprocess.check_output(["git","show",f"{PARENT_REVISION}:WRF/phys/module_mp_udm.F"],cwd=repo)
    if sha(baseline)!=PARENT_UDM_SHA256: raise ValueError("historical baseline identity mismatch")
    pins={"candidate_udm":pin(source),"driver":pin(driver),"runner":pin(here),"helper":pin(helper),
          "dependencies":[pin(p) for p in deps],"compiler":pin(compiler),
          "repository_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()}
    if pins["candidate_udm"]["sha256"]!=UDM_SHA256: raise ValueError("candidate source hash mismatch")
    STATE={"schema":"udm-cloud-top-shrink-native-v1","status":"RUNNING","source_pins_before":pins,
           "baseline_context":{"revision":PARENT_REVISION,"udm_sha256":sha(baseline),"compiled":False},
           "counts":{"compile_link_processes":0,"fixture_processes":0,"udm_invocations":0,
                     "WRF_forecasts":0,"REAL_calls":0,"RTE_calls":0},"processes":[],"optimization_results":{}}
    receipt=work/"execution-receipt.json"; records=STATE["processes"]; atomic(receipt,STATE)
    stub=work/"module_wrf_error.f90"
    stub.write_text("module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\ninteger,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\n",encoding="ascii")
    try:
        for opt in ("O0","O2"):
            d=work/opt/"candidate"; d.mkdir(parents=True)
            udmfile=d/"module_mp_udm.F"; instrumented=h.instrument_candidate(source.read_bytes()); udmfile.write_bytes(instrumented)
            STATE.setdefault("instrumented_candidate",{})[opt]={"sha256":sha(instrumented),"size_bytes":len(instrumented)}
            include=["-I",str(d),"-J",str(d)]; flags=[f"-{opt}",*STRICT]
            sources=[deps[1],stub,deps[0],udmfile]; objects=[]
            for src in sources:
                obj=d/(src.stem+".o"); extra=["-ffixed-form"] if src.name=="module_gfs_machine.F" else ["-ffree-form","-ffree-line-length-none"]
                cflags=flags if src==udmfile else [f"-{opt}","-g",*extra]
                rec={"role":"compile","optimization":opt,"source":str(src)}
                run_one([str(compiler),*cflags,*include,"-cpp","-c",str(src),"-o",str(obj)],d,d/f"compile-{src.stem}.log",rec,receipt,records)
                STATE["counts"]["compile_link_processes"]+=1; atomic(receipt,STATE); objects.append(obj)
            exe=d/"shrink_fixture"
            rec={"role":"link","optimization":opt}
            run_one([str(compiler),*flags,"-cpp",*include,str(driver),*map(str,objects),"-o",str(exe)],d,d/"link.log",rec,receipt,records)
            STATE["counts"]["compile_link_processes"]+=1; atomic(receipt,STATE)
            log=d/"profile6.log"; rec={"role":"fixture","optimization":opt,"case_id":6}
            run_one([str(exe)],d,log,rec,receipt,records)
            STATE["counts"]["fixture_processes"]+=1; STATE["counts"]["udm_invocations"]+=9; atomic(receipt,STATE)
            parsed,traces=h.parse_output(log.read_text(errors="replace"),6,True)
            if len(parsed)!=9: raise ValueError(f"expected 9 finite outputs, got {len(parsed)}")
            retention=validate_traces(traces)
            STATE["optimization_results"][opt]={"actual_returncode":rec["actual_returncode"],"log":pin(log),
                "output_records":len(parsed),"slope_trace_records":len(traces),"retention":retention}
            atomic(receipt,STATE)
        after={"candidate_udm":pin(source),"driver":pin(driver),"runner":pin(here),"helper":pin(helper),
               "dependencies":[pin(p) for p in deps],"compiler":pin(compiler)}
        for k in ("candidate_udm","driver","runner","helper","dependencies","compiler"):
            if after[k]!=pins[k]: raise ValueError(f"source/tool pin changed during experiment: {k}")
        STATE["source_pins_after"]=after
        STATE["status"]="PASS_SCOPED_NATURAL_SHRINK_AND_SLOPE_RETENTION"
        STATE["limitations"]=["Synthetic homogeneous-freezing mechanism fixture only; no meteorological frequency claim.",
                              "Candidate only; no original-versus-candidate comparison.",
                              "No rain initialized; no downstream qrcon-consumer claim."]
        atomic(receipt,STATE)
        print(json.dumps({"status":STATE["status"],"receipt":pin(receipt),"counts":STATE["counts"]},indent=2))
        return 0
    except BaseException as exc:
        STATE.update(status="FAIL_PRESERVED_STOPPED",error=f"{type(exc).__name__}: {exc}")
        STATE["counts"]["compile_link_processes"]=sum(x.get("pid") and x["role"] in ("compile","link") for x in records)
        STATE["counts"]["fixture_processes"]=sum(x.get("pid") and x["role"]=="fixture" for x in records)
        STATE["counts"]["udm_invocations"]=9*STATE["counts"]["fixture_processes"]
        atomic(receipt,STATE)
        print(json.dumps({"status":STATE["status"],"error":STATE["error"],"receipt":pin(receipt)},indent=2))
        return 1

if __name__=="__main__":
    raise SystemExit(main())
