#!/usr/bin/env python3
"""One-use 13-hour NetCDF ZZ persistence control; no physical approval."""
import argparse, datetime as dt, hashlib, json, os, pathlib, resource, re, signal, subprocess, sys, time
import importlib.util
import numpy as np
from netCDF4 import Dataset
BASE=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
SOURCE=BASE/'build/udm37-main-runtime-io-mpi-source-v1'
BUILD=BASE/'build/udm37-main-runtime-io-mpi-build-v1'
MPI=BASE/'build/deps/mpich-sock/bin/mpiexec.hydra'

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(p):return {'path':str(p.resolve()),'sha256':sha(p),'size':p.stat().st_size,'link':os.readlink(p) if p.is_symlink() else None}
def atomic(p,v):
 t=p.with_name(p.name+'.tmp')
 with t.open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p)
 fd=os.open(p.parent,os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def snapshot(root,cases):
 # Only the explicit staged static roster is an input; namelist.output is generated.
 return {arm:{n:pin(root/arm/n) for n in cases[arm]['files']} for arm in ('ra4','ra37')}
def stop(proc):
 try:os.killpg(proc.pid,signal.SIGTERM)
 except ProcessLookupError:pass
 try:rc=proc.wait(timeout=15)
 except subprocess.TimeoutExpired:
  try:os.killpg(proc.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  try:rc=proc.wait(timeout=15)
  except subprocess.TimeoutExpired:rc=None
 try:os.killpg(proc.pid,signal.SIGKILL)
 except ProcessLookupError:pass
 return rc
def validate(case,minutes,interval,arm,expected_restart_files,scanner_path):
 spec=importlib.util.spec_from_file_location('numeric_scan',scanner_path)
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 paths=sorted(case.glob('wrfout_d01_*'))
 assert len(paths)==1,('history roster',paths)
 start=dt.datetime(2016,10,6); expected=[(start+dt.timedelta(minutes=m)).strftime('%Y-%m-%d_%H:%M:%S') for m in range(0,minutes+1,interval)]
 assert minutes%interval==0
 restarts=sorted(case.glob('wrfrst_d01_*'))
 assert len(restarts)==expected_restart_files,('restart roster',restarts,expected_restart_files)
 if expected_restart_files:
  restart_times=[(start+dt.timedelta(minutes=m)).strftime('%Y-%m-%d_%H:%M:%S') for m in range(720,minutes+1,720)]
  assert len(restart_times)==expected_restart_files
  assert [p.name for p in restarts]==['wrfrst_d01_'+t for t in restart_times]
  for path,expected_time in zip(restarts,restart_times):
   with Dataset(path) as d:
    assert [b''.join(r).decode() for r in d['Times'][:]]==[expected_time]
    assert int(d.MP_PHYSICS)==27 and int(d.RA_LW_PHYSICS)==int(d.RA_SW_PHYSICS)==(37 if arm=='ra37' else 4)
    for n in ('P','PB','T','QVAPOR','MUB','TSK',*(f'{v}_{t}' for v in ('U','V','W','PH','MU') for t in (1,2))):assert n in d.variables,(path.name,n)
    assert np.all(d['P'][:]+d['PB'][:]>0),(path.name,'pressure')
    assert 'ISEEDARR_MULT3D' in d.variables, (path.name,'missing seed')
    seed=d['ISEEDARR_MULT3D']; assert seed.dimensions==('Time','num_pert_3d','bottom_top')
    assert seed.dtype.kind=='i' and seed.dtype.itemsize==4
    assert seed.shape==(1,len(d.dimensions['num_pert_3d']),len(d.dimensions['bottom_top']))
    assert getattr(seed,'MemoryOrder','').strip()=='ZZ'
    assert all(not re.search(r'BAD MEMORY ORDER\s*\|\s*ZZ\s*\|',t,re.I) and 'VARIABLE NOT FOUND' not in t for t in ((case/f'rsl.error.{rank:04d}').read_text(errors='replace') for rank in range(4)))
    for n in ('MU_1','MU_2'):assert np.all(d[n][:]+d['MUB'][:]>0),(path.name,n)

 scans=[mod.scan_file(p) for p in paths+restarts]
 assert all(r['status']=='PASS' for r in scans), 'raw/decoded numeric scan failed'
 with Dataset(paths[0]) as d:
  actual=[b''.join(r).decode() for r in d['Times'][:]]
  assert actual==expected,(actual,expected)
  assert int(d.MP_PHYSICS)==27 and int(d.RA_LW_PHYSICS)==int(d.RA_SW_PHYSICS)==(37 if arm=='ra37' else 4)
  for n in ('QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL','QNCLOUD','QNRAIN','QNCCN','SWDOWN','GLW','RTHRATEN','P','PB','MU','MUB','U','V','W','PH','PHB','T','QVAPOR','TSK'):
   assert n in d.variables,n
  assert np.all(d['P'][:]+d['PB'][:]>0) and np.all(d['MU'][:]+d['MUB'][:]>0)
  identities={}
  if arm=='ra37':
   for key,l,r in [('down_vs_broadband','SWDOWN','SWDNB'),('direct_diffuse','SWDOWN',None),('net_absorbed','GSW',None)]:
    x=np.asarray(d[l][:],dtype='f8')
    y=np.asarray(d[r][:],dtype='f8') if r else (np.asarray(d['SWDDIR'][:],dtype='f8')+np.asarray(d['SWDDIF'][:],dtype='f8') if key=='direct_diffuse' else np.asarray(d['SWDNB'][:],dtype='f8')-np.asarray(d['SWUPB'][:],dtype='f8'))
    diff=np.abs(x-y); tolerance=2e-4+2e-6*np.abs(y)
    assert np.all(diff<=tolerance),(key,float(diff.max()))
    identities[key]={'max_abs':float(diff.max()),'atol':2e-4,'rtol':2e-6}
  omitted={n:{'min':float(np.min(d[n][:])),'max':float(np.max(d[n][:]))} for n in ('QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL','QNCLOUD','QNRAIN','QNCCN')}
 return {'status':'PASS_RUNTIME_SCOPED','times':actual,'numeric_scan':scans,'surface_contracts':identities,'hydrometeor_number_ranges':omitted,'physical_accepted':False}
def main():
 a=argparse.ArgumentParser();a.add_argument('--cases',type=pathlib.Path,required=True);a.add_argument('--minutes',type=int,required=True);a.add_argument('--history-interval',type=int,required=True);a.add_argument('--max-seconds',type=int,required=True);args=a.parse_args();root=args.cases.resolve()
 assert not (root/'execution.json').exists() and not (root/'.one-use.lock').exists()
 br=json.loads((BUILD/'result.json').read_text());assert br['status']=='PASS_BUILD_INSTALL_SCOPED'
 stage=json.loads((root/'stage-plan.json').read_text())
 assert stage['source']['head']==br['source_head']
 def declared_pin(path,expected):
  assert path.resolve()==pathlib.Path(expected['path']).resolve()
  assert sha(path)==expected['sha256'] and path.stat().st_size==expected.get('size_bytes',expected.get('size'))
 declared_pin(BUILD/'result.json',stage['build_result'])
 declared_pin(pathlib.Path(__file__).resolve(),stage['runner'])
 assert 0 < args.max_seconds <= stage['limits']['per_arm_timeout_seconds'],('timeout outside stage bound',args.max_seconds,stage['limits']['per_arm_timeout_seconds'])
 assert stage['case']['duration_seconds']==60*args.minutes and stage['case']['history_interval_minutes']==args.history_interval
 subprocess.run([sys.executable,str(root/'verify_stage.py')],cwd=root,check=True)
 scanner=stage['numeric_scanner'];scanner_path=pathlib.Path(scanner['path']);declared_pin(scanner_path,scanner)
 source_pins={n:pin(SOURCE/n) for n in stage['source']['selected_files']}
 assert all(x['sha256']==stage['source']['selected_files'][n]['sha256'] for n,x in source_pins.items())
 stage_pins={n:pin(root/n) for n in ('stage-plan.json','verify_stage.py')}
 auth=json.loads((root/'root-authorization.json').read_text())
 assert auth['stage_plan_sha256']==sha(root/'stage-plan.json') and auth['runner_sha256']==sha(pathlib.Path(__file__).resolve())
 assert auth['max_models']==2 and auth['minutes']==args.minutes
 assert args.minutes==780 and args.history_interval==60 and args.max_seconds<=300
 assert stage['limits']['max_models']==2
 stage_pins['root-authorization.json']=pin(root/'root-authorization.json')
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==br['source_head']
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip()
 env=os.environ.copy()
 for k in list(env):
  if k.startswith(('OMP_','GOMP_','KMP_','WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE')) or k in ('LD_PRELOAD','LD_AUDIT'):env.pop(k,None)
 env.update(LD_LIBRARY_PATH=':'.join(str(BASE/p) for p in ('build/deps/netcdf/lib','build/deps/root/usr/lib/x86_64-linux-gnu','build/deps/mpich-sock/lib')),MPICH_INTERFACE_HOSTNAME='127.0.0.1',OMP_NUM_THREADS='2',OMP_STACKSIZE='512M',OMP_DYNAMIC='FALSE',OMP_MAX_ACTIVE_LEVELS='1',OPENBLAS_NUM_THREADS='1')
 libraries=subprocess.check_output(['ldd',str(BUILD/'install/bin/wrf')],env=env,text=True);assert 'not found' not in libraries,libraries
 libs=[pathlib.Path(line.split('=>')[1].split()[0]) for line in libraries.splitlines() if '=>' in line and line.split('=>')[1].split()[0].startswith('/')]
 library_pins={str(p):pin(p) for p in libs};before=snapshot(root,stage['cases'])
 for arm in ('ra4','ra37'):
  namelist=(root/arm/'namelist.input').read_text()
  def scalar(name,default=None):
   values=re.findall(r'(?mi)^\s*'+re.escape(name)+r'\s*=\s*([^,\n]+)',namelist)
   assert len(values)<=1,('duplicate time setting',name)
   if not values:
    assert default is not None,('missing time setting',name)
    return default
   return int(values[0])
  run_seconds=sum(scalar('run_'+n)*m for n,m in [('days',86400),('hours',3600),('minutes',60),('seconds',1)])
  assert run_seconds==60*args.minutes,('WRF run_* duration overrides end date',arm,run_seconds,args.minutes)
  dates={}
  for prefix in ('start','end'):
   dates[prefix]=dt.datetime(*(scalar(prefix+'_'+n,0 if n in ('minute','second') else None) for n in ('year','month','day','hour','minute','second')))
  assert (dates['end']-dates['start']).total_seconds()==run_seconds,('run duration/end time disagree',arm,dates)
  assert dates['start'].strftime('%Y-%m-%d_%H:%M:%S')==stage['case']['start'] and dates['end'].strftime('%Y-%m-%d_%H:%M:%S')==stage['case']['end']
  assert scalar('time_step')==60 and scalar('history_interval')==args.history_interval
  assert not any((root/arm).glob('rsl.*')) and not any((root/arm).glob('wrfout*')) and not any((root/arm).glob('wrfrst*'))
  assert before[arm]['wrf.exe']['sha256']==br['executables']['wrf']['sha256']
 hard=resource.getrlimit(resource.RLIMIT_STACK)[1];assert hard==resource.RLIM_INFINITY or hard>=512*1024**2
 resource.setrlimit(resource.RLIMIT_STACK,(512*1024**2,hard))
 with (root/'.one-use.lock').open('x') as f:f.write(str(os.getpid()))
 receipt={'source_head':br['source_head'],'source_tree':br['source_tree'],'build_result':pin(BUILD/'result.json'),'runner':pin(pathlib.Path(__file__).resolve()),'MPI':pin(MPI),'library_pins':library_pins,'stage_pins':stage_pins,'assets_before':before,'runtime':{'MPI':4,'OMP':2,'minutes':args.minutes,'dt_seconds':60,'capture':False,'history_interval_minutes':args.history_interval},'status':'STARTING','model_calls':0,'results':{},'physical_accepted':False,'interpretation':'Coupled production-policy comparison; radiation and UDM policy effects not isolated'}
 atomic(root/'execution.json',receipt)
 for arm in ('ra4','ra37'):
  case=root/arm; arm_env=env.copy()
  if arm=='ra37':arm_env['WRF_RRTMGP_BATCH_SIZE']='32'
  cmd=[str(MPI),'-launcher','fork','-iface','lo','-n','4',str(case/'wrf.exe')]
  r={'argv':cmd,'cwd':str(case),'started_unix':time.time(),'status':'STARTING','actual_rc':None,'models':0};receipt['results'][arm]=r;atomic(root/'execution.json',receipt)
  proc=None
  try:
   with (case/'wrf.stdout.log').open('xb') as log:
    proc=subprocess.Popen(cmd,cwd=case,env=arm_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    r.update(pid=proc.pid,status='RUNNING',models=1);receipt['model_calls']+=1
    atomic(root/'execution.json',receipt)
    try:rc=proc.wait(timeout=args.max_seconds)
    except subprocess.TimeoutExpired:r['timed_out']=True;rc=stop(proc)
    # Preserve observed wait/cleanup RC before log close and numeric inspection.
    r.update(actual_rc=rc,reaped=proc.returncode is not None,status='REAPED' if proc.returncode is not None else 'REAP_PENDING',ended_unix=time.time());atomic(root/'execution.json',receipt)
   r.update(actual_rc=rc,status=('REAPED' if proc.returncode is not None else 'REAP_PENDING'),reaped=proc.returncode is not None,ended_unix=time.time());atomic(root/'execution.json',receipt)
   assert rc==0 and not r.get('timed_out'),(arm,rc)
   texts={rank:'\n'.join((case/f'{prefix}.{rank:04d}').read_text(errors='replace') for prefix in ('rsl.out','rsl.error')) for rank in range(4)}
   assert all('SUCCESS COMPLETE WRF' in s for s in texts.values()),'missing rank success'
   assert all(not any(n in s for n in ('FATAL CALLED','MPI_ABORT','ERROR: FATAL')) for s in texts.values()),'fatal marker'
   assert sha(scanner_path)==scanner['sha256']
   r['validation']=validate(case,args.minutes,args.history_interval,arm,stage['case']['expected_restart_files'],scanner_path);assert sha(scanner_path)==scanner['sha256']
   r['status']='PASS_RUNTIME_SCOPED';atomic(root/'execution.json',receipt)
  except BaseException as exc:
   if proc is not None:
    if 'timed_out' not in r:
     try:stop(proc)
     except Exception as cleanup_exc:r['cleanup_error']=repr(cleanup_exc)
    r['actual_rc']=proc.poll();r['reaped']=proc.returncode is not None
   r.update(status='FAIL_PRESERVED' if proc is None or proc.returncode is not None else 'FAIL_REAP_PENDING',error=repr(exc),ended_unix=time.time());receipt['status']=r['status']
   atomic(root/'execution.json',receipt);raise
 try:
  receipt['assets_after']=snapshot(root,stage['cases']);assert before==receipt['assets_after'],'runtime static input bytes changed'
  assert library_pins=={str(p):pin(p) for p in libs},'shared libraries changed'
  assert stage_pins=={n:pin(root/n) for n in stage_pins},'stage plan/verifier/authorization changed'
  assert not subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip(),'source changed during run'
  assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==br['source_head']
  assert source_pins=={n:pin(SOURCE/n) for n in source_pins},'selected source changed'
  assert sha(scanner_path)==scanner['sha256'],'numeric scanner changed'
  receipt['numeric_scanner']=pin(scanner_path);receipt['selected_source_pins']=source_pins
  receipt.update(status='PASS_PAIRED_RUNTIME_SCOPED',ended_unix=time.time());atomic(root/'execution.json',receipt)
 except BaseException as exc:
  receipt.update(status='POSTFLIGHT_FAIL_PRESERVED',postflight_error=repr(exc),ended_unix=time.time());atomic(root/'execution.json',receipt);raise
 print(json.dumps({'status':receipt['status'],'models':receipt['model_calls'],'receipt':str(root/'execution.json')}))
if __name__=='__main__':main()
