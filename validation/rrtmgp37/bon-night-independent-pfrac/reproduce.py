#!/usr/bin/env python3
"""Optionally stage and rerun the archived Python-only pfrac reconstruction."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,os,shutil,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
from verify import verify, PIN_FILES, PRODUCTION_KEYS

def sha(b):return hashlib.sha256(b).hexdigest()
def fsha(p):return sha(Path(p).read_bytes())
def compare(a,b,path='',tol=1e-12):
 e=[]
 if isinstance(a,dict) and isinstance(b,dict):
  if set(a)!=set(b):return [path+': object keys differ']
  for k in a:e+=compare(a[k],b[k],path+'/'+k,tol)
 elif isinstance(a,list) and isinstance(b,list):
  if len(a)!=len(b):return [path+': list lengths differ']
  for i,(x,y) in enumerate(zip(a,b)):e+=compare(x,y,path+f'/{i}',tol)
 elif isinstance(a,bool) or isinstance(b,bool):
  if a!=b:e.append(path+': boolean mismatch')
 elif isinstance(a,(int,float)) and isinstance(b,(int,float)):
  if not math.isfinite(float(a)) or not math.isfinite(float(b)) or abs(float(a)-float(b))>tol:e.append(path+': numerical mismatch')
 elif a!=b:e.append(path+': value mismatch')
 return e

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');ap.add_argument('--output-dir',type=Path);ap.add_argument('--source-root',type=Path)
 a=ap.parse_args();pkg=Path(__file__).resolve().parent;repo=a.source_root.resolve() if a.source_root else pkg.parents[2]
 verify(pkg,repo)
 if not a.run:
  if a.output_dir:ap.error('--output-dir requires --run')
  print(json.dumps({'status':'PASS_PACKAGE_PREFLIGHT','analysis_run':False}));return 0
 if a.output_dir is None:ap.error('--run requires --output-dir')
 out=a.output_dir.absolute()
 if out.exists():raise FileExistsError('refusing to reuse output directory')
 out.mkdir(parents=True,exist_ok=False);stage=out/'stage';stage.mkdir()
 planb=(pkg/'analysis/plan.json').read_bytes();plan=json.loads(planb);before={};proc=None;stdout=None;stderr=None;launch=None
 try:
  shutil.copyfile(pkg/'analysis/plan.json',stage/'plan.json');shutil.copyfile(pkg/'analysis/analyze.py',stage/'analyze.py')
  for key,pin in plan['pins'].items():
   if key in PRODUCTION_KEYS:
    suffix=pin['path'].split('/WRF/',1)[1];source=repo/'WRF'/suffix
    if fsha(source)!=pin['sha256'] or source.stat().st_size!=pin['bytes']:raise ValueError('tracked source pin changed: '+key)
    target=stage/pin['path'];target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(source.resolve())
    before[key]={'sha256':fsha(source),'size_bytes':source.stat().st_size}
   else:
    rel=PIN_FILES[key];archive=pkg/rel
    raw=gzip.decompress(archive.read_bytes()) if key in {'captured_n2_result','captured_n2_sidecar','held_input'} else archive.read_bytes()
    if len(raw)!=pin['bytes'] or sha(raw)!=pin['sha256']:raise ValueError('archived pin changed: '+key)
    target=stage/pin['path'];target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  # The provenance-only replay executable is deliberately not staged or invoked.
  expected=json.loads((pkg/'analysis/result.json').read_text())
  launch={'status':'LAUNCHED','pid':None,'started_epoch':time.time(),'plan_sha256':sha(planb),'script_sha256':fsha(stage/'analyze.py'),
          'python':sys.executable,'RTE_calls':0,'WRF_forecasts':0,'compiled_replays':0}
  proc=subprocess.Popen([sys.executable,'-B',str(stage/'analyze.py')],cwd=stage,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  launch['pid']=proc.pid
  with (out/'launch.json').open('x') as f:json.dump(launch,f,indent=2,sort_keys=True);f.write('\n')
  try:stdout,stderr=proc.communicate(timeout=30)
  except subprocess.TimeoutExpired:
   proc.terminate()
   try:stdout,stderr=proc.communicate(timeout=10)
   except subprocess.TimeoutExpired:proc.kill();stdout,stderr=proc.communicate()
  (out/'stdout.log').write_text(stdout or '',encoding='utf-8');(out/'stderr.log').write_text(stderr or '',encoding='utf-8')
  generated=stage/'result.json';errors=[]
  comparable=proc.returncode==0 and generated.is_file()
  if comparable:
   actual=json.loads(generated.read_text());errors=compare(expected,actual)
   shutil.copyfile(generated,out/'result.json')
  else:
   errors=['analysis returned no result.json']
  after={}
  for key in PRODUCTION_KEYS:
   pin=plan['pins'][key];source=repo/'WRF'/pin['path'].split('/WRF/',1)[1]
   after[key]={'sha256':fsha(source),'size_bytes':source.stat().st_size}
  unchanged=before==after
  status='PASS_REPRODUCED_PFRAC' if comparable and proc.returncode==0 and not errors and unchanged else 'FAIL_PRESERVED'
  rec={'status':status,'pid':proc.pid,'returncode':proc.returncode,'started_epoch':launch['started_epoch'],'ended_epoch':time.time(),
       'plan_sha256':sha(planb),'script_sha256':fsha(stage/'analyze.py'),'result_sha256':fsha(generated) if generated.exists() else None,
       'comparison_tolerance_abs':1e-12,'comparison_performed':comparable,'comparison_error_count':len(errors),'first_errors':errors[:20],
       'tracked_source_pre':before,'tracked_source_post':after,'source_unchanged':unchanged,
       'scope':'One Python reconstruction only; no RTE, compiled replay, WRF or forecast executable.'}
  with (out/'execution-receipt.json').open('x') as f:json.dump(rec,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  print(json.dumps(rec,sort_keys=True));return 0 if status.startswith('PASS') else 1
 except Exception as exc:
  if proc is not None:
   if proc.poll() is None:
    proc.terminate()
    try:stdout,stderr=proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();stdout,stderr=proc.communicate()
   elif stdout is None or stderr is None:stdout,stderr=proc.communicate()
   for name,value in [('stdout.log',stdout),('stderr.log',stderr)]:
    if value is not None and not (out/name).exists():(out/name).write_text(value,encoding='utf-8')
  rec={'status':'FAIL_PRESERVED','error':f'{type(exc).__name__}: {exc}','pid':proc.pid if proc else None,
       'returncode':proc.poll() if proc else None,'started_epoch':launch.get('started_epoch') if launch else None,
       'scope':'No automatic retry; child process terminated/reaped if launched.'}
  if not (out/'execution-receipt.json').exists():
   with (out/'execution-receipt.json').open('x') as f:json.dump(rec,f,indent=2,sort_keys=True);f.write('\n')
  raise
if __name__=='__main__':raise SystemExit(main())
