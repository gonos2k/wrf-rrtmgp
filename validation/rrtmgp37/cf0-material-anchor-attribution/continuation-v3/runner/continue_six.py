#!/usr/bin/env python3
"""No-retry continuation for only six unlaunched CF0 material-anchor calls."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, sys, time
from pathlib import Path
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=ROOT/'build/udm37-cf0-material-anchor-continuation-v3'; PLAN=HERE/'plan.json'; PF=HERE/'preflight-v3.json'
RUN=HERE/'run-v3'; OUT=RUN/'outputs'; LOG=RUN/'logs'; AUTH_SCHEMA='cf0-material-anchor-six-call-continuation-authorization-v3'
BASE_DIR=ROOT/'build/udm37-cf0-material-anchor-runtime-v1'; BASE_RUN=BASE_DIR/'run-v1'; BASE_EXEC=BASE_RUN/'execution.json'
BASE_RUNNER=BASE_DIR/'run_material_anchor.py'; CURRENT_READER=ROOT/'build/cf0-cu-src-v1/WRF/test/rrtmgp/compare_column_replay.py'
HIST_COMPARATOR=ROOT/'build/udm37-phase-diagnostic-contract-pr-work/WRF/test/rrtmgp/compare_column_replay.py'

def hfile(p):
 h=hashlib.sha256(); n=0
 with Path(p).open('rb') as f:
  while b:=f.read(1<<20): h.update(b); n+=len(b)
 return h.hexdigest(),n
def pin(p):
 p=Path(p); h,n=hfile(p); return {'path':str(p.resolve()),'sha256':h,'size_bytes':n}
def require(r,label):
 p=Path(r['path'])
 if not p.is_file() or hfile(p)!=(r['sha256'],r['size_bytes']): raise RuntimeError(f'pin mismatch {label}: {p}')
def atomic(p,obj):
 if isinstance(obj,dict) and 'solver_invocations' in obj:
  obj['new_solver_invocations']=obj['solver_invocations']
  obj['total_completed_or_reused_calls']=2+sum(x.get('status')=='CALL_VALIDATED' for x in obj.get('calls',[]))
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+'.tmp')
 with t.open('w') as f: json.dump(obj,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
 os.replace(t,p); fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def load_base():
 spec=importlib.util.spec_from_file_location('frozen_material_anchor_core',BASE_RUNNER)
 m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
 m.READER=CURRENT_READER; m.RUN=RUN; m.OUT=OUT; m.LOG=LOG
 hist=m.import_module(HIST_COMPARATOR,'material_anchor_historical_comparator')
 def historical_compare(case,fresh):
  captured=m.read_result(case['result_context']['path'])
  report=hist.compare(captured,fresh)
  if not report.get('passed'): raise ValueError(f'historical comparator failed: {report.get("failed_sections")}')
  return report
 m.run_comparator=historical_compare
 # Use this same synchronizing writer for both the imported launcher and the
 # continuation's validation writes, so every durable receipt is consistent.
 m.atomic=atomic
 return m

def plan(): return json.loads(PLAN.read_text())
def snapshot(m):
 p=plan(); fixed=p['fixed_pins']
 for k,v in fixed.items(): require(v,k)
 # Preserve the source attempt and outputs; this receipt remains FAILED_STOPPED by design.
 old=json.loads(BASE_EXEC.read_text())
 if old.get('status')!='FAILED_STOPPED' or old.get('solver_invocations')!=2: raise RuntimeError('original v1 failed attempt changed or unexpected')
 tr=json.loads((BASE_DIR/'root-tool-terminal-receipt-v1.json').read_text())
 if tr.get('actual_exec_tool_exit_code')!=1 or tr.get('actual_reference_executable_calls')!=2: raise RuntimeError('original terminal tool receipt does not document the two-call parser failure')
 attest=json.loads(Path(fixed['reuse_attestation']['path']).read_text())
 if attest.get('status')!='PASS_OFFLINE_REVALIDATED_NO_SOLVER' or attest.get('solver_invocations')!=0: raise RuntimeError('first-two reuse attestation is not passing')
 prior=[]
 for row in attest['calls']:
  require(row['result'],row['call_id']+' reused output'); require(row['log'],row['call_id']+' reused log'); prior.extend([pin(row['result']['path']),pin(row['log']['path'])])
 if prior!=p['reused_first_two_files']: raise RuntimeError('reused first-two output/log hashes changed')
 core=m.immutable_snapshot()
 return {'core_snapshot':core,'continuation_runner':pin(Path(__file__)),'continuation_plan':pin(PLAN),'reuse_attestation':pin(fixed['reuse_attestation']['path']),
         'current_reader':pin(CURRENT_READER),'historical_comparator':pin(HIST_COMPARATOR),'failed_v1_execution':pin(BASE_EXEC),
         'root_terminal_receipt':pin(BASE_DIR/'root-tool-terminal-receipt-v1.json'),'reused_first_two_files':prior,
         'build_executable':core['executable'],'build_receipt':core['build_receipt'],'runtime_libraries':core['runtime_libraries']}

def validate_resume(m):
 p=plan(); oldp=json.loads((BASE_DIR/'plan.json').read_text()); old=json.loads(BASE_EXEC.read_text())
 if p['case_order']!=[c['call_id'] for c in oldp['cases'][2:]]: raise RuntimeError('continuation order includes skipped calls or is incorrect')
 # Independently re-run result parsing and validation; never relaunch the completed calls.
 baseline=oldp['cases'][0]; incr=oldp['cases'][1]
 if [x['status'] for x in old['calls'][:2]]!=['CALL_VALIDATED','CHILD_RC_DURABLE'] or [x.get('returncode') for x in old['calls'][:2]]!=[0,0]: raise RuntimeError('first two prior child statuses/return codes mismatch')
 r0=m.read_result(baseline['output']); r1=m.read_result(incr['output']);m.finite_result(r0);m.finite_result(r1)
 bcheck=m.baseline_validate(baseline,r0)
 pcheck=m.positive_validate(incr,r1,r0)
 # Verify exact v1 outputs/logs remain those in the additive posthoc attestation.
 att=json.loads((HERE/'reuse-attestation.json').read_text())
 for i,c in enumerate((baseline,incr)):
  ar=att['calls'][i]
  if pin(c['output'])!=ar['result'] or pin(c['log'])!=ar['log']: raise RuntimeError('first two outputs changed since offline attestation')
 return {'baseline':bcheck,'increment':pcheck,'result_section_counts':[len(r0['sections']),len(r1['sections'])],
         'outputs':[pin(baseline['output']),pin(incr['output'])],'logs':[pin(baseline['log']),pin(incr['log'])],
         'prior_attempt_status_preserved':old['status']}

def prepare(m):
 p=plan(); snap=snapshot(m); reused=validate_resume(m)
 old_roster=json.loads((ROOT/'build/udm37-cf0-material-anchor-inputs-v1/roster.json').read_text())
 source={x['call_id']:x for x in old_roster['planned_calls']}
 for c in p['cases']:
  src=source[c['call_id']]
  for key,rkey in [('input','input_pin'),('raw','raw_pin'),('result_context','result_context_pin')]:
   require(c[key],c['call_id']+'.'+key)
   if c[key]['sha256']!=src[rkey]['sha256']: raise RuntimeError('continuation input differs from frozen roster')
  if c['sidecar']: require(c['sidecar'],c['call_id']+'.sidecar')
  if os.path.lexists(c['output']) or os.path.lexists(c['log']): raise RuntimeError('continuation output already exists')
  argv=[str(m.EXE),str(m.DATA.resolve()),c['input']['path'],c['output'],'1','']+([c['sidecar']['path']] if c['sidecar'] else [])
  if argv!=c['argv']: raise RuntimeError('derived continuation argv mismatch')
  ctx=m.validate_sidecar(c)
  c['_sidecar_context']=ctx
 if os.path.lexists(RUN): raise RuntimeError('continuation execution root collision')
 return {'schema':'cf0-material-anchor-continuation-preflight-v1','status':'PREFLIGHT_PASS_NO_SOLVER','new_solver_invocations':0,
         'snapshot':snap,'reused_first_two_validation':reused,'six_cases':[{'call_id':c['call_id'],'argv':c['argv'],'sidecar_context':c.get('_sidecar_context')} for c in p['cases']]}
def write_preflight(m):
 if PF.exists(): raise RuntimeError('preflight collision; preserving existing receipt')
 o=prepare(m);o.update({'runner_sha256':hfile(__file__)[0],'plan_sha256':hfile(PLAN)[0],'generated_unix':time.time()});atomic(PF,o);return o

def check_auth(path):
 p=plan(); a=json.loads(Path(path).read_text());pf=json.loads(PF.read_text()); runner=hfile(__file__)[0]
 expected={'schema':AUTH_SCHEMA,'approved':True,'runner_sha256':runner,'plan_sha256':hfile(PLAN)[0],'preflight_sha256':hfile(PF)[0],
           'failed_v1_execution_sha256':p['fixed_pins']['failed_execution']['sha256'],'reuse_attestation_sha256':p['fixed_pins']['reuse_attestation']['sha256'],
           'roster_sha256':p['fixed_pins']['roster']['sha256'],'build_receipt_sha256':p['fixed_pins']['build_receipt']['sha256'],
           'executable_sha256':p['executable_sha256'],'case_order':p['case_order'],'max_new_solver_invocations':6,'reused_completed_invocations':2}
 if any(a.get(k)!=v for k,v in expected.items()): raise RuntimeError('continuation authorization mismatch')
 if pf.get('status')!='PREFLIGHT_PASS_NO_SOLVER' or pf.get('new_solver_invocations')!=0: raise RuntimeError('continuation preflight missing/stale')
 return pin(path)

def execute(authpath):
 m=load_base(); snap=snapshot(m); reuse=validate_resume(m); ap=check_auth(authpath)
 pfpin=pin(PF); authpin=ap
 if prepare(m)['snapshot']!=snap: raise RuntimeError('preflight/base snapshot changed')
 if os.path.lexists(RUN): raise RuntimeError('one-use continuation root already exists')
 lock=HERE/'execution.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,json.dumps({'authorization':ap,'claimed_unix':time.time()}).encode()+b'\n');os.fsync(fd);os.close(fd)
 d=os.open(HERE,os.O_RDONLY|os.O_DIRECTORY);os.fsync(d);os.close(d)
 RUN.mkdir();OUT.mkdir();LOG.mkdir()
 p=plan(); state={'schema':'cf0-material-anchor-six-call-continuation-execution-v3','status':'RUNNING','runner_sha256':hfile(__file__)[0],
  'plan_sha256':hfile(PLAN)[0],'authorization':ap,'started_unix':time.time(),'initial_snapshot':snap,'reused_first_two_validation':reuse,
  'solver_invocations':0,'new_solver_invocations':0,'reused_solver_invocations':2,'total_completed_or_reused_calls':2,'model_invocations':0,'calls':[{'call_id':c['call_id'],'status':'NOT_STARTED'} for c in p['cases']]}
 atomic(RUN/'execution.json',state); results={}
 try:
  for pathpin,label in ((authpin,'authorization'),(pfpin,'preflight')): require(pathpin,label)
  if snapshot(m)!=snap or validate_resume(m)!=reuse: raise RuntimeError('pre-call resume/source snapshot changed')
  for i,c in enumerate(p['cases']):
   require(authpin,'continuation authorization'); require(pfpin,'continuation preflight')
   for k in ('input','raw','result_context','historical_reference'): require(c[k],c['call_id']+'.'+k)
   if c['sidecar']: require(c['sidecar'],c['call_id']+'.sidecar')
   ctx=m.validate_sidecar(c); state['calls'][i].update({'status':'PRECALL_VALIDATED','sidecar_context':ctx,'argv':c['argv'],'output':c['output'],'log':c['log']});atomic(RUN/'execution.json',state)
   rc,timed=m.launch(c,c['argv'],state,i)
   if timed or rc!=0: raise RuntimeError(f'{c["call_id"]} failed rc={rc} timeout={timed}; stop with no retry')
   if b'FATAL CALLED' in Path(c['log']).read_bytes(): raise RuntimeError(f'{c["call_id"]} log contains FATAL CALLED')
   r=m.read_result(c['output']);m.finite_result(r)
   if c['mode']=='baseline': checks=m.baseline_validate(c,r)
   else:
    b=results.get(c['baseline_call_id'])
    if b is None: raise RuntimeError('same-executable anchor/phase baseline not available')
    checks=m.positive_validate(c,r,b)
   results[c['call_id']]=r; state['calls'][i].update({'checks':checks,'status':'CALL_VALIDATED'});atomic(RUN/'execution.json',state)
   if snapshot(m)!=snap or validate_resume(m)!=reuse: raise RuntimeError(f'immutable snapshot changed after {c["call_id"]}')
   require(authpin,'authorization');require(pfpin,'preflight')
  for row in state['calls']:
   if row.get('status')!='CALL_VALIDATED' or not row.get('output_pin') or not row.get('log_pin'): raise RuntimeError('incomplete durable call output')
   require(row['output_pin'],row['call_id']+' output');require(row['log_pin'],row['call_id']+' log')
  state['final_snapshot']=snapshot(m)
  if state['final_snapshot']!=snap: raise RuntimeError('final snapshot changed')
  if state['solver_invocations']!=6 or state['new_solver_invocations']!=6 or state['total_completed_or_reused_calls']!=8: raise RuntimeError('final call counters do not account for two reused and six new calls')
  state['status']='ALL_SIX_NEW_CALLS_VALIDATED';state['ended_unix']=time.time()
 except BaseException as e:
  state['status']='FAILED_STOPPED';state['error']=repr(e);state['ended_unix']=time.time()
  try: state['final_snapshot']=snapshot(m);state['final_pins_match_initial']=state['final_snapshot']==snap
  except BaseException as pe: state['postflight_error']=repr(pe);state['final_pins_match_initial']=False
  atomic(RUN/'execution.json',state);raise
 atomic(RUN/'execution.json',state);return state

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--execute',action='store_true');ap.add_argument('--authorization',type=Path);a=ap.parse_args();m=load_base()
 if a.check:
  x=write_preflight(m);print(json.dumps({'status':x['status'],'new_solver_invocations':0,'reused_calls':2,'runner_sha256':x['runner_sha256']}));return 0
 if a.execute:
  if not a.authorization: raise RuntimeError('separate root-issued authorization required')
  r=execute(a.authorization);print(json.dumps({'status':r['status'],'new_solver_invocations':r['new_solver_invocations'],'reused_calls':2,'total_completed_or_reused_calls':r['total_completed_or_reused_calls']}));return 0
 return 2
if __name__=='__main__':
 try: raise SystemExit(main())
 except Exception as e: print('CONTINUATION_ERROR: '+repr(e),file=sys.stderr);raise
