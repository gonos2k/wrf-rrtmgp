#!/usr/bin/env python3
"""Narrow real-input producer: exact-zero condensate and number only, no inferred Nc.

This resolves the representation of zero; it does NOT enable specified boundaries
in dry-number-grid-v1. The current WRF guard must still reject this research path.
"""
from pathlib import Path
import argparse,hashlib,json,shutil
import numpy as np
from netCDF4 import Dataset
MASS=('QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL')
NUMBER=('QNCLOUD','QNRAIN','QNI','QNS','QNG','QNH')
SUFFIX=tuple('_B'+x for x in ('XS','XE','YS','YE','TXS','TXE','TYS','TYE'))
def digest(a):return hashlib.sha256(np.asarray(a).tobytes()).hexdigest()
def inspect(path,boundary=False):
 with Dataset(path) as d:
  d.set_auto_mask(False)
  required=[x+s for x in MASS+('QNCLOUD','QNRAIN') for s in (SUFFIX if boundary else ('',))]
  for n in required:
   if n not in d.variables:raise ValueError('missing required field '+n)
  checked={}
  for n,v in d.variables.items():
   if n in MASS+NUMBER or any(n==x+s for x in MASS+NUMBER for s in SUFFIX):
    a=np.asarray(v[:])
    if not np.isfinite(a).all() or np.any(a!=0):raise ValueError('nonzero/nonfinite condensate or number: '+n)
    checked[n]={'shape':list(a.shape),'sha256':digest(a),'min':0,'max':0}
  arrays={n:digest(v[:]) for n,v in d.variables.items()}
  return {'checked':checked,'all_variable_array_sha256':arrays,'times':[b''.join(row).decode() for row in np.asarray(d['Times'][:])]}
def produce(initial,boundary,out):
 before={n:inspect(p,n=='wrfbdy_d01') for n,p in [('wrfinput_d01',initial),('wrfbdy_d01',boundary)]}
 out.mkdir(exist_ok=False)
 for name,p in [('wrfinput_d01',initial),('wrfbdy_d01',boundary)]:
  dst=out/name;shutil.copyfile(p,dst)
  with Dataset(dst,'r+') as d:
   d.setncattr('UDM_NUMBER_POLICY',np.int32(1));d.setncattr('UDM_POPULATION_POLICY',np.int32(0))
   d.setncattr('UDM_ZERO_NUMBER_PRODUCER','exact-zero-clear-real-v1')
   d.setncattr('UDM_NUMBER_DEFINITION','eta=n/rho_d; exact zero only; no nonzero conversion')
   d.setncattr('UDM_BOUNDARY_SUPPORT','not enabled; existing specified-boundary guard retained')
  after=inspect(dst,name=='wrfbdy_d01')
  if before[name]!=after:raise ValueError('producer changed arrays')
 result={'files':before,'all_arrays_preserved':True,'number_definition':'exact zero is invariant between n and n/rho_d for finite positive density','boundary_runtime_support':False,'production_accepted':False}
 (out/'producer.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('initial',type=Path);a.add_argument('boundary',type=Path);a.add_argument('output',type=Path);q=a.parse_args();produce(q.initial,q.boundary,q.output)
