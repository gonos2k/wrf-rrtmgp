#!/usr/bin/env python3
"""Read-only validator for the paired 48-hour Matthew WRF forecast outputs.

It does not launch WRF or alter case data. Each invocation inspects one arm and
writes a new JSON receipt outside (or inside) the case, as requested.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import traceback
from typing import Any

START = "2016-10-06_00:00:00"
END = "2016-10-08_00:00:00"
HISTORY_NAME = "wrfout_d01_2016-10-06_00:00:00"
RESTART_TIMES = ["2016-10-06_12:00:00", "2016-10-07_00:00:00", "2016-10-07_12:00:00", "2016-10-08_00:00:00"]
WRF_SUCCESS = "wrf: SUCCESS COMPLETE WRF"
FATAL_MARKERS = ("FATAL CALLED FROM FILE", "MPI_ABORT", "ERROR: FATAL")
CORE = ("P", "PB", "T", "QVAPOR", "U", "V", "W", "PH", "PHB", "MU", "MUB", "TSK")
SOIL = ("SMOIS", "TSLB", "SH2O")
HYDRO = ("QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP", "QHAIL")
QNUMBER = ("QNCCN", "QNCLOUD", "QNRAIN")
RADIATION_CORE = ("SWDOWN", "GLW", "RTHRATEN")
RA37_IDENTITY_FIELDS = ("SWDOWN", "SWDNB", "SWDDIR", "SWDDIF", "SWUPB", "GSW", "RTHRATLW", "RTHRATSW")
SURFACE_FLUX_ATOL = 2.0e-4
SURFACE_FLUX_RTOL = 2.0e-6
HEATING_ATOL = 2.0e-10
HEATING_RTOL = 2.0e-6
EXPECTED_GRID_DIMS = {"west_east":90,"south_north":99,"bottom_top":44,"soil_layers_stag":4}
DIAG_TAGS = ("RRTMGP_UDM_PHASE_PATH", "RRTMGP_UDM_CF0_OMITTED", "RRTMGP_UDM_LUT_CLIP", "RRTMGP_CU_POPULATION", "RRTMGP_CU_LUT_CLIP")


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()

def pin(path: Path) -> dict[str,Any]:
    st=path.stat();return {"path":str(path.resolve()),"size_bytes":st.st_size,"sha256":sha(path)}

def jv(v: Any) -> Any:
    if hasattr(v,"item"):
        try:return jv(v.item())
        except (ValueError,TypeError):pass
    if isinstance(v,bytes):return v.decode("ascii",errors="replace")
    if isinstance(v,(list,tuple)):return [jv(x) for x in v]
    if isinstance(v,dict):return {str(k):jv(x) for k,x in v.items()}
    if isinstance(v,(str,int,float,bool)) or v is None:return v
    return str(v)

def time_strings(var: Any) -> list[str]:
    import numpy as np
    a=var[:]
    if np.ma.isMaskedArray(a) and np.ma.getmaskarray(a).any():raise ValueError(f"{var.name}: masked time characters")
    a=np.asarray(a)
    if a.ndim!=2 or a.dtype.kind not in "SU":raise ValueError(f"{var.name}: expected 2-D char time array, found {a.dtype} {a.shape}")
    rows=[]
    for row in a:
        chars=[x.decode("ascii") if isinstance(x,bytes) else str(x) for x in row]
        rows.append("".join(chars).replace("\x00","").strip())
    return rows

def expected_history_times() -> list[str]:
    t=dt.datetime.strptime(START,"%Y-%m-%d_%H:%M:%S")
    return [(t+dt.timedelta(hours=n)).strftime("%Y-%m-%d_%H:%M:%S") for n in range(49)]

def expected_restart_filename(t: str) -> str:
    return "wrfrst_d01_"+t

def default_fill(dtype: Any) -> Any | None:
    import numpy as np
    d=np.dtype(dtype)
    key={("f",4):"f4",("f",8):"f8",("i",1):"i1",("u",1):"u1",("i",2):"i2",("u",2):"u2",("i",4):"i4",("u",4):"u4",("i",8):"i8",("u",8):"u8"}.get((d.kind,d.itemsize))
    if key is None:return None
    from netCDF4 import default_fillvals
    return default_fillvals.get(key)

def marker_count(a: Any, marker: Any) -> int:
    import numpy as np
    try:
        if np.asarray(a).dtype.kind=="f" and isinstance(marker,(float,np.floating)) and math.isnan(float(marker)):return int(np.isnan(a).sum())
        return int((a==marker).sum())
    except (ValueError,TypeError,OverflowError):return 0

def quality(var: Any) -> dict[str,Any]:
    """Report native raw and decoded quality. Callers decide gate vs diagnostic."""
    import numpy as np
    var.set_auto_maskandscale(False); raw=np.asarray(var[:])
    raw_nonfinite=int((~np.isfinite(raw)).sum()) if raw.dtype.kind in "fci" else 0
    markers=[]
    for att in ("_FillValue","missing_value"):
        if att in var.ncattrs():
            for x in np.asarray(var.getncattr(att)).reshape(-1):markers.append((att,x.item() if hasattr(x,"item") else x))
    df=default_fill(raw.dtype)
    if df is not None:markers.append(("netCDF_default_fill",df))
    fills=[]
    for label,m in markers:
        count=marker_count(raw,m)
        if count:fills.append({"marker":label,"value":jv(m),"count":count})
    var.set_auto_maskandscale(True);decoded=var[:]
    mask=np.ma.getmaskarray(decoded) if np.ma.isMaskedArray(decoded) else np.zeros(np.shape(decoded),bool)
    vals=np.asarray(decoded.data if np.ma.isMaskedArray(decoded) else decoded)
    nonfinite=int((~np.isfinite(vals)).sum()) if vals.dtype.kind in "fci" else 0
    valid=vals[~mask]
    if valid.dtype.kind=="f":valid=valid[np.isfinite(valid)]
    minv=float(np.min(valid)) if valid.size and valid.dtype.kind in "fiu" else None
    maxv=float(np.max(valid)) if valid.size and valid.dtype.kind in "fiu" else None
    neg=int((valid<0).sum()) if valid.size and valid.dtype.kind in "fiu" else 0
    return {"dimensions":list(var.dimensions),"shape":list(raw.shape),"dtype":str(raw.dtype),"raw_nonfinite_count":raw_nonfinite,"raw_fill_missing_count":sum(x["count"] for x in fills),"raw_fill_missing_markers":fills,"decoded_masked_count":int(mask.sum()),"decoded_nonfinite_count":nonfinite,"decoded_min":minv,"decoded_max":maxv,"decoded_negative_count":neg,"scale_factor":jv(var.getncattr("scale_factor")) if "scale_factor" in var.ncattrs() else None,"add_offset":jv(var.getncattr("add_offset")) if "add_offset" in var.ncattrs() else None}

def fail_quality(q: dict[str,Any]) -> bool:
    return bool(q["raw_nonfinite_count"] or q["raw_fill_missing_count"] or q["decoded_masked_count"] or q["decoded_nonfinite_count"])

def read_values(ds: Any, name: str) -> Any:
    v=ds.variables[name];v.set_auto_maskandscale(True);a=v[:]
    import numpy as np
    return np.asarray(a.data if np.ma.isMaskedArray(a) else a)

def check_identity(ds: Any, lhs_name: str, rhs: Any, label: str, atol: float, rtol: float, errors: list[str]) -> dict[str,Any]:
    import numpy as np
    lhs=read_values(ds,lhs_name)
    if lhs.shape!=rhs.shape:
        errors.append(f"{label}: shape mismatch {lhs.shape} vs {rhs.shape}")
        return {"status":"FAIL_SHAPE","lhs_shape":list(lhs.shape),"rhs_shape":list(rhs.shape)}
    diff=np.asarray(lhs,dtype="float64")-np.asarray(rhs,dtype="float64")
    absolute=np.abs(diff);limit=atol+rtol*np.abs(rhs)
    bad=absolute>limit
    result={"status":"PASS" if not bad.any() else "FAIL","lhs":lhs_name,"shape":list(lhs.shape),"atol":atol,"rtol":rtol,"mismatch_count":int(bad.sum()),"max_abs_error":float(absolute.max()) if absolute.size else 0.0,"max_abs_error_index":list(map(int,np.unravel_index(absolute.argmax(),absolute.shape))) if absolute.size else [],"lhs_at_max_error":float(lhs[np.unravel_index(absolute.argmax(),absolute.shape)]) if absolute.size else 0.0,"rhs_at_max_error":float(rhs[np.unravel_index(absolute.argmax(),absolute.shape)]) if absolute.size else 0.0}
    if bad.any():errors.append(f"{label}: {bad.sum()} mismatches, max abs error {result['max_abs_error']}")
    return result

def validate_quality_fields(ds: Any, names: set[str], label: str, errors: list[str], required: set[str]) -> dict[str,Any]:
    fields={}
    for name in sorted(names):
        if name not in ds.variables:
            if name in required:errors.append(f"{label}: required variable {name} is missing")
            continue
        q=quality(ds.variables[name]);fields[name]=q
        if fail_quality(q):errors.append(f"{label}/{name}: raw/decoded finite-mask-fill check failed")
    return fields

def check_positive_coordinates(ds: Any, label: str, errors: list[str]) -> dict[str,Any]:
    import numpy as np
    result={}
    if "P" in ds.variables and "PB" in ds.variables:
        p=read_values(ds,"P").astype("float64")+read_values(ds,"PB").astype("float64")
        result["P_plus_PB"]={"min":float(p.min()),"max":float(p.max()),"nonpositive_count":int((p<=0).sum()),"units":"Pa"}
        if not (p>0).all():errors.append(f"{label}: P+PB must be strictly positive")
    else:errors.append(f"{label}: cannot form P+PB")
    if "MU" in ds.variables and "MUB" in ds.variables:
        m=read_values(ds,"MU").astype("float64")+read_values(ds,"MUB").astype("float64")
        result["MU_plus_MUB"]={"min":float(m.min()),"max":float(m.max()),"nonpositive_count":int((m<=0).sum()),"units":"Pa"}
        if not (m>0).all():errors.append(f"{label}: MU+MUB dry column mass coordinate must be strictly positive")
    else:errors.append(f"{label}: cannot form MU+MUB")
    return result

def check_ra37_identities(ds: Any, arm: str, errors: list[str]) -> dict[str,Any]:
    import numpy as np
    out={}
    present=lambda n:n in ds.variables
    identities=[("SWDOWN","SWDNB",SURFACE_FLUX_ATOL,SURFACE_FLUX_RTOL,"SWDOWN equals SWDNB"),
                ("SWDOWN","SWDDIR+SWDDIF",SURFACE_FLUX_ATOL,SURFACE_FLUX_RTOL,"SWDOWN equals SWDDIR+SWDDIF"),
                ("GSW","SWDNB-SWUPB",SURFACE_FLUX_ATOL,SURFACE_FLUX_RTOL,"GSW equals SWDNB-SWUPB"),
                ("RTHRATEN","RTHRATLW+RTHRATSW",HEATING_ATOL,HEATING_RTOL,"RTHRATEN equals LW+SW")]
    if arm=="ra37":
        missing=[n for n in RA37_IDENTITY_FIELDS if not present(n)]
        if missing:errors.append(f"RA37 history lacks required radiation identity fields: {missing}")
        for n in ("SWDOWN","GLW","RTHRATEN","RTHRATLW","RTHRATSW","SWDNB","SWDDIR","SWDDIF","SWUPB","GSW"):
            if not present(n):errors.append(f"RA37 history lacks required field {n}")
    for lhs,rhs,atol,rtol,label in identities:
        required=(arm=="ra37")
        if lhs not in ds.variables:
            if required:errors.append(f"{label}: missing {lhs}")
            continue
        if rhs=="SWDNB":
            if rhs not in ds.variables:
                if required:errors.append(f"{label}: missing {rhs}")
                continue
            right=read_values(ds,rhs)
        elif rhs=="SWDDIR+SWDDIF":
            if not all(present(x) for x in ("SWDDIR","SWDDIF")):
                if required:errors.append(f"{label}: missing SWDDIR or SWDDIF")
                continue
            right=read_values(ds,"SWDDIR").astype("float64")+read_values(ds,"SWDDIF").astype("float64")
        elif rhs=="SWDNB-SWUPB":
            if not all(present(x) for x in ("SWDNB","SWUPB")):
                if required:errors.append(f"{label}: missing SWDNB or SWUPB")
                continue
            right=read_values(ds,"SWDNB").astype("float64")-read_values(ds,"SWUPB").astype("float64")
        else:
            if not all(present(x) for x in ("RTHRATLW","RTHRATSW")):
                if required:errors.append(f"{label}: missing RTHRATLW or RTHRATSW")
                continue
            right=read_values(ds,"RTHRATLW").astype("float64")+read_values(ds,"RTHRATSW").astype("float64")
        out[label]=check_identity(ds,lhs,right,label,atol,rtol,errors)
    return out

def rank_logs(case: Path, errors: list[str]) -> list[dict[str,Any]]:
    expected=[case/f"rsl.error.{n:04d}" for n in range(4)]
    got=sorted(case.glob("rsl.error.*"))
    if [p.name for p in got]!=[p.name for p in expected]:errors.append(f"expected exactly four rank logs {[p.name for p in expected]}, found {[p.name for p in got]}")
    rows=[]
    for p in got:
        text=p.read_text(errors="replace")
        success=WRF_SUCCESS in text
        fatal=[m for m in FATAL_MARKERS if m in text]
        if not success:errors.append(f"{p.name}: missing {WRF_SUCCESS!r}")
        if fatal:errors.append(f"{p.name}: fatal markers {fatal}")
        counts={tag:text.count(tag) for tag in DIAG_TAGS}
        # These are rank-local logger records (often called multiple times); retain exact text, do not
        # interpret duplicated LW/SW summaries as globally unique water mass.
        diag=[line for line in text.splitlines() if any(tag in line for tag in DIAG_TAGS)]
        rows.append({**pin(p),"relative_path":p.name,"success_marker":success,"fatal_markers":fatal,"diagnostic_line_counts":counts,"diagnostic_lines":diag})
    return rows

def inspect_case(case: Path, arm: str, errors: list[str]) -> dict[str,Any]:
    import numpy as np
    from netCDF4 import Dataset
    expected_hist=case/HISTORY_NAME
    histories=sorted(case.glob("wrfout_d01_*"))
    if len(histories)!=1:errors.append(f"expected exactly one history file (frames_per_outfile=1000), found {len(histories)}")
    if not expected_hist.is_file():errors.append(f"expected history file missing: {HISTORY_NAME}")
    restarts=sorted(case.glob("wrfrst_d01_*"))
    expected_rst=[case/expected_restart_filename(t) for t in RESTART_TIMES]
    if [p.name for p in restarts]!=[p.name for p in expected_rst]:errors.append(f"restart file set mismatch: expected {[p.name for p in expected_rst]}, found {[p.name for p in restarts]}")
    files=[];hist_info={};cp_info=[]
    for p in histories:
        if not p.is_file():continue
        files.append({"role":"history","name":p.name,**pin(p)})
        try:
            with Dataset(p,"r") as ds:
                times=time_strings(ds.variables["Times"]) if "Times" in ds.variables else []
                expected=expected_history_times()
                if times!=expected:errors.append(f"{p.name}: expected exactly 49 hourly Times from {START} through {END}; got count={len(times)}, first={times[:1]}, last={times[-1:]}")
                td=len(ds.dimensions["Time"]) if "Time" in ds.dimensions else None
                if td!=49:errors.append(f"{p.name}: Time dimension {td}, expected 49")
                grid_dims={n:len(ds.dimensions[n]) if n in ds.dimensions else None for n in EXPECTED_GRID_DIMS}
                for name,want in EXPECTED_GRID_DIMS.items():
                    if grid_dims[name]!=want:errors.append(f"{p.name}: dimension {name}={grid_dims[name]}, expected {want}")
                quality_fields=set(CORE)|set(RADIATION_CORE)|set(HYDRO)|set(QNUMBER)|set(SOIL)|set(RA37_IDENTITY_FIELDS)|{"RTHRATENLW","RTHRATENSW","LWUPT","LWDNT","LWDNB","OLR","CLDFRA","CLDFRA_DP","CLDFRA_SH","UDM_CF_STEP","UDM_CF_TOP"}
                # Registry history uses the external names RTHRATLW/RTHRATSW.
                quality_fields|={"RTHRATLW","RTHRATSW"}
                required=set(CORE)|set(RADIATION_CORE)
                qfields=validate_quality_fields(ds,quality_fields,f"history {p.name}",errors,required)
                positive=check_positive_coordinates(ds,f"history {p.name}",errors)
                identities=check_ra37_identities(ds,arm,errors)
                # Negative water/number values are observations, not new rejection thresholds.
                negative={n:{"min":qfields[n]["decoded_min"],"negative_count":qfields[n]["decoded_negative_count"],"shape":qfields[n]["shape"]} for n in (*HYDRO,*QNUMBER) if n in qfields}
                cf_stats={n:{"min":qfields[n]["decoded_min"],"max":qfields[n]["decoded_max"],"shape":qfields[n]["shape"]} for n in ("CLDFRA","CLDFRA_DP","CLDFRA_SH","UDM_CF_STEP","UDM_CF_TOP") if n in qfields}
                hist_info={"file":p.name,"sha256":sha(p),"times_count":len(times),"first_time":times[0] if times else None,"last_time":times[-1] if times else None,"time_dimension":td,"dimension_sizes":grid_dims,"global_attrs":{n:jv(ds.getncattr(n)) for n in ("MAP_PROJ","MMINLU","NUM_LAND_CAT","START_DATE","SIMULATION_START_DATE","RA_LW_PHYSICS","RA_SW_PHYSICS") if n in ds.ncattrs()},"field_quality":qfields,"positive_coordinates":positive,"negative_species_and_numbers_report_only":negative,"cloud_fraction_and_udm_extent_diagnostics":cf_stats,"radiation_identities":identities}
        except Exception as e:errors.append(f"{p.name}: NetCDF validation exception {type(e).__name__}: {e}")
    for p in restarts:
        if not p.is_file():continue
        files.append({"role":"restart","name":p.name,**pin(p)})
        expected_time=p.name.removeprefix("wrfrst_d01_")
        try:
            with Dataset(p,"r") as ds:
                times=time_strings(ds.variables["Times"]) if "Times" in ds.variables else []
                if times!=[expected_time]:errors.append(f"{p.name}: restart Times {times} != filename timestamp {expected_time}")
                td=len(ds.dimensions["Time"]) if "Time" in ds.dimensions else None
                if td!=1:errors.append(f"{p.name}: restart Time dimension {td}, expected 1")
                grid_dims={n:len(ds.dimensions[n]) if n in ds.dimensions else None for n in EXPECTED_GRID_DIMS}
                for name,want in EXPECTED_GRID_DIMS.items():
                    if grid_dims[name]!=want:errors.append(f"{p.name}: dimension {name}={grid_dims[name]}, expected {want}")
                names=set(CORE)|set(SOIL)|set(HYDRO)|set(QNUMBER)
                required=set(CORE)
                qfields=validate_quality_fields(ds,names,f"restart {p.name}",errors,required)
                positive=check_positive_coordinates(ds,f"restart {p.name}",errors)
                cp_info.append({"file":p.name,"sha256":sha(p),"size_bytes":p.stat().st_size,"time":times,"time_dimension":td,"dimension_sizes":grid_dims,"field_quality":qfields,"positive_coordinates":positive})
        except Exception as e:errors.append(f"{p.name}: NetCDF validation exception {type(e).__name__}: {e}")
    # Pin all top-level output and log files, including the input/boundary and namelist context.
    inventory=[]
    for p in sorted(case.iterdir()):
        if p.is_file():
            r={**pin(p),"relative_path":p.name}
            if p.is_symlink():r["symlink_target"]=os.readlink(p)
            inventory.append(r)
    return {"arm":arm,"history":hist_info,"history_files":[r for r in files if r["role"]=="history"],"restarts":cp_info,"history_and_restart_output_pins":files,"top_level_file_inventory":inventory}

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case-dir",required=True,type=Path)
    ap.add_argument("--arm",required=True,choices=("ra4","ra37"))
    ap.add_argument("--receipt",required=True,type=Path)
    args=ap.parse_args();case=args.case_dir.resolve();receipt=args.receipt.resolve()
    errors=[];result={"schema":"matthew-paired-forecast-postflight-v1","created_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"status":"FAIL","arm":args.arm,"case_dir":str(case),"expected":{"history_file":HISTORY_NAME,"history_times_count":49,"history_start":START,"history_end":END,"restart_times":RESTART_TIMES,"restart_file_count":4,"grid_dimensions":EXPECTED_GRID_DIMS,"mpi_rank_logs":4,"surface_flux_tolerance":{"atol_W_m2":SURFACE_FLUX_ATOL,"rtol":SURFACE_FLUX_RTOL},"heating_identity_tolerance":{"atol_K_s":HEATING_ATOL,"rtol":HEATING_RTOL},"negative_water_and_number_policy":"report counts/minima; no new rejection threshold"},"errors":errors}
    try:
        if os.path.lexists(receipt):raise FileExistsError(f"refusing to overwrite receipt: {receipt}")
        if not case.is_dir():raise FileNotFoundError(f"case directory does not exist: {case}")
        result["rank_logs"]=rank_logs(case,errors)
        result["case_validation"]=inspect_case(case,args.arm,errors)
        result["status"]="PASS" if not errors else "FAIL"
    except Exception as e:
        errors.append(f"validator exception: {type(e).__name__}: {e}")
        result["traceback"]=traceback.format_exc(limit=8)
        result["status"]="FAIL"
    receipt.parent.mkdir(parents=True,exist_ok=True)
    tmp=receipt.with_name(receipt.name+".tmp")
    try:
        with tmp.open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,receipt)
    except Exception as e:
        print(f"could not persist receipt {receipt}: {type(e).__name__}: {e}",file=sys.stderr)
        return 2
    print(json.dumps({"status":result["status"],"arm":args.arm,"receipt":str(receipt),"errors":len(errors)},sort_keys=True))
    return 0 if result["status"]=="PASS" else 1

if __name__=="__main__":raise SystemExit(main())
