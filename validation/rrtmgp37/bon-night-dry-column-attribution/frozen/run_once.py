#!/usr/bin/env python3
"""One diagnostic dry-column intervention; immutable baseline and production state."""
import importlib.util,json,os,resource,subprocess,sys,time
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def main():
 plan=json.loads((HERE/'plan.json').read_text());reuse=load('bon_dry_reuse',plan['reuse_runner']['path'])
 auth=json.loads((HERE/'root-execution-authorization.json').read_text())
 assert auth['runner_sha256']==reuse.pin(__file__)['sha256'] and auth['plan_sha256']==reuse.pin(HERE/'plan.json')['sha256'] and auth['maximum_solver_calls']==1
 for n in ['inventory','reuse_runner','baseline_execution','baseline_result','original_input','counterfactual_input','legacy_export','export_parser']:reuse.check(plan[n])
 inv=json.loads(Path(plan['inventory']['path']).read_text());base=json.loads(Path(plan['baseline_execution']['path']).read_text())
 assert base['status']=='PASS_SIX_DIRECT_LIBRARY_REPLAYS' and base['actual_solver_invocations']==6 and base['calls'][0]['result']==plan['baseline_result']
 original=Path(plan['original_input']['path']).read_bytes().splitlines(keepends=True)
 changed=Path(plan['counterfactual_input']['path']).read_bytes().splitlines(keepends=True)
 ix=next(i for i,l in enumerate(original) if l.startswith(b'NATIVE_DRY_LAYER_MASS_KG_M2 '))
 assert original[:ix]==changed[:ix] and original[ix+33:]==changed[ix+46:]
 assert original[ix].split()==[b'NATIVE_DRY_LAYER_MASS_KG_M2',b'1',b'32'] and changed[ix].split()==[b'NATIVE_DRY_LAYER_MASS_KG_M2',b'1',b'45']
 expected=np.array(plan['expected_COLDry_molecule_cm2']);mass=np.array([float(x) for x in changed[ix+1:ix+46]])
 reconstructed=mass*plan['avogad_molecules_mol']/(plan['M_dry_kg_mol']*10000.)
 assert np.isfinite(mass).all() and np.all(mass>0) and np.all(np.abs(reconstructed/expected-1)<=1e-15)
 env=base['environment'];before=reuse.snapshot(inv,env)
 out=HERE/'run-v1';out.mkdir();fd=os.open(str(out/'ONE_USE'),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
 dest=out/'execution.json';result=out/'matched-legacy-dry.result';log=out/'solver.log'
 argv=[inv['executable']['path'],inv['data_dir'],plan['counterfactual_input']['path'],str(result),'1','']
 rec={'schema':'bon-night-dry-column-attribution-execution-v1','status':'RUNNING','actual_solver_invocations':0,'WRF_REAL_build_invocations':0,'plan':reuse.pin(HERE/'plan.json'),'runner':reuse.pin(__file__),'authorization':reuse.pin(HERE/'root-execution-authorization.json'),'before':before,'argv':argv,'started_unix':time.time(),'environment':env}
 reuse.write(dest,rec)
 _,hard=resource.getrlimit(resource.RLIMIT_STACK);assert hard==resource.RLIM_INFINITY or hard>=512*1024**2
 def stack():resource.setrlimit(resource.RLIMIT_STACK,(512*1024**2,hard))
 try:
  with log.open('xb') as f:
   p=subprocess.Popen(argv,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,preexec_fn=stack)
   rec['actual_solver_invocations']=1;rec['pid']=p.pid;reuse.write(dest,rec)
   try:rec['returncode']=p.wait(timeout=180);rec['timed_out']=False
   except subprocess.TimeoutExpired:p.kill();rec['returncode']=p.wait();rec['timed_out']=True
  rec['log']=reuse.pin(log);rec['solver_ended_unix']=time.time();reuse.write(dest,rec)
  assert rec['returncode']==0 and not rec['timed_out']
  rec['result']=reuse.pin(result);helper=load('bon_dry_compare',inv['comparison_helper']['path'])
  native=helper.read_result(Path(plan['baseline_result']['path']));cf=helper.read_result(result)
  a=native['sections'];b=cf['sections'];assert (native['phase'],native['nc'],native['nl'])==('LW',1,45) and set(a)==set(b)
  held=set(a)-helper.FLOAT_OUTPUT_SECTIONS-{'GAS_TAU','GAS_TAU_RAW','GAS_COL_DRY','TOTAL_TAU'}
  assert len(held)==14
  for n in held:assert np.array_equal(a[n],b[n]),n
  col=b['GAS_COL_DRY'].reshape(-1,order='F');assert np.all(np.abs(col/expected-1)<=1e-15)
  reader=load('bon_dry_export',plan['export_parser']['path']);ex=reader.read_export(Path(plan['legacy_export']['path']),expected_phase='LW',expected_context=plan['expected_context'])
  assert list(ex['fields']['INPUT','COLDry'].values)==plan['expected_COLDry_molecule_cm2']
  f_native=float(a['DN'][0,0]);f_cf=float(b['DN'][0,0]);f4=float(ex['fields']['RESULT','DOWN_FLUX'].values[0])
  captured=helper.read_result(Path(inv['cases'][0]['result']['path']))['sections']
  boundary_delta=float(np.float32(captured['WRF_GLW'][0,0,0]))-float(np.float32(f4))
  metrics={'reference_native_dry_surface_W_m2':f_native,'reference_legacy_dry_surface_W_m2':f_cf,'legacy_export_surface_W_m2':f4,
           'native37_minus_legacy4_direct_F64_W_m2':f_native-f4,'dry_construction_native_minus_matched_W_m2':f_native-f_cf,
           'matched37_minus_legacy4_residual_W_m2':f_cf-f4,'legacy_dry_injection_response_W_m2':f_cf-f_native,
           'original_WRF_boundary_REAL32_delta_W_m2':boundary_delta,'held_exact_sections':sorted(held),
           'gas_dry_matching_max_relative':float(np.max(np.abs(col/expected-1))),
           'algebra_residual_W_m2':(f_native-f4)-((f_native-f_cf)+(f_cf-f4)),
           'scope':'Flux sensitivity to same-call molecular dry column. All other input bytes and14cloud/mask/size/frozen optics sections held; same pinned library/data.45-layer mass is diagnostic carrier, not new WRFnative state. Remaining residual is combined spectral/engine/other construction difference, not independent physical truth.'}
  assert abs(metrics['algebra_residual_W_m2'])<=1e-12
  reuse.write(out/'metrics.json',metrics);rec['metrics']=reuse.pin(out/'metrics.json')
  rec['after']=reuse.snapshot(inv,env);assert rec['before']==rec['after']
  for n in ['inventory','reuse_runner','baseline_execution','baseline_result','original_input','counterfactual_input','legacy_export','export_parser']:reuse.check(plan[n])
  rec['status']='PASS_ONE_DRY_COLUMN_INTERVENTION'
 except Exception as exc:rec['status']='FAIL_STOPPED_NO_RETRY';rec['error']=str(exc);raise
 finally:
  rec['ended_unix']=time.time();reuse.write(dest,rec);print(json.dumps({'status':rec['status'],'actual_solver_invocations':rec['actual_solver_invocations'],'receipt':reuse.pin(dest)}))
if __name__=='__main__':main()
