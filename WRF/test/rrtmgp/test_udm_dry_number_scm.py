#!/usr/bin/env python3
"""Run one policy-1 SCM control/restart and explicit representation rejections."""
import argparse,hashlib,importlib.util,json,os,shutil,sys
from pathlib import Path
import netCDF4,numpy as np
sys.dont_write_bytecode=True

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def require(ok,msg):
 if not ok:raise ValueError(msg)

def convert_input(path):
 # Explicit opt-in migration of this manufactured cold input only. Never a
 # checkpoint migration and never inferred from units strings alone.
 with netCDF4.Dataset(path,'r+') as d:
  require('UDM_NUMBER_POLICY' not in d.ncattrs() or int(d.UDM_NUMBER_POLICY)==0,'already encoded input')
  rho=np.float32(1.)/np.float32(d['AL'][:]+d['ALB'][:])
  require(np.all(np.isfinite(rho)) and np.all(rho>0),'invalid input dry density')
  for name in ('QNCCN','QNCLOUD','QNRAIN'):
   v=d[name][:];d[name][:]=np.float32(v/rho)
  d.setncattr('UDM_NUMBER_POLICY',np.int32(1))
  d.setncattr('UDM_NUMBER_POPULATION','dry-number-grid-v1; grid mean free CCN/cloud/rain; research candidate')


