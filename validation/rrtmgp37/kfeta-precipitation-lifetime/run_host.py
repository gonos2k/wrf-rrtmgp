from pathlib import Path
import importlib.util,json,os,re,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-kfeta-expiry-host-v1';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},2)
prior=B/'udm37-restart-first-fix-run-v2/restart';nml=(prior/'namelist.input').read_text()
nml,count=re.subn(r'(?im)^(\s*end_minute\s*=\s*)[^,\n]+',lambda m:m[1]+'6',nml);assert count==1
nml,count=re.subn(r'(?im)^(\s*run_seconds\s*=\s*)[^,\n]+',lambda m:m[1]+'420',nml);assert count==1
receipt={'scope':'same old checkpoint, 05:59--06:06 candidate integration and observer ON/OFF, not a cold-versus-restart proof','commands':[],'arms':{}}
for arm,build in [('public','udm37-kfeta-expiry-build-v1'),('observed','udm37-kfeta-expiry-probe-v1')]:
 d=O/arm;d.mkdir()
 for p in prior.iterdir():
  if p.is_symlink():(d/p.name).symlink_to(p.resolve())
  elif p.name.startswith('wrfrst') or p.name=='wrfbdy_d01':(d/p.name).symlink_to(p.resolve())
  elif p.name=='radiation_iofields.txt':shutil.copyfile(p,d/p.name)
 (d/'namelist.input').write_text(nml);exe=B/build/'wrf'
 receipt['arms'][arm]={'executable':h.pin(exe),'namelist':h.pin(d/'namelist.input'),'forcing':h.pin(d/'wrfbdy_d01'),'checkpoint':h.pin(next(d.glob('wrfrst*')))}
 r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],d,'KFETA_candidate_'+arm)
receipt['commands']=r.commands;receipt['status']='SUCCESS';h.write_json(O/'receipt.json',receipt)
