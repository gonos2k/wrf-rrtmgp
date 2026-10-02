#!/usr/bin/env python3
"""Prepare or run isolated MPI/OpenMP restart-equivalence trials for frozen UDM mode 1.

Default is preflight-only. `--prepare` creates case directories; `--execute` is an explicit
separate action and refuses to run before the checkpoint and all immutable hashes validate.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, resource, subprocess, time, threading
from pathlib import Path
from typing import Any
import numpy as np
from netCDF4 import Dataset

BUILD=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build')
WORK=BUILD/'udm-lw-trace-gases-dm-sm'
PLAN=BUILD/'udm-lw-trace-gases-parallel'
CASE=BUILD/'udm-frozen-runtime-mpi/case-mode1'
CHECKPOINT=BUILD/'udm-frozen-restart-plan/trial-mode1-0to12/wrfrst_d01_2010-06-11_12:00:00'
BINARY=WORK/'WRF/main/wrf.exe'
TABLE=BUILD/'udm-frozen-runtime-wrf/source/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
MPICH=BUILD/'deps/mpich-sock'; NETCDF=BUILD/'deps/netcdf'; ROOTLIB=BUILD/'deps/root/usr/lib/x86_64-linux-gnu'
EXPECTED_BINARY='6c0c1e3efc948a68b1579137d58dd972890b6e338a8cfa1c5c96e539c1c0daeb'
EXPECTED_TABLE='8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583'
START='2010-06-11_12:00:00'; STOP='2010-06-11_12:11:00'
CONFIGS=[('mpi1-omp1-v2',1,1),('mpi2-omp1-v2',2,1),('mpi4-omp1-v2',4,1),('mpi1-omp2-v2',1,2)]
DYNAMIC=re.compile(r'^(wrfout_|wrfrst_|rsl\.|namelist\.output$|.*\.log$|.*receipt\.json$)')

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def time_text(ds:Dataset)->str:
 return b''.join(np.asarray(ds.variables['Times'][:])[0].tolist()).decode('ascii')

def set_values(text:str,group:str,values:dict[str,str])->str:
 m=re.search(rf'(?im)^\s*&{re.escape(group)}\b',text)
 if not m:raise RuntimeError(f'missing namelist group &{group}')
 close=re.search(r'(?m)^\s*/\s*(?:!.*)?$',text[m.end():])
 if not close:raise RuntimeError(f'missing closing slash for &{group}')
 end=m.end()+close.start(); block=text[m.start():end]
 for key,val in values.items():
  p=re.compile(rf'(?im)^(\s*{re.escape(key)}\s*=\s*)([^!\n]*)(.*)$')
  block,n=p.subn(lambda x:x.group(1)+val+','+x.group(3),block)
  if n==0 and key=='override_restart_timers':
   block=block.rstrip()+f'\n override_restart_timers = {val},\n'
   n=1
  if n!=1:raise RuntimeError(f'expected one {key} in &{group}; found {n}')
 return text[:m.start()]+block+text[end:]

def validate_checkpoint()->dict[str,Any]:
 if not CHECKPOINT.is_file():raise RuntimeError(f'12h checkpoint not ready: {CHECKPOINT}')
 with Dataset(CHECKPOINT) as ds:
  if time_text(ds)!=START:raise RuntimeError(f'checkpoint time={time_text(ds)} expected {START}')
  def scalar(name):
   x=np.asarray(ds.variables[name][:]).reshape(-1)
   if x.size!=1 or not np.isfinite(x[0]):raise RuntimeError(f'invalid checkpoint {name}: {x}')
   return float(x[0])
  step=scalar('ITIMESTEP'); xtime=scalar('XTIME')
  if step!=720 or xtime!=720.:raise RuntimeError(f'checkpoint clock is ITIMESTEP={step} XTIME={xtime}, expected 720')
  options={k:int(ds.getncattr(k)) for k in ('MP_PHYSICS','RA_LW_PHYSICS','RA_SW_PHYSICS') if k in ds.ncattrs()}
  if options!={'MP_PHYSICS':27,'RA_LW_PHYSICS':37,'RA_SW_PHYSICS':37}:raise RuntimeError(f'checkpoint physics mismatch: {options}')
  bad=[]; nfloat=0
  for name,var in ds.variables.items():
   if var.dtype.kind=='f':
    a=np.asarray(var[:]); nfloat+=1
    if not np.isfinite(a).all():bad.append(name)
  if bad:raise RuntimeError(f'nonfinite checkpoint values in {bad[:8]}')
  return {'path':str(CHECKPOINT),'sha256':sha(CHECKPOINT),'bytes':CHECKPOINT.stat().st_size,'time':START,'timestep':int(step),'xtime_minutes':xtime,'physics':options,'finite_float_variables':nfloat,'nonfinite_variables':bad}

def make_namelist(name:str)->tuple[str,str]:
 text=(CASE/'namelist.input').read_text()
 values={'run_days':'0','run_hours':'0','run_minutes':'11','run_seconds':'0',
 'start_year':'2010, 2010','start_month':'06, 06','start_day':'11, 11','start_hour':'12, 12','start_minute':'00, 00','start_second':'00, 00',
 'end_year':'2010, 2010','end_month':'06, 06','end_day':'11, 11','end_hour':'12, 12','end_minute':'11, 11','end_second':'00, 00',
 'restart':'.true.','override_restart_timers':'.true.','history_interval':'1, 1','frames_per_outfile':'1, 1'}
 text=set_values(text,'time_control',values)
 return text,sha(CASE/'namelist.input')

def prepare()->dict[str,Any]:
 checkpoint=validate_checkpoint()
 for x in (BINARY,CASE/'wrfinput_d01',CASE/'wrfbdy_d01',TABLE):
  if not x.is_file():raise RuntimeError(f'missing immutable asset {x}')
 if sha(BINARY)!=EXPECTED_BINARY:raise RuntimeError(f'binary SHA mismatch {sha(BINARY)}')
 if sha(TABLE)!=EXPECTED_TABLE:raise RuntimeError(f'table SHA mismatch {sha(TABLE)}')
 nml,source_nml_sha=make_namelist('')
 report={'status':'PREPARED_NOT_EXECUTED','attempt':'v2; prior attempt preserved in unsuffixed directories and failed because restored hourly checkpoint history timer suppressed 12:11 output','checkpoint':checkpoint,'binary':{'path':str(BINARY),'sha256':sha(BINARY)},'table':{'path':str(TABLE),'sha256':sha(TABLE)},'inputs':{n:{'path':str(CASE/n),'sha256':sha(CASE/n)} for n in ('wrfinput_d01','wrfbdy_d01')},'source_namelist_sha256':source_nml_sha,'run_namelist_sha256':sha_from_bytes(nml.encode()),'physics_run_controls':'Only &time_control timestamps/duration/restart/override_restart_timers/history interval/frames-per-outfile differ; all configs use same generated namelist. override_restart_timers=.true. is required to schedule the requested 1-minute history output rather than restoring the checkpoint hourly history alarm.','configs':[],'comparison_reference':'mpi1-omp1-v2 at 2010-06-11_12:11:00; metadata/run-control attributes are reported separately from exact numeric fields','compare_at':STOP,'execution_authorized_by_cli':False}
 for name,ranks,threads in CONFIGS:
  target=PLAN/name
  if target.exists():raise RuntimeError(f'refusing existing trial path {target}')
  target.mkdir(parents=True)
  for ent in CASE.iterdir():
   if ent.name in ('namelist.input','run-receipt.json','preparation-receipt.json') or DYNAMIC.match(ent.name):continue
   if ent.name in ('wrfinput_d01','wrfbdy_d01') or ent.is_symlink():
    if not ent.exists():raise RuntimeError(f'broken static input symlink {ent}')
    (target/ent.name).symlink_to(ent.resolve(strict=True))
   elif ent.is_file():(target/ent.name).symlink_to(ent.resolve(strict=True))
   elif ent.is_dir():(target/ent.name).symlink_to(ent.resolve(strict=True),target_is_directory=True)
  (target/'wrf.exe').symlink_to(BINARY.resolve(strict=True))
  (target/f'wrfrst_d01_{START}').symlink_to(CHECKPOINT.resolve(strict=True))
  (target/'namelist.input').write_text(nml)
  report['configs'].append({'name':name,'mpi_ranks':ranks,'omp_threads':threads,'case_dir':str(target),'namelist_sha256':sha(target/'namelist.input'),'checkpoint_sha256':sha(target/f'wrfrst_d01_{START}')})
 (PLAN/'preflight-plan.json').write_text(json.dumps(report,indent=2)+'\n')
 return report

def sha_from_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def runtime_env(threads:int)->dict[str,str]:
 env=os.environ.copy()
 env['PATH']=os.pathsep.join((str(MPICH/'bin'),'/home/korea_keun/.local/bin',env.get('PATH','')))
 env['LD_LIBRARY_PATH']=os.pathsep.join((str(MPICH/'lib'),str(NETCDF/'lib'),str(ROOTLIB),'/usr/lib/x86_64-linux-gnu',env.get('LD_LIBRARY_PATH','')))
 env['NETCDF']=str(NETCDF); env['MPICH_INTERFACE_HOSTNAME']='127.0.0.1'
 env['OMP_NUM_THREADS']=str(threads); env['OMP_STACKSIZE']='512M'; env['OMP_DYNAMIC']='FALSE'; env['OMP_MAX_ACTIVE_LEVELS']='1'
 for k in list(env):
  if k.startswith('WRF_RRTMGP_'):env.pop(k,None)
 return env

def descendants(root:int)->list[int]:
 ppid={}
 for ent in Path('/proc').iterdir():
  if not ent.name.isdigit():continue
  try:
   s=(ent/'stat').read_text(); tail=s[s.rfind(')')+2:].split(); ppid[int(ent.name)]=int(tail[1])
  except (OSError,ValueError,IndexError):pass
 found={root}; changed=True
 while changed:
  changed=False
  for pid,parent in ppid.items():
   if parent in found and pid not in found:found.add(pid);changed=True
 return sorted(found)

def proc_ticks(pid:int,tid:int|None=None)->int|None:
 path=Path('/proc')/str(pid)/'stat' if tid is None else Path('/proc')/str(pid)/'task'/str(tid)/'stat'
 try:
  s=path.read_text(); f=s[s.rfind(')')+2:].split(); return int(f[11])+int(f[12])
 except (OSError,ValueError,IndexError):return None

class ThreadMonitor:
 def __init__(self,root:int,wrf_exe:Path):self.root=root;self.wrf_exe=wrf_exe.resolve();self.stop=threading.Event();self.lock=threading.Lock();self.max_threads={};self.ticks={};self.samples=0;self.exe_paths={}
 def run(self):
  while not self.stop.is_set():
   snap={}
   for pid in descendants(self.root):
    try: exe=os.path.realpath(f'/proc/{pid}/exe')
    except OSError:continue
    if exe!=str(self.wrf_exe):continue
    self.exe_paths[pid]=exe
    task=Path('/proc')/str(pid)/'task'
    try:tids=[int(x.name) for x in task.iterdir() if x.name.isdigit()]
    except OSError:continue
    self.max_threads[pid]=max(self.max_threads.get(pid,0),len(tids))
    for tid in tids:
     ticks=proc_ticks(pid,tid)
     if ticks is not None:snap[(pid,tid)]=ticks
   with self.lock:
    for key,val in snap.items():
     old=self.ticks.get(key)
     if old is None:self.ticks[key]=[val,val]
     else:old[1]=val
    self.samples+=1
   self.stop.wait(.2)
 def summary(self):
  with self.lock:
   bypid={}
   for (pid,tid),(first,last) in self.ticks.items():
    x=bypid.setdefault(pid,{'max_threads_observed':self.max_threads.get(pid,0),'observed_threads':0,'active_threads':0,'cpu_ticks_delta':0})
    x['observed_threads']+=1;x['cpu_ticks_delta']+=max(0,last-first)
    if last>first:x['active_threads']+=1
   return {'sampling_interval_seconds':0.2,'samples':self.samples,'target_executable':str(self.wrf_exe),'process_exe_paths':self.exe_paths,'processes':bypid,'saw_process_with_multiple_threads':any(x['max_threads_observed']>1 for x in bypid.values()),'observed_active_threads':sum(x['active_threads'] for x in bypid.values()),'multiple_wrf_workers_active':any(x['active_threads']>1 for x in bypid.values())}

def compare_arrays(ref:Path,other:Path,expected:str)->dict[str,Any]:
 from compare_restart_outputs import compare
 report=compare(ref,other,expected)
 # Add aggregate L2 and explicit max absolute difference for all numeric variables.
 l2sq=0.; maxabs=0.; neq=0
 with Dataset(ref) as a, Dataset(other) as b:
  for name in sorted(set(a.variables)&set(b.variables)):
   va,vb=a.variables[name],b.variables[name]
   if va.dtype.kind not in 'fiu' or vb.dtype.kind not in 'fiu' or va.shape!=vb.shape:continue
   xa=np.asarray(va[:],dtype=np.float64);xb=np.asarray(vb[:],dtype=np.float64)
   d=np.abs(xa-xb)
   if d.size:
    maxabs=max(maxabs,float(np.nanmax(d)));l2sq+=float(np.nansum(d*d));neq+=int(np.count_nonzero(xa!=xb))
 report['numeric_delta_summary']={'all_numeric_values_bitwise_equal':neq==0,'different_numeric_values':neq,'max_abs_difference':maxabs,'l2_norm_difference':l2sq**0.5,'all_numeric_values_finite':not report['errors'] or not any(isinstance(x,dict) and 'nonfinite_variable' in x for x in report['errors'])}
 return report

def static_case_manifest()->list[dict[str,Any]]:
 manifest=[]
 for entry in sorted(CASE.iterdir()):
  if entry.name in ('namelist.input','run-receipt.json','preparation-receipt.json') or DYNAMIC.match(entry.name):continue
  target=entry.resolve(strict=True)
  if target.is_file():
   manifest.append({'case_name':entry.name,'target':str(target),'sha256':sha(target),'bytes':target.stat().st_size})
  elif target.is_dir():
   files=[]
   for f in sorted(target.rglob('*')):
    if f.is_file():files.append({'relative_path':str(f.relative_to(target)),'sha256':sha(f),'bytes':f.stat().st_size})
   manifest.append({'case_name':entry.name,'target':str(target),'files':files})
 return manifest

def frozen_source_manifest()->list[dict[str,Any]]:
 build=json.loads((WORK/'buildlogs/build-receipt.json').read_text())
 manifest=build['production_source_hashes']
 for item in manifest:
  p=WORK/item['path']
  if not p.is_file() or sha(p)!=item['sha256']:raise RuntimeError(f'production source hash changed: {p}')
 return manifest

def verify_prepared()->dict[str,Any]:
 cp=validate_checkpoint()
 if sha(BINARY)!=EXPECTED_BINARY or sha(TABLE)!=EXPECTED_TABLE:raise RuntimeError('binary or table hash changed since preflight')
 plan=json.loads((PLAN/'preflight-plan.json').read_text())
 expected_nml=plan['run_namelist_sha256']
 if plan.get('status')!='PREPARED_NOT_EXECUTED' or plan.get('execution_authorized_by_cli') is not False:raise RuntimeError('invalid preflight plan status')
 dirs=[]
 for name,ranks,threads in CONFIGS:
  p=PLAN/name
  if not p.is_dir():raise RuntimeError(f'missing prepared trial {p}; run --prepare')
  cfg=next((x for x in plan['configs'] if x['name']==name),None)
  if cfg is None or cfg['mpi_ranks']!=ranks or cfg['omp_threads']!=threads:raise RuntimeError(f'{name} config changed from preflight')
  if sha(p/'namelist.input')!=expected_nml or sha(p/'namelist.input')!=cfg['namelist_sha256']:raise RuntimeError(f'{name} namelist differs from preflight hash')
  if sha(p/f'wrfrst_d01_{START}')!=cp['sha256']:raise RuntimeError(f'{name} restart link differs from validated checkpoint')
  dirs.append({'name':name,'ranks':ranks,'threads':threads,'case_dir':str(p)})
 return {'checkpoint':cp,'configs':dirs,'preflight_plan_sha256':sha(PLAN/'preflight-plan.json'),'namelist_sha256':expected_nml,'production_sources':frozen_source_manifest(),'static_case_assets':static_case_manifest()}

def execute()->dict[str,Any]:
 pre=verify_prepared(); runs=[]; reference=None; errors=[]
 immutable={str(BINARY):sha(BINARY),str(TABLE):sha(TABLE),str(CHECKPOINT):sha(CHECKPOINT),str(CASE/'wrfinput_d01'):sha(CASE/'wrfinput_d01'),str(CASE/'wrfbdy_d01'):sha(CASE/'wrfbdy_d01')}
 source_snapshot={x['path']:x['sha256'] for x in pre['production_sources']}
 static_snapshot=pre['static_case_assets']
 def snapshot_ok()->dict[str,Any]:
  asset_after={k:sha(Path(k)) for k in immutable}
  sources_after={x['path']:sha(WORK/x['path']) for x in pre['production_sources']}
  static_after=static_case_manifest()
  return {'assets_unchanged':asset_after==immutable,'asset_after':asset_after,'production_sources_unchanged':sources_after==source_snapshot,'production_source_sha256_after':sources_after,'static_case_assets_unchanged':static_after==static_snapshot,'static_case_assets_after':static_after}
 receipt={'status':'RUNNING','runtime_completed':False,'numeric_equivalence':False,'metadata_match':False,'omp_worker_verified':False,'run_start':START,'run_end':STOP,'build_commit':'e73b353f2b76f323809f99bed19a29eaaf25af02','binary_sha256':sha(BINARY),'table_sha256':sha(TABLE),'preflight':pre,'matrix':runs,'errors':errors,'scope':'Restarted 11-minute MPI/OpenMP reproducibility only; no forecast accuracy claim.'}
 try:
  for item in pre['configs']:
   p=Path(item['case_dir']);name=item['name'];log=p/'wrf-mpi-omp.log';run={'name':name,'mpi_ranks':item['ranks'],'omp_threads_requested':item['threads'],'status':'RUNNING'};runs.append(run)
   try:
    if list(p.glob('rsl.*')) or (p/f'wrfout_d01_{STOP}').exists():raise RuntimeError(f'refusing non-fresh case {p}')
    preflight=json.loads((PLAN/'preflight-plan.json').read_text()); expected=preflight['run_namelist_sha256']
    if sha(p/'namelist.input')!=expected:raise RuntimeError(f'{name} namelist SHA differs from preflight')
    command=[str(MPICH/'bin/mpiexec'),'-launcher','fork','-iface','lo','-n',str(item['ranks']),'./wrf.exe'];run['command']=command
    env=runtime_env(item['threads']);run['runtime_env']={'OMP_NUM_THREADS':env['OMP_NUM_THREADS'],'OMP_STACKSIZE':env['OMP_STACKSIZE'],'OMP_DYNAMIC':env['OMP_DYNAMIC'],'OMP_MAX_ACTIVE_LEVELS':env['OMP_MAX_ACTIVE_LEVELS'],'MPICH_INTERFACE_HOSTNAME':env['MPICH_INTERFACE_HOSTNAME'],'capture_audit_environment_cleared':True,'main_stack_limit':'unlimited (RLIMIT_STACK preexec)'}
    def stack_unlimited():resource.setrlimit(resource.RLIMIT_STACK,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))
    start=time.monotonic();mon=None
    with log.open('w') as out:
     proc=subprocess.Popen(command,cwd=p,env=env,stdout=out,stderr=subprocess.STDOUT,preexec_fn=stack_unlimited)
     mon=ThreadMonitor(proc.pid,BINARY);monitor_thread=threading.Thread(target=mon.run,daemon=True);monitor_thread.start()
     rc=proc.wait();mon.stop.set();monitor_thread.join(timeout=5)
    elapsed=time.monotonic()-start
    rsl=sorted(p.glob('rsl.error.*'));success=[];fatal=[];rank_decomp=[]
    for f in rsl:
     txt=f.read_text(errors='replace');success.append('SUCCESS COMPLETE WRF' in txt)
     fatal.append(any(x in txt for x in ('FATAL','MPI_ABORT','outside frozen optics table')))
     mp=re.search(r'Ntasks in X\s+(\d+)\s*,\s*ntasks in Y\s+(\d+)',txt)
     tiles=[tuple(int(y) for y in m) for m in re.findall(r'WRF TILE\s+\d+ IS\s+(\d+) IE\s+(\d+) JS\s+(\d+) JE\s+(\d+)',txt)]
     rank_decomp.append({'rsl':f.name,'mpi_grid':[int(mp.group(1)),int(mp.group(2))] if mp else None,'tiles':tiles})
    output=p/f'wrfout_d01_{STOP}'
    runtime_ok=rc==0 and len(rsl)==item['ranks'] and bool(success) and all(success) and not any(fatal) and output.is_file()
    run.update({'exit_status':rc,'wall_seconds':elapsed,'runtime_completed':runtime_ok,'rank_success_markers':success,'fatal_markers':fatal,'rank_decomposition':rank_decomp,'stdout_log':str(log)})
    if mon is not None:run['thread_cpu_evidence']=mon.summary()
    if not runtime_ok:raise RuntimeError(f'{name} failed runtime completion check (exit={rc}, ranks={len(rsl)}, success={success}, fatal={fatal}); inspect {log}')
    with Dataset(output) as ds:
     if time_text(ds)!=STOP:raise RuntimeError(f'{name} output time mismatch {time_text(ds)}')
     fvars=[v for v in ds.variables.values() if v.dtype.kind=='f'];bad=[]
     for v in fvars:
      if not np.isfinite(np.asarray(v[:])).all():bad.append(v.name)
     if bad:raise RuntimeError(f'{name} has nonfinite fields: {bad[:8]}')
     output_meta={'time':time_text(ds),'variables':len(ds.variables),'float_variables':len(fvars),'physics_attrs':{k:int(ds.getncattr(k)) for k in ('MP_PHYSICS','RA_LW_PHYSICS','RA_SW_PHYSICS') if k in ds.ncattrs()},'itimestep':int(np.asarray(ds.variables['ITIMESTEP'][:]).reshape(-1)[0]) if 'ITIMESTEP' in ds.variables else None}
    imm=snapshot_ok();run['immutable_snapshot']=imm
    if not imm['assets_unchanged'] or not imm['production_sources_unchanged'] or not imm['static_case_assets_unchanged']:raise RuntimeError(f'immutable source/assets changed during {name}')
    run['output']={'path':str(output),'sha256':sha(output),'bytes':output.stat().st_size,**output_meta}
    run['status']='COMPLETED'
    if reference is None:
     reference=output;run['comparison_to']='self';run['comparison_report']={'passed':True,'dynamics_passed':True,'metadata_match':True,'numeric_delta_summary':{'all_numeric_values_bitwise_equal':True,'max_abs_difference':0.0,'l2_norm_difference':0.0}}
    else:
     rep=compare_arrays(reference,output,STOP);name_json=f'compare-{CONFIGS[0][0]}-vs-{name}.json';(PLAN/name_json).write_text(json.dumps(rep,indent=2)+'\n');run['comparison_to']=str(reference);run['comparison_report_path']=name_json;run['comparison_report']=rep;run['numeric_delta_summary']=rep['numeric_delta_summary'];run['dynamics_passed']=rep['dynamics_passed'];run['metadata_match']=rep['metadata_match'];run['comparison_errors']=rep['errors'];run['shape_and_field_differences']=rep['variable_differences']
   except Exception as e:
    run['status']='FAILED';run['error']=f'{type(e).__name__}: {e}';errors.append({'config':name,'error':run['error']});raise
 finally:
  runtime_completed=len(runs)==len(CONFIGS) and all(r.get('runtime_completed',False) for r in runs)
  comparisons=[r for r in runs if r.get('comparison_report')]
  numeric_equivalence=runtime_completed and all(r.get('comparison_report',{}).get('dynamics_passed',False) and r.get('comparison_report',{}).get('numeric_delta_summary',{}).get('all_numeric_values_bitwise_equal',False) for r in comparisons) and len(comparisons)==len(CONFIGS)
  metadata_match=runtime_completed and all(r.get('comparison_report',{}).get('metadata_match',False) for r in comparisons) and len(comparisons)==len(CONFIGS)
  omp_trial=next((r for r in runs if r.get('name')=='mpi1-omp2-v2'),{})
  omp_worker_verified=bool(omp_trial.get('thread_cpu_evidence',{}).get('multiple_wrf_workers_active',False))
  receipt.update({'runtime_completed':runtime_completed,'numeric_equivalence':numeric_equivalence,'metadata_match':metadata_match,'omp_worker_verified':omp_worker_verified,'immutable_sources_unchanged_final':snapshot_ok(),'status':'MATRIX_RUN_PASS' if runtime_completed and numeric_equivalence and metadata_match and omp_worker_verified and not errors else ('MATRIX_RUN_COMPLETED_WITH_DIFFERENCES' if runtime_completed else 'MATRIX_RUN_FAILED_OR_INCOMPLETE')})
  (PLAN/'matrix-run-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 return receipt

def main()->int:
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--prepare',action='store_true',help='prepare three new trial dirs if checkpoint is valid')
 p.add_argument('--execute',action='store_true',help='launch the prepared matrix only after explicit parent preflight review')
 p.add_argument('--preflight-reviewed',action='store_true',help='required together with --execute after review')
 a=p.parse_args()
 if a.execute:
  if not a.preflight_reviewed:raise SystemExit('refusing execution without --preflight-reviewed after parent approval')
  print(json.dumps(execute(),indent=2))
 if a.prepare: print(json.dumps(prepare(),indent=2))
 else:
  result={'checkpoint_exists':CHECKPOINT.is_file(),'checkpoint_path':str(CHECKPOINT),'binary_sha256':sha(BINARY),'table_sha256':sha(TABLE),'prepared_directories':[str(PLAN/n) for n,_,_ in CONFIGS if (PLAN/n).exists()]}
  print(json.dumps(result,indent=2))
 return 0
if __name__=='__main__':raise SystemExit(main())