def main():
 ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--exe',required=True,type=Path);ap.add_argument('--seed',required=True,type=Path);ap.add_argument('--workdir',required=True,type=Path);args=ap.parse_args()
 root=args.wrf_root.resolve();seed=args.seed.resolve();exe=args.exe.resolve();work=args.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
 helper=load(root/'test/rrtmgp/test_netcdf_zz.py','runner');setup=load(root/'test/rrtmgp/test_udm_startup_snow_scm.py','setup')
 env={**os.environ,'OMP_NUM_THREADS':'1','LC_ALL':'C'}
 for key in tuple(env):
  if key.startswith(('WRF_RRTMGP_','WRF_UDM_')):env.pop(key)
 env['LD_LIBRARY_PATH']='/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/lib:'+env.get('LD_LIBRARY_PATH','')
 runner=helper.Runner(work,180,env,12)
 report={'schema':'DRY_NUMBER_GRID_V1_SCM_TEST','status':'PREPARED','production_accepted':False,'seed_input':helper.pin(seed/'wrfinput_d01'),'executable':helper.pin(exe),'processes':[]}
 def save():report['processes']=runner.commands;helper.write_json(work/'receipt.json',report)
 def make(name,seconds=120,restart=False,policy=1,migrate=True):
  d=work/name;d.mkdir()
  for p in seed.iterdir():
   if not p.is_file() or p.name.startswith(('wrfout','wrfrst','rsl.','udm_')) or p.name in ('namelist.output','stdout.log','namelist.input'):continue
   shutil.copy2(p,d/p.name)
  text=(seed/'namelist.input').read_text()
  settings=[('run_minutes',str(1 if restart else seconds//60),'time_control'),('run_seconds',str(seconds%60),'time_control'),
            ('end_minute',str(2 if seconds==120 else 1),'time_control'),('end_second','0','time_control'),
            ('history_interval_s','10','time_control'),('restart_interval','1','time_control'),
            ('restart','.true.' if restart else '.false.','time_control'),('udm_number_policy',str(policy),'physics')]
  if restart:settings += [('start_minute','1','time_control')]
  for key,value,group in settings:text=setup.set_assignment(text,key,value,group=group)
  (d/'namelist.input').write_text(text)
  if migrate:convert_input(d/'wrfinput_d01')
  return d
 def run(d,kind,expected_failure=False):
  try:runner.run([exe],d,kind)
  except RuntimeError:
   require(expected_failure and runner.commands[-1]['actual_returncode'] not in (None,0),'unexpected solver failure');save();return
  output=(work/f'command-{len(runner.commands):02d}.stdout').read_text(errors='replace')
  if expected_failure:
   require(('UDM number representation differs' in output or 'Malformed UDM number policy metadata' in output),'failure was not representation check')
  else:
   require('SUCCESS COMPLETE WRF' in output and 'FATAL CALLED' not in output,'solver did not complete successfully')
  save()
 save()
 try:
  control=make('control');run(control,'WRF_policy1_control')
  out=next(control.glob('wrfout_d01*'));checkpoint=control/'wrfrst_d01_1999-10-22_19:01:00'
  require(checkpoint.is_file(),'60s checkpoint absent')
  with netCDF4.Dataset(out) as d:
   require(int(d.UDM_NUMBER_POLICY)==1,'history policy marker absent')
   require(d['Times'].shape[0]==13,'control time roster differs')
   require(all(np.all(np.isfinite(d[n][:])) for n in ('QNCCN','QNCLOUD','QNRAIN','QCLOUD','QICE','T')),'nonfinite control state')
   native_last={n:np.array(d[n][-1]) for n in d.variables if 'Time' in d[n].dimensions}
  with netCDF4.Dataset(checkpoint) as d:
   require(int(d.UDM_NUMBER_POLICY)==1,'checkpoint policy marker absent')
  restart=make('restart',restart=True);shutil.copy2(checkpoint,restart/checkpoint.name);run(restart,'WRF_policy1_restart')
  restartout=next(restart.glob('wrfout_d01*'))
  with netCDF4.Dataset(restartout) as d:
   require(int(d.UDM_NUMBER_POLICY)==1,'restart output policy marker')
   compared=0
   for n,controlvalues in native_last.items():
    require(n in d.variables and np.array_equal(controlvalues,np.array(d[n][-1])), 'restart terminal state differs '+n);compared+=1
  # Old raw files may only run legacy; policy-1 cannot consume them silently.
  missing=make('reject_missing_cold_tag',seconds=60,migrate=False);run(missing,'WRF_reject_missing_cold_tag',True)
  rawrestart=make('reject_raw_restart',restart=True);shutil.copy2(checkpoint,rawrestart/checkpoint.name)
  with netCDF4.Dataset(rawrestart/checkpoint.name,'r+') as d:d.delncattr('UDM_NUMBER_POLICY')
  run(rawrestart,'WRF_reject_raw_restart',True)
  inverse=make('reject_eta_as_legacy',seconds=60,policy=0);run(inverse,'WRF_reject_eta_as_legacy',True)
  malformed=make('reject_malformed_tag',seconds=60,policy=0)
  with netCDF4.Dataset(malformed/'wrfinput_d01','r+') as d:d.setncattr('UDM_NUMBER_POLICY','1')
  run(malformed,'WRF_reject_malformed_tag',True)
  for d in (missing,rawrestart,inverse):
   logs=''.join(p.read_text(errors='replace') for p in d.glob('rsl.*'))
   logs+=''.join(p.read_text(errors='replace') for p in d.glob('*.log'))
   # stdout path lives in root Runner journals rather than the runtime directory.
   require('UDM number representation differs' in logs or 'UDM number representation differs' in (work/f"command-{[missing,rawrestart,inverse].index(d)+3:02d}.stdout").read_text(errors='replace'), 'failure was not representation check')
  report.update(status='PASS_SCOPED_POLICY1_SCM_RESTART',history_variables_compared=compared,control_seconds=120,
                restart_seconds=60,WRF_processes=6,expected_representation_rejections=4,source_files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'phys/module_mp_udm.F',root/'phys/module_microphysics_driver.F',root/'share/input_wrf.F',root/'share/output_wrf.F',root/'Registry/Registry.EM_COMMON',root/'dyn_em/start_em.F']},
                checkpoint=helper.pin(checkpoint),control_history=helper.pin(out),restart_history=helper.pin(restartout),
                limits=['One manufactured periodic 2x2x59 SCM with scalar_adv_opt=0; no general transport/MPI or atmosphere validation.',
                        'Cold input explicitly transformed; no legacy checkpoint migration and no external QNN preservation.',
                        'Restart equality covers saved terminal variables; not physical PSD/occurrence/reference/forecast acceptance.'])
  require(helper.pin(exe)==report['executable'],'executable changed during campaign');save();print(json.dumps({'status':report['status'],'receipt':str(work/'receipt.json')}));return 0
 except BaseException as e:report.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':raise SystemExit(main())
