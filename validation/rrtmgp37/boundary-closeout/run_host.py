#!/usr/bin/env python3
"""Bounded actual host replay of PR189's existing declared nonzero branch."""
from pathlib import Path
import importlib.util,json,os,shutil,hashlib
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-boundary-closeout-host-v1';O.mkdir(exist_ok=False);d=O/'host';d.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-restart-first-nonzero-host-v1/host'
for p in prior.iterdir():
 if p.is_symlink():(d/p.name).symlink_to(p.resolve())
 elif p.name in ['wrfbdy_d01']:(d/p.name).symlink_to(p.resolve())
 elif p.name in ['namelist.input','radiation_iofields.txt']:shutil.copyfile(p,d/p.name)
(d/'boundary_closeout.enabled').touch();exe=B/'udm37-boundary-closeout-probe-build-v1/wrf'
r=h.Runner(O,180,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
receipt={'executable':h.pin(exe),'namelist':h.pin(d/'namelist.input'),'checkpoint':h.pin(d/'wrfrst_d01_2016-10-06_05:59:00'),'forcing':h.pin(d/'wrfbdy_d01'),'commands':r.commands,'production_accepted':False}
log=r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],d,'bounded_nonzero_host_observation').read_text(errors='replace');receipt['commands']=r.commands;h.write_json(O/'receipt.json',receipt);assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log
inventory={}
with Dataset(next(prior.glob('wrfout*'))) as a,Dataset(next(d.glob('wrfout*'))) as b:
 a.set_auto_mask(False);b.set_auto_mask(False);assert set(a.variables)==set(b.variables)
 times=lambda f:[b''.join(t).decode() for t in f['Times'][:]]
 ta=times(a);tb=times(b);assert ta==tb
 for i,t in enumerate(ta):
  inventory[t]={}
  for n,v in a.variables.items():
   aa=np.asarray(v[i] if v.dimensions and v.dimensions[0]=='Time' else v[:]);bb=np.asarray(b[n][i] if v.dimensions and v.dimensions[0]=='Time' else b[n][:]);assert aa.tobytes()==bb.tobytes(),('observer changed history',t,n)
   inventory[t][n]={'shape':list(aa.shape),'dtype':aa.dtype.str,'reference_sha256':hashlib.sha256(aa.tobytes()).hexdigest(),'observed_sha256':hashlib.sha256(bb.tobytes()).hexdigest()}
receipt.update(status='SUCCESS',observer_compared_pairs=sum(map(len,inventory.values())),observer_inventory=inventory,reference_history=h.pin(next(prior.glob('wrfout*'))),observed_history=h.pin(next(d.glob('wrfout*'))),trace=h.pin(d/'boundary-closeout.txt'));h.write_json(O/'receipt.json',receipt);print('BOUNDED_HOST_OBSERVER_NONINTERFERENCE',receipt['observer_compared_pairs']);print((d/'boundary-closeout.txt').read_text())
