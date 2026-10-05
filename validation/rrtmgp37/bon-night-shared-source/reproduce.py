#!/usr/bin/env python3
"""Optional reproducibility check for the archived shared-source analysis."""
from __future__ import annotations
import argparse,hashlib,json,math,os,shutil,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
from verify import verify, PIN_PATHS, DECOMPRESSED

def sha(data): return hashlib.sha256(data).hexdigest()
def compare(a,b,path=''):
 errors=[]
 if isinstance(a,bool) or isinstance(b,bool):
  if type(a) is not type(b) or a!=b: errors.append(path+': boolean/type mismatch')
 elif isinstance(a,int) or isinstance(b,int):
  if type(a) is not type(b) or a!=b: errors.append(path+': integer/type mismatch')
 elif isinstance(a,float) and isinstance(b,float):
  if not math.isfinite(a) or not math.isfinite(b) or abs(a-b)>1e-9: errors.append(path+': float mismatch')
 elif isinstance(a,dict) and isinstance(b,dict):
  if set(a)!=set(b): return [path+': object keys differ']
  for k in a: errors.extend(compare(a[k],b[k],path+'/'+k))
 elif isinstance(a,list) and isinstance(b,list):
  if len(a)!=len(b): return [path+': list lengths differ']
  for i,(x,y) in enumerate(zip(a,b)): errors.extend(compare(x,y,path+f'/{i}'))
 elif type(a) is not type(b) or a!=b: errors.append(path+': value/type mismatch')
 return errors

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',action='store_true');ap.add_argument('--output-dir',type=Path);ap.add_argument('--source-root',type=Path)
 a=ap.parse_args();pkg=Path(__file__).resolve().parent;repo=a.source_root.resolve() if a.source_root else pkg.parents[2]
 verify(pkg,repo)
 if not a.run:
  if a.output_dir: ap.error('--output-dir requires --run')
  print(json.dumps({'status':'PASS_PACKAGE_PREFLIGHT','analysis_run':False}));return 0
 if a.output_dir is None: ap.error('--run requires --output-dir')
 out=a.output_dir.absolute()
 if out.exists(): raise FileExistsError('refusing to reuse output directory')
 out.mkdir(parents=True,exist_ok=False); stage=out/'stage';stage.mkdir()
 original_planb=(pkg/'analysis/plan.json').read_bytes();original=json.loads(original_planb);derived=json.loads(original_planb)
 before={};proc=None;stdout=stderr=None;launch=None;start=None
 try:
  shutil.copyfile(pkg/'analysis/analyze.py',stage/'analyze.py')
  for key,pin in derived['pins'].items():
   if key in {'legacy_source','GP_kernel'}:
    rel='WRF/phys/module_ra_rrtmg_lw.F' if key=='legacy_source' else 'WRF/external/rte_rrtmgp/rrtmgp-kernels/mo_gas_optics_rrtmgp_kernels.F90'
    source=repo/rel;data=source.read_bytes()
   else:
    archive=pkg/PIN_PATHS[key];stored=archive.read_bytes();data=stored
    if key in DECOMPRESSED: data=__import__('gzip').decompress(stored)
    source=None
   if (len(data),sha(data))!=(pin['bytes'],pin['sha256']): raise ValueError('staged source/input pin mismatch: '+key)
   before[key]={'sha256':sha(data),'size_bytes':len(data)}
   target=stage/'pins'/key/(Path(pin['path']).name or key);target.parent.mkdir(parents=True,exist_ok=True)
   if source is None:
    with target.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
   else: target.symlink_to(source.resolve())
   pin['path']=str(target.absolute())
  derived_planb=(json.dumps(derived,indent=2,sort_keys=True)+'\n').encode()
  with (stage/'plan.json').open('xb') as f:f.write(derived_planb);f.flush();os.fsync(f.fileno())
  expected=json.loads((pkg/'analysis/result.json').read_text())
  launch={'status':'LAUNCHED','pid':None,'started_epoch':time.time(),'original_plan_sha256':sha(original_planb),'derived_plan_sha256':sha(derived_planb),'script_sha256':sha((stage/'analyze.py').read_bytes()),'python':sys.executable,'new_WRF_forecasts':0,'new_builds':0,'new_compiled_RTE_or_replays':0,'new_SI_integrations':0}
  with (out/'launch.json').open('x') as f: json.dump(launch,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  start=launch['started_epoch']
  proc=subprocess.Popen([sys.executable,'-B',str(stage/'analyze.py')],cwd=stage,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  launch['pid']=proc.pid
  # Persist PID immediately in the existing fresh launch record.
  (out/'launch.json').write_text(json.dumps(launch,indent=2,sort_keys=True)+'\n')
  try: stdout,stderr=proc.communicate(timeout=30)
  except subprocess.TimeoutExpired:
   proc.terminate()
   try: stdout,stderr=proc.communicate(timeout=10)
   except subprocess.TimeoutExpired: proc.kill();stdout,stderr=proc.communicate()
  (out/'stdout.log').write_text(stdout or '',encoding='utf-8');(out/'stderr.log').write_text(stderr or '',encoding='utf-8')
  generated=stage/'result.json';errors=[];compared=False
  if proc.returncode==0 and generated.is_file():
   actual=json.loads(generated.read_text())
   if actual.get('plan_sha256')!=sha(derived_planb) or actual.get('script_sha256')!=sha((stage/'analyze.py').read_bytes()) or actual.get('pins')!=derived['pins']:
    errors.append('generated result does not attest derived plan/script/pins')
   else:
    for key,pin in original['pins'].items():
     if (actual['pins'][key].get('sha256'),actual['pins'][key].get('bytes'))!=(pin['sha256'],pin['bytes']):errors.append('staged pin changed '+key)
    if not errors:
     # Only path-derived metadata is canonicalized; all numeric and other fields remain untouched.
     actual['plan_sha256']=sha(original_planb)
     for key,pin in original['pins'].items():actual['pins'][key]['path']=pin['path']
     errors.extend(compare(expected,actual));compared=True
   shutil.copyfile(generated,out/'result.json')
  else: errors.append('analysis exited without an attested result file')
  after={}
  for key in before:
   if key in {'legacy_source','GP_kernel'}:
    rel='WRF/phys/module_ra_rrtmg_lw.F' if key=='legacy_source' else 'WRF/external/rte_rrtmgp/rrtmgp-kernels/mo_gas_optics_rrtmgp_kernels.F90';data=(repo/rel).read_bytes()
   else:data=(stage/'pins'/key/Path(original['pins'][key]['path']).name).read_bytes()
   after[key]={'sha256':sha(data),'size_bytes':len(data)}
  unchanged=before==after
  status='PASS_REPRODUCED_SHARED_SOURCE' if proc.returncode==0 and generated.is_file() and compared and not errors and unchanged else 'FAIL_PRESERVED'
  rec={'status':status,'pid':proc.pid,'returncode':proc.returncode,'started_epoch':start,'ended_epoch':time.time(),'original_plan_sha256':sha(original_planb),'derived_plan_sha256':sha(derived_planb),'script_sha256':sha((stage/'analyze.py').read_bytes()),'generated_result_sha256':sha(generated.read_bytes()) if generated.is_file() else None,'comparison':{'performed':compared,'absolute_float_tolerance':1e-9,'integer_boolean':'exact','error_count':len(errors),'first_errors':errors[:20]},'source_and_input_pins_pre':before,'source_and_input_pins_post':after,'pins_unchanged':unchanged,'scope':'One optional Python-only angular calculation; no RTE, compiled replay, build, SI integration, WRF or forecast executable.'}
  with (out/'execution-receipt.json').open('x') as f:json.dump(rec,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
  print(json.dumps(rec,sort_keys=True));return 0 if status.startswith('PASS') else 1
 except Exception as exc:
  if proc is not None:
   if proc.poll() is None:
    proc.terminate()
    try: stdout,stderr=proc.communicate(timeout=10)
    except subprocess.TimeoutExpired: proc.kill();stdout,stderr=proc.communicate()
   elif stdout is None or stderr is None: stdout,stderr=proc.communicate()
   for name,value in [('stdout.log',stdout),('stderr.log',stderr)]:
    if value is not None and not (out/name).exists():(out/name).write_text(value,encoding='utf-8')
  if not (out/'execution-receipt.json').exists():
   rec={'status':'FAIL_PRESERVED','error':f'{type(exc).__name__}: {exc}','pid':proc.pid if proc else None,'returncode':proc.poll() if proc else None,'started_epoch':start,'scope':'Optional reproduction failed; no automatic retry; child process terminated/reaped if launched.'}
   with (out/'execution-receipt.json').open('x') as f:json.dump(rec,f,indent=2,sort_keys=True);f.write('\n')
  raise
if __name__=='__main__':raise SystemExit(main())
