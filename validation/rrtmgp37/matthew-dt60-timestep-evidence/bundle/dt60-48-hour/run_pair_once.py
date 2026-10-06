#!/usr/bin/env python3
"""Root-authorized one-use paired 48-hour DT60 run; no implicit execution."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, resource, signal, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PLAN=HERE/'plan.json'; MANIFEST=HERE/'manifest.json'; SELF=Path(__file__).resolve()
AUTH=HERE/'root-authorization.json'; RECEIPT=HERE/'execution-receipt.json'; LOCK=HERE/'.one-use.lock'
ARMS=('ra4','ra37'); FATAL=('FATAL CALLED FROM FILE','APPLICATION CALLED MPI_ABORT','ERROR: FATAL','RRtmgp_fatal','DP_HPA_NOT_FINITE')

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(p):
 p=Path(p)
 return {'path':str(p.resolve()),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def atomic(p,obj):
 tmp=p.with_name(p.name+f'.tmp.{os.getpid()}')
 with tmp.open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
 fd=os.open(p.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def static_snapshot(m,plan):
 out={}
 for arm in ARMS:
  case=Path(plan['arms'][arm]['directory']); records={}
  for name,entry in m['cases'][arm].items():
   p=case/name
   if not os.path.lexists(p):raise RuntimeError(f'missing staged entry {arm}/{name}')
   link=os.readlink(p) if p.is_symlink() else None
   if link!=entry['link_text']:raise RuntimeError(f'link text changed: {arm}/{name}')
   actual=pin(p)
   expected=entry['resolved']
   if actual['sha256']!=expected['sha256'] or actual['size_bytes']!=expected['size_bytes']:
    raise RuntimeError(f'staged file hash changed: {arm}/{name}')
   records[name]={'link_text':link,'resolved':actual}
  out[arm]=records
 return out
def check_pin_record(item,label):
 if not all(k in item for k in ('path','sha256')):raise RuntimeError(f'{label}: incomplete path/hash pin record')
 q=Path(item['path'])
 if not q.is_file():raise RuntimeError(f'{label}: pinned file missing: {q}')
 if ('size_bytes' in item and q.stat().st_size!=item['size_bytes']) or sha(q)!=item['sha256']:
  raise RuntimeError(f'{label}: pinned bytes changed: {q}')
def verify_tree_pins(obj,label):
 checked=[]
 if isinstance(obj,dict):
  if {'path','sha256'}<=set(obj):
   check_pin_record(obj,label)
   checked.append({'label':label,'path':str(Path(obj['path']).resolve()),'sha256':obj['sha256'],'size_bytes':Path(obj['path']).stat().st_size})
  else:
   for k,v in obj.items():checked.extend(verify_tree_pins(v,f'{label}.{k}'))
 elif isinstance(obj,list):
  for i,v in enumerate(obj):checked.extend(verify_tree_pins(v,f'{label}[{i}]'))
 return checked
def verify_frozen_inputs(plan,manifest):
 if manifest.get('plan_sha256')!=sha(PLAN):raise RuntimeError('manifest no longer binds current plan')
 checked=verify_tree_pins(plan,'plan')+verify_tree_pins(manifest,'manifest')
 mpi_path=str(Path(plan['mpi']['path']).resolve())
 shared_path=str(Path(plan['provenance']['shared_dependency_inventory']['path']).resolve())
 checked_paths={item['path'] for item in checked}
 if mpi_path not in checked_paths:raise RuntimeError('MPI launcher path/hash pin was not checked')
 if shared_path not in checked_paths:raise RuntimeError('shared dependency inventory path/hash pin was not checked')
 readback=json.loads((HERE/'stage-readback.json').read_text())
 if readback.get('status')!='STAGED_NOT_AUTHORIZED_NOT_RUN' or readback.get('plan_sha256')!=sha(PLAN) or readback.get('manifest_sha256')!=sha(MANIFEST):
  raise RuntimeError('stage readback status or plan/manifest pins mismatch')
 for k,path in (('runner',SELF),('all_numeric_scanner',HERE/'validate_all_numeric.py')):
  expected=readback.get(k)
  if not expected or expected.get('sha256')!=sha(path):raise RuntimeError(f'stage readback does not pin {k}')
 checked.extend(verify_tree_pins(readback,'stage_readback'))
 return {'stage_readback_sha256':sha(HERE/'stage-readback.json'),'plan_sha256':sha(PLAN),'manifest_sha256':sha(MANIFEST),
         'checked_mpi_launcher':next(item for item in checked if item['path']==mpi_path),
         'checked_shared_dependency_inventory':next(item for item in checked if item['path']==shared_path),
         'checked_path_sha_records':len(checked)}
def set_master_stack():
 wanted=512*1024*1024
 before=resource.getrlimit(resource.RLIMIT_STACK)
 hard=before[1]
 if hard!=resource.RLIM_INFINITY and hard<wanted:raise RuntimeError(f'RLIMIT_STACK hard limit {hard} below required {wanted}')
 resource.setrlimit(resource.RLIMIT_STACK,(wanted,hard))
 after=resource.getrlimit(resource.RLIMIT_STACK)
 if after[0]!=wanted:raise RuntimeError(f'could not set master RLIMIT_STACK to {wanted}: {after}')
 return {'before_bytes':list(before),'after_bytes':list(after),'requested_soft_bytes':wanted}
def inspect_logs(case):
 rank_success=set(); fatal=[]; scans=[]
 for stream in ('rsl.out','rsl.error'):
  for rank in range(4):
   p=case/f'{stream}.{rank:04d}'
   if not p.is_file():continue
   text=p.read_text(errors='replace'); low=text.lower()
   if 'wrf: success complete wrf' in low:rank_success.add(rank)
   for n,line in enumerate(text.splitlines(),1):
    ll=line.lower()
    if any(x.lower() in ll for x in FATAL):fatal.append({'file':p.name,'line':n,'text':line[:1000]})
   scans.append(pin(p))
 p=case/'wrf.stdout.log'
 if p.exists():
  text=p.read_text(errors='replace')
  for n,line in enumerate(text.splitlines(),1):
   if any(x.lower() in line.lower() for x in FATAL):fatal.append({'file':p.name,'line':n,'text':line[:1000]})
  scans.append(pin(p))
 return {'unique_success_ranks':sorted(rank_success),'success_rank_count':len(rank_success),'fatal':fatal,'logs':scans}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--authorization',type=Path,default=AUTH);a=ap.parse_args()
 if not a.execute:
  print(json.dumps({'status':'PREPARED_NOT_RUN','plan_sha256':sha(PLAN),'manifest_sha256':sha(MANIFEST),'runner_sha256':sha(SELF),'model_invocations':0}))
  return 0
 if RECEIPT.exists() or LOCK.exists():raise SystemExit('one-use receipt/lock exists; refusing run')
 pb=PLAN.read_bytes();mb=MANIFEST.read_bytes();p=json.loads(pb);m=json.loads(mb)
 if p.get('status')!='STAGED_NOT_AUTHORIZED_NOT_RUN' or m.get('status')!='STAGED_NOT_AUTHORIZED_NOT_RUN':raise SystemExit('stage status is not executable')
 if not a.authorization.is_file():raise SystemExit('root authorization file missing')
 auth=json.loads(a.authorization.read_text())
 expected={'status':'AUTHORIZED_TO_RUN','plan_sha256':hashlib.sha256(pb).hexdigest(),'manifest_sha256':hashlib.sha256(mb).hexdigest(),'runner_sha256':sha(SELF),'stage_readback_sha256':sha(HERE/'stage-readback.json')}
 if any(auth.get(k)!=v for k,v in expected.items()):raise SystemExit('authorization does not bind exact staged plan, manifest and runner')
 for arm in ARMS:
  c=Path(p['arms'][arm]['directory'])
  if any(c.glob('rsl.*')) or any(c.glob('wrfout_d01_*')) or any(c.glob('wrfrst_d01_*')):raise SystemExit(f'pre-existing model outputs in {arm}')
 pins_before=verify_frozen_inputs(p,m)
 stack_limits=set_master_stack()
 before=static_snapshot(m,p)
 fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,json.dumps({'created_utc':utc(),'pid':os.getpid(),'plan_sha256':expected['plan_sha256']}).encode());os.fsync(fd);os.close(fd)
 receipt={'schema':'matthew-dt60-paired-48h-execution-v1','status':'RUNNING','created_utc':utc(),'plan_sha256':expected['plan_sha256'],'manifest_sha256':expected['manifest_sha256'],'runner_sha256':expected['runner_sha256'],'authorization_sha256':sha(a.authorization),'stage_readback_sha256':pins_before['stage_readback_sha256'],'pins_before':pins_before,'master_RLIMIT_STACK':stack_limits,'arm_order':list(ARMS),'model_invocations':0,'forecast_invocations':0,'max_invocations':2,'assets_before':before,'arm_results':{},'assets_after':None}
 atomic(RECEIPT,receipt); env=os.environ.copy()
 for k in list(env):
  if k.startswith(('WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE','OMP_','GOMP_','KMP_')) or k in ('LD_PRELOAD','LD_AUDIT'):env.pop(k,None)
 env.update({'LD_LIBRARY_PATH':':'.join(p['environment']['LD_LIBRARY_PATH']),'MPICH_INTERFACE_HOSTNAME':'127.0.0.1','OMP_NUM_THREADS':'2','OMP_STACKSIZE':'512M','OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1','OPENBLAS_NUM_THREADS':'1'})
 status='PASS_BOTH_VALIDATED'
 for arm in ARMS:
  c=Path(p['arms'][arm]['directory']);env['WRF_RRTMGP_BATCH_SIZE']='32' if arm=='ra37' else None
  if env.get('WRF_RRTMGP_BATCH_SIZE') is None:env.pop('WRF_RRTMGP_BATCH_SIZE',None)
  cmd=[p['mpi']['path'],'-launcher','fork','-iface','lo','-n','4',str(c/'wrf.exe')]
  rec={'status':'STARTING','command':cmd,'cwd':str(c),'started_utc':utc(),'returncode':None,'timed_out':False,'launcher_pid':None,'model_invocations':0,'forecast_invocations':0}
  receipt['arm_results'][arm]=rec;atomic(RECEIPT,receipt)
  proc=None; rc=None; timed=False
  try:
   with (c/'wrf.stdout.log').open('xb') as log:
    proc=subprocess.Popen(cmd,cwd=c,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    rec['launcher_pid']=proc.pid;rec['model_invocations']=1;rec['forecast_invocations']=1
    receipt['model_invocations']+=1;receipt['forecast_invocations']+=1;rec['status']='RUNNING';atomic(RECEIPT,receipt)
    try:rc=proc.wait(timeout=p['future_runner_contract']['max_seconds_per_arm'])
    except subprocess.TimeoutExpired:
     timed=True
     try:os.killpg(proc.pid,signal.SIGTERM)
     except ProcessLookupError:pass
     try:rc=proc.wait(timeout=15)
     except subprocess.TimeoutExpired:
      try:os.killpg(proc.pid,signal.SIGKILL)
      except ProcessLookupError:pass
      rc=proc.wait()
  except BaseException as e:
   rec['launcher_error']=repr(e)
   if proc is not None and proc.poll() is None:
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:rc=proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
     try:os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     rc=proc.wait()
  # Persist observed process status before any output parsing or validators.
  rec['returncode']=rc;rec['timed_out']=timed;rec['ended_utc']=utc();rec['status']='PROCESS_COMPLETE';atomic(RECEIPT,receipt)
  scan=inspect_logs(c);rec['log_scan']=scan
  if rc!=0 or timed or scan['unique_success_ranks']!=[0,1,2,3] or scan['fatal']:
   rec['status']='FAIL_PRESERVED';rec['failure_reason']='nonzero/timeout/incomplete unique-rank SUCCESS/fatal output'
   receipt['status']='FAIL_PRESERVED';status='FAIL_PRESERVED';atomic(RECEIPT,receipt);break
  vout=c/'forecast-postflight.json'
  if vout.exists():
   rec['status']='FAIL_PRESERVED';rec['failure_reason']='validator receipt collision';receipt['status']='FAIL_PRESERVED';status='FAIL_PRESERVED';atomic(RECEIPT,receipt);break
  try:
   vp=subprocess.run([sys.executable,'-B',str(HERE/'validate_forecast_outputs_v2.py'),'--case-dir',str(c),'--arm',arm,'--receipt',str(vout)],cwd=c,env=env,capture_output=True,text=True,timeout=1800)
   vr=json.loads(vout.read_text()) if vout.is_file() else {}
   rec['validator']={'returncode':vp.returncode,'status':vr.get('status'),'receipt':pin(vout),'stdout':vp.stdout[-2000:],'stderr':vp.stderr[-2000:]}
   if vp.returncode or vr.get('status')!='PASS':raise RuntimeError('strict V2 output validator failed')
   quality_receipt=c/'all-numeric-quality.json'
   qp=subprocess.run([sys.executable,'-B',str(HERE/'validate_all_numeric.py'),'--case-dir',str(c),'--output',str(quality_receipt)],cwd=c,env=env,capture_output=True,text=True,timeout=1800)
   qr=json.loads(quality_receipt.read_text()) if quality_receipt.is_file() else {}
   rec['all_numeric_quality']={'returncode':qp.returncode,'status':qr.get('status'),'receipt':pin(quality_receipt),'stdout':qp.stdout[-2000:],'stderr':qp.stderr[-2000:]}
   if qp.returncode or qr.get('status')!='PASS':raise RuntimeError('all-variable raw/decoded quality scan failed')
   rec['status']='PASS_VALIDATED';atomic(RECEIPT,receipt)
  except BaseException as e:
   rec['status']='FAIL_PRESERVED';rec['failure_reason']=repr(e);receipt['status']='FAIL_PRESERVED';status='FAIL_PRESERVED';atomic(RECEIPT,receipt);break
 try:
  receipt['assets_after']=static_snapshot(m,p)
  receipt['pins_after']=verify_frozen_inputs(p,m)
  if receipt['pins_after']!=pins_before:raise RuntimeError('plan/manifest/stage-readback/tool or dependency pins changed during run')
  receipt['static_assets_unchanged']=receipt['assets_after']==before
  if not receipt['static_assets_unchanged']:raise RuntimeError('staged inputs/runtime assets changed during execution')
 except Exception as e:
  receipt['status']='FAIL_PRESERVED';receipt['asset_integrity_error']=repr(e);status='FAIL_PRESERVED'
 if status=='PASS_BOTH_VALIDATED':
  try:
   for arm in ARMS:
    c=Path(p['arms'][arm]['directory']);hist=c/'wrfout_d01_2016-10-06_00:00:00'
    out=HERE/f'{arm}-native-ww.json'
    aa=subprocess.run([sys.executable,'-B',str(HERE/'analyze_native_ww.py'),str(hist),'--output',str(out)],cwd=HERE,env=env,capture_output=True,text=True,timeout=1800)
    ar=json.loads(out.read_text())
    if aa.returncode or ar.get('status')!='ANALYZED_NO_ACCEPTANCE_THRESHOLD' or ar.get('dt_seconds')!=60.0 or len(ar.get('records',[]))!=49:raise RuntimeError(f'{arm} endpoint WW audit invalid')
    receipt.setdefault('native_ww_analysis',{})[arm]={'receipt':pin(out),'returncode':aa.returncode,'status':ar['status'],'times':len(ar['records']),'invalid_endpoint_count':ar.get('aggregate_nonfinite_courant_count')}
   cmp=HERE/'paired-descriptive-differences.json'
   cp=subprocess.run([sys.executable,'-B',str(HERE/'compare_pair.py'),'--ra4',str(Path(p['arms']['ra4']['directory'])/'wrfout_d01_2016-10-06_00:00:00'),'--ra37',str(Path(p['arms']['ra37']['directory'])/'wrfout_d01_2016-10-06_00:00:00'),'--output',str(cmp)],cwd=HERE,env=env,capture_output=True,text=True,timeout=1800)
   if cp.returncode:raise RuntimeError(f'descriptive pair comparison failed: {cp.stderr[-1200:]}')
   receipt['paired_comparison']={'receipt':pin(cmp),'thresholds_applied':False,'interpretation':'coupled trajectory difference only'}
   receipt['status']='PASS_BOTH_VALIDATED_DESCRIPTIVE'
  except BaseException as e:
   receipt['status']='POSTPROCESS_FAIL_PRESERVED';receipt['postprocess_error']=repr(e)
 receipt['finished_utc']=utc();atomic(RECEIPT,receipt)
 print(json.dumps({'status':receipt['status'],'receipt':str(RECEIPT),'forecast_invocations':receipt['forecast_invocations']}))
 return 0 if receipt['status']=='PASS_BOTH_VALIDATED_DESCRIPTIVE' else 2
if __name__=='__main__':main()
