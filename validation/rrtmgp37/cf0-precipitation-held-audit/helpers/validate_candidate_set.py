#!/usr/bin/env python3
"""Recheck the pinned eight sidecars against their raw/input sources; no solver."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location("sidecar_validator",HERE/"validate_sidecar.py")
v=importlib.util.module_from_spec(sp); sys.modules[sp.name]=v; sp.loader.exec_module(v)

def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()

def validate(workspace:Path, sidecar_dir:Path):
    m=json.loads((sidecar_dir/"manifest.json").read_text())
    cases=m.get("cases",[])
    if len(cases)!=8 or m.get("solver_calls")!=0:
        raise ValueError("expected exactly eight prepared sidecars and zero solver calls")
    modes={}
    results=[]
    for c in cases:
        raw=workspace/c["raw_path"]; side=sidecar_dir/c["sidecar_path"]
        if sha(raw)!=c["raw_sha256"] or sha(side)!=c["sidecar_sha256"]:
            raise ValueError(f"pinned raw/sidecar changed: {c['sidecar_path']}")
        hdr,rec=v.parse_raw(raw)
        if hdr[0]!=c["phase"] or hdr[3]!=c["native_layers"]:
            raise ValueError(f"raw identity mismatch: {c['sidecar_path']}")
        if c["mode"]=="positive-omitted-path":
            inp=workspace/c["input_path"]
            if sha(inp)!=c["input_sha256"]: raise ValueError(f"input changed: {c['input_path']}")
            summary=v.validate_against_raw(side.read_text(),raw,c["species"],c["engine_layers"],inp)
        elif c["mode"]=="all-zero-control":
            phase,ncol,native,species,occ,rain,snow=v.decode(side.read_text())
            if phase!=hdr[0] or ncol!=1 or native!=hdr[3] or species!={"rain":1,"snow":2}[c["species"]]:
                raise ValueError(f"zero sidecar identity mismatch: {c['sidecar_path']}")
            if any(x!=0.0 for a in (rain,snow) for row in a for x in row):
                raise ValueError(f"zero sidecar is nonzero: {c['sidecar_path']}")
            v.validate_payload(phase,ncol,native,species,occ,rain,snow,[rec["CF"]],c["engine_layers"])
            summary={"phase":phase,"native_layers":native,"zero_sidecar":True}
        else: raise ValueError(f"unknown sidecar mode: {c['mode']}")
        key=(c["phase"],c["species"]); modes.setdefault(key,set()).add(c["mode"])
        results.append({"sidecar":c["sidecar_path"],"sha256":sha(side),"status":"PASS","summary":summary})
    if len(modes)!=4 or any(x!={"positive-omitted-path","all-zero-control"} for x in modes.values()):
        raise ValueError("each of four phase/species pairs must have one positive and one zero case")
    return {"schema":"cf0-candidate-sidecar-validation-v1","status":"PASS_OFFLINE_ONLY",
            "solver_invocations":0,"case_count":8,"workspace_root":"WORKSPACE_RELATIVE",
            "cases":results}

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--sidecars",type=Path,default=HERE/"sidecars-v4"); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): p.error("output exists; refusing overwrite")
    result=validate(a.workspace.resolve(),a.sidecars.resolve())
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(f"PASS_OFFLINE_ONLY cases={result['case_count']} solver_invocations=0")
