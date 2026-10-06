#!/usr/bin/env python3
"""Three fixed-input LW transport diagnostics; fail-closed one-use runner."""
import importlib.util,json,os,re,resource,subprocess,sys,time
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def main():
 p=json.loads((HERE/'plan.json').read_text());reuse=load('transport_reuse',p['reuse_runner']['path']);auth=json.loads((HERE/'root-execution-authorization.json').read_text())
 assert auth['runner_sha256']==reuse.pin(__file__)['sha256'] and auth['plan_sha256']==reuse.pin(HERE/'plan.json')['sha256'] and auth['maximum_solver_calls']==3 and auth['retries']==0
 for n in ['reuse_runner','inventory','baseline_execution','baseline_result','input','legacy_export','export_parser','source','source_adaptation','build_receipt','executable','trace_parser','trace_parser_import_index']:reuse.check(p[n])
 inv=json.loads(Path(p['inventory']['path']).read_text());env=json.loads(Path(p['baseline_execution']['path']).read_text())['environment'];before=reuse.snapshot(inv,env)
 build=json.loads(Path(p['build_receipt']['path']).read_text());assert build['status']=='PASS_PRIVATE_REFERENCE_COMPILE_LINK' and build['returncode']==0 and build['executable']==p['executable'] and build['before']==build['after'] and build['extra_before']==build['extra_after']
 ld=subprocess.run(['/usr/bin/ldd',p['executable']['path']],env=env,text=True,capture_output=True,check=True);assert 'not found' not in ld.stdout
 paths=sorted({str(Path(x).resolve()) for x in re.findall(r'(?:=>\s*)?(/[^\s()]+)',ld.stdout)});assert paths==before['ldd_resolved_paths']
 trace=load('transport_trace_parser',p['trace_parser']['path']);helper=load('transport_compare',inv['comparison_helper']['path']);reader=load('transport_export',p['export_parser']['path'])
 baseline=helper.read_result(Path(p['baseline_result']['path']));ex=reader.read_export(Path(p['legacy_export']['path']),expected_phase='LW',expected_context=p['context']);f4=float(ex['fields']['RESULT','DOWN_FLUX'].values[0]);b=baseline['sections'];held=set(b)-helper.FLOAT_OUTPUT_SECTIONS;assert len(held)==18
 out=HERE/'run-v1';out.mkdir();fd=os.open(str(out/'ONE_USE'),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
 rec={'schema':'bon-night-transport-attribution-execution-v1','status':'RUNNING','actual_solver_invocations':0,'WRF_REAL_build_invocations':0,'before':before,'new_executable_ldd_paths':paths,'plan':reuse.pin(HERE/'plan.json'),'runner':reuse.pin(__file__),'authorization':reuse.pin(HERE/'root-execution-authorization.json'),'environment':env,'started_unix':time.time(),'calls':[]};dest=out/'execution.json';reuse.write(dest,rec)
 _,hard=resource.getrlimit(resource.RLIMIT_STACK);assert hard==resource.RLIM_INFINITY or hard>=512*1024**2
 def stack():resource.setrlimit(resource.RLIMIT_STACK,(512*1024**2,hard))
 source_baseline=None;result_baseline=None
 try:
  for mode in [1,2,3]:
   result=out/f'policy{mode}.result';log=out/f'policy{mode}.log';argv=[p['executable']['path'],inv['data_dir'],p['input']['path'],str(result),'1','','',str(mode)]
   call={'policy':mode,'argv':argv,'input':p['input'],'started_unix':time.time()};rec['calls'].append(call);reuse.write(dest,rec)
   with log.open('xb') as f:
    q=subprocess.Popen(argv,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,preexec_fn=stack);rec['actual_solver_invocations']+=1;call['pid']=q.pid;reuse.write(dest,rec)
    try:call['returncode']=q.wait(timeout=180);call['timed_out']=False
    except subprocess.TimeoutExpired:q.kill();call['returncode']=q.wait();call['timed_out']=True
   call['ended_unix']=time.time();call['log']=reuse.pin(log);reuse.write(dest,rec);assert call['returncode']==0 and not call['timed_out']
   call['result']=reuse.pin(result);side=Path(str(result)+'.lw_transport');call['transport_source']=reuse.pin(side)
   actual=helper.read_result(result);srcmeta,srcsections=trace.read_trace(side,'result');src=dict(phase=srcmeta['phase'],nc=srcmeta['ncol'],nl=srcmeta['nlay']);a=actual['sections'];z={n:np.asarray(v['values'],dtype=np.float64).reshape(v['shape'],order='F') for n,v in srcsections.items()};assert (actual['phase'],actual['nc'],actual['nl'])==('LW',1,45) and set(a)==set(b)
   assert (src['phase'],src['nc'],src['nl'])==('LW',1,45) and int(z['TRANSPORT_POLICY'][0,0,0])==mode
   for n in held:assert np.array_equal(a[n].view(np.uint64),b[n].view(np.uint64)),n
   held_sources={'SOURCE_LAYER','SOURCE_LEVEL','SOURCE_SURFACE','BAND_LIMITS_GPOINT','BAND_LIMITS_WAVENUMBER'};assert held_sources<=set(z)
   assert z['SOURCE_LAYER'].shape==(1,45,128) and z['SOURCE_LEVEL'].shape==(1,46,128) and z['SOURCE_SURFACE'].shape==(1,1,128) and z['BAND_LIMITS_GPOINT'].shape==z['BAND_LIMITS_WAVENUMBER'].shape==(2,16,1)
   if mode==1:
    assert result.read_bytes()==Path(p['baseline_result']['path']).read_bytes(),'adapted default exact retained matched-dry baseline bytes'
    for n in a:assert np.array_equal(a[n].view(np.uint64),b[n].view(np.uint64)),n
    result_baseline=a;source_baseline=z;call['all24_baseline_sections_and_result_bytes_exact']=True
   else:
    for n in held_sources:assert np.array_equal(z[n].view(np.uint64),source_baseline[n].view(np.uint64)),n
   if mode==2:assert z['LW_DIFFUSIVITY_ANGLE'].shape==(1,1,1) and z['LW_DIFFUSIVITY_ANGLE'][0,0,0]==1.66
   if mode==3:assert z['GAUSS_ANGLE_COUNT'].shape==(1,1,1) and z['GAUSS_ANGLE_COUNT'][0,0,0]==4.
   f=float(a['DN'][0,0,0]);f0=float(b['DN'][0,0,0]);call['metrics']={'surface_down_W_m2':f,'relative_to_default_W_m2':f-f0,'minus_actual_legacy4_W_m2':f-f4,'TOA_up_W_m2':float(a['UP'][0,-1,0]),'max_native_heating_response_K_day':float(np.max(np.abs(a['HR'][0,:32,0]-b['HR'][0,:32,0]))),'max_full_engine_heating_response_K_day':float(np.max(np.abs(a['HR']-b['HR']))),'held_main_sections':sorted(held),'held_source_sections':sorted(held_sources),'gas_source_and_optical_inputs_exact':True}
   reuse.write(dest,rec)
  rec['after']=reuse.snapshot(inv,env);assert rec['before']==rec['after']
  for n in ['reuse_runner','inventory','baseline_execution','baseline_result','input','legacy_export','export_parser','source','source_adaptation','build_receipt','executable','trace_parser','trace_parser_import_index']:reuse.check(p[n])
  rec['status']='PASS_THREE_FIXED_INPUT_TRANSPORT_POLICIES'
 except Exception as exc:rec['status']='FAIL_STOPPED_NO_RETRY';rec['error']=str(exc);raise
 finally:rec['ended_unix']=time.time();reuse.write(dest,rec);print(json.dumps({'status':rec['status'],'actual_solver_invocations':rec['actual_solver_invocations'],'receipt':reuse.pin(dest)}))
if __name__=='__main__':main()
