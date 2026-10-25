from pathlib import Path
import importlib.util,json,os,re,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-cloud-run-v1';O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-vapor-corrected-day-v2/host';cp=prior/'wrfrst_d01_2016-10-06_11:58:00';(D/cp.name).symlink_to(cp)
for p in prior.iterdir():
 if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 elif p.name in ['wrfinput_d01','wrfbdy_d01']:(D/p.name).symlink_to(p.resolve())
 elif p.name=='radiation_iofields.txt':shutil.copyfile(p,D/p.name)
nml=(prior/'namelist.input').read_text();changes=dict(run_seconds='18120',start_hour='11',start_minute='58',end_day='06',end_hour='17',end_minute='0',end_second='0',history_begin_s='120',history_interval_s='3600',restart_interval_s='1000000',restart='.true.',override_restart_timers='.true.')
for n,v in changes.items():
 if not re.search(r'(?im)^\s*'+n+r'\s*=',nml):nml=nml.replace('&time_control','&time_control\n '+n+' = '+v+',',1)
 nml,c=re.subn(r'(?im)^(\s*'+re.escape(n)+r'\s*=\s*)[^,\n]+',lambda m:m[1]+v,nml);assert c==1,(n,c)
(D/'namelist.input').write_text(nml);exe=B/'udm37-sterling-cloud-build-v1/wrf'
env={k:v for k,v in os.environ.items() if not k.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_RESEARCH_','WRF_RADIATION_ENERGY'))};env.update(LD_LIBRARY_PATH=str(B/'deps/netcdf/lib'),OMP_NUM_THREADS='1')
r=h.Runner(O,3600,env,1);receipt={'status':'STARTING','checkpoint':h.pin(cp),'initial':h.pin(D/'wrfinput_d01'),'forcing':h.pin(D/'wrfbdy_d01'),'namelist':h.pin(D/'namelist.input'),'executable':h.pin(exe),'commands':[],'production_changes':False,'new_policy':False};h.write_json(O/'receipt.json',receipt);error=None
try:r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],D,'bounded_actual_cloud_input_observation')
except Exception as e:error=str(e)
log=(O/'command-01.stdout').read_text(errors='replace');receipt.update(status='SUCCESS' if not error and 'SUCCESS COMPLETE WRF' in log else 'STOPPED',commands=r.commands,error=error);h.write_json(O/'receipt.json',receipt);print(receipt['status'],error)
