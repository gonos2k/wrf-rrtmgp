#!/usr/bin/env python3
"""Strict raw/decoded finite and fill scan for every numeric history/restart array."""
from __future__ import annotations
import argparse, hashlib, json, math, os, sys
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, default_fillvals

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def fill_for(dtype):
 d=np.dtype(dtype); key={('f',4):'f4',('f',8):'f8',('i',1):'i1',('u',1):'u1',('i',2):'i2',('u',2):'u2',('i',4):'i4',('u',4):'u4',('i',8):'i8',('u',8):'u8'}.get((d.kind,d.itemsize))
 return default_fillvals.get(key) if key else None
def scan_file(path):
 path=Path(path); errors=[]; rows=[]
 with Dataset(path,'r') as ds:
  for name,var in ds.variables.items():
   if np.dtype(var.dtype).kind not in 'iufc': continue
   var.set_auto_maskandscale(False); raw=np.asarray(var[:]); markers=[]
   for att in ('_FillValue','missing_value'):
    if att in var.ncattrs(): markers.extend(np.asarray(var.getncattr(att)).reshape(-1).tolist())
   df=fill_for(raw.dtype)
   if df is not None: markers.append(df)
   raw_bad=[]
   if raw.dtype.kind in 'fc' and not np.isfinite(raw).all(): raw_bad.append({'type':'nonfinite','count':int((~np.isfinite(raw)).sum())})
   for marker in markers:
    try:
     count=int(np.count_nonzero(np.isnan(raw))) if raw.dtype.kind in 'fc' and isinstance(marker,(float,np.floating)) and math.isnan(float(marker)) else int(np.count_nonzero(raw==marker))
    except (TypeError,ValueError,OverflowError): count=0
    if count: raw_bad.append({'type':'fill_or_missing','marker':str(marker),'count':count})
   var.set_auto_maskandscale(True); dec=var[:]
   mask=np.ma.getmaskarray(dec) if np.ma.isMaskedArray(dec) else np.zeros(np.shape(dec),bool)
   data=np.asarray(dec.data if np.ma.isMaskedArray(dec) else dec)
   dec_bad=[]
   if mask.any(): dec_bad.append({'type':'masked','count':int(mask.sum())})
   if data.dtype.kind in 'fc' and not np.isfinite(data).all(): dec_bad.append({'type':'nonfinite','count':int((~np.isfinite(data)).sum())})
   row={'name':name,'dtype':str(raw.dtype),'dimensions':list(var.dimensions),'shape':list(raw.shape),'raw_issues':raw_bad,'decoded_issues':dec_bad}
   rows.append(row)
   if raw_bad or dec_bad: errors.append(row)
 return {'path':str(path.resolve()),'size_bytes':path.stat().st_size,'sha256':sha(path),'numeric_variables':len(rows),'errors':errors,'status':'PASS' if not errors else 'FAIL'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--case-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 case=a.case_dir.resolve(); paths=[case/'wrfout_d01_2016-10-06_00:00:00',*sorted(case.glob('wrfrst_d01_*'))]
 if len(paths)!=5 or any(not p.is_file() for p in paths): raise SystemExit(f'expected one 49-time history plus four restart files; found {len(paths)} candidates')
 files=[scan_file(p) for p in paths]; status='PASS' if all(x['status']=='PASS' for x in files) else 'FAIL'
 out={'schema':'matthew-dt60-paired-48h-all-numeric-quality-v1','status':status,'files':files,
      'scope':'Every numeric variable in the history and all four restart files; both raw storage and decoded NetCDF views. No thresholds or variable exclusions.'}
 a.output.parent.mkdir(parents=True,exist_ok=True)
 tmp=a.output.with_name(a.output.name+'.tmp')
 with tmp.open('x') as f:json.dump(out,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,a.output)
 print(json.dumps({'status':status,'files':len(files),'numeric_variables':sum(x['numeric_variables'] for x in files),'receipt':str(a.output)}))
 return 0 if status=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
