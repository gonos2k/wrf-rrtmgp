#!/usr/bin/env python3
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
BASE=ROOT/'build/udm37-bon-night-normal-positive-n2-math-v1'
PLAN=ROOT/'build/udm37-bon-night-normal-positive-n2-plan-v3/plan.json'
RUNNER=BASE/'run_point_once_v3.py'
REVIEW=ROOT/'build/udm37-normal-positive-n2-plan-runner-review-v1/review-v3.json'
EXPECT={'plan':'5e1aec7a79b1f986757cb921840928638ef37d7c78dc4f79075aa6f33c73741f','runner':'f2a35019da1aac904bd1159e8238c6111313fcf92e6b36b73fe3d8d3460e8ac8','review':'f6af007d95e551c3639261c282397bce2547108911d755eaa3c389df4b36e282'}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def pin(p):return {'path':str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),'sha256':sha(p),'size_bytes':p.stat().st_size}
def once(p,obj):
 with p.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def walk(x):
 if isinstance(x,dict):
  if {'path','sha256','size_bytes'}<=x.keys():yield x
  for v in x.values():yield from walk(v)
 elif isinstance(x,list):
  for v in x:yield from walk(v)
def resolve(rec):
 p=Path(rec['path']);return p if p.is_absolute() else ROOT/p
for name,p in [('plan',PLAN),('runner',RUNNER),('review',REVIEW)]:
 assert sha(p)==EXPECT[name],(name,'changed')
review=json.loads(REVIEW.read_text());assert review['status']=='PASS_SCOPED_PLAN_AND_RUNNER_REVIEW' and review['blockers']==[]
assert review['reviewed_plan']['sha256']==EXPECT['plan'] and review['reviewed_runner']['sha256']==EXPECT['runner']
plan=json.loads(PLAN.read_text());records=list(walk(plan));assert len(records)==108
for rec in records:
 p=resolve(rec).resolve(strict=True);assert p.is_file() and sha(p)==rec['sha256'] and p.stat().st_size==rec['size_bytes'],rec['path']
OUT=ROOT/plan['output_policy']['output_dir'];assert not OUT.exists()
AUTH=BASE/'root-authorization.json';assert not AUTH.exists()
EXEC=BASE/'execution-v1';EXEC.mkdir(exist_ok=False)
auth={'schema':plan['authorization']['required_fields']['schema'],'authorized':True,'plan_sha256':EXPECT['plan'],'runner_sha256':EXPECT['runner'],'point_source_sha256':plan['pinned_artifacts']['point_source']['sha256'],'source_review_sha256':plan['pinned_artifacts']['normal_positive_n2_source_review']['sha256'],'precondition_receipt_sha256':plan['pinned_artifacts']['input_precondition_pass']['sha256'],'max_point_invocations':1,'plan_runner_review':pin(REVIEW),'artifact_pin_count':len(records),'scope':'One diagnostic source-order Python reconstruction; no WRF, REAL, RTE, compiler or physical accuracy verdict. Root authorization under standing user autonomous-work instruction.'}
once(AUTH,auth)
cmd=['/usr/bin/python3.12','-B',str(RUNNER),'--execute','--root',str(ROOT),'--plan',str(PLAN),'--authorization',str(AUTH),'--output',str(OUT)]
inv={'schema':'udm37-positive-n2-root-invocation-v1','argv':cmd,'cwd':str(ROOT),'plan':pin(PLAN),'runner':pin(RUNNER),'authorization':pin(AUTH),'plan_runner_review':pin(REVIEW),'verified_plan_pin_records':len(records),'started_unix':time.time(),'parent_source':pin(Path(__file__)),'new_WRF_invocations':0,'new_REAL_invocations':0,'new_RTE_invocations':0,'new_compile_invocations':0,'allowed_point_invocations':1}
once(EXEC/'invocation.json',inv)
with (EXEC/'stdout.log').open('xb') as stdout,(EXEC/'stderr.log').open('xb') as stderr:
 proc=subprocess.run(cmd,cwd=ROOT,stdout=stdout,stderr=stderr)
 stdout.flush();os.fsync(stdout.fileno());stderr.flush();os.fsync(stderr.fileno())
# Parent OS return code is durable before reading any child numerical artifact.
once(EXEC/'process-return-code.json',{'actual_return_code':proc.returncode,'completed_unix':time.time(),'numerical_output_read_by_parent':False})
rec={'schema':'udm37-positive-n2-root-execution-v1','actual_return_code':proc.returncode,'invocation':pin(EXEC/'invocation.json'),'return_code_receipt':pin(EXEC/'process-return-code.json'),'stdout':pin(EXEC/'stdout.log'),'stderr':pin(EXEC/'stderr.log'),'authorization':pin(AUTH),'output_dir':str(OUT.relative_to(ROOT)),'new_point_invocations_authorized':1,'new_model_RTE_compile_invocations':0,'numerical_output_read_by_parent':False}
once(EXEC/'execution.json',rec)
print(json.dumps({'actual_return_code':proc.returncode,'execution_receipt':pin(EXEC/'execution.json'),'numerical_output_read_by_parent':False}))
sys.exit(proc.returncode)
