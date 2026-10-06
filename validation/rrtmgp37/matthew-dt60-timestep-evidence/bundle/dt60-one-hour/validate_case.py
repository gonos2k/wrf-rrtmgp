#!/usr/bin/env python3
"""Strict one-hour dt60 output check. Read-only; no model execution."""
from __future__ import annotations
import argparse, datetime as dt, json, hashlib
from pathlib import Path
import netCDF4
import numpy as np

def sha(p: Path) -> str:
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def expected_times():
    start=dt.datetime(2016,10,6,0,0,0)
    return [(start+dt.timedelta(seconds=120*n)).strftime('%Y-%m-%d_%H:%M:%S') for n in range(31)]

def check_file(path: Path) -> dict:
    ds=netCDF4.Dataset(path,'r')
    try:
        if 'Times' not in ds.variables: raise RuntimeError('missing Times')
        raw_times=ds.variables['Times'][:]
        times=netCDF4.chartostring(raw_times).astype(str).tolist()
        want=expected_times()
        if times != want: raise RuntimeError(f'history timestamps mismatch: got {len(times)} records; expected 31 exact records')
        names={n.casefold():n for n in ds.variables}
        required=('WW','C1F','C2F','DNW','MU','MUB')
        missing=[n for n in required if n.casefold() not in names]
        if missing: raise RuntimeError(f'native WW/Courant fields missing: {missing}')
        checked=[]; total=0
        for name,var in ds.variables.items():
            if name == 'Times' or np.dtype(var.dtype).kind not in 'iufc': continue
            arr=var[:]
            if np.ma.isMaskedArray(arr) and np.ma.getmaskarray(arr).any():
                raise RuntimeError(f'{name}: decoded/masked fill values present')
            values=np.asarray(arr)
            if not np.isfinite(values).all():
                idx=np.argwhere(~np.isfinite(values))[0].tolist()
                raise RuntimeError(f'{name}: nonfinite decoded value at {idx}')
            var.set_auto_maskandscale(False)
            raw=np.asarray(var[:])
            if not np.isfinite(raw).all():
                idx=np.argwhere(~np.isfinite(raw))[0].tolist()
                raise RuntimeError(f'{name}: nonfinite raw value at {idx}')
            for attr in ('_FillValue','missing_value'):
                if attr in var.ncattrs():
                    sent=np.asarray(var.getncattr(attr))
                    if np.any(np.isin(raw,sent)):
                        raise RuntimeError(f'{name}: raw explicit {attr} sentinel present')
            total += raw.size
            checked.append({'name':name,'dimensions':list(var.dimensions),'shape':list(var.shape),
                            'dtype':str(var.dtype),'units':str(getattr(var,'units','')),
                            'raw_min':float(raw.min()) if raw.size else None,
                            'raw_max':float(raw.max()) if raw.size else None})
        return {'path':str(path.resolve()),'sha256':sha(path),'size_bytes':path.stat().st_size,
                'times':times,'numeric_variable_count':len(checked),'numeric_element_count':total,
                'variables':checked}
    finally: ds.close()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--case-dir',required=True); ap.add_argument('--arm',choices=['ra4','ra37'],required=True); ap.add_argument('--receipt',required=True)
    a=ap.parse_args(); case=Path(a.case_dir); out=Path(a.receipt)
    histories=sorted(case.glob('wrfout_d01_*'))
    result={'schema':'matthew-dt60-one-hour-case-validation-v1','arm':a.arm,'status':'FAIL',
            'case_dir':str(case.resolve()),'expected_times':expected_times(),'history_count':len(histories),'histories':[],'error':None}
    try:
        if len(histories)!=1: raise RuntimeError(f'expected one history file, found {len(histories)}')
        result['histories']=[check_file(histories[0])]
        result['status']='PASS_NUMERIC_HISTORY_CONTRACT'
    except Exception as e:
        result['error']=f'{type(e).__name__}: {e}'
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'error':result['error'],'history_count':result['history_count']}))
    raise SystemExit(0 if result['status'].startswith('PASS') else 1)
if __name__=='__main__': main()
