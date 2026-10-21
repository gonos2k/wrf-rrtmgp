#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,shutil,os
from netCDF4 import Dataset
import numpy as np
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-restart-first-fix-run-v2';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
seed=B/'udm37-specified-number-run-v2';exe=B/'udm37-restart-first-fix-build-v2/wrf'
r=h.Runner(O,900,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},2);receipt={'executable':h.pin(exe),'source':h.pin(R/'WRF/dyn_em/solve_em.F'),'commands':r.commands,'original_configuration_preserved':True,'production_accepted':False}
for arm in ['continuous','restart']:
 d=O/arm;d.mkdir()
 for p in (seed/arm).iterdir():
  if p.is_symlink() and not p.name.startswith('wrfrst'):(d/p.name).symlink_to(p.resolve())
  elif p.name in ['namelist.input','radiation_iofields.txt']:shutil.copyfile(p,d/p.name)
 if arm=='restart':
  n='wrfrst_d01_2016-10-06_05:59:00';(d/n).symlink_to((O/'continuous'/n).resolve(strict=True))
 log=r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],d,arm).read_text(errors='replace');assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log
 receipt['commands']=r.commands;h.write_json(O/'receipt.json',receipt);print('FIXED_REAL_COMPLETED',arm,flush=True)
a=next((O/'continuous').glob('wrfout*'));b=next((O/'restart').glob('wrfout*'));differences=[];pairs=0
with Dataset(a) as x,Dataset(b) as y:
 x.set_auto_mask(False);y.set_auto_mask(False)
 times=lambda d:[b''.join(t).decode() for t in d['Times'][:]]
 ta=times(x);tb=times(y);assert set(x.variables)==set(y.variables)
 for t in tb:
  for n,v in x.variables.items():
   aa=np.asarray(v[ta.index(t)] if v.dimensions[0]=='Time' else v[:]);bb=np.asarray(y[n][tb.index(t)] if v.dimensions[0]=='Time' else y[n][:]);pairs+=1
   if aa.tobytes()!=bb.tobytes():differences.append({'time':t,'variable':n,'max_abs':float(np.max(abs(aa.astype(float)-bb.astype(float))))})
receipt.update(array_pairs=pairs,differences=differences,full_host_bitwise_passed=not differences);h.write_json(O/'receipt.json',receipt);print('FIXED_RESTART_ARRAY_PAIRS',pairs,'DIFFERENCES',len(differences),differences,flush=True)
