#!/usr/bin/env python3
"""One preregistered cold 24-hour real-data evaluation; no guard bypass or retry."""
from pathlib import Path
import importlib.util,json,os,re,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-convective-support-host-v1';O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-restart-first-fix-run-v2/continuous'
for p in prior.iterdir():
 if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 elif p.name in ['wrfinput_d01','wrfbdy_d01']:(D/p.name).symlink_to(p.resolve())
 elif p.name=='radiation_iofields.txt':shutil.copyfile(p,D/p.name)
nml=(prior/'namelist.input').read_text()
changes={'run_seconds':'86400','end_day':'07','end_hour':'0','end_minute':'0','end_second':'0','history_begin_s':'0','history_interval_s':'3600','restart_interval_s':'1000000'}
for n,v in changes.items():
 nml,count=re.subn(r'(?im)^(\s*'+re.escape(n)+r'\s*=\s*)[^,\n]+',lambda m:m[1]+v,nml);assert count==1,(n,count)
(D/'namelist.input').write_text(nml)
exe=B/'udm37-convective-support-build-v2/wrf';r=h.Runner(O,7200,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
receipt={'executable':h.pin(exe),'initial':h.pin(D/'wrfinput_d01'),'forcing':h.pin(D/'wrfbdy_d01'),'namelist':h.pin(D/'namelist.input'),'plan':h.pin(P/'plan.json'),'commands':[],'planned_seconds':86400,'status':'STARTING','physical_approval':False};h.write_json(O/'receipt.json',receipt)
error=None
try:r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],D,'fixed_real_24h_evaluation')
except Exception as e:error=str(e)
receipt['commands']=r.commands;log=(O/'command-01.stdout').read_text(errors='replace')
receipt['error']=error;receipt['status']='SUCCESS' if not error and 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log else 'STOPPED'
receipt['last_model_times']=re.findall(r'Timing for main: time (\S+) on domain',log)[-5:]
receipt['trace']=h.pin(D/'real-budget.txt') if (D/'real-budget.txt').exists() else None
h.write_json(O/'receipt.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if k in ['status','error','last_model_times']}))
