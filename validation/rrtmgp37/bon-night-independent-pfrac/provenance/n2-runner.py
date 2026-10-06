#!/usr/bin/env python3
"""One-use, three-call N2 sensitivity runner. Default is offline --check."""
import argparse, hashlib, importlib.util, json, math, os, re, resource, subprocess, sys, time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
PLAN=HERE/'plan.json'
def pin(path):
 p=Path(path); b=p.read_bytes(); return {'path':str(p.resolve()),'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b)}
def check(p):
 q=pin(p['path']); assert (q['sha256'],q['size_bytes'])==(p['sha256'],p['size_bytes']),p['path']; return q
def write(path,obj):
 path=Path(path); tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w') as f: json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path); d=os.open(path.parent,os.O_RDONLY);os.fsync(d);os.close(d)
def load(name,path):
 sp=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(sp);sys.modules[name]=m;sp.loader.exec_module(m);return m
def equal(a,b): return a.shape==b.shape and np.array_equal(a.view(np.uint64),b.view(np.uint64))
def ldd_paths(exe,env):
 q=subprocess.run(['/usr/bin/ldd',exe],env=env,text=True,capture_output=True,check=True)
 assert 'not found' not in q.stdout
 return sorted({str(Path(x).resolve()) for x in re.findall(r'(?:=>\s*)?(/[^\s()]+)',q.stdout)})
def static_snapshot(p,env):
 listed=[]
 for group in ('runtime_support_pins',):
  obj=p[group]
  for v in obj.values():
   if isinstance(v,list): listed+=v
   elif isinstance(v,dict) and 'path' in v: listed.append(v)
 direct_keys=['build_receipt','source','source_adaptation','prior_angular_source','prior_angular_build_receipt','input','matched_dry_baseline_result','prior_angular_policy1_result','prior_angular_policy1_sidecar','comparison_helper','reuse_runner','inventory','trace_parser','trace_parser_import_index','frozen_table']
 listed.extend(p[k] for k in direct_keys)
 pins=[]; seen=set()
 for item in listed:
  if item['path'] not in seen: pins.append(check(item)); seen.add(item['path'])
 exe=check(p['executable']); assert exe==p['executable']
 expected=set(str(Path(x['path']).resolve()) for x in p['runtime_support_pins']['receipt_runtime_libraries'])
 actual=set(ldd_paths(p['executable']['path'],env)); loader=str(Path('/lib64/ld-linux-x86-64.so.2').resolve())
 assert actual==expected|{loader}, {'extra':sorted(actual-expected-{loader}),'missing':sorted(expected-actual)}
 return {'files':pins,'executable':exe,'ldd_resolved_paths':sorted(actual),'loader':pin(loader)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args()
 p=json.loads(PLAN.read_text()); assert p['status']=='PREPARED_NO_SOLVER_CALLS'
 for k in ['build_receipt','source','source_adaptation','prior_angular_source','prior_angular_build_receipt','input','matched_dry_baseline_result','prior_angular_policy1_result','prior_angular_policy1_sidecar','trace_parser','trace_parser_import_index','comparison_helper','reuse_runner','inventory','frozen_table']:
  check(p[k])
 inv=json.loads(Path(p['inventory']['path']).read_text()); build=json.loads(Path(p['build_receipt']['path']).read_text())
 assert build['status']=='PASS_PRIVATE_REFERENCE_COMPILE_LINK' and build['returncode']==0 and build['WRF_REAL_solver_calls']==0
 assert build['executable']==p['executable'] and build['after']==build['before'] and build['extra_after']==build['extra_before']
 assert len(p['calls'])==3 and p['maximum_solver_calls']==3 and p['retries']==0
 env=dict(p['runtime_environment']); assert env['WRF_RRTMGP_FROZEN_TABLE']==p['frozen_table']['path']
 before=static_snapshot(p,env)
 helper=load('n2_result_reader',p['comparison_helper']['path'])
 reader=load('n2_trace_reader',p['trace_parser']['path'])
 baseline=helper.read_result(Path(p['matched_dry_baseline_result']['path']))
 angular=helper.read_result(Path(p['prior_angular_policy1_result']['path']))
 assert baseline['phase']==angular['phase']=='LW' and baseline['nc']==angular['nc']==1 and baseline['nl']==angular['nl']==45
 assert set(baseline['sections'])==set(angular['sections'])==set(p['expected']['main_result_sections'])
 assert Path(p['matched_dry_baseline_result']['path']).read_bytes()==Path(p['prior_angular_policy1_result']['path']).read_bytes()
 for n in baseline['sections']: assert equal(baseline['sections'][n],angular['sections'][n]),n
 input_meta,input_sections=reader.read_trace(Path(p['input']['path']),'input')
 prior_meta,prior_side=reader.read_trace(Path(p['prior_angular_policy1_sidecar']['path']),'result')
 assert prior_meta['phase']=='LW' and prior_meta['ncol']==1 and prior_meta['nlay']==45
 assert input_meta['phase']=='LW' and input_meta['ncol']==1 and input_meta['nlay']==45
 if not args.execute:
  pf={'schema':'bon-night-n2-preflight-v1','status':'PREFLIGHT_PASS_NO_SOLVER_CALLS','plan':pin(PLAN),'runner':pin(__file__),'source':p['source'],'executable':p['executable'],'build_receipt':p['build_receipt'],'baseline_sections':sorted(baseline['sections']),'baseline_result_bytes_exact_to_prior_policy1':True,'baseline_sidecar_sections':sorted(prior_side),'snapshot':before,'solver_calls':0}
  write(p['preflight_receipt'],pf)
  print(json.dumps({'status':pf['status'],'preflight':pin(p['preflight_receipt']),'source':p['source'],'executable':p['executable'],'baseline_sections':len(baseline['sections']),'snapshot_files':len(before['files'])}))
  return
 auth_path=HERE/'root-execution-authorization.json'; assert auth_path.is_file(), 'root authorization file absent'
 auth=pin(auth_path); a=json.loads(auth_path.read_text())
 assert a['schema']=='bon-night-n2-execution-authorization-v1' and a['approved'] is True
 assert a['plan_sha256']==pin(PLAN)['sha256'] and a['runner_sha256']==pin(__file__)['sha256'] and a['maximum_solver_calls']==3 and a['retries']==0
 out=HERE/'run-v1'; out.mkdir()
 lock=out/'ONE_USE'; fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.fsync(fd);os.close(fd)
 rec={'schema':'bon-night-n2-execution-v1','status':'RUNNING','actual_solver_invocations':0,'WRF_REAL_build_invocations':0,'before':before,'runner':pin(__file__),'plan':pin(PLAN),'authorization':auth,'calls':[],'started_unix':time.time(),'environment':env}
 dest=out/'execution.json';write(dest,rec)
 soft,hard=resource.getrlimit(resource.RLIMIT_STACK); assert hard==resource.RLIM_INFINITY or hard>=512*1024**2
 def setstack():resource.setrlimit(resource.RLIMIT_STACK,(512*1024**2,hard))
 proc=None
 try:
  refsections=baseline['sections']; result0=None; side0=None
  for c in p['calls']:
   result=out/(c['id']+'.result'); log=out/(c['id']+'.log'); side=Path(str(result)+'.lw_transport')
   assert not result.exists() and not log.exists() and not side.exists()
   argv=[p['executable']['path'],inv['data_dir'],p['input']['path'],str(result),'1','','','1']
   if c['n2_argument']!='ABSENT': argv.append(c['n2_argument'])
   assert argv[4:]==c['argv_tail'], (c['id'],argv[4:],c['argv_tail'])
   call={'id':c['id'],'argv':argv,'n2_argument':c['n2_argument'],'started_unix':time.time()};rec['calls'].append(call);write(dest,rec)
   with log.open('xb') as f:
    proc=subprocess.Popen(argv,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,preexec_fn=setstack,start_new_session=True)
    rec['actual_solver_invocations']+=1;call['pid']=proc.pid;write(dest,rec)
    try: call['returncode']=proc.wait(timeout=p['timeout_seconds_each']);call['timed_out']=False
    except subprocess.TimeoutExpired:
     import signal
     os.killpg(proc.pid,signal.SIGTERM)
     try:proc.wait(timeout=5)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
     call['returncode']=proc.returncode;call['timed_out']=True
   call['ended_unix']=time.time();call['log']=pin(log);write(dest,rec)
   assert call['returncode']==0 and not call['timed_out'],call
   call['result']=pin(result);call['sidecar']=pin(side)
   actual=helper.read_result(result);assert actual['phase']=='LW' and actual['nc']==1 and actual['nl']==45
   assert set(actual['sections'])==set(refsections), (c['id'],sorted(set(refsections)-set(actual['sections'])),sorted(set(actual['sections'])-set(refsections)))
   sm,ss=reader.read_trace(side,'result');assert sm['phase']=='LW' and sm['ncol']==1 and sm['nlay']==45
   exp=set(p['expected']['sidecar_sections_absent_n2'] if c['n2_argument']=='ABSENT' else p['expected']['sidecar_sections_with_n2'])
   assert set(ss)==exp, (c['id'],set(ss)^exp)
   side_shapes={'TRANSPORT_POLICY':(1,1,1),'SOURCE_LAYER':(1,45,128),'SOURCE_LEVEL':(1,46,128),'SOURCE_SURFACE':(1,1,128),'BAND_LIMITS_GPOINT':(2,16,1),'BAND_LIMITS_WAVENUMBER':(2,16,1)}
   if c['n2_argument']!='ABSENT': side_shapes['N2_OVERRIDE']=(1,1,1)
   for name,shape in side_shapes.items():
    vals=np.asarray(ss[name]['values'],dtype=np.float64);assert tuple(ss[name]['shape'])==shape and vals.size==math.prod(shape) and np.all(np.isfinite(vals)),name
   assert float(ss['TRANSPORT_POLICY']['values'][0])==1.
   for name in refsections:
    vals=actual['sections'][name]; assert np.all(np.isfinite(vals)),name
   if c['n2_argument']=='ABSENT':
    assert result.read_bytes()==Path(p['matched_dry_baseline_result']['path']).read_bytes()
    assert result.read_bytes()==Path(p['prior_angular_policy1_result']['path']).read_bytes()
    for n in refsections:assert equal(actual['sections'][n],refsections[n]),n
    for n in p['expected']['sidecar_sections_absent_n2']:
     assert np.all(np.isfinite(np.asarray(ss[n]['values'],dtype=np.float64)))
    result0=actual['sections'];side0=ss
    assert set(side0)==set(prior_side)
    for name in side0: assert np.array_equal(np.asarray(side0[name]['values'],dtype=np.float64).view(np.uint64),np.asarray(prior_side[name]['values'],dtype=np.float64).view(np.uint64)),name
    call['baseline_exact_both_references']=True
   elif c['n2_argument']=='0.0':
    assert result.read_bytes()==(out/'n2-absent-baseline.result').read_bytes(),'zero N2 result must be whole-file identical'
    for n in refsections:assert equal(actual['sections'][n],result0[n]),n
    for n in p['expected']['sidecar_sections_absent_n2']:assert np.array_equal(np.asarray(ss[n]['values'],dtype=np.float64).view(np.uint64),np.asarray(side0[n]['values'],dtype=np.float64).view(np.uint64)),n
    assert ss['N2_OVERRIDE']['values']==[0.0]
    call['zero_exact_whole_result_and_all_common_sidecar_arrays']=True
   else:
    assert ss['N2_OVERRIDE']['values']==[0.7808]
    for n in set(refsections)-{'GAS_TAU','GAS_TAU_RAW','TOTAL_TAU','UP','DN','HR','UPC','DNC','HRC'}: assert equal(actual['sections'][n],result0[n]),n
    for n in p['expected']['sidecar_sections_absent_n2']:
     assert np.array_equal(np.asarray(ss[n]['values'],dtype=np.float64).view(np.uint64),np.asarray(side0[n]['values'],dtype=np.float64).view(np.uint64)),n
    gt0=result0['GAS_TAU'];gt=actual['sections']['GAS_TAU']; assert equal(gt,actual['sections']['GAS_TAU_RAW'])
    # Exact allowed support: N2-bearing g-points and only the pressure regime used by the LW kernel.
    play=np.asarray(input_sections['PLAY']['values'],dtype=np.float64).reshape((1,45,1),order='F')
    pressure_ref=9948.431564193395
    changed=np.any(gt.view(np.uint64)!=gt0.view(np.uint64),axis=0)
    allowed=np.zeros((45,128),dtype=bool);allowed[:,0:26]=True;allowed[play[0,:,0]*100.0>pressure_ref,122:124]=True
    assert not np.any(changed & ~allowed), 'N2 changed gas tau outside documented gpoint/pressure support'
    assert np.any(changed), 'positive N2 caused no gas tau change'
    call['positive_scope']={'changed_gas_cells':int(changed.sum()),'allowed_gpoints_1_26_all_layers':True,'gpoints_123_124_lower_only_pressure_ref_Pa':pressure_ref,'held_sections':sorted(set(refsections)-{'GAS_TAU','GAS_TAU_RAW','TOTAL_TAU','UP','DN','HR','UPC','DNC','HRC'}),'held_common_sidecar_sections':sorted(p['expected']['sidecar_sections_absent_n2'])}
    call['metrics']={'surface_down_delta':float(actual['sections']['DN'][0,0,0]-result0['DN'][0,0,0]),'toa_up_delta':float(actual['sections']['UP'][0,-1,0]-result0['UP'][0,-1,0]),'native_heating_max_abs_delta':float(np.max(np.abs(actual['sections']['HR'][0,:32,0]-result0['HR'][0,:32,0]))),'full_heating_max_abs_delta':float(np.max(np.abs(actual['sections']['HR']-result0['HR'])))}
   call['validated']=True;write(dest,rec)
  rec['after']=static_snapshot(p,env);assert rec['before']==rec['after']
  for n in ['build_receipt','source','source_adaptation','input','matched_dry_baseline_result','prior_angular_policy1_result','prior_angular_policy1_sidecar','trace_parser','trace_parser_import_index','comparison_helper','reuse_runner','inventory','frozen_table']:check(p[n])
  rec['status']='PASS_THREE_N2_SENSITIVITY_CALLS'
 except BaseException as exc:
  if proc is not None and proc.poll() is None:
   import signal
   try: os.killpg(proc.pid,signal.SIGTERM); proc.wait(timeout=5)
   except BaseException:
    try: os.killpg(proc.pid,signal.SIGKILL); proc.wait()
    except BaseException: pass
  rec['status']='FAIL_STOPPED_NO_RETRY';rec['error']=repr(exc);raise
 finally:
  rec['ended_unix']=time.time();write(dest,rec);print(json.dumps({'status':rec['status'],'actual_solver_invocations':rec['actual_solver_invocations'],'receipt':pin(dest)}))
if __name__=='__main__':main()
