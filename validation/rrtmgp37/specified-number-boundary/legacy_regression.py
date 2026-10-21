#!/usr/bin/env python3
"""Changed-boundary regression: old/new public executables, same real state, terminal output."""
from pathlib import Path
import os,importlib.util,re,shutil,json
from netCDF4 import Dataset
import numpy as np
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-specified-number-legacy-v1';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
r=h.Runner(O,180,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},2)
seed=B/'udm37-specified-number-run-v1/legacy20';exe={'old':B/'udm37-radiation-options-build-v1/producer/main/wrf','new':B/'udm37-specified-number-build-v1/wrf'}
for name in exe:
 d=O/name;d.mkdir()
 for p in seed.iterdir():
  if p.is_symlink():(d/p.name).symlink_to(p.resolve())
  elif p.name in ['namelist.input','radiation_iofields.txt']:shutil.copyfile(p,d/p.name)
 text=(d/'namelist.input').read_text();text=re.sub(r'(?m)^(\s*history_interval\s*=).*$',r'\g<1> 0,',text);text=re.sub(r'(?m)^(\s*history_interval_s\s*=).*$',r'\g<1> 10,',text);(d/'namelist.input').write_text(text)
 log=r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe[name]],d,name).read_text();assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log
files=[next((O/name).glob('wrfout*')) for name in exe];count=0;rows={}
with Dataset(files[0]) as old,Dataset(files[1]) as new:
 old.set_auto_mask(False);new.set_auto_mask(False);assert list(old.variables)==list(new.variables)
 assert len(old.dimensions['Time'])==3
 for name,v in old.variables.items():
  a=np.asarray(v[:]);b=np.asarray(new[name][:]);assert a.shape==b.shape and a.dtype==b.dtype and a.tobytes()==b.tobytes(),name
  rows[name]={'shape':list(a.shape),'sha256':__import__('hashlib').sha256(a.tobytes()).hexdigest()};count+=1
h.write_json(O/'receipt.json',{'commands':r.commands,'executables':{n:h.pin(p) for n,p in exe.items()},'same_arrays':count,'times':3,'through_model_seconds':20,'array_inventory':rows,'namelists':{n:h.pin(O/n/'namelist.input') for n in exe},'production_accepted':False})
print('LEGACY_BOUNDARY_REGRESSION_IDENTICAL',count,'arrays x3 times')
