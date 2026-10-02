#!/usr/bin/env python3
"""Compare V5 native dry-mass paths with the historical dp/g counterfactual."""
from __future__ import annotations
import hashlib
import importlib
import json
import os
import argparse
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

REPO = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "WRF/test/rrtmgp/test_udm_cf_replay.py").is_file())
TESTS = REPO / "WRF/test/rrtmgp"
column = None
cf = None
ROOT = REPO / "build/udm-native-dry-mass-pr15"
OUT = ROOT / "path-counterfactual"
DATA = REPO / "WRF/run"
EXE = ROOT / "standalone/reference_column"
NETCDF_LIB = REPO.parent / "deps/netcdf/lib"
ROOT_LIB = REPO.parent / "deps/root/usr/lib/x86_64-linux-gnu"
PATH_FIELDS = ("LWP", "IWP", "RWP", "SWP")
Q_BY_PATH = {"LWP": "QC", "IWP": "QI", "RWP": "QR", "SWP": "QS"}
PHASES = ("LW", "SW")
SEEDS = 32

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()

def summarize(values):
    a=np.asarray(values,dtype=np.float64)
    return {"mean":float(np.mean(a)),"sample_sd":float(np.std(a,ddof=1)) if len(a)>1 else 0.0,
            "min":float(np.min(a)),"max":float(np.max(a)),"max_abs":float(np.max(np.abs(a)))}

def result_arrays(path: Path):
    r=column.read_result(path)
    for name,values in r["sections"].items():
        if not np.isfinite(values).all(): raise RuntimeError(f"nonfinite output section {name}: {path}")
    return r

def run_ref(inp: Path, out: Path, phase: str):
    start=time.perf_counter()
    p=cf.run_reference(EXE,DATA,inp,out,1)
    elapsed=time.perf_counter()-start
    if p.returncode or not out.is_file():
        raise RuntimeError(f"reference run failed {phase} {inp.name}: {p.stdout[-2000:]}")
    return result_arrays(out),elapsed

def expected_legacy_paths(raw, native_input, nl_raw, nl_adapter):
    dp=np.asarray(raw["DP_HPA"][:nl_raw],dtype=np.float64)
    gravity=float(raw["GRAVITY"][0])
    if not np.isfinite(dp).all() or np.any(dp<=0) or not np.isfinite(gravity) or gravity<=0:
        raise RuntimeError("invalid historical dp/gravity inputs")
    mass=dp*100.0/gravity
    cfv=np.asarray(native_input["CF"][0,:nl_raw],dtype=np.float64)
    outputs={}; stats={}
    for name in PATH_FIELDS:
        qname=Q_BY_PATH[name]
        q=column.corrected_hydrometeor(raw,qname,name,nl_raw)
        out=np.zeros((native_input["CF"].shape[0],nl_adapter),dtype=np.float64)
        wet=cfv>0
        out[0,:nl_raw][wet]=q[wet]*mass[wet]*1000.0/cfv[wet]
        if np.any(~np.isfinite(out)) or np.any(out<0): raise RuntimeError(f"invalid counterfactual {name}")
        outputs[name]=out
        native=np.asarray(native_input[name][0,:nl_raw],dtype=np.float64)
        delta=out[0,:nl_raw]-native
        stats[name]={"changed_layer_count":int(np.count_nonzero(delta!=0)),
                     "max_abs_difference_g_m2":float(np.max(np.abs(delta),initial=0)),
                     "native_max_g_m2":float(np.max(native,initial=0)),
                     "legacy_max_g_m2":float(np.max(out[0,:nl_raw],initial=0)),
                     "cf_zero_count":int(np.count_nonzero(cfv==0)),
                     "cf_zero_counterfactual_nonzero_count":int(np.count_nonzero(out[0,:nl_raw][cfv==0]!=0)),
                     "extra_layer_count":nl_adapter-nl_raw,
                     "extra_layer_counterfactual_nonzero_count":int(np.count_nonzero(out[0,nl_raw:]!=0))}
        if stats[name]["cf_zero_counterfactual_nonzero_count"] or stats[name]["extra_layer_counterfactual_nonzero_count"]:
            raise RuntimeError(f"nonzero clear/top path for {name}: {stats[name]}")
    return outputs,stats

def assert_only_four_path_fields(changed, legacy):
    allowed=set(PATH_FIELDS)
    for name, native in changed.items():
        if name not in allowed and not np.array_equal(native,legacy[name]):
            raise RuntimeError(f"counterfactual unexpectedly changed non-path field {name}")
    if set(legacy)-set(changed): raise RuntimeError("section inventory changed")
    if set(PATH_FIELDS)-set(legacy): raise RuntimeError("one or more of four path sections missing")

def compare_metric(a,b):
    ma=cf.metric_values(a); mb=cf.metric_values(b)
    return {k:float(mb[k]-ma[k]) for k in ma}

def bitwise_sections(a,b):
    if a["sections"].keys()!=b["sections"].keys(): return False, ["section inventory"]
    bad=[]
    for key in a["sections"]:
        if a["sections"][key].shape!=b["sections"][key].shape or a["sections"][key].tobytes()!=b["sections"][key].tobytes(): bad.append(key)
    return not bad,bad

