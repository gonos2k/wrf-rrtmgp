from pathlib import Path
import importlib.util,json,os,re,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-vapor-components-host-v1';O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-restart-first-fix-run-v2/restart'
for p in prior.iterdir():
 if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 elif p.name.startswith('wrfrst') or p.name=='wrfbdy_d01':(D/p.name).symlink_to(p.resolve())
 elif p.name=='radiation_iofields.txt':shutil.copyfile(p,D/p.name)
nml=(prior/'namelist.input').read_text()
for n,v in {'run_seconds':'21720','end_hour':'12','end_minute':'1','history_interval_s':'3600','history_begin_s':'60'}.items():
 nml,c=re.subn(r'(?im)^(\s*'+n+r'\s*=\s*)[^,\n]+',lambda m:m[1]+v,nml);assert c==1
(D/'namelist.input').write_text(nml);exe=B/'udm37-vapor-components-build-v1/wrf';r=h.Runner(O,3600,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
receipt={'scope':'bounded original 05:59--12:01 replay for actual first PD source components at (88,98,22), original physics and forcing','checkpoint':h.pin(next(D.glob('wrfrst*'))),'forcing':h.pin(D/'wrfbdy_d01'),'namelist':h.pin(D/'namelist.input'),'executable':h.pin(exe),'status':'STARTING'};h.write_json(O/'receipt.json',receipt)
error=None
try:r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],D,'original_PD_source_components')
except Exception as e:error=str(e)
receipt.update(commands=r.commands,error=error,status='SUCCESS' if error is None else 'STOPPED');h.write_json(O/'receipt.json',receipt)
