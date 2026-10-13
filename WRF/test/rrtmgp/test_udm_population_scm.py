#!/usr/bin/env python3
"""Short actual warm-only host integration and population checkpoint identity.

The all-warm EOS-adjusted column is a manufactured research input, not a general
real/ideal producer or a migration of an unknown legacy checkpoint.
"""
import argparse,hashlib,importlib.util,json,os,shutil,sys
from pathlib import Path
import netCDF4,numpy as np
sys.dont_write_bytecode=True

def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def require(ok,msg):
 if not ok:raise ValueError(msg)

def manufacture(path,population=1):
 with netCDF4.Dataset(path,'r+') as d:
  pressure=np.asarray(d['P'][:]+d['PB'][:],dtype=np.float32)
  exner=np.float32((pressure/1.e5)**(287./1004.5))
  # Declare all-warm column explicitly. Update inverse dry density consistently
  # with fixed pressure, temperature and vapor at the initial state.
  temp=np.full_like(pressure,285.);svp=np.float32(610.78*np.exp(17.269*(285.-273.16)/(285.-35.86)))
  vapor=np.float32(1.001*.622*svp/(pressure-svp))
  rho=np.float32(pressure/(temp*(287.+461.6*vapor)))
  d['T'][:]=np.float32(temp/exner-300.)
  if 'THM' in d.variables:d['THM'][:]=np.float32((temp/exner)*(1.+(461.6/287.)*vapor)-300.)
  if 'T_INIT' in d.variables:d['T_INIT'][:]=d['T'][:]
  d['QVAPOR'][:]=vapor
  d['AL'][:]=np.float32(1./rho-np.asarray(d['ALB'][:]))
  for n in ('QICE','QSNOW','QGRAUP','QHAIL'):d[n][:]=0.
  d['QCLOUD'][:]=.01;d['QRAIN'][:]=0.
  for n,volume in [('QNCCN',2.e8),('QNCLOUD',2.e9),('QNRAIN',0.)]:d[n][:]=np.float32(volume/rho)
  d.setncattr('UDM_NUMBER_POLICY',np.int32(1));d.setncattr('UDM_POPULATION_POLICY',np.int32(population))
  d.setncattr('UDM_RESEARCH_INPUT','manufactured all-warm constant T=285K; EOS density; grid dry-mass number')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--exe',required=True,type=Path);ap.add_argument('--seed',required=True,type=Path);ap.add_argument('--workdir',required=True,type=Path);a=ap.parse_args();root=a.wrf_root.resolve();exe=a.exe.resolve();seed=a.seed.resolve();work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
 helper=load(root/'test/rrtmgp/test_netcdf_zz.py','runner');setup=load(root/'test/rrtmgp/test_udm_startup_snow_scm.py','setup')
 env={**os.environ,'OMP_NUM_THREADS':'1','LC_ALL':'C','LD_LIBRARY_PATH':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/lib:'+os.environ.get('LD_LIBRARY_PATH','')}
 for n in tuple(env):
  if n.startswith(('WRF_RRTMGP_','WRF_UDM_')):env.pop(n)
 runner=helper.Runner(work,180,env,10);report={'schema':'UDM_POPULATION_SCM_V1','status':'PREPARED','executable':helper.pin(exe),'production_accepted':False,'processes':[]}
 def save():report['processes']=runner.commands;helper.write_json(work/'receipt.json',report)
 def case(name,pop=1,restart=False):
  d=work/name;d.mkdir()
  for p in seed.iterdir():
   if not p.is_file() or p.name.startswith(('wrfout','wrfrst','rsl.','udm_')) or p.name in ('namelist.output','stdout.log','namelist.input'):continue
   shutil.copy2(p,d/p.name)
  text=(seed/'namelist.input').read_text()
  for k,v,g in [('run_minutes','0','time_control'),('run_seconds','10','time_control'),('end_minute','0','time_control'),('end_second','20' if restart else '10','time_control'),('history_interval_s','10','time_control'),('restart_interval','0','time_control'),('restart_interval_s','10','time_control'),('restart','.true.' if restart else '.false.','time_control'),('udm_number_policy','1','physics'),('udm_population_policy',str(pop),'physics')]:text=setup.set_assignment(text,k,v,group=g)
  if restart:text=setup.set_assignment(text,'start_second','10',group='time_control')
  (d/'namelist.input').write_text(text);manufacture(d/'wrfinput_d01',pop);return d
 def run(d,name,failure=None):
  try:out=runner.run([exe],d,name)
  except RuntimeError:
   require(failure is not None,'unexpected WRF failure');out=work/f'command-{len(runner.commands):02d}.stdout'
  text=out.read_text(errors='replace')
  if failure:
   require(failure in text and 'SUCCESS COMPLETE WRF' not in text,'intended rejection not observed')
   if 'population differs' in failure:require(not list(d.glob('wrfout*')),'input rejection wrote history')
   else:
    for p in d.glob('wrfout*'):
     with netCDF4.Dataset(p) as nc:require(nc['Times'].shape[0]==1,'unsupported physics advanced history')
  else:require('SUCCESS COMPLETE WRF' in text and 'FATAL CALLED' not in text,'actual host did not complete')
  save()
 try:
  control=case('control');run(control,'WRF_integrated_control')
  restart=case('restart',restart=True);checkpoint=control/'wrfrst_d01_1999-10-22_19:00:10';require(checkpoint.is_file(),'checkpoint missing');shutil.copy2(checkpoint,restart/checkpoint.name);run(restart,'WRF_integrated_restart')
  # Matching elapsed integration as one 20s execution for restart equality.
  full=case('full20');text=(full/'namelist.input').read_text();text=setup.set_assignment(text,'run_seconds','20',group='time_control');text=setup.set_assignment(text,'end_second','20',group='time_control');(full/'namelist.input').write_text(text);run(full,'WRF_integrated_full20')
  with netCDF4.Dataset(next(full.glob('wrfout*'))) as x,netCDF4.Dataset(next(restart.glob('wrfout*'))) as y:
   require(int(x.UDM_POPULATION_POLICY)==int(y.UDM_POPULATION_POLICY)==1,'history marker absent')
   compared=0
   for n in x.variables:
    if 'Time' in x[n].dimensions:
     require(np.array_equal(x[n][-1],y[n][-1]),'integrated restart differs '+n);compared+=1
   report['terminal_variable_comparisons']=compared
   report['finite_state']=all(np.all(np.isfinite(x[n][:])) for n in ('QNCCN','QNCLOUD','QNRAIN','QCLOUD','QRAIN','T'))
  with netCDF4.Dataset(checkpoint) as d:require(int(d.UDM_POPULATION_POLICY)==1,'checkpoint marker absent')
  wrong=case('reject_population');
  with netCDF4.Dataset(wrong/'wrfinput_d01','r+') as d:d.delncattr('UDM_POPULATION_POLICY')
  run(wrong,'WRF_reject_population','UDM population differs')
  cold=case('reject_cold');
  with netCDF4.Dataset(cold/'wrfinput_d01','r+') as d:d['QICE'][:]=1.e-5
  run(cold,'WRF_reject_cold','warm-only column required')
  report.update(status='PASS_SCOPED_ACTUAL_WARM_HOST_INTEGRATION',WRF_processes=5,control_seconds=20,restart_seconds=10,physical_gate_closed=False,source_files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'phys/module_mp_udm.F',root/'phys/module_microphysics_driver.F',root/'share/input_wrf.F',root/'share/output_wrf.F',root/'Registry/Registry.EM_COMMON']});save();print(json.dumps({'status':report['status'],'receipt':str(work/'receipt.json')}))
 except BaseException as e:report.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':main()
