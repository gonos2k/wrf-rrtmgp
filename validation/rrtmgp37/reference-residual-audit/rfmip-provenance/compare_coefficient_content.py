#!/usr/bin/env python3
"""Read-only provenance/schema comparison for RFMIP source-id 181204."""
import argparse, hashlib, json
from pathlib import Path
import netCDF4
import numpy as np

OLD = {
    "lw": "build/udm37-rfmip-reference-provenance-v1/rrtmgp-data-lw-g256-2018-12-04.nc",
    "sw": "build/udm37-rfmip-reference-provenance-v1/rrtmgp-data-sw-g224-2018-12-04.nc",
}
CURRENT = {
    "lw": "build/official-rrtmgp-reference/data/rrtmgp-gas-lw-g256.nc",
    "sw": "build/official-rrtmgp-reference/data/rrtmgp-gas-sw-g224.nc",
}
REF = "build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/reference/rld_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc"
EXPECTED = {
    OLD["lw"]: "3c78d7dde0480775b6d9fd1e9f3e360c2c28bcbd107a6adfa83dadb8140bd197",
    OLD["sw"]: "b9f4b15796d132880fffb49ac45c29753c1ee70a8ee3fed733899cb315c75e9b",
    CURRENT["lw"]: "4048360199d1917ed8f2ccaae2ec097d0f990da3bbad9830337b739b4fa01be7",
    CURRENT["sw"]: "584f1dd41ea9fc07d4ee3754eb1dafbd46ad3161cd6fd20fa06b6922b6f0702e",
}

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def attrs(ds):
    out={}
    for k in ds.ncattrs():
        v=ds.getncattr(k)
        if isinstance(v,bytes): v=v.decode('utf-8','replace')
        if isinstance(v,np.ndarray): v=v.tolist()
        if isinstance(v,np.generic): v=v.item()
        out[k]=v
    return out

def compare(old_path,current_path):
    old=netCDF4.Dataset(old_path); cur=netCDF4.Dataset(current_path)
    try:
        old_dims={k:{"length":len(v),"unlimited":v.isunlimited()} for k,v in old.dimensions.items()}
        cur_dims={k:{"length":len(v),"unlimited":v.isunlimited()} for k,v in cur.dimensions.items()}
        old_vars=set(old.variables); cur_vars=set(cur.variables); common=sorted(old_vars&cur_vars)
        values_equal=[]; diffs=[]
        for n in common:
            a=np.asarray(old[n][:]); b=np.asarray(cur[n][:])
            item={"name":n,"old_shape":list(a.shape),"current_shape":list(b.shape),"old_dtype":str(a.dtype),"current_dtype":str(b.dtype)}
            if a.shape!=b.shape or a.dtype!=b.dtype:
                item["equal"]=False; item["reason"]="shape_or_dtype"; diffs.append(item); continue
            # Compare materialized NetCDF values exactly, preserving dtype representation.
            exact=np.array_equal(a,b,equal_nan=True) if a.dtype.kind in "f" else np.array_equal(a,b)
            item["equal"]=bool(exact)
            if a.dtype.kind in "fiu":
                delta=np.abs(a.astype(np.float64)-b.astype(np.float64))
                item["max_abs_difference"]=float(np.nanmax(delta)) if delta.size else 0.0
                item["different_elements"]=int(np.count_nonzero(delta))
            if exact: values_equal.append(n)
            else: diffs.append(item)
        old_attrs=attrs(old); cur_attrs=attrs(cur)
        attr_differences={k:{"old":old_attrs.get(k),"current":cur_attrs.get(k)} for k in sorted(set(old_attrs)|set(cur_attrs)) if old_attrs.get(k)!=cur_attrs.get(k)}
        out={"old_path":old_path,"current_path":current_path,"old_file_sha256":digest(old_path),"current_file_sha256":digest(current_path),
            "old_size_bytes":Path(old_path).stat().st_size,"current_size_bytes":Path(current_path).stat().st_size,
            "dimensions":{"old":old_dims,"current":cur_dims},
            "variables":{"old_count":len(old_vars),"current_count":len(cur_vars),"old_only":sorted(old_vars-cur_vars),"current_only":sorted(cur_vars-old_vars),
                "shared_count":len(common),"shared_exact_values":values_equal,"shared_value_differences":diffs},
            "global_attribute_differences":attr_differences}
        if "solar_source" in old.variables and all(n in cur.variables for n in ("solar_source_quiet","solar_source_facular","solar_source_sunspot","mg_default","sb_default")):
            old_src=np.asarray(old["solar_source"][:],dtype=np.float64)
            mg=float(cur["mg_default"][:]); sb=float(cur["sb_default"][:])
            rebuilt=(np.asarray(cur["solar_source_quiet"][:],dtype=np.float64)+
                (mg-0.1495954)*np.asarray(cur["solar_source_facular"][:],dtype=np.float64)+
                (sb-0.00066696)*np.asarray(cur["solar_source_sunspot"][:],dtype=np.float64))
            out["sw_default_source_reconstruction"]={"method":"current frontend set_solar_variability formula using file mg_default/sb_default",
                "mg_default":mg,"sb_default":sb,"compared_points":int(old_src.size),
                "max_abs_difference_old_single_solar_source_vs_current_default":float(np.max(np.abs(old_src-rebuilt))),
                "different_points":int(np.count_nonzero(old_src!=rebuilt)),
                "note":"This compares stored spectra; it is not an RFMIP flux attribution or exact source-id run reconstruction."}
        return out
    finally:
        old.close(); cur.close()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--workspace',default='.'); ap.add_argument('--output',required=True); a=ap.parse_args()
    root=Path(a.workspace).resolve(); out={"schema":"rfmip-source-id-provenance-content-v1","scope":"read-only source/tag and coefficient content comparison; no model runs or builds","comparisons":{}}
    for key in ('lw','sw'):
        op=(root/OLD[key]).resolve(); cp=(root/CURRENT[key]).resolve()
        for p in (op,cp):
            if not p.is_file(): raise FileNotFoundError(p)
            rel=str(p.relative_to(root))
            if rel in EXPECTED and digest(p)!=EXPECTED[rel]:
                raise ValueError(f"pinned coefficient artifact changed: {rel}")
        out['comparisons'][key]=compare(str(op),str(cp))
    ref=(root/REF).resolve(); out['published_reference_sample']={"path":str(ref),"sha256":digest(ref),"size_bytes":ref.stat().st_size}
    ds=netCDF4.Dataset(ref)
    try:
        out['published_reference_sample']['global_attributes']={k:attrs(ds).get(k) for k in ('source_id','source','creation_date','tracking_id','mip_era','institution_id','experiment_id','further_info_url')}
        out['published_reference_sample']['dimensions']={k:len(v) for k,v in ds.dimensions.items()}
    finally: ds.close()
    p=Path(a.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps({"output":str(p),"comparisons":{k:{"shared_count":v['variables']['shared_count'],"exact_shared_values":len(v['variables']['shared_exact_values']),"value_diffs":len(v['variables']['shared_value_differences']),"old_only":v['variables']['old_only'],"current_only":v['variables']['current_only']} for k,v in out['comparisons'].items()}},indent=2))
if __name__=='__main__': main()