def main():
    global REPO, TESTS, ROOT, OUT, DATA, EXE, NETCDF_LIB, ROOT_LIB, SEEDS, column, cf
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root",type=Path,default=REPO,help="RRTMGP checkout containing WRF/phys and WRF/test/rrtmgp")
    parser.add_argument("--case-root",type=Path,default=ROOT,help="directory containing scm/control and scm/mixed")
    parser.add_argument("--reference-executable",type=Path,default=EXE)
    parser.add_argument("--data-directory",type=Path,default=DATA)
    parser.add_argument("--output-directory",type=Path,default=OUT)
    parser.add_argument("--seeds",type=int,default=SEEDS)
    args=parser.parse_args()
    REPO=args.repo_root.resolve(); TESTS=REPO/"WRF/test/rrtmgp"
    ROOT=args.case_root.resolve(); OUT=args.output_directory.resolve()
    DATA=args.data_directory.resolve(); EXE=args.reference_executable.resolve(); SEEDS=args.seeds
    NETCDF_LIB=REPO.parent/"deps/netcdf/lib"; ROOT_LIB=REPO.parent/"deps/root/usr/lib/x86_64-linux-gnu"
    if SEEDS<1 or SEEDS>512: parser.error("--seeds must be in 1..512")
    if not ROOT.is_dir() or not EXE.is_file() or not DATA.is_dir(): parser.error("case root, reference executable, and data directory must exist")
    OUT.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(TESTS))
    column=importlib.import_module("test_column_replay")
    cf=importlib.import_module("test_udm_cf_replay")
    os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(NETCDF_LIB),str(ROOT_LIB),os.environ.get("LD_LIBRARY_PATH","")]).rstrip(os.pathsep)
    case_receipts={}; all_calls={}
    for case in ("control","mixed"):
        case_receipts[case]={}
        for phase in PHASES:
            cap=ROOT/"scm"/case/"ra37-call1"/"capture"
            raw_path=cap/f"{phase.lower()}.raw"; native_path=cap/f"{phase.lower()}.input"
            phase_raw,ri,rj,raw=column.read_raw(raw_path)
            phase_in,nc,nl,overlap,seed,iceflag,native=column.read_input(native_path)
            if phase_raw!=phase or phase_in!=phase or nc!=1 or nl<len(raw["DP_HPA"]): raise RuntimeError("capture header mismatch")
            nlraw=len(raw["DP_HPA"])
            if "DRY_LAYER_MASS_KG_M2" not in raw: raise RuntimeError(f"{case}/{phase}: missing fresh native dry mass")
            native_mass, mass_source=column.dry_layer_mass_kg_m2(raw,nlraw,require_native=True)
            legacy_paths,path_stats=expected_legacy_paths(raw,native,nlraw,nl)
            # Enforce that native and legacy V5 variants differ in only the four requested path sections.
            for s in range(SEEDS):
                this_seed=((seed+s-1)%2147483646)+1
                sub=OUT/"runs"/case/phase.lower()/f"seed-{this_seed}"
                sub.mkdir(parents=True,exist_ok=True)
                legacy_input=sub/"legacy-dp-over-g.input"
                cf.write_variant(native_path,legacy_input,legacy_paths,this_seed)
                legacy_header=column.read_input(legacy_input)
                if legacy_header[:6] != (phase,nc,nl,overlap,this_seed,iceflag):
                    raise RuntimeError("legacy variant changed the paired replay header")
                legacy=legacy_header[6]
                assert_only_four_path_fields(native,legacy)
                base_input=sub/"native.input"
                cf.write_variant(native_path,base_input,{},this_seed)
                native_header=column.read_input(base_input)
                if native_header[:6] != legacy_header[:6]: raise RuntimeError("A/B replay headers differ")
                native_seed=native_header[6]
                assert_only_four_path_fields(native,native_seed)
                native_result,native_sec=run_ref(base_input,sub/"native.result",phase)
                legacy_result,legacy_sec=run_ref(legacy_input,sub/"legacy.result",phase)
                all_calls.setdefault(case,{}).setdefault(phase,[]).append({
                    "seed":this_seed,"native_metrics":cf.metric_values(native_result),
                    "legacy_metrics":cf.metric_values(legacy_result),
                    "legacy_minus_native":compare_metric(native_result,legacy_result),
                    "timing_seconds":{"native":native_sec,"legacy":legacy_sec}})
            rows=all_calls[case][phase]
            names=rows[0]["native_metrics"].keys()
            metrics={}
            for name in names:
                metrics[name]={
                    "native_seed0":rows[0]["native_metrics"][name],
                    "legacy_seed0":rows[0]["legacy_metrics"][name],
                    "delta_seed0_legacy_minus_native":rows[0]["legacy_minus_native"][name],
                    "native_seed_summary":summarize([r["native_metrics"][name] for r in rows]),
                    "legacy_seed_summary":summarize([r["legacy_metrics"][name] for r in rows]),
                    "paired_delta_seed_summary":summarize([r["legacy_minus_native"][name] for r in rows])}
            case_receipts[case][phase]={"source_capture":{"raw":str(raw_path.relative_to(REPO)),"input":str(native_path.relative_to(REPO)),"column_i":ri,"column_j":rj,"native_layers":nlraw,"replay_layers":nl,"base_seed":seed},
                "mass_source":mass_source,"native_mass_kg_m2":{"min":float(native_mass.min()),"max":float(native_mass.max())},
                "path_comparison":path_stats,"counterfactual_definition":"clipped nonnegative raw q * (DP_HPA*100/GRAVITY kg/m2) * 1000 / captured CF for CF>0; zero otherwise; all adapter layers above raw_nl zero",
                "only_sections_changed":list(PATH_FIELDS),"seed_count":SEEDS,"seed_values":[r["seed"] for r in rows],"metrics":metrics,
                "mean_reference_runtime_seconds":{"native":float(np.mean([r["timing_seconds"]["native"] for r in rows])),"legacy":float(np.mean([r["timing_seconds"]["legacy"] for r in rows]))}}
    # Control is clear: rerun original and explicit four-zero path inputs with same seed; require bitwise result identity.
    clear={}
    for phase in PHASES:
        cap=ROOT/"scm/control/ra37-call1/capture"; src=cap/f"{phase.lower()}.input"
        _,_,_,_,_,_,records=column.read_input(src)
        updates={name:np.zeros_like(records[name]) for name in PATH_FIELDS}
        if any(np.any(records[name]!=0) for name in PATH_FIELDS): raise RuntimeError(f"control {phase} is not clear")
        sub=OUT/"clear-bitwise"/phase.lower(); sub.mkdir(parents=True,exist_ok=True)
        changed=sub/"four-zero-paths.input"; cf.write_variant(src,changed,updates, int(column.read_input(src)[4]))
        base,bt=run_ref(src,sub/"original.result",phase); zero,zt=run_ref(changed,sub/"zero-path.result",phase)
        equal,bad=bitwise_sections(base,zero)
        if not equal: raise RuntimeError(f"clear {phase} output not bitwise identical in sections: {bad}")
        clear[phase]={"all_four_native_paths_zero":True,"explicit_four_zero_path_sections":list(PATH_FIELDS),"bitwise_identical_result_sections":list(base["sections"]),"bitwise_equal":True,"runtime_seconds":{"original":bt,"explicit_zero_paths":zt}}
    tracked=subprocess.run(["git","-C",str(REPO),"rev-parse","HEAD"],text=True,stdout=subprocess.PIPE,check=True).stdout.strip()
    status=subprocess.run(["git","-C",str(REPO),"status","--short","--untracked-files=no"],text=True,stdout=subprocess.PIPE,check=True).stdout.strip()
    source_files=[REPO/"WRF/phys/module_ra_rrtmgp.F",REPO/"WRF/phys/module_ra_rrtmgp_input.F",TESTS/"reference_column.f90",Path(__file__)]
    upper_layers={case:{phase:case_receipts[case][phase]["source_capture"]["replay_layers"]-case_receipts[case][phase]["source_capture"]["native_layers"] for phase in PHASES} for case in ("control","mixed")}
    receipt={"status":"PASS","scope":"offline same-state column replay; only cloud paths recomputed using historical pressure/gravity dry-mass estimate","not_claimed":"No attribution beyond measured paired output differences; not a forecast A/B, accuracy judgement, or physical causal decomposition.","reproduction_command":"python3 run_counterfactual.py --repo-root REPO_CHECKOUT --case-root CASE_ROOT --reference-executable REF --data-directory DATA --output-directory OUTPUT --seeds N","source_pin":{"git_head":tracked,"tracked_worktree_status":status,"sha256":{str(p.relative_to(REPO)):sha(p) for p in source_files}},"actual_wrf_executable":{"path":"WRF/main/wrf.exe","sha256":sha(REPO/"WRF/main/wrf.exe")},"reference_executable":str(EXE),"reference_sha256":sha(EXE),"data_directory":str(DATA),"coefficient_sha256":{p.name:sha(p) for p in sorted(DATA.glob("rrtmgp-*.nc"))},"captured_input_raw_sha256":{f"{case}/{phase}":{"input":sha(ROOT/"scm"/case/"ra37-call1/capture"/f"{phase.lower()}.input"),"raw":sha(ROOT/"scm"/case/"ra37-call1/capture"/f"{phase.lower()}.raw")} for case in ("control","mixed") for phase in PHASES},"counterfactual":{"fields_changed":list(PATH_FIELDS),"cloud_fraction_zero_path_g_m2":0,"upper_extended_layers_by_case_phase":upper_layers,"seeds":SEEDS,"seed_sequence":"((base_seed + offset - 1) % 2147483646) + 1"},"cases":case_receipts,"clear_control_bitwise":clear}
    (OUT/"counterfactual.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":"PASS","receipt":str(OUT/"counterfactual.json"),"run_count":SEEDS*2*2*2,"clear_bitwise":True},indent=2))
if __name__=="__main__": main()
