#!/usr/bin/env python3
"""One-use OMP2/MPI4 reporter reproduction; requires an exact root authorization."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, signal, subprocess, sys
from pathlib import Path
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
BASE=ROOT/'build/udm37-matthew-paired-48h-v1'
OLD_DIAG=ROOT/'build/udm37-matthew-fatal-diagnostic-v1'
HERE=ROOT/'build/udm37-pr65-worker-fatal-reproduction-v1'
PLAN=HERE/'plan.json'; MANIFEST=HERE/'manifest.json'; SELF=HERE/'run_once.py'
CASE=HERE/'case'; RECEIPT=HERE/'execution-receipt.json'; LOCK=HERE/'.one-run.lock'; TIMEOUT=3600

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(path):
 p=Path(path).resolve(strict=True);return {'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def atomic(path,obj):
 tmp=path.with_name(path.name+f'.tmp.{os.getpid()}')
 with tmp.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path);fd=os.open(path.parent,os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def check(path,expected,label):
 got=pin(path)
 if got['sha256']!=expected['sha256'] or got['size_bytes']!=expected['size_bytes']:raise RuntimeError(label+' pin mismatch')
 return got
def snapshots(p,m):
 if sha(PLAN)!=m['plan_sha256']:raise RuntimeError('plan/manifest binding mismatch')
 if sha(SELF)!=p['runner_sha256']:raise RuntimeError('runner digest mismatch')
 out={'plan':pin(PLAN),'manifest':pin(MANIFEST),'runner':pin(SELF),'executable':check(p['executable']['path'],p['executable'],'executable')}
 if sha(HERE/'bind_reporter.py') != p.get('executable_binder_sha256'):raise RuntimeError('executable binder digest mismatch')
 for key,path in [('pair_stage_manifest',BASE/'stage-manifest.json'),('pair_execution_plan',BASE/'execution-plan.json'),('pair_execution_receipt',BASE/'execution-receipt.json'),('omp1_diagnostic_execution_receipt',OLD_DIAG/'execution-receipt.json')]:
  out[key]=check(path,p['source_evidence_pins'][key],key)
 out['old_omp1_logs']={name:check(OLD_DIAG/'case'/name,exp,name) for name,exp in p['old_omp1_log_pins'].items()}
 out['mpi_launcher']=check(p['mpi_launcher']['path'],p['mpi_launcher'],'MPI launcher')
 out['table']=check(p['physics_and_inputs']['table_path'],{'sha256':p['physics_and_inputs']['table_sha256'],'size_bytes':Path(p['physics_and_inputs']['table_path']).stat().st_size},'old frozen table')
 out['runtime_libraries']={e['soname']:check(e['path'],e,e['soname']) for e in p['runtime_libraries']}
 out['inputs']={n:check(CASE/n,e,n) for n,e in p['common_inputs'].items()}
 out['namelist']=check(CASE/'namelist.input',p['namelist'],'namelist')
 out['iofields']=check(CASE/'radiation_iofields.txt',p['radiation_iofields'],'radiation_iofields')
 assets={}
 for name,e in p['assets'].items():
  link=CASE/name
  if not link.is_symlink() or os.readlink(link)!=e['link_text']:raise RuntimeError('asset link changed: '+name)
  assets[name]=check(link,e,name)
 out['assets']=assets
 return out
def scan_logs():
 files=[CASE/f'rsl.{kind}.{rank:04d}' for kind in ('error','out') for rank in range(4)]+[CASE/'wrf.stdout.log']
 pattern=re.compile(r'RRTMGP_FATAL\s*\[([^]]+)\]:\s*(.*)',re.I)
 detail=[]; rows=[]
 for path in files:
  if not path.is_file():
   rows.append({'name':path.name,'missing':True});continue
  text=path.read_text(errors='replace'); lines=text.splitlines(); markers=[]
  for ln,line in enumerate(lines,1):
   match=pattern.search(line)
   if match:
    markers.append({'line':ln,'source':match.group(1),'message':match.group(2)[:2000]})
    low=line.lower()
    if ('temperature outside table range' in low and 'extrapolation forbidden' in low and
        'species=graupel' in low and 'lambda_m_inv' in low and 'temperature_k' in low and
        'axis_k' in low and 'path_g_m2' in low):
     # Capture the exact direct reporter line; later verify its parsed physical bound.
     detail.append({'log':path.name,'line':ln,'text':line})
  success=[ln for ln,line in enumerate(lines,1) if 'wrf: success complete wrf' in line.lower()]
  abort=[{'line':ln,'text':line} for ln,line in enumerate(lines,1) if 'mpi_abort' in line.lower() or 'application called mpi_abort' in line.lower()]
  rows.append({'name':path.name,'sha256':sha(path),'size_bytes':path.stat().st_size,'fatal_markers':markers,'abort_markers':abort,'success_marker_lines':success,'last_lines':lines[-6:]})
 return {'expected_logs':9,'present_logs':sum(not x.get('missing') for x in rows),'direct_marker_count':sum(len(x['fatal_markers']) for x in rows),'table_bound_detail_lines':detail,'logs':rows}
def parse_bound(detail):
 if not detail:return False,[]
 checked=[]
 for d in detail:
  s=d['text']
  def val(name):
   m=re.search(rf'\b{name}\s*=\s*([-+0-9.Ee]+)',s,re.I)
   return float(m.group(1)) if m else None
  temp=val('temperature_k'); wave=val('lambda_m_inv'); path=val('path_g_m2')
  axis=re.search(r'axis_K\s*=\s*\[\s*([-+0-9.Ee]+)\s*,\s*([-+0-9.Ee]+)\s*\]',s,re.I)
  ok=(re.search(r'RRTMGP_FATAL\s*\[',s,re.I) is not None and temp is not None and temp<180.0 and wave is not None and abs(wave-20000.0)<1e-6 and
      path is not None and path>0.0 and axis is not None and
      abs(float(axis.group(1))-180.0)<1e-5 and abs(float(axis.group(2))-300.0)<1e-5 and
      re.search(r'\bspecies\s*=\s*graupel\b',s,re.I) is not None)
  checked.append({'log':d['log'],'line':d['line'],'temperature_k':temp,'lambda_m_inv':wave,'path_g_m2':path,
                  'axis_K':[float(axis.group(1)),float(axis.group(2))] if axis else None,'all_expected_bound_fields_match':bool(ok)})
 return any(x['all_expected_bound_fields_match'] for x in checked),checked
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');ap.add_argument('--authorization',type=Path);a=ap.parse_args()
 if not a.execute or a.authorization is None:ap.error('requires --execute and --authorization')
 if RECEIPT.exists() or LOCK.exists():raise SystemExit('one-use run already attempted; preserving existing evidence')
 for pattern in ('rsl.*','wrfout_d01_*','wrfrst_d01_*','wrf.stdout.log'):
  if any(CASE.glob(pattern)):raise SystemExit('preexisting output prevents launch: '+pattern)
 p=json.loads(PLAN.read_text());m=json.loads(MANIFEST.read_text())
 if p.get('status')!='STAGED_WAITING_FOR_ROOT_AUTHORIZATION' or m.get('status')!=p.get('status'):raise SystemExit('stage is not root-authorized-ready')
 if p.get('executable') is None or not p.get('runtime_libraries'):raise SystemExit('reporter executable/runtime pins are unset')
 if m.get('plan_sha256')!=sha(PLAN):raise SystemExit('manifest does not bind plan bytes')
 rh=sha(SELF);ph=sha(PLAN);mh=sha(MANIFEST)
 auth=json.loads(a.authorization.read_text())
 expected={'status':'AUTHORIZED_ONE_HOUR_OMP2_FATAL_REPRODUCTION','plan_sha256':ph,'manifest_sha256':mh,'runner_sha256':rh,
           'executable_sha256':p['executable']['sha256'],'frozen_table_sha256':p['physics_and_inputs']['table_sha256'],
           'mpi_ranks':4,'omp_threads':2,'batch_size':32,'forecast_invocations_max':1}
 for key,value in expected.items():
  if auth.get(key)!=value:raise SystemExit('authorization mismatch: '+key)
 fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,json.dumps({'pid':os.getpid(),'utc':utc(),'plan_sha256':ph}).encode());os.fsync(fd);os.close(fd)
 rec={'schema':'pr65-omp2-fatal-reproduction-execution-v1','status':'PREFLIGHT','created_utc':utc(),
      'model_invocations':0,'forecast_invocations':0,'plan_sha256':ph,'manifest_sha256':mh,'runner_sha256':rh,
      'authorization_sha256':sha(a.authorization),'pins_before':None,'pins_after':None,
      'experiment_scope':'one 1-hour OMP2/MPI4/B32 reporter validation only; old frozen table; no completion claim'}
 atomic(RECEIPT,rec)
 try:
  before=snapshots(p,m);rec['pins_before']=before;atomic(RECEIPT,rec)
  exe_source=Path(p['executable']['path'])
  if (CASE/'wrf.exe').exists() or (CASE/'wrf.exe').is_symlink():raise RuntimeError('unexpected preexisting case executable')
  import shutil
  shutil.copy2(exe_source,CASE/'wrf.exe')
  staged_exe=pin(CASE/'wrf.exe')
  if staged_exe['sha256']!=p['executable']['sha256'] or staged_exe['size_bytes']!=p['executable']['size_bytes']:raise RuntimeError('staged executable copy differs')
  if snapshots(p,m)!=before:raise RuntimeError('immutable inputs/assets changed during executable staging')
 except BaseException as exc:
  rec.update({'status':'FAIL_PRESERVED','preflight_error':repr(exc),'finished_utc':utc()});atomic(RECEIPT,rec)
  print(json.dumps({'status':rec['status'],'phase':'preflight','error':repr(exc),'receipt':str(RECEIPT)}));return 2
 rec.update({'status':'PREPARED_TO_LAUNCH','staged_executable':staged_exe});atomic(RECEIPT,rec)
 env=os.environ.copy()
 for k in list(env):
  if k.startswith(('WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE','OMP_','GOMP_','KMP_')) or k in ('LD_PRELOAD','LD_AUDIT'):env.pop(k,None)
 env.update({'LD_LIBRARY_PATH':':'.join(p['execution_ld_library_path']),'MPICH_INTERFACE_HOSTNAME':'127.0.0.1',
             'OMP_NUM_THREADS':'2','OMP_STACKSIZE':'512M','WRF_RRTMGP_BATCH_SIZE':'32'})
 cmd=[p['mpi_launcher']['path'],'-launcher','fork','-iface','lo','-n','4',str(CASE/'wrf.exe')]
 rec.update({'status':'RUNNING','command':cmd,'started_utc':utc(),'cwd':str(CASE),'returncode':None,'launcher_pid':None,'timed_out':False})
 atomic(RECEIPT,rec);proc=None;rc=None;timed_out=False
 try:
  with (CASE/'wrf.stdout.log').open('xb') as out:
   proc=subprocess.Popen(cmd,cwd=CASE,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
   rec.update({'launcher_pid':proc.pid,'model_invocations':1,'forecast_invocations':1,'launched_utc':utc()});atomic(RECEIPT,rec)
   try:rc=proc.wait(timeout=3600)
   except subprocess.TimeoutExpired:
    timed_out=True
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:rc=proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
     try:os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     rc=proc.wait()
 except BaseException as exc:
  rec['launcher_error']=repr(exc)
  if proc is not None and proc.poll() is None:
   try:os.killpg(proc.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:rc=proc.wait(timeout=10)
   except subprocess.TimeoutExpired:
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    rc=proc.wait()
 rec.update({'returncode':rc,'timed_out':timed_out,'ended_utc':utc(),'staged_executable':staged_exe,'status':'PROCESS_COMPLETE_PENDING_SCAN'});atomic(RECEIPT,rec)
 try:
  scanned=scan_logs();detail_ok,bound_fields=parse_bound(scanned['table_bound_detail_lines'])
  rec['log_scan']=scanned;rec['table_bound_validation']=bound_fields
  rec['rank_success_markers']={str(rank):('wrf: success complete wrf' in (CASE/f'rsl.out.{rank:04d}').read_text(errors='replace').lower()) if (CASE/f'rsl.out.{rank:04d}').exists() else False for rank in range(4)}
  rec['pins_after']=snapshots(p,m);rec['assets_stable']=rec['pins_before']==rec['pins_after']
  rec['case_executable_after']=pin(CASE/'wrf.exe')
  rec['case_executable_stable']=(rec['case_executable_after']['sha256']==p['executable']['sha256'] and rec['case_executable_after']['size_bytes']==p['executable']['size_bytes'])
  rec['authorization_stable']=(sha(a.authorization)==rec['authorization_sha256'])
  direct=any(x['fatal_markers'] for x in scanned['logs'])
  rc_ok=(rc==1 and not timed_out)
  logs_ok=(scanned['present_logs']==9)
  rec['status']='PASS_EXPECTED_FATAL_REPRODUCTION' if (rc_ok and logs_ok and direct and detail_ok and rec['assets_stable'] and rec.get('case_executable_stable') is True and rec.get('authorization_stable') is True) else 'FAIL_PRESERVED'
  rec['interpretation']='Expected fatal reproduction only; no successful forecast, no full-period validation, and no physical-accuracy claim.'
 except BaseException as exc:
  rec['postprocess_error']=repr(exc);rec['status']='FAIL_PRESERVED'
 rec['finished_utc']=utc();atomic(RECEIPT,rec)
 print(json.dumps({'status':rec['status'],'returncode':rc,'fatal_detail_match':bool(rec.get('table_bound_validation')),
                   'receipt':str(RECEIPT)},indent=2))
 return 0 if rec['status']=='PASS_EXPECTED_FATAL_REPRODUCTION' else 2
if __name__=='__main__':raise SystemExit(main())
