#!/usr/bin/env python3
"""One private reference-only compile/link; no WRF/REAL/coefficient changes."""
import importlib.util,json,os,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def main():
 p=json.loads((HERE/'build-plan-v2.json').read_text());reuse=load('transport_build_reuse',p['reuse_runner']['path']);auth=json.loads((HERE/'root-build-authorization-v2.json').read_text())
 assert auth['runner_sha256']==reuse.pin(__file__)['sha256'] and auth['plan_sha256']==reuse.pin(HERE/'build-plan-v2.json')['sha256'] and auth['maximum_compiler_calls']==1
 for n in ['source','source_adaptation','retained_link_dependencies','inventory','reuse_runner','baseline_execution']:reuse.check(p[n])
 inv=json.loads(Path(p['inventory']['path']).read_text());base=json.loads(Path(p['baseline_execution']['path']).read_text());env=base['environment'];before=reuse.snapshot(inv,env)
 link=json.loads(Path(p['retained_link_dependencies']['path']).read_text());link_roster=[dict(path=x['path'],sha256=x['sha256'],size_bytes=x['bytes']) for x in link['assets']];extra_before=[reuse.check(x) for x in link_roster]+[reuse.check(p['source']),reuse.check(p['source_adaptation'])]
 out=HERE/'build-v2';out.mkdir();fd=os.open(str(out/'ONE_USE'),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
 rec={'schema':'bon-night-n2-private-build-v1','status':'RUNNING','actual_compiler_calls':0,'WRF_REAL_solver_calls':0,'before':before,'extra_before':extra_before,'argv':p['argv'],'environment':env,'plan':reuse.pin(HERE/'build-plan-v2.json'),'runner':reuse.pin(__file__),'authorization':reuse.pin(HERE/'root-build-authorization-v2.json'),'started_unix':time.time()};dest=out/'build-receipt.json';reuse.write(dest,rec)
 try:
  with (out/'build.log').open('xb') as f:
   q=subprocess.Popen(p['argv'],cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT);rec['actual_compiler_calls']=1;rec['pid']=q.pid;reuse.write(dest,rec)
   try:rec['returncode']=q.wait(timeout=180);rec['timed_out']=False
   except subprocess.TimeoutExpired:q.kill();rec['returncode']=q.wait();rec['timed_out']=True
  rec['log']=reuse.pin(out/'build.log');reuse.write(dest,rec);assert rec['returncode']==0 and not rec['timed_out']
  rec['executable']=reuse.pin(out/'reference_transport');ld=subprocess.run(['/usr/bin/ldd',rec['executable']['path']],cwd=out,env=env,text=True,capture_output=True,check=True);assert 'not found' not in ld.stdout;rec['ldd_stdout']=ld.stdout
  rec['after']=reuse.snapshot(inv,env);rec['extra_after']=[reuse.check(x) for x in link_roster]+[reuse.check(p['source']),reuse.check(p['source_adaptation'])]
  assert rec['before']==rec['after'] and rec['extra_before']==rec['extra_after'];rec['status']='PASS_PRIVATE_REFERENCE_COMPILE_LINK'
 except Exception as exc:rec['status']='FAIL_STOPPED_NO_RETRY';rec['error']=str(exc);raise
 finally:rec['ended_unix']=time.time();reuse.write(dest,rec);print(json.dumps({'status':rec['status'],'actual_compiler_calls':rec['actual_compiler_calls'],'receipt':reuse.pin(dest)}))
if __name__=='__main__':main()
