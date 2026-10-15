#!/usr/bin/env python3
"""Replay original failing physical input, policy2 continuation across CF0 and restart."""
import argparse,hashlib,importlib.util,json,os,shutil,sys
from pathlib import Path
import numpy as np,netCDF4
sys.dont_write_bytecode=True

def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def require(ok,msg):
 if not ok:raise ValueError(msg)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--exe',required=True,type=Path);ap.add_argument('--original',required=True,type=Path);ap.add_argument('--workdir',required=True,type=Path);a=ap.parse_args();root=a.wrf_root.resolve();src=a.original.resolve();exe=a.exe.resolve();b=a.workdir.resolve();b.mkdir(parents=True,exist_ok=False)
 h=load(root/'test/rrtmgp/test_netcdf_zz.py','runner');setup=load(root/'test/rrtmgp/test_udm_startup_snow_scm.py','setup');env={**os.environ,'OMP_NUM_THREADS':'1','LD_LIBRARY_PATH':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/lib:'+os.environ.get('LD_LIBRARY_PATH','')}
 for key in tuple(env):
  if key.startswith(('WRF_RRTMGP_','WRF_UDM_')):env.pop(key)
 runner=h.Runner(b,180,env,8);r={'schema':'CF0_WARM_SCM_V1','status':'PREPARED','executable':h.pin(exe),'original_input':h.pin(src/'wrfinput_d01'),'original_namelist':h.pin(src/'namelist.input'),'source_files':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'phys/module_mp_udm.F',root/'phys/module_ra_rrtmgp.F',root/'phys/module_ra_rrtmg_lw.F',root/'phys/module_ra_rrtmg_sw.F',root/'phys/module_physics_init.F',root/'share/input_wrf.F']},'processes':[],'production_accepted':False}
 def save():r['processes']=runner.commands;h.write_json(b/'receipt.json',r)
 def case(name,policy=2,seconds=60,restart=False,capture=False):
  d=b/name;d.mkdir()
  for p in src.iterdir():
   if p.is_file() and not p.name.startswith(('wrfout','wrfrst','rsl.','udm_')) and p.name not in ('namelist.output','stdout.log'):shutil.copy2(p,d/p.name)
  text=(src/'namelist.input').read_text()
  settings=[('udm_population_policy',str(policy),'physics'),('run_minutes','0' if restart else str(seconds//60),'time_control'),('run_seconds','30' if restart else str(seconds%60),'time_control'),('restart_interval','0','time_control'),('restart_interval_s','30','time_control'),('restart','.true.' if restart else '.false.','time_control'),('end_minute','1','time_control'),('end_second','0','time_control')]
  if restart:settings += [('start_second','30','time_control')]
  for k,v,g in settings:text=setup.set_assignment(text,k,v,group=g)
  (d/'namelist.input').write_text(text)
  if policy==2:
   with netCDF4.Dataset(d/'wrfinput_d01','r+') as x:x.setncattr('UDM_POPULATION_POLICY',np.int32(2))
  # Physical values must be unchanged; only an explicit policy tag may differ.
  with netCDF4.Dataset(src/'wrfinput_d01') as x,netCDF4.Dataset(d/'wrfinput_d01') as y:
   for n in x.variables:require(np.array_equal(x[n][:],y[n][:]),'physical initial input changed '+n)
  if capture:(d/'capture').mkdir()
  return d
 def run(d,name,reject=False,capture=False):
  if capture:runner.environment['WRF_RRTMGP_CAPTURE_DIR']=str(d/'capture')
  else:runner.environment.pop('WRF_RRTMGP_CAPTURE_DIR',None)
  p=runner.run([exe],d,name);text=p.read_text(errors='replace');save()
  if reject:require('UDM_CF0_REJECT' in text and 'CF0 condensate unsupported' in text and 'SUCCESS COMPLETE WRF' not in text,'strict failure not reproduced')
  else:require('SUCCESS COMPLETE WRF' in text and 'FATAL CALLED' not in text,'new policy does not complete original failing window')
 try:
  strict=case('strict',1);run(strict,'WRF_original_strict',True)
  control=case('control',capture=True);run(control,'WRF_CF0_grid_control',capture=True)
  checkpoint=control/'wrfrst_d01_1999-10-22_19:00:30';require(checkpoint.is_file(),'checkpoint before transition absent')
  restart=case('restart',restart=True);shutil.copy2(checkpoint,restart/checkpoint.name);run(restart,'WRF_CF0_grid_restart')
  with netCDF4.Dataset(next(control.glob('wrfout*'))) as x,netCDF4.Dataset(next(restart.glob('wrfout*'))) as y:
   require(int(x.UDM_POPULATION_POLICY)==int(y.UDM_POPULATION_POLICY)==2,'version2 output marker missing')
   compared=0
   for n in x.variables:
    if 'Time' in x[n].dimensions:require(np.array_equal(x[n][-1],y[n][-1]),'restart crossing CF0 differs '+n);compared+=1
   require(all(np.all(np.isfinite(x[n][:])) for n in ('QNCCN','QNCLOUD','QNRAIN','QVAPOR','QCLOUD','QRAIN','T')),'nonfinite continuing state')
  r.update(status='PASS_SCOPED_ACTUAL_CF0_CONTINUATION',WRF_processes=3,continuous_seconds=60,restart_seconds=30,checkpoint_before_original_failure=True,terminal_arrays_equal=compared,physical_initial_arrays_unchanged=True,first_strict_failure_seconds=40,physical_gate_closed=False);save();print(json.dumps({'status':r['status'],'receipt':str(b/'receipt.json')}))
 except BaseException as e:r.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':main()
