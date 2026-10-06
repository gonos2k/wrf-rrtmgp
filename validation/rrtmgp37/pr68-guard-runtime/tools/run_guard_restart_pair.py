#!/usr/bin/env python3
"""Fail-closed, one-use PR65/PR68 guard restart runner. Requires later root authorization."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, resource, signal, subprocess, sys
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

HERE=Path(__file__).resolve().parent
PLAN=HERE/'plan-v3.json'; MANIFEST=HERE/'stage-manifest-v3.json'; READBACK=HERE/'stage-readback-v3.json'
AUTH=HERE/'root-authorization-v3.json'; LOCK=HERE/'.one-use-v3.lock'; RECEIPT=HERE/'execution-receipt-v3.json'
ARMS=('pr65','pr68'); TIMES=('2016-10-07_12:00:00','2016-10-07_13:00:00'); FATAL=('FATAL CALLED FROM FILE','APPLICATION CALLED MPI_ABORT','ERROR: FATAL','RRtmgp_fatal','DP_HPA_NOT_FINITE')
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(path):
 p=Path(path);return {'path':str(p.resolve()),'sha256':sha(p),'size_bytes':p.stat().st_size}
def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def atomic(path,obj):
 p=Path(path);t=p.with_name(p.name+f'.tmp.{os.getpid()}')
 with t.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p)
 dfd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(dfd)
 finally:os.close(dfd)
def verify_pins(obj,label):
 checked=[]
 if isinstance(obj,dict):
  if {'path','sha256'}<=set(obj):
   q=Path(obj['path'])
   if not q.is_file():raise RuntimeError(f'{label}: pinned file absent: {q}')
   if ('size_bytes' in obj and q.stat().st_size!=obj['size_bytes']) or sha(q)!=obj['sha256']:
    raise RuntimeError(f'{label}: pinned bytes changed: {q}')
   checked.append({'label':label,'path':str(q.resolve()),'sha256':obj['sha256'],'size_bytes':q.stat().st_size})
  else:
   for k,v in obj.items():checked.extend(verify_pins(v,f'{label}.{k}'))
 elif isinstance(obj,list):
  for i,v in enumerate(obj):checked.extend(verify_pins(v,f'{label}[{i}]'))
 return checked
def check_stage(plan,manifest,reject_outputs=True):
 if plan['status']!='STAGED_WAITING_FOR_ROOT_AUTHORIZATION':raise RuntimeError('unexpected plan state')
 if manifest['plan_sha256']!=sha(PLAN):raise RuntimeError('manifest does not bind current plan')
 checked=verify_pins(plan,'plan')+verify_pins(manifest,'manifest')
 readback=json.loads(READBACK.read_text())
 if readback.get('plan_sha256')!=sha(PLAN) or readback.get('manifest_sha256')!=sha(MANIFEST):raise RuntimeError('stage readback hashes do not match')
 expected_runner=sha(Path(__file__))
 if plan.get('runner',{}).get('sha256')!=expected_runner or manifest.get('runner',{}).get('sha256')!=expected_runner or readback.get('runner',{}).get('sha256')!=expected_runner:raise RuntimeError('runner is not bound by plan/manifest/readback')
 checked.extend(verify_pins(readback,'readback'))
 common_names=set(manifest['cases']['pr65'])&set(manifest['cases']['pr68'])
 if set(manifest['cases']['pr65'])!=set(manifest['cases']['pr68']):raise RuntimeError('restart arms do not carry the same staged asset set')
 for name in sorted(common_names-{'wrf.exe'}):
  left,right=manifest['cases']['pr65'][name],manifest['cases']['pr68'][name]
  if (left['resolved']['sha256'],left['resolved']['size_bytes'])!=(right['resolved']['sha256'],right['resolved']['size_bytes']):raise RuntimeError(f'restart-arm shared asset bytes mismatch: {name}')
  if left['link_text'] is not None and right['link_text'] is not None and left['resolved']['path']!=right['resolved']['path']:raise RuntimeError(f'restart-arm linked target differs: {name}')
 for arm in ARMS:
  c=Path(plan['arms'][arm]['directory'])
  for name,item in manifest['cases'][arm].items():
   q=c/name
   if not q.exists():raise RuntimeError(f'missing staged asset {arm}/{name}')
   if item['link_text'] is not None and (not q.is_symlink() or os.readlink(q)!=item['link_text']):raise RuntimeError(f'link text mismatch {arm}/{name}')
   actual=pin(q)
   if actual['sha256']!=item['resolved']['sha256'] or actual['size_bytes']!=item['resolved']['size_bytes']:raise RuntimeError(f'asset changed {arm}/{name}')
  if arm=='pr68' and (c/'wrf.exe').exists():
   expected=plan['pr68_candidate'].get('verified_executable')
   if not expected or pin(c/'wrf.exe')['sha256']!=expected['sha256']:raise RuntimeError('PR68 staged executable is not the separately verified candidate')
  if reject_outputs:
   for pat in ('rsl.*','wrfout_d01_*','wrfrst_d01_*'):
    found=[str(x.name) for x in c.glob(pat) if x.name!='wrfrst_d01_2016-10-07_12:00:00']
    if found:raise RuntimeError(f'pre-existing model output in {arm}: {found[:3]}')
  else:
   candidate_exe=plan['pr68_candidate']['verified_executable']
   if arm=='pr68' and (not (c/'wrf.exe').is_file() or sha(c/'wrf.exe')!=candidate_exe['sha256']):raise RuntimeError('post-run guard executable changed')
 nml_diff=validate_namelists(plan)
 candidate=validate_candidate_build(plan)
 if len({(x['path'],x['sha256']) for x in checked})<100:raise RuntimeError('unexpectedly incomplete frozen-pin inventory')
 return {'entries':{a:len(manifest['cases'][a]) for a in ARMS},'checked_pin_records':len(checked),'checked_mpi':next(x for x in checked if x['path']==str(Path(plan['runtime']['mpi_launcher']['path']).resolve())),'candidate_build':candidate,'namelist_diff':nml_diff}
def time_control_values(path):
 text=Path(path).read_text();m=__import__('re').search(r'(?is)&time_control\b(.*?)^\s*/\s*',text,__import__('re').M)
 if not m:raise RuntimeError(f'{path}: missing &time_control')
 values={}
 for line in m.group(1).splitlines():
  q=__import__('re').match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*(?:!.*)?$',line)
  if q:values[q.group(1).lower()]=q.group(2).rstrip(',').strip()
 return values
def validate_namelists(plan):
 p65=Path(plan['arms']['pr65']['namelist']['path']);p68=Path(plan['arms']['pr68']['namelist']['path'])
 parent=Path(plan['namelist_contract']['parent_namelist']['path'])
 t65=p65.read_bytes();t68=p68.read_bytes();tp=parent.read_bytes()
 if t65!=t68:raise RuntimeError('restart arms have different namelists')
 before=time_control_values(parent);after=time_control_values(p65)
 diff={k:{'parent':before.get(k),'restart':after.get(k)} for k in sorted(set(before)|set(after)) if before.get(k)!=after.get(k)}
 if diff!=plan['namelist_contract']['only_time_control_differences_from_completed_parent']:raise RuntimeError('namelist time-control changes differ from pinned contract')
 import re
 def rest(data):return re.sub(rb'(?is)&time_control\b.*?^\s*/\s*',b'',data,count=1,flags=re.M)
 if rest(tp)!=rest(t65):raise RuntimeError('non-time-control namelist sections changed')
 return {'same_between_arms':True,'only_expected_time_control_changes':True,'changed_values':diff,'changed_keys':sorted(diff),'non_time_control_sections_byte_identical':True}
def validate_candidate_build(plan):
 cand=plan['pr68_candidate']
 exe=cand.get('verified_executable')
 post=cand.get('build_postflight')
 evidence=cand.get('build_evidence',{})
 if not exe or not post:raise RuntimeError('PR68 executable/build postflight not pinned')
 if sha(exe['path'])!=exe['sha256'] or Path(exe['path']).stat().st_size!=exe['size_bytes']:raise RuntimeError('PR68 executable pin changed')
 post_data=json.loads(Path(post['path']).read_text())
 if post_data.get('status')!='BUILD_PASS_SCOPED_POSTFLIGHT_RECONCILED' or post_data.get('candidate_head')!=cand['source_commit'] or post_data.get('failed_checks'):
  raise RuntimeError('PR68 reconciled build postflight is not a scoped pass for the pinned source')
 if not all(x.get('pass') for x in post_data.get('checks',{}).values()):raise RuntimeError('PR68 build postflight contains a failed check')
 original=json.loads(Path(evidence['original_BUILD_FAIL_receipt']['path']).read_text())
 process=json.loads(Path(evidence['process_complete']['path']).read_text())
 summary=json.loads(Path(evidence['reconciled_build_summary']['path']).read_text())
 log_pin=evidence['original_BUILD_FAIL_log']
 if original.get('status')!='BUILD_FAIL':raise RuntimeError('original build failure receipt not preserved')
 if process.get('returncode')!=0 or process.get('timed_out'):raise RuntimeError('PR68 compiler process did not complete successfully')
 if summary.get('status')!='BUILD_PASS_SCOPED_POSTFLIGHT_RECONCILED' or summary.get('original_runner_receipt_status')!='BUILD_FAIL' or summary.get('model_invocations')!=0:
  raise RuntimeError('reconciled build summary does not preserve original BUILD_FAIL/zero-model scope')
 if sha(evidence['original_BUILD_FAIL_receipt']['path'])!=post_data.get('original_build_receipt_sha256'):
  raise RuntimeError('reconciled postflight does not bind the preserved original BUILD_FAIL receipt')
 if sha(evidence['process_complete']['path'])!=post_data.get('original_process_receipt_sha256') or sha(log_pin['path'])!=post_data.get('original_build_log_sha256'):
  raise RuntimeError('reconciled postflight does not bind the compiler process/log')
 if sha(evidence['process_complete']['path'])!=summary.get('process_complete_sha256') or sha(log_pin['path'])!=summary.get('compile_log_sha256'):
  raise RuntimeError('build summary process/log pins disagree')
 staged=Path(plan['arms']['pr68']['directory'])/'wrf.exe'
 if not staged.is_file() or sha(staged)!=exe['sha256']:raise RuntimeError('staged candidate bytes do not match attested PR68 executable')
 source_exe=cand.get('source_build_executable')
 if not source_exe or sha(source_exe['path'])!=exe['sha256']:raise RuntimeError('source build executable differs from staged candidate')
 if post_data.get('executables',{}).get('wrf.exe',{}).get('sha256')!=exe['sha256']:raise RuntimeError('reconciled build postflight executable hash mismatch')
 cfg=Path(cand['build_evidence']['candidate_configure']['path']);oldcfg=Path(cand['build_evidence']['pr65_configure']['path'])
 if sha(cfg)!=sha(oldcfg):raise RuntimeError('PR68 and PR65 configure.wrf bytes differ')
 closure=json.loads(Path(plan['runtime']['runtime_closure_readback']['path']).read_text())
 verify_pins(closure,'PR65/PR68 runtime closure readback')
 if not closure.get('all_resolved_libraries_identical') or closure.get('library_counts')!={'pr65':50,'pr68':50}:
  raise RuntimeError('PR65/PR68 runtime library closures are not identical')
 if closure.get('new_executable',{}).get('sha256')!=exe['sha256'] or closure.get('old_executable',{}).get('sha256')!=plan['pr65_binary']['sha256']:
  raise RuntimeError('runtime closure comparison does not bind the two actual binaries')
 return {'status':post_data['status'],'candidate_source_commit':post_data['candidate_head'],'candidate_executable':exe,'original_runner_status':original['status'],'compiler_returncode':process['returncode'],'timed_out':process.get('timed_out',False),'configure_sha256':sha(cfg),'pr65_configure_sha256':sha(oldcfg),'configure_sha256_equal':sha(cfg)==sha(oldcfg),'runtime_libraries_equal':True,'runtime_library_count':50,'build_summary_sha256':sha(evidence['reconciled_build_summary']['path'])}
def output_quality(path):
 result={'path':pin(path),'times':[],'variables':0,'finite_values_checked':0}
 with Dataset(path,'r') as ds:
  if 'Times' not in ds.variables:raise RuntimeError(f'{path}: missing Times')
  ts=[''.join(x.decode() if isinstance(x,bytes) else str(x) for x in row).strip() for row in ds['Times'][:]]
  result['times']=ts
  result['dimensions']={k:{'size':len(v),'unlimited':bool(v.isunlimited())} for k,v in ds.dimensions.items()}
  for name,var in ds.variables.items():
   result['variables']+=1
   var.set_auto_maskandscale(False);raw=np.asarray(var[:])
   if raw.dtype.kind in 'fci':
    if not np.isfinite(raw).all():raise RuntimeError(f'{path}:{name} has nonfinite raw values')
    fill=getattr(var,'_FillValue',None)
    if fill is not None and np.any(raw==fill):raise RuntimeError(f'{path}:{name} contains _FillValue')
    result['finite_values_checked']+=raw.size
   var.set_auto_maskandscale(True);decoded=var[:]
   if np.ma.isMaskedArray(decoded) and np.ma.getmaskarray(decoded).any():raise RuntimeError(f'{path}:{name} contains masked decoded values')
   decoded_values=np.asarray(decoded.data if np.ma.isMaskedArray(decoded) else decoded)
   if decoded_values.dtype.kind in 'fci' and not np.isfinite(decoded_values).all():raise RuntimeError(f'{path}:{name} has nonfinite decoded values')
 return result
def file_compare(left,right):
 out={'left':pin(left),'right':pin(right),'status':'PASS_EXACT_DATA','array_mismatches':[],'schema_mismatches':[],'attribute_differences':[]}
 with Dataset(left,'r') as a,Dataset(right,'r') as b:
  dims_a={k:(len(v),bool(v.isunlimited())) for k,v in a.dimensions.items()}
  dims_b={k:(len(v),bool(v.isunlimited())) for k,v in b.dimensions.items()}
  if dims_a!=dims_b:out['schema_mismatches'].append({'dimension_maps_equal':False,'left':dims_a,'right':dims_b})
  if set(a.variables)!=set(b.variables):out['schema_mismatches'].append({'variable_sets_equal':False,'left_only':sorted(set(a.variables)-set(b.variables)),'right_only':sorted(set(b.variables)-set(a.variables))})
  for name in sorted(set(a.variables)&set(b.variables)):
   va,vb=a[name],b[name]
   if va.dimensions!=vb.dimensions or va.shape!=vb.shape or va.dtype!=vb.dtype:
    out['schema_mismatches'].append({'variable':name,'left':{'dims':va.dimensions,'shape':va.shape,'dtype':str(va.dtype)},'right':{'dims':vb.dimensions,'shape':vb.shape,'dtype':str(vb.dtype)}});continue
   va.set_auto_maskandscale(False);vb.set_auto_maskandscale(False)
   xa,xb=np.asarray(va[:]),np.asarray(vb[:])
   if xa.tobytes(order='C')!=xb.tobytes(order='C'):
    out['array_mismatches'].append({'variable':name,'dtype':str(xa.dtype),'shape':xa.shape,'max_abs':float(np.max(np.abs(xa.astype('float64')-xb.astype('float64')))) if xa.dtype.kind in 'fiu' and xa.size else None})
   attrs_a={k:repr(va.getncattr(k)) for k in va.ncattrs()};attrs_b={k:repr(vb.getncattr(k)) for k in vb.ncattrs()}
   if attrs_a!=attrs_b:
    out['attribute_differences'].append({'variable':name,'left':attrs_a,'right':attrs_b})
    out['schema_mismatches'].append({'variable':name,'attribute_sets_or_values_equal':False})
  ga={k:repr(a.getncattr(k)) for k in a.ncattrs()};gb={k:repr(b.getncattr(k)) for k in b.ncattrs()}
  out['global_attribute_differences']={k:{'left':ga.get(k),'right':gb.get(k)} for k in sorted(set(ga)|set(gb)) if ga.get(k)!=gb.get(k)}
 if out['schema_mismatches'] or out['array_mismatches']:out['status']='FAIL_NUMERIC_OR_SCHEMA_DIFFERENCE'
 return out
def compare_parent_record(parent,child,index):
 out={'parent':pin(parent),'child':pin(child),'record_index':index,'status':'DIAGNOSTIC_ONLY','differences':[],'variable_set_differences':{'parent_only':[],'restart_only':[]}}
 with Dataset(parent,'r') as a,Dataset(child,'r') as b:
  out['variable_set_differences']={'parent_only':sorted(set(a.variables)-set(b.variables)),'restart_only':sorted(set(b.variables)-set(a.variables))}
  for name in sorted(set(a.variables)&set(b.variables)):
   va,vb=a[name],b[name]; va.set_auto_maskandscale(False);vb.set_auto_maskandscale(False)
   xa=np.asarray(va[index:index+1,...] if va.dimensions and va.dimensions[0]=='Time' else va[:])
   xb=np.asarray(vb[:])
   if xa.shape!=xb.shape or xa.dtype!=xb.dtype or xa.tobytes()!=xb.tobytes():
    maxabs=None
    if xa.shape==xb.shape and xa.dtype.kind in 'fiu' and xb.dtype.kind in 'fiu' and xa.size:
     maxabs=float(np.max(np.abs(xa.astype('float64')-xb.astype('float64'))))
    out['differences'].append({'variable':name,'parent_shape':xa.shape,'restart_shape':xb.shape,'parent_dtype':str(xa.dtype),'restart_dtype':str(xb.dtype),'max_abs':maxabs})
  out['parent_global_attributes']={k:repr(a.getncattr(k)) for k in a.ncattrs()}
  out['restart_global_attributes']={k:repr(b.getncattr(k)) for k in b.ncattrs()}
 return out
def run_arm(arm,plan,env,receipt):
 c=Path(plan['arms'][arm]['directory']); exe=Path(plan['arms'][arm]['executable']['path'])
 if not exe.is_file() or sha(exe)!=plan['arms'][arm]['executable']['sha256']:raise RuntimeError(f'{arm}: executable pin mismatch')
 command=[plan['runtime']['mpi_launcher']['path'],'-launcher','fork','-iface','lo','-n','4',str(exe)]
 rec={'status':'STARTING','command':command,'cwd':str(c),'started_utc':stamp(),'returncode':None,'timed_out':False,'launcher_pid':None,'model_invocations':0}
 receipt['arms'][arm]=rec;atomic(RECEIPT,receipt)
 env['WRF_RRTMGP_BATCH_SIZE']='32'
 proc=None;rc=None;timed=False
 try:
  with (c/'wrf.stdout.log').open('xb') as log:
   proc=subprocess.Popen(command,cwd=c,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   rec['launcher_pid']=proc.pid;rec['model_invocations']=1;receipt['model_invocations']+=1;rec['status']='RUNNING';atomic(RECEIPT,receipt)
   try:rc=proc.wait(timeout=1800)
   except subprocess.TimeoutExpired:
    timed=True
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:rc=proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
     try:os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     rc=proc.wait()
 except BaseException as exc:
  rec['launcher_error']=repr(exc)
  if proc is not None and proc.poll() is None:
   try:os.killpg(proc.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:rc=proc.wait(timeout=15)
   except subprocess.TimeoutExpired:
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    rc=proc.wait(timeout=15)
 rec['returncode']=rc;rec['timed_out']=timed;rec['ended_utc']=stamp();rec['status']='PROCESS_COMPLETE';atomic(RECEIPT,receipt)
 rank_success=set();fatal=[]
 for pat in ('rsl.out.*','rsl.error.*'):
  for log in c.glob(pat):
   text=log.read_text(errors='replace')
   if 'wrf: success complete wrf' in text.lower():
    try:rank_success.add(int(log.name.rsplit('.',1)[1]))
    except ValueError:pass
   for line_no,line in enumerate(text.splitlines(),1):
    if any(marker.lower() in line.lower() for marker in FATAL):fatal.append({'file':log.name,'line':line_no,'text':line[:1000]})
 stdout=c/'wrf.stdout.log'
 if stdout.is_file():
  for line_no,line in enumerate(stdout.read_text(errors='replace').splitlines(),1):
   if any(marker.lower() in line.lower() for marker in FATAL):fatal.append({'file':stdout.name,'line':line_no,'text':line[:1000]})
 rec['unique_success_ranks']=sorted(rank_success);rec['fatal_markers']=fatal
 if rc!=0 or timed or sorted(rank_success)!=[0,1,2,3] or fatal:
  rec['status']='FAIL_PRESERVED';rec['reason']='nonzero/timeout/incomplete unique-rank success/fatal marker';return False
 expected=plan['restart']['expected_history_times']; checked=[]
 for ts in expected:
  f=c/f'wrfout_d01_{ts}'
  if not f.is_file():raise RuntimeError(f'{arm}: expected history missing {f.name}')
  q=output_quality(f)
  if q['times']!=[ts]:raise RuntimeError(f'{arm}: unexpected Times in {f.name}: {q["times"]}')
  checked.append(q)
 checkpoint=c/plan['restart']['expected_checkpoint']
 if not checkpoint.is_file():raise RuntimeError(f'{arm}: final checkpoint missing')
 cq=output_quality(checkpoint)
 if cq['times']!=[plan['restart']['end']]:raise RuntimeError(f'{arm}: unexpected checkpoint Times {cq["times"]}')
 rec['history_quality']=checked;rec['checkpoint_quality']=cq;rec['final_checkpoint']=pin(checkpoint);rec['status']='PASS_OUTPUTS_VALID';atomic(RECEIPT,receipt)
 return True
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--preflight',action='store_true');ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 plan=json.loads(PLAN.read_text());manifest=json.loads(MANIFEST.read_text()); counts=check_stage(plan,manifest)
 if a.preflight or not a.execute:
  print(json.dumps({'status':'PREPARED_WAITING_FOR_ROOT_AUTH','stage_readback':counts,'candidate_executable_present':True,'model_invocations':0},indent=2));return 0
 if LOCK.exists() or RECEIPT.exists():raise SystemExit('one-use lock or receipt exists; refusing to run')
 cand=plan['pr68_candidate']
 if not cand.get('verified_executable') or not cand.get('build_postflight'):raise SystemExit('PR68 guard executable/build postflight not yet pinned; no execution')
 if not AUTH.is_file():raise SystemExit('root authorization absent; no execution')
 auth=json.loads(AUTH.read_text())
 expected={'plan_sha256':sha(PLAN),'manifest_sha256':sha(MANIFEST),'readback_sha256':sha(READBACK),'runner_sha256':sha(Path(__file__)),'pr68_executable_sha256':cand['verified_executable']['sha256'],'pr68_build_postflight_sha256':cand['build_postflight']['sha256']}
 if any(auth.get(k)!=v for k,v in expected.items()):raise SystemExit('authorization does not bind the frozen plan, runner, stage, and PR68 build')
 if auth.get('status')!='AUTHORIZED_TO_RUN' or auth.get('max_model_invocations')!=2 or auth.get('model_invocations')!=0 or auth.get('build_invocations')!=0:raise SystemExit('authorization must explicitly allow at most two model calls, start with zero model calls, and permit no build')
 if sha(cand['verified_executable']['path'])!=cand['verified_executable']['sha256']:raise SystemExit('PR68 executable bytes changed')
 stack_before=resource.getrlimit(resource.RLIMIT_STACK);wanted=536870912
 if stack_before[1]!=resource.RLIM_INFINITY and stack_before[1]<wanted:raise SystemExit('master stack hard limit too small')
 resource.setrlimit(resource.RLIMIT_STACK,(wanted,stack_before[1]))
 stack_after=resource.getrlimit(resource.RLIMIT_STACK)
 if stack_after[0]!=wanted:raise SystemExit('could not enforce required master stack')
 pins_before=check_stage(plan,manifest)
 fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,json.dumps({'utc':stamp(),'pid':os.getpid(),'plan_sha256':sha(PLAN)}).encode());os.fsync(fd);os.close(fd)
 receipt={'schema':'udm37-pr68-guard-success-restart-execution-v1','status':'RUNNING','plan_sha256':sha(PLAN),'manifest_sha256':sha(MANIFEST),'readback_sha256':sha(READBACK),'runner_sha256':sha(Path(__file__)),'authorization_sha256':sha(AUTH),'started_utc':stamp(),'model_invocations':0,'master_RLIMIT_STACK':{'before':list(stack_before),'after':list(stack_after)},'preflight_entries':pins_before,'arms':{},'comparisons':{}}
 atomic(RECEIPT,receipt);env=os.environ.copy()
 for key in list(env):
  if key.startswith(('OMP_','GOMP_','KMP_','WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE')) or key in ('LD_PRELOAD','LD_AUDIT'):env.pop(key,None)
 env.update({'LD_LIBRARY_PATH':':'.join(plan['runtime']['LD_LIBRARY_PATH']),'MPICH_INTERFACE_HOSTNAME':'127.0.0.1','OMP_NUM_THREADS':'2','OMP_STACKSIZE':'512M','OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1','OPENBLAS_NUM_THREADS':'1','WRF_RRTMGP_BATCH_SIZE':'32'})
 status='PASS_GUARD_PAIR_EXACT'
 for arm in ARMS:
  try:
   if not run_arm(arm,plan,env,receipt):status='FAIL_PRESERVED';break
  except BaseException as exc:
   receipt['arms'].setdefault(arm,{})['status']='FAIL_PRESERVED';receipt['arms'][arm]['error']=repr(exc);status='FAIL_PRESERVED';atomic(RECEIPT,receipt);break
 try:
  pins_after=check_stage(plan,manifest,reject_outputs=False)
  receipt['post_execution_pins']=pins_after
  if pins_after!=pins_before:raise RuntimeError('static inputs, source, runtime, build evidence, or pins changed during both runs')
  if sha(AUTH)!=receipt['authorization_sha256']:raise RuntimeError('root authorization bytes changed during execution')
 except BaseException as exc:
  receipt['status']='FAIL_PRESERVED';receipt['post_execution_pin_error']=repr(exc);receipt['ended_utc']=stamp();atomic(RECEIPT,receipt)
  print(json.dumps({'status':'FAIL_PRESERVED','reason':repr(exc),'receipt':str(RECEIPT)},indent=2));return 1
 try:
  if all(receipt['arms'].get(a,{}).get('status')=='PASS_OUTPUTS_VALID' for a in ARMS):
   for ts in TIMES:
    name=f'wrfout_d01_{ts}'
    receipt['comparisons'][name]=file_compare(Path(plan['arms']['pr65']['directory'])/name,Path(plan['arms']['pr68']['directory'])/name)
   rst=plan['restart']['expected_checkpoint']
   receipt['comparisons'][rst]=file_compare(Path(plan['arms']['pr65']['directory'])/rst,Path(plan['arms']['pr68']['directory'])/rst)
   for key,result in receipt['comparisons'].items():
    if result['status']!='PASS_EXACT_DATA':status='FAIL_NUMERIC_OR_SCHEMA_DIFFERENCE'
   parent=Path(plan['parent_context']['continuous_history']['path'])
   for arm in ARMS:
    receipt.setdefault('continuous_parent_context',{})[arm]=compare_parent_record(parent,Path(plan['arms'][arm]['directory'])/'wrfout_d01_2016-10-07_13:00:00',37)
 except BaseException as exc:
  status='FAIL_PRESERVED'
  receipt['comparison_error']=repr(exc)
 receipt['status']=status;receipt['ended_utc']=stamp();receipt['model_invocations']=sum(x.get('model_invocations',0) for x in receipt['arms'].values());atomic(RECEIPT,receipt)
 print(json.dumps({'status':status,'model_invocations':receipt['model_invocations'],'receipt':str(RECEIPT)},indent=2))
 return 0 if status=='PASS_GUARD_PAIR_EXACT' else 1
if __name__=='__main__':
 try:raise SystemExit(main())
 except BaseException as exc:
  if isinstance(exc,SystemExit):raise
  print(f'PREPARATION_ERROR: {exc}',file=sys.stderr);raise SystemExit(2)
