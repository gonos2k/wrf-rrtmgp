#!/usr/bin/env python3
"""One-use bounded RA37 fatal-message diagnostic. Does not retry or score a forecast."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,signal,subprocess,sys
from pathlib import Path
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=ROOT/'build/udm37-matthew-fatal-diagnostic-v1';PLAN=HERE/'diagnostic-plan.json';MANIFEST=HERE/'diagnostic-manifest.json';SELF=HERE/'run_once.py';RECEIPT=HERE/'execution-receipt.json';LOCK=HERE/'.one-run.lock';BASE=ROOT/'build/udm37-matthew-paired-48h-v1';TIMEOUT=3600

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def pin(p):
 p=Path(p).resolve(strict=True);return {'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def atomic(p,obj):
 tmp=p.with_name(p.name+f'.tmp.{os.getpid()}')
 with tmp.open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p);fd=os.open(p.parent,os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def check(p,e,label):
 got=pin(p)
 if got['sha256']!=e['sha256'] or got['size_bytes']!=e['size_bytes']:raise RuntimeError(label+' mismatch')
 return got
def snapshot(plan,manifest):
 case=Path(plan['case_dir']);out={'plan':pin(PLAN),'manifest':pin(MANIFEST),'runner':pin(SELF)}
 if out['runner']['sha256']!=plan['runner_sha256']:raise RuntimeError('diagnostic runner drift')
 pairpin=pin(BASE/'execution-receipt.json')
 if pairpin['sha256']!=plan['source_pair_receipt_sha256']:raise RuntimeError('original pair receipt drift')
 out['original_pair_receipt']=pairpin
 for n,expected in [('ra4-postflight-v2-final.json',plan['source_ra4_v2_sha256']),('ra4-expanded-log-review-v1.json',plan['source_ra4_log_review_sha256'])]:
  q=pin(BASE/n)
  if q['sha256']!=expected:raise RuntimeError(n+' drift')
  out[n]=q
 for key in ('executable','mpiexec','frozen_table'):
  out[key]=check(Path(plan[key]['path']),plan[key],key)
 out['runtime_libraries']={x['soname']:check(Path(x['path']),x,x['soname']) for x in plan['runtime_libraries']}
 out['coefficient_files']={x['name']:check(Path(x['path']),x,x['name']) for x in plan['coefficient_files']}
 out['common_inputs']={n:check(case/n,e,n) for n,e in plan['common_inputs'].items()}
 out['radiation_iofields']=check(case/'radiation_iofields.txt',plan['radiation_iofields'],'iofields')
 out['namelist']=check(case/'namelist.input',plan['namelist'],'namelist')
 assets={}
 for name,e in plan['assets'].items():
  p=case/name
  if not p.is_symlink() or os.readlink(p)!=e['link_text']:raise RuntimeError('link mismatch '+name)
  assets[name]=check(p,e,name)
 out['assets']=assets
 return out
def logs(case):
 expected=[case/f'rsl.{kind}.{r:04d}' for kind in ('error','out') for r in range(4)]+[case/'wrf.stdout.log']
 patterns=('fatal','mpi_abort','error: fatal','application called mpi_abort')
 rows=[]
 for p in expected:
  if not p.is_file():rows.append({'name':p.name,'missing':True});continue
  lines=p.read_text(errors='replace').splitlines(); found=[]
  for i,line in enumerate(lines,1):
   low=line.lower()
   if any(marker in low for marker in patterns):found.append({'line':i,'text':line[:1000]})
  success=[i for i,line in enumerate(lines,1) if 'wrf: success complete wrf' in line.lower()]
  timing=[line for line in lines if 'timing for main: time' in line.lower()]
  rows.append({'name':p.name,'sha256':sha(p),'size_bytes':p.stat().st_size,'fatal_or_abort_matches':found,'success_marker_lines':success,'last_timing_line':timing[-1] if timing else None,'last_lines':lines[-5:]})
 return {'expected_log_count':9,'present_log_count':sum(not r.get('missing',False) for r in rows),'fatal_or_abort_match_count':sum(len(r.get('fatal_or_abort_matches',[])) for r in rows),'logs':rows}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');ap.add_argument('--approval',type=Path);a=ap.parse_args()
 if not a.execute or not a.approval:ap.error('requires explicit --execute --approval')
 p=json.loads(PLAN.read_text());m=json.loads(MANIFEST.read_text());ph=sha(PLAN);mh=sha(MANIFEST);rh=sha(SELF)
 if p.get('status')!='STAGED_NOT_RUN_REQUIRES_ROOT_AUTHORIZATION' or m.get('status')!='STAGED_NOT_RUN':raise SystemExit('stage is not in launchable state')
 if m.get('plan_sha256')!=ph:raise SystemExit('manifest does not bind plan')
 old=json.loads((BASE/'execution-receipt.json').read_text())
 if old.get('status')!='FAIL_PRESERVED' or old.get('forecast_invocations')!=1 or old.get('arm_results',{}).get('ra37',{}).get('forecast_invocations',0)!=0:raise SystemExit('original pair receipt is not the expected one-arm preserved failure')
 ra4=json.loads((BASE/'ra4-postflight-v2-final.json').read_text());review=json.loads((BASE/'ra4-expanded-log-review-v1.json').read_text())
 if ra4.get('status')!='PASS' or ra4.get('arm')!='ra4':raise SystemExit('corrected RA4 v2 postflight is not PASS')
 if review.get('conclusion')!='SCOPED_RA4_PROCESS_SUCCESS_AND_EXPANDED_LOG_SCAN_PASS' or not review.get('no_expanded_fatal_marker_in_any_scanned_log'):raise SystemExit('expanded RA4 log review not PASS')
 expected={'status':'AUTHORIZED_ONE_HOUR_RA37_DIAGNOSTIC','plan_sha256':ph,'manifest_sha256':mh,'runner_sha256':rh,'corrected_ra4_postflight_sha256':p['source_ra4_v2_sha256']}
 approval=json.loads(a.approval.read_text())
 for k,v in expected.items():
  if approval.get(k)!=v:raise SystemExit('approval mismatch: '+k)
 if sha(BASE/'execution-receipt.json')!=p['source_pair_receipt_sha256'] or sha(BASE/'ra4-postflight-v2-final.json')!=p['source_ra4_v2_sha256']:raise SystemExit('source evidence changed')
 for pat in ('rsl.out.*','wrfout_d01_*','wrfrst_d01_*'):
  if list(Path(p['case_dir']).glob(pat)):raise SystemExit('pre-existing output: '+pat)
 fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,json.dumps({'pid':os.getpid(),'utc':utc(),'plan_sha256':ph}).encode());os.fsync(fd);os.close(fd)
 if RECEIPT.exists():raise SystemExit('receipt collision')
 before=snapshot(p,m)
 receipt={'schema':'matthew-ra37-fatal-diagnostic-execution-v1','status':'PREPARED_TO_LAUNCH','created_utc':utc(),'model_invocations':0,'forecast_invocations':0,'plan_sha256':ph,'manifest_sha256':mh,'runner_sha256':rh,'approval_sha256':sha(a.approval),'corrected_ra4_postflight_sha256':p['source_ra4_v2_sha256'],'assets_before':before,'assets_after':None}
 atomic(RECEIPT,receipt)
 env=os.environ.copy()
 for k in list(env):
  if k.startswith(('WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE','OMP_','GOMP_','KMP_')) or k in ('LD_PRELOAD','LD_AUDIT'):env.pop(k,None)
 env.update({'LD_LIBRARY_PATH':':'.join(p['launch']['ld_library_path']),'MPICH_INTERFACE_HOSTNAME':'127.0.0.1','OMP_NUM_THREADS':'1','OMP_STACKSIZE':'512M','WRF_RRTMGP_BATCH_SIZE':'32'})
 cmd=p['launch']['command'];case=Path(p['case_dir']);rec={'status':'RUNNING','started_utc':utc(),'command':cmd,'cwd':str(case),'launcher_pid':None,'returncode':None,'timed_out':False,'rank_success':{}}
 receipt['run']=rec;atomic(RECEIPT,receipt);proc=None;rc=None;timeout=False
 try:
  with (case/'wrf.stdout.log').open('xb') as log:
   proc=subprocess.Popen(cmd,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   rec['launcher_pid']=proc.pid;receipt['model_invocations']=1;receipt['forecast_invocations']=1;atomic(RECEIPT,receipt)
   try:rc=proc.wait(timeout=TIMEOUT)
   except subprocess.TimeoutExpired:
    timeout=True
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:rc=proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
     try:os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     rc=proc.wait()
 except BaseException as e:
  rec['launcher_error']=repr(e)
  if proc is not None and proc.poll() is None:
   try:os.killpg(proc.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:rc=proc.wait(timeout=10)
   except subprocess.TimeoutExpired:
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    rc=proc.wait()
 rec['returncode']=rc;rec['timed_out']=timeout;rec['ended_utc']=utc();rec['status']='PROCESS_COMPLETE_PENDING_LOG_SCAN';atomic(RECEIPT,receipt)
 try:
  for rank in range(4):
   f=case/f'rsl.out.{rank:04d}';text=f.read_text(errors='replace') if f.exists() else '';rec['rank_success'][str(rank)]='wrf: SUCCESS COMPLETE WRF' in text
  rec['log_diagnostics']=logs(case)
  rec['partial_outputs']=[pin(f) for f in sorted(list(case.glob('wrfout_d01_*'))+list(case.glob('wrfrst_d01_*'))) if f.is_file()]
  after=snapshot(p,m);receipt['assets_after']=after;rec['assets_stable']=before==after
 except BaseException as e:
  rec['diagnostic_error']=repr(e);rec['assets_stable']=False
 rec['status']='PASS_DIAGNOSTIC_RUN' if rc==0 and not timeout and all(rec.get('rank_success',{}).values()) and rec.get('assets_stable') is True and 'diagnostic_error' not in rec and rec.get('log_diagnostics',{}).get('present_log_count')==9 and rec.get('log_diagnostics',{}).get('fatal_or_abort_match_count')==0 else 'FAIL_PRESERVED'
 rec['interpretation']='one-hour diagnostic only; no full 48-hour validation or pair claim'
 receipt['status']=rec['status'];receipt['finished_utc']=utc();atomic(RECEIPT,receipt)
 print(json.dumps({'status':receipt['status'],'receipt':str(RECEIPT),'model_invocations':receipt['model_invocations'],'returncode':rc}))
 return 0 if receipt['status']=='PASS_DIAGNOSTIC_RUN' else 2
if __name__=='__main__':raise SystemExit(main())
