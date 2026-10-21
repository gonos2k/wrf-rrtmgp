#!/usr/bin/env python3
"""One bounded replay, original forcing. This is not another restart acceptance campaign."""
from pathlib import Path
import importlib.util,json,os,shutil,hashlib
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-real-budget-host-v2';O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-restart-first-fix-run-v2/restart'
for p in prior.iterdir():
 if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 elif p.name=='wrfbdy_d01':(D/p.name).symlink_to(p.resolve())
 elif p.name in ['namelist.input','radiation_iofields.txt']:shutil.copyfile(p,D/p.name)
exe=B/'udm37-real-budget-build-v5/wrf'
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
receipt={'executable':h.pin(exe),'namelist':h.pin(D/'namelist.input'),'checkpoint':h.pin(D/'wrfrst_d01_2016-10-06_05:59:00'),'forcing':h.pin(D/'wrfbdy_d01'),'commands':[],'scope':'original real baseline forcing; three steps; observer noninterference only'}
log=r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],D,'bounded_real_case_ledger').read_text(errors='replace');receipt['commands']=r.commands;h.write_json(O/'receipt.json',receipt);assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log
inventory={}
with Dataset(next(prior.glob('wrfout*'))) as a,Dataset(next(D.glob('wrfout*'))) as b:
 a.set_auto_mask(False);b.set_auto_mask(False);assert set(a.variables)==set(b.variables)
 ts=lambda f:[b''.join(t).decode() for t in f['Times'][:]]
 assert ts(a)==ts(b)
 for i,t in enumerate(ts(a)):
  inventory[t]={}
  for n,v in a.variables.items():
   aa=np.asarray(v[i] if v.dimensions and v.dimensions[0]=='Time' else v[:]);bb=np.asarray(b[n][i] if v.dimensions and v.dimensions[0]=='Time' else b[n][:]);assert aa.tobytes()==bb.tobytes(),('observer changed',t,n)
   inventory[t][n]={'shape':list(aa.shape),'dtype':aa.dtype.str,'reference_sha256':hashlib.sha256(aa.tobytes()).hexdigest(),'observed_sha256':hashlib.sha256(bb.tobytes()).hexdigest()}
receipt.update(status='SUCCESS',observer_pairs=sum(map(len,inventory.values())),observer_inventory=inventory,trace=h.pin(D/'real-budget.txt'),reference_history=h.pin(next(prior.glob('wrfout*'))),observed_history=h.pin(next(D.glob('wrfout*'))));h.write_json(O/'receipt.json',receipt);print('REAL_CASE_LEDGER_SUCCESS',receipt['observer_pairs'])
