from pathlib import Path
import importlib.util,json,os,re,shutil,sys
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;arm=sys.argv[1];assert arm in ['selection','capture']
O=B/('udm37-frozen-selected-'+arm+'-v1');O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-vapor-corrected-day-v2/host'
for p in prior.iterdir():
 if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 elif p.name in ['wrfinput_d01','wrfbdy_d01']:(D/p.name).symlink_to(p.resolve())
 elif p.name=='radiation_iofields.txt':shutil.copyfile(p,D/p.name)
nml=(prior/'namelist.input').read_text()
for n,v in dict(run_seconds='3600',end_day='06',end_hour='1').items():
 nml,c=re.subn(r'(?im)^(\s*'+n+r'\s*=\s*)[^,\n]+',lambda m:m[1]+v,nml);assert c==1,(n,c)
(D/'namelist.input').write_text(nml)
env={k:v for k,v in os.environ.items() if not k.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_RESEARCH_','WRF_RADIATION_ENERGY'))};env.update(LD_LIBRARY_PATH=str(B/'deps/netcdf/lib'),OMP_NUM_THREADS='1')
if arm=='selection':exe=B/'udm37-frozen-selected-build-v1/wrf'
else:
 exe=B/'udm37-vapor-corrected-public-v2/wrf';target=json.loads((B/'udm37-frozen-selected-selection-v1/target.json').read_text());(D/'capture').mkdir();env.update(WRF_RRTMGP_CAPTURE_DIR=str(D/'capture'),WRF_RRTMGP_CAPTURE_CALL='6',WRF_RRTMGP_COLUMN_I=str(target['i']),WRF_RRTMGP_COLUMN_J=str(target['j']))
r=h.Runner(O,1800,env,1);receipt={'arm':arm,'executable':h.pin(exe),'initial':h.pin(D/'wrfinput_d01'),'forcing':h.pin(D/'wrfbdy_d01'),'namelist':h.pin(D/'namelist.input'),'environment':{k:v for k,v in env.items() if k.startswith('WRF_RRTMGP_') or k=='OMP_NUM_THREADS'},'status':'STARTING','commands':[]};h.write_json(O/'receipt.json',receipt);error=None
try:r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],D,'important_frozen_'+arm)
except Exception as e:error=str(e)
log=(O/'command-01.stdout').read_text(errors='replace');receipt.update(commands=r.commands,error=error,status='SUCCESS' if not error and 'SUCCESS COMPLETE WRF' in log else 'STOPPED');h.write_json(O/'receipt.json',receipt);print(receipt['status'],error)
