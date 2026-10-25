"""Produce real initial/boundary input using the retained identified REAL producer."""
from pathlib import Path
import importlib.util,json,os,re,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
W=B/'udm37-sterling-interior-wps-v3';assert json.loads((W/'receipt.json').read_text())['status']=='SUCCESS'
O=B/'udm37-sterling-interior-real-v1';O.mkdir(exist_ok=False);D=O/'host';D.mkdir();prior=B/'udm37-matthew-real-v1/case'
for p in prior.iterdir():
 if p.is_symlink() and not p.name.startswith('met_em'):(D/p.name).symlink_to(p.resolve())
for p in sorted(W.glob('met_em*.nc')):(D/p.name).symlink_to(p)
nml=(prior/'namelist.input').read_text()
for key,val in {'e_sn':'144','time_step':'60','numtiles':'1'}.items():
 nml,n=re.subn(r'(?m)^(\s*'+key+r'\s*=\s*)[^,\n]+',lambda m:m[1]+val,nml);assert n==1
(D/'namelist.input').write_text(nml)
exe=B/'udm37-pr60-active-cu-current-build-v1/source-v3/WRF/main/real.exe';env={**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'};run=h.Runner(O,600,env,1)
receipt={'status':'STARTING','preprocessor_executable':h.pin(exe),'namelist':h.pin(D/'namelist.input'),'retained_preprocessor_not_current_WRF_build':True,'preprocessor_namelist_is_original_REAL_with_geometry_dt_tile_only_changes':True,'forecast_processes':0,'commands':[]};h.write_json(O/'receipt.json',receipt)
try:
 run.run(['bash','-c','ulimit -s unlimited; exec "$@"','real',exe],D,'retained_REAL_new_interior_inputs')
 logs='\n'.join(p.read_text(errors='replace') for p in [O/'command-01.stdout',*D.glob('rsl.out.*')]);assert 'SUCCESS COMPLETE REAL_EM INIT' in logs
 receipt.update(status='SUCCESS',commands=run.commands,outputs={n:h.pin(D/n) for n in ['wrfinput_d01','wrfbdy_d01']})
except Exception as e:receipt.update(status='FAILED',commands=run.commands,error=str(e));raise
finally:h.write_json(O/'receipt.json',receipt)
s=importlib.util.spec_from_file_location('conv',R/'WRF/test/rrtmgp/convert_udm_specified.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c);c.produce_zero(D/'wrfinput_d01',D/'wrfbdy_d01',O/'encoded')
forecast=(B/'udm37-vapor-corrected-day-v2/host/namelist.input').read_text();forecast,n=re.subn(r'(?m)^(\s*e_sn\s*=\s*)[^,\n]+',r'\g<1>144',forecast);assert n==1
(O/'forecast.namelist.input').write_text(forecast);receipt['encoded_outputs']={n:h.pin(O/'encoded'/n) for n in ['wrfinput_d01','wrfbdy_d01']};receipt['forecast_namelist']=h.pin(O/'forecast.namelist.input');receipt['unprovided_condensate_remains_explicit_limitation']=True;h.write_json(O/'receipt.json',receipt);print('REAL_AND_NUMBER_CONTRACT_PREPARED')
