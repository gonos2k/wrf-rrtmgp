#!/usr/bin/env python3
"""Run private 2-rank coefficient-loader failure probes; require no manual cleanup."""
from __future__ import annotations
import hashlib,json,os,pathlib,signal,subprocess,sys,time
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
BUNDLE=ROOT/'build/udm-sr-row-dm-sm/validation/collective-coefficient-failures-v2'
EXE=ROOT/'build/udm-sr-row-dm-sm/source/WRF/main/wrf.exe'
LAUNCHER=ROOT/'build/deps/mpich-sock/bin/mpiexec'
DATA=ROOT/'build/pr-wrf-rrtmgp/WRF/run'
RESTART=ROOT/'build/udm-frozen-restart-plan/trial-mode1-0to12/wrfrst_d01_2010-06-11_12:00:00'
TABLE=ROOT/'build/udm-mpix-evidence-work/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
COEFFS=['rrtmgp-gas-lw-g128.nc','rrtmgp-gas-sw-g112.nc','rrtmgp-clouds-lw-bnd.nc','rrtmgp-clouds-sw-bnd.nc']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def active(case):
 rows=[]
 for proc in pathlib.Path('/proc').glob('[0-9]*'):
  try:
   cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
   if str(EXE) in cmd and os.readlink(proc/'cwd')==str(case):rows.append({'pid':int(proc.name),'cmdline':cmd})
  except (OSError,ValueError):pass
 return rows
def main():
 pre=json.loads((BUNDLE/'preflight.json').read_text())
 if sha(EXE)!=pre['executable_sha256'] or sha(RESTART)!=pre['checkpoint_sha256']:raise RuntimeError('exe/restart preflight mismatch')
 before={n:sha(DATA/n) for n in COEFFS}
 if before!=pre['shared_coeff_hashes_before']:raise RuntimeError('shared coefficient preflight mismatch')
 cases=[]
 for name in pre['cases']:
  case=BUNDLE/name
  if active(case):raise RuntimeError(f'refusing preexisting WRF rank in {case}')
  env=os.environ.copy();env['PATH']=str(LAUNCHER.parent)+os.pathsep+env.get('PATH','')
  env['LD_LIBRARY_PATH']=str(ROOT/'build/deps/root/usr/lib/x86_64-linux-gnu')+':'+str(ROOT/'build/deps/mpich-sock/lib')+':'+env.get('LD_LIBRARY_PATH','')
  env.update({'MPICH_INTERFACE_HOSTNAME':'127.0.0.1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
  for key in list(env):
   if key.startswith(('WRF_RRTMGP_','RRTMGP_TRACE','RRTMGP_AUDIT')):env.pop(key,None)
  cmd=[str(LAUNCHER),'-launcher','fork','-iface','lo','-n','2','./wrf.exe'];log=case/'launcher.log';started=time.time();timeout=False;cleanup=[]
  with log.open('w') as f:
   p=subprocess.Popen(cmd,cwd=case,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
   try:rc=p.wait(timeout=60)
   except subprocess.TimeoutExpired:
    timeout=True;cleanup.append('timeout SIGTERM process group')
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:rc=p.wait(timeout=5)
    except subprocess.TimeoutExpired:
     cleanup.append('timeout SIGKILL process group after grace')
     try:os.killpg(p.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     rc=p.wait(timeout=5)
  elapsed=time.time()-started;remaining_before=active(case)
  if remaining_before:
   cleanup.append('manual case-scoped WRF-rank SIGTERM/SIGKILL after launcher return')
   for q in remaining_before:
    try:os.kill(q['pid'],signal.SIGTERM)
    except ProcessLookupError:pass
   time.sleep(1)
   for q in active(case):
    try:os.kill(q['pid'],signal.SIGKILL)
    except ProcessLookupError:pass
  remaining_after=active(case);logs={}
  for q in sorted(case.glob('rsl.error.*')):logs[q.name]=q.read_text(errors='replace')
  expected="load_cld_lutcoeff(): can't open file" if name=='missing-sw-cloud' else "load_and_init(): can't open file"
  diagnostic=logs.get('rsl.error.0000','')
  criteria={'launcher_nonzero':rc!=0,'within_60_seconds':elapsed<=60 and not timeout,'expected_loader_message_on_rank0':expected in diagnostic,'wrf_mpi_abort_on_rank0':'MPI_Abort(MPI_COMM_WORLD' in diagnostic,'both_rank_error_logs_present':all(f'rsl.error.{k:04d}' in logs for k in (0,1)),'no_manual_cleanup_needed':not remaining_before and not cleanup,'no_orphan_rank':not remaining_after}
  result={'case':name,'argv':cmd,'returncode':rc,'timeout_seconds':60,'timed_out':timeout,'elapsed_seconds':elapsed,'remaining_before_cleanup':remaining_before,'cleanup_actions':cleanup,'remaining_after_cleanup':remaining_after,'criteria':criteria,'status':'PASS' if all(criteria.values()) else 'FAIL','expected_error':expected,'launcher_log_sha256':sha(log),'rank_logs':{k:{'sha256':sha(case/k),'tail':v[-4000:]} for k,v in logs.items()},'private_coefficient_hashes_after':{q.name:{'sha256':sha(q),'bytes':q.stat().st_size} for q in sorted((case/'coefficients').iterdir())}}
  (case/'run-receipt.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');cases.append(result)
  print(json.dumps({'case':name,'status':result['status'],'rc':rc,'elapsed':elapsed,'remaining_before_cleanup':remaining_before,'cleanup_actions':cleanup},sort_keys=True),flush=True)
 after={n:sha(DATA/n) for n in COEFFS};binary_after=sha(EXE);restart_after=sha(RESTART);table_after=sha(TABLE)
 result={'schema':'WRF_MPI_COEFFICIENT_FAILURE_RUN_V2','status':'PASS' if all(x['status']=='PASS' for x in cases) and before==after and binary_after==pre['executable_sha256'] and restart_after==pre['checkpoint_sha256'] and table_after==pre['frozen_table_sha256'] else 'FAIL','executable_sha256_before_after':[pre['executable_sha256'],binary_after],'checkpoint_sha256_before_after':[pre['checkpoint_sha256'],restart_after],'canonical_table_sha256_before_after':[pre['frozen_table_sha256'],table_after],'shared_coefficient_hashes_before':before,'shared_coefficient_hashes_after':after,'shared_assets_unchanged':before==after,'cases':cases}
 (BUNDLE/'run-results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
