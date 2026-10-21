#!/usr/bin/env python3
"""Execute a real forcing-record crossing and a between-call restart, serial only."""
from pathlib import Path
import os,sys,importlib.util,shutil,re,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-specified-number-run-v2';O.mkdir(exist_ok=False)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');conv=load('converter',R/'WRF/test/rrtmgp/convert_udm_specified.py')
source=B/'udm37-matthew-real-v1/case';exe=B/'udm37-specified-number-build-v1/wrf';conv.produce_zero(source/'wrfinput_d01',source/'wrfbdy_d01',O/'encoded')
runner=h.Runner(O,900,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},8)
receipt={'plan':h.pin(P/'plan.json'),'executable':h.pin(exe),'runs':[],'production_accepted':False}
def assign(text,key,val,group):
 pattern=r'(?m)^(\s*'+key+r'\s*=).*?[,]?\s*$'
 if re.search(pattern,text):return re.sub(pattern,lambda m:m[1]+' '+str(val)+',',text)
 return text.replace('&'+group,'&'+group+'\n '+key+' = '+str(val)+',',1)
def stage(name,kind):
 d=O/name;d.mkdir()
 for f in (R/'WRF/run').iterdir():
  if f.is_file() and f.name!='namelist.input':(d/f.name).symlink_to(f.resolve())
 for f in ['wrfinput_d01','wrfbdy_d01']:(d/f).symlink_to(((source if kind=='legacy' else O/'encoded')/f).resolve())
 shutil.copyfile(source/'radiation_iofields.txt',d/'radiation_iofields.txt')
 text=(source/'namelist.input').read_text()
 vals={'time_control':{'run_hours':0,'run_seconds':20 if kind=='legacy' else 21720,'end_day':'06','end_hour':0 if kind=='legacy' else 6,'end_minute':0 if kind=='legacy' else 2,'end_second':20 if kind=='legacy' else 0,'history_interval':0 if kind!='legacy' else 1,'history_interval_s':60 if kind!='legacy' else 0,'history_begin_s':21480 if kind!='legacy' else 0,'restart_interval':0,'restart_interval_s':21540 if kind!='legacy' else 0},'domains':{'time_step':10 if kind=='legacy' else 60,'numtiles':1},'physics':{'ra_lw_physics':37,'ra_sw_physics':37,'udm_number_policy':0 if kind=='legacy' else 1,'udm_population_policy':0,'rrtmgp_capacity_policy':0,'rrtmgp_liquid_size_policy':0,'rrtmgp_udm_frozen_optics':0 if kind=='legacy' else 1,'rrtmgp_udm_frozen_table':"'"+str(R/'validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc')+"'",'rrtmgp_data_path':"'"+str(R/'WRF/run')+"'"},'dynamics':{'scalar_adv_opt':0},'bdy_control':{'have_bcs_scalar':'.false.' if kind=='legacy' else '.true.','have_bcs_moist':'.false.' if kind=='legacy' else '.true.'}}
 for group,v in vals.items():
  for k,value in v.items():text=assign(text,k,value,group)
 if kind=='restart':
  for k,v in {'restart':'.true.','start_hour':5,'start_minute':59,'start_second':0,'run_seconds':180,'override_restart_timers':'.true.','history_begin_s':0,'restart_interval_s':1000000}.items():text=assign(text,k,v,'time_control')
  f=O/'continuous/wrfrst_d01_2016-10-06_05:59:00';(d/f.name).symlink_to(f.resolve(strict=True))
 (d/'namelist.input').write_text(text);return d
for name,kind in [('continuous','number1'),('restart','restart')]:
 d=stage(name,kind);receipt['runs'].append({'name':name,'status':'PREPARED','namelist':h.pin(d/'namelist.input')});receipt['commands']=runner.commands;h.write_json(O/'receipt.json',receipt)
 try:
  log=runner.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],d,name).read_text(errors='replace')
  assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log and not runner.commands[-1]['timed_out']
  receipt['runs'][-1]['status']='SUCCESS'
 except BaseException as err:
  receipt['runs'][-1].update(status='FAIL_PRESERVED',error=repr(err));raise
 finally:
  receipt['commands']=runner.commands;h.write_json(O/'receipt.json',receipt)
 print('WRF_COMPLETED',name,flush=True)
print('SPECIFIED_NUMBER_BOUNDARY_EXECUTION_COMPLETE')
