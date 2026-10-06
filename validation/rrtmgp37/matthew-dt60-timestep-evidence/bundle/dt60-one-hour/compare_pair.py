#!/usr/bin/env python3
"""Descriptive matched-time RA37-minus-RA4 metrics; no acceptance threshold."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json
from pathlib import Path
import netCDF4, numpy as np

FIELDS=('SWDOWN','GLW','SWUPB','SWDNB','SWDDIR','SWDDIF','GSW','OLR','RTHRATLW','RTHRATSW',
        'T','QVAPOR','QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL','QC_CU','QI_CU','CLDFRA_DP','CLDFRA_SH','UDM_CLDFRA','UDM_CF_TOP','UDM_CF_STEP','WW')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def read(path):
 with netCDF4.Dataset(path) as ds:
  ds.set_auto_maskandscale(False)
  tm=netCDF4.chartostring(ds['Times'][:]).astype(str).tolist()
  vals={n:np.asarray(v[:]) for n,v in ds.variables.items() if np.dtype(v.dtype).kind in 'iufc' and n!='Times'}
  return tm,vals
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--ra4',required=True);ap.add_argument('--ra37',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 p4=Path(a.ra4);p37=Path(a.ra37);t4,v4=read(p4);t37,v37=read(p37)
 if t4!=t37:raise SystemExit('timestamp grids differ')
 out={'schema':'matthew-dt60-paired-descriptive-differences-v1','status':'DESCRIPTIVE_ONLY',
      'ra4':{'path':str(p4.resolve()),'sha256':sha(p4)},'ra37':{'path':str(p37.resolve()),'sha256':sha(p37)},
      'times':t4,'fields':{},'interpretation':'Coupled-state/radiation differences only; no observational accuracy or winner claim.'}
 for name in FIELDS:
  n4=next((n for n in v4 if n.casefold()==name.casefold()),None);n37=next((n for n in v37 if n.casefold()==name.casefold()),None)
  if n4 is None or n37 is None:out['fields'][name]={'status':'MISSING','ra4_name':n4,'ra37_name':n37};continue
  x=np.asarray(v4[n4],dtype=np.float64);y=np.asarray(v37[n37],dtype=np.float64)
  if x.shape!=y.shape:out['fields'][name]={'status':'SHAPE_MISMATCH','ra4_shape':list(x.shape),'ra37_shape':list(y.shape)};continue
  d=y-x;finite=np.isfinite(d)
  out['fields'][name]={'status':'COMPARED','ra4_name':n4,'ra37_name':n37,'shape':list(x.shape),
      'finite_count':int(finite.sum()),'nonfinite_count':int((~finite).sum()),
      'mean_difference':float(np.mean(d[finite])) if finite.any() else None,
      'rmse_difference':float(np.sqrt(np.mean(d[finite]**2))) if finite.any() else None,
      'max_abs_difference':float(np.max(np.abs(d[finite]))) if finite.any() else None}
 Path(a.output).write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n')
 print(json.dumps({'status':out['status'],'fields':len(out['fields']),'timestamps':len(t4)}))
if __name__=='__main__':main()
