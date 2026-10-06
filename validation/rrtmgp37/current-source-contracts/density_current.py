#!/usr/bin/env python3
"""Compile a small current-source density-policy fixture (never a WRF build)."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile
import time


REL = {
    "udm": "WRF/phys/module_mp_udm.F",
    "prep": "WRF/dyn_em/module_big_step_utilities_em.F",
    "driver": "WRF/phys/module_microphysics_driver.F",
    "constants": "WRF/share/module_model_constants.F",
}
EPS32 = 2.0 ** -23


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def f32(value: float) -> float:
    return struct.unpack("=f", struct.pack("=f", float(value)))[0]


def one(pattern: str, text: str, label: str, flags=0) -> re.Match[str]:
    matches = list(re.finditer(pattern, text, flags))
    if len(matches) != 1:
        raise ValueError(f"expected one {label}, found {len(matches)}")
    return matches[0]


def extract(root: Path):
    files = {k: root / rel for k, rel in REL.items()}
    texts = {k: p.read_text(errors="strict") for k, p in files.items()}
    hashes = {k: sha(p.read_bytes()) for k, p in files.items()}
    # Authenticate the current policy through source semantics, not an expected
    # whole-file digest that would break on unrelated future UDM edits.
    branch = one(
        r"(?ims)^\s*if\s*\(\s*input_density_is_dry\s*\)\s*then\s*\n"
        r"\s*dend\s*\(\s*k\s*,\s*i\s*\)\s*=\s*den\s*\(\s*k\s*,\s*i\s*\)\s*\n"
        r"\s*else\s*\n\s*dend\s*\(\s*k\s*,\s*i\s*\)\s*=\s*"
        r"\(\s*p\s*\(\s*k\s*,\s*i\s*\)\s*/\s*t\s*\(\s*k\s*,\s*i\s*\)\s*"
        r"-\s*den\s*\(\s*k\s*,\s*i\s*\)\s*\*\s*rv\s*\)\s*/\s*\(\s*rd\s*-\s*rv\s*\)"
        r"[^\n]*\n\s*endif",
        texts["udm"], "current DEND policy branch")
    # Verify the optional argument defaults to the legacy EOS policy.
    for pattern, label in (
        (r"logical\s*,\s*optional\s*,\s*intent\s*\(\s*in\s*\)\s*::\s*input_density_is_dry", "optional input declaration"),
        (r"use_input_density_is_dry\s*=\s*\.false\.", "default false policy"),
        (r"if\s*\(\s*present\s*\(\s*input_density_is_dry\s*\)\s*\)\s*use_input_density_is_dry\s*=\s*input_density_is_dry", "present-input forwarding"),
    ):
        one(pattern, texts["udm"], label, re.I)
    udm_calls = list(re.finditer(r"(?is)\bcall\s+udm\s*\((.*?)\n\s*\)", texts["driver"]))
    if not udm_calls:
        raise ValueError("current driver has no UDM call")
    dry_calls = [m.group(1) for m in udm_calls
                 if re.search(r"(?i)input_density_is_dry\s*=\s*\.true\.", m.group(1))]
    if not dry_calls:
        raise ValueError("no production UDM call passes the dry-density policy")
    host = one(r"(?m)^\s*rho\s*\(\s*i\s*,\s*k\s*,\s*j\s*\)\s*=\s*1\./\s*\(\s*al\(i,k,j\)\+alb\(i,k,j\)\)\s*$",
               texts["prep"], "host dry-density expression", re.I).group(0).strip()
    def constant(name: str) -> tuple[str, float]:
        match = one(rf"(?im)^\s*real\s*,\s*parameter\s*::\s*{name}\s*=\s*([0-9.eEdD+-]+)",
                    texts["constants"], f"{name} constant")
        return match.group(1), float(match.group(1).replace("D", "E").replace("d", "e"))
    rd_lit, rd = constant("r_d")
    rv_lit, rv = constant("r_v")
    if (rd, rv) != (287.0, 461.6):
        raise ValueError(f"current dry/vapor gas constants differ from the declared source contract: {(rd, rv)}")
    contract = {
        "files": files, "hashes": hashes, "texts": texts,
        "branch": branch.group(0).rstrip() + "\n", "host": host,
        "driver_call_count": len(udm_calls), "driver_dry_call_count": len(dry_calls),
        "rd_literal": rd_lit, "rd": rd, "rv_literal": rv_lit, "rv": rv,
    }
    return contract


def make_fixture(c):
    return f'''module current_density_fixture
 implicit none
 real, parameter :: rd={c['rd_literal']}, rv={c['rv_literal']}
contains
 subroutine host_density(al,alb,rho)
  real,intent(in)::al(1,1,1),alb(1,1,1)
  real,intent(out)::rho(1,1,1)
  integer::i,k,j
  do j=1,1; do k=1,1; do i=1,1
   {c['host']}
  enddo; enddo; enddo
 end subroutine
 subroutine policy(p,t,den,dend,input_density_is_dry)
  real,intent(in)::p(1,1),t(1,1),den(1,1)
  real,intent(out)::dend(1,1)
  logical,intent(in)::input_density_is_dry
  integer::i,k
  do k=1,1; do i=1,1
{c['branch']}  enddo; enddo
 end subroutine
end module
program current_density_cases
 use current_density_fixture
 implicit none
 real,parameter::rhos(3)=[0.5,1.0,1.5],qvs(5)=[0.0,0.001,0.01,0.02,0.03],temps(2)=[250.,300.]
 real::rho, qv, temp, alpha, al(1,1,1),alb(1,1,1),rh(1,1,1)
 real::p(1,1),t(1,1),den(1,1),dend_eos(1,1),dend_dry(1,1)
 integer::ir,iq,it,caseid
 write(*,'(A,1X,I0)') 'REAL_BITS',storage_size(0.)
 caseid=0
 do ir=1,3; do iq=1,5; do it=1,2
  caseid=caseid+1; rho=rhos(ir); qv=qvs(iq); temp=temps(it)
  alpha=1./rho; al=alpha; alb=0.; call host_density(al,alb,rh)
  t=temp; p=rho*temp*(rd+rv*qv); den=rh(:,:,1)
  call policy(p,t,den,dend_eos,.false.)
  call policy(p,t,den,dend_dry,.true.)
 write(*,'(4(I0,1X),10(ES24.16E3,1X))') caseid,ir,iq,it,rho,qv,temp,rh(1,1,1), &
    dend_eos(1,1),dend_dry(1,1),p(1,1),alpha,rd,rv
 enddo; enddo; enddo
end program
'''


def write_json(path: Path, obj):
    payload=(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,path)
        dfd=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root",required=True,type=Path)
    ap.add_argument("--output-dir",required=True,type=Path)
    ap.add_argument("--fc",default="gfortran")
    a=ap.parse_args(); root=a.source_root.resolve(); out=a.output_dir.resolve()
    if out.exists(): raise SystemExit(f"refusing existing output: {out}")
    c=extract(root); out.mkdir(parents=True)
    process_receipts_path = Path(__file__).with_name("process_receipts.py")
    process_receipts_spec = importlib.util.spec_from_file_location(
        "density_current_process_receipts", process_receipts_path)
    if process_receipts_spec is None or process_receipts_spec.loader is None:
        raise RuntimeError("could not load durable subprocess receipt helper")
    process_receipts_module = importlib.util.module_from_spec(process_receipts_spec)
    process_receipts_spec.loader.exec_module(process_receipts_module)
    process_ledger = out / "current-process-status.jsonl"
    process_runner = process_receipts_module.DurableProcessRunner(
        process_ledger, default_timeout_seconds=300)
    run_child = process_runner.run
    source=make_fixture(c); generated=out/"current_density_fixture.f90"; generated.write_text(source)
    head=run_child(["git","rev-parse","HEAD"],cwd=root,check=True,capture_output=True,text=True).stdout.strip()
    compiler=shlex.split(a.fc)
    version=run_child(compiler+["--version"],capture_output=True,text=True,timeout=30)
    if version.returncode: raise RuntimeError("compiler version probe failed")
    tree=run_child(["git","rev-parse","HEAD^{tree}"],cwd=root,check=True,capture_output=True,text=True).stdout.strip()
    source_files={}
    for k,rel in REL.items():
        blob=run_child(["git","rev-parse",f"HEAD:{rel}"],cwd=root,check=True,capture_output=True,text=True).stdout.strip()
        raw=(root/rel).read_bytes(); git_blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        dirty=run_child(["git","status","--porcelain","--",rel],cwd=root,check=True,capture_output=True,text=True).stdout
        source_files[k]={"path":rel,"working_file_sha256":c["hashes"][k],"head_blob":blob,
                         "working_file_git_blob":git_blob,"working_file_matches_head_blob":git_blob==blob,
                         "dirty_source_status":dirty}
    receipt={"schema":"udm37-current-density-policy-fixture-v1","status":"PREPARED",
             "checkout_head":head,"checkout_tree":tree,"source_files":source_files,
             "source_contract":{"host_dry_density":c["host"],"udm_branch":c["branch"],
                 "rd":c["rd_literal"],"rv":c["rv_literal"],"default_density_policy":False,
                 "explicit_host_policy":True,"udm_call_count":c["driver_call_count"],
                 "udm_dry_policy_call_count":c["driver_dry_call_count"]},"generated_source_sha256":sha(generated.read_bytes()),
             "compiler":{"argv":compiler,"version":version.stdout.splitlines()[0]},
             "durable_process_ledger":{"path":process_ledger.name},
             "execution":{"compile_count":0,"fixture_run_count":0,"WRF_builds":0,"models":0,"RTE_calls":0}}
    receipt_path=out/"receipt.json"; write_json(receipt_path,receipt)
    env=os.environ.copy(); env["OMP_NUM_THREADS"]="1"
    rows_by_opt=[]
    receipt["processes"]=[]
    for opt in ("O0","O2"):
        exe=out/f"fixture_{opt}"; clog=out/f"compile_{opt}.log"
        argv=compiler+[f"-{opt}","-std=f2008","-ffp-contract=off",str(generated),"-o",str(exe)]
        t0=time.time()
        with clog.open("wb") as f: cp=run_child(argv,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT)
        receipt["execution"]["compile_count"]+=1
        process={"kind":"compile","opt":opt,"argv":argv,"returncode":cp.returncode,"started":t0,"ended":time.time()}
        receipt["processes"].append(process)
        # Persist the actual child status before hashing or parsing its output.
        write_json(receipt_path,receipt)
        process["log_sha256"]=sha(clog.read_bytes()); process["log_bytes"]=clog.stat().st_size
        write_json(receipt_path,receipt)
        if cp.returncode: receipt["status"]="COMPILE_FAILED"; write_json(receipt_path,receipt); raise SystemExit(f"compile failed at {opt}")
        rlog=out/f"run_{opt}.log"; t0=time.time()
        with rlog.open("wb") as f: rp=run_child([str(exe)],cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=30)
        receipt["execution"]["fixture_run_count"]+=1
        process={"kind":"fixture","opt":opt,"argv":[str(exe)],"returncode":rp.returncode,"started":t0,"ended":time.time()}
        receipt["processes"].append(process)
        # Persist actual fixture RC before output hashing/parsing.
        write_json(receipt_path,receipt)
        process["log_sha256"]=sha(rlog.read_bytes()); process["log_bytes"]=rlog.stat().st_size
        process["executable_sha256"]=sha(exe.read_bytes()); process["executable_bytes"]=exe.stat().st_size
        write_json(receipt_path,receipt)
        if rp.returncode: receipt["status"]="RUN_FAILED"; write_json(receipt_path,receipt); raise SystemExit(f"fixture failed at {opt}")
        lines=rlog.read_text().splitlines()
        if not lines or lines[0].split()!=["REAL_BITS","32"]: raise ValueError("fixture requires default REAL32")
        rows=[]
        for line in lines[1:]:
            f=line.split()
            if len(f)!=14: raise ValueError(f"bad output row: {line}")
            ix=list(map(int,f[:4])); v=list(map(float,f[4:]))
            if not all(math.isfinite(x) for x in v): raise ValueError("nonfinite output")
            case,ir,iq,it=ix; rho,qv,temp,rhohost,deos,ddry,p,alpha,rd,rv=v
            if rd!=f32(c["rd"]) or rv!=f32(c["rv"]):
                raise ValueError("fixture source constants do not match the dynamically extracted values")
            expected_rho=(0.5,1.0,1.5)[ir-1]; expected_qv=(0.,.001,.01,.02,.03)[iq-1]; expected_t=(250.,300.)[it-1]
            if (rho,qv,temp)!=(f32(expected_rho),f32(expected_qv),f32(expected_t)) or rhohost!=rho:
                raise ValueError("fixture input/host-density echo mismatch")
            expected_eos=(p/temp-rho*rv)/(rd-rv)
            # Explicit dry branch returns the passed density exactly; the false
            # branch must reproduce the existing ideal-mixture EOS expression.
            tol=16*EPS32*max(1.,abs(expected_eos))
            if ddry!=rho or abs(deos-expected_eos)>tol: raise ValueError("current density policy mismatch")
            rows.append({"case":ix,"rho":rho,"qv":qv,"temperature_K":temp,"host_rho":rhohost,
                         "legacy_eos_dend":deos,"explicit_dry_dend":ddry,"expected_eos":expected_eos,"eos_abs_tolerance":tol})
        if len(rows)!=30: raise ValueError(f"expected 30 cases, got {len(rows)}")
        rows_by_opt.append(rows)
        receipt.setdefault("runs",[]).append({"optimization":opt,"rows":rows,"row_count":len(rows)})
        receipt["status"]="PASS_CURRENT_DENSITY_SOURCE_FIXTURE_PARTIAL"; write_json(receipt_path,receipt)
    for x,y in zip(*rows_by_opt):
        if x["case"]!=y["case"] or x["legacy_eos_dend"]!=y["legacy_eos_dend"] or x["explicit_dry_dend"]!=y["explicit_dry_dend"]:
            raise ValueError("O0/O2 output mismatch")
    receipt["status"]="PASS_CURRENT_DENSITY_SOURCE_FIXTURE_BOTH_O0_O2"
    receipt["durable_process_ledger"]["sha256"] = sha(process_ledger.read_bytes())
    receipt["durable_process_ledger"]["row_count"] = len(process_ledger.read_text().splitlines())
    receipt.pop("last_process",None); write_json(receipt_path,receipt)
    print(json.dumps({"status":receipt["status"],"source_head":head,"output_dir":str(out),"cases_per_opt":30},sort_keys=True))


if __name__=="__main__": main()
