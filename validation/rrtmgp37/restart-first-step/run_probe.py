#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,shutil,os
from netCDF4 import Dataset
import numpy as np
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-restart-first-probe-run-v1';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
seed=B/'udm37-specified-number-run-v2';exe=B/'udm37-restart-first-probe-build-v1/wrf'
r=h.Runner(O,900,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},2);receipt={'executable':h.pin(exe),'commands':r.commands,'noninterference':{},'production_accepted':False}
for arm in ['restart','continuous']:
 d=O/arm;d.mkdir()
 for p in (seed/arm).iterdir():
  if p.is_symlink():(d/p.name).symlink_to(p.resolve())
  elif p.name in ['namelist.input','radiation_iofields.txt']:shutil.copyfile(p,d/p.name)
 (d/'restart_probe.enabled').touch()
 log=r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],d,arm).read_text(errors='replace');assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log
 a=next(d.glob('wrfout*'));b=next((seed/arm).glob('wrfout*'));same=0
 with Dataset(a) as x,Dataset(b) as y:
  x.set_auto_mask(False);y.set_auto_mask(False);assert set(x.variables)==set(y.variables)
  for n in x.variables:
   assert x[n][:].tobytes()==y[n][:].tobytes(),('probe changes original history',arm,n)
   same+=1
 receipt['noninterference'][arm]={'same_full_history_arrays':same,'probe_outputs':len(list(d.glob('probe-*.bin'))),'history':h.pin(a)};receipt['commands']=r.commands;h.write_json(O/'receipt.json',receipt);print('PROBE_TRAJECTORY_MATCHES_ORIGINAL',arm,same,flush=True)
