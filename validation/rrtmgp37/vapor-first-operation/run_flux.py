from pathlib import Path
import importlib.util,json,os,re,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-vapor-flux-host-v1';O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-convective-support-host-v1/host'
for p in prior.iterdir():
 if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 elif p.name in ['wrfinput_d01','wrfbdy_d01']:(D/p.name).symlink_to(p.resolve())
 elif p.name=='radiation_iofields.txt':shutil.copyfile(p,D/p.name)
nml=(prior/'namelist.input').read_text()
for n,v in {'run_seconds':'120','end_day':'06','end_hour':'0','end_minute':'2','history_interval_s':'60'}.items():
 nml,c=re.subn(r'(?im)^(\s*'+n+r'\s*=\s*)[^,\n]+',lambda m:m[1]+v,nml);assert c==1
(D/'namelist.input').write_text(nml);exe=B/'udm37-vapor-flux-build-v1/wrf';r=h.Runner(O,3600,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
receipt={'purpose':'actual PD face operands for first final negative at source60, native (7,49,20), original unmodified physics','initial':h.pin(D/'wrfinput_d01'),'forcing':h.pin(D/'wrfbdy_d01'),'namelist':h.pin(D/'namelist.input'),'executable':h.pin(exe),'status':'STARTING'};h.write_json(O/'receipt.json',receipt)
error=None
try:r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],D,'original_vapor_first_operation')
except Exception as e:error=str(e)
receipt.update(commands=r.commands,error=error,status='SUCCESS' if error is None else 'STOPPED');h.write_json(O/'receipt.json',receipt)
