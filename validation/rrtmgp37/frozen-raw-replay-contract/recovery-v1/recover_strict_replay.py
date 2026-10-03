#!/usr/bin/env python3
"""Replay only two preserved captures; never invokes WRF or sensitivity variants."""
import hashlib,importlib,importlib.util,json,os,resource,shutil,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
OUT=Path(__file__).resolve().parent
ORIGINAL=OUT.parent
PLAN=ROOT/'build/udm-stratified-capture-plan-v3/plan.json'
REVIEWED_PLAN='4f9e642fad9b648f352805ac6f9d71363945df0388c1e0acc608b3740f374279'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def write(p,o):p.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
def main():
 assert sha(PLAN)==REVIEWED_PLAN
 plan=json.loads(PLAN.read_text());validator=Path(plan['replay_validator']['path']);source=validator.parents[3]
 manifest=json.loads(Path(plan['source_manifest']['path']).read_text());entries={e['path']:e for e in manifest['files']}
 dependency_names=['test_column_replay','test_cloud_scm','test_surface_scm','compare_column_replay']
 dependency_pins={}
 for name in dependency_names:
  p=validator.parent/(name+'.py');entry=entries[str(p.relative_to(source))]
  assert entry['kind']=='file' and sha(p)==entry['sha256']
  dependency_pins[name]={'path':str(p),'sha256':entry['sha256']}
 assert sha(validator)==plan['replay_validator']['sha256']
 pins={p['path']:p['sha256'] for p in [plan['source_manifest'],plan['build_receipt'],plan['executable'],plan['configure'],plan['strict_reference'],plan['strict_reference_source'],plan['replay_validator'],plan['state_identity']['checkpoint']]}
 pins.update(plan['external_asset_sha256']);pins.update({p:h['sha256'] for p,h in plan['executor_support_scripts'].items()})
 # Check original receipt and all six exact captures independently of copies.
 original_receipt_sha=sha(ORIGINAL/'receipt.json')
 names=[phase+'.'+ext for phase in ['lw','sw'] for ext in ['raw','input','result']]
 original_captures={n:sha(ORIGINAL/'capture'/n) for n in names}
 pins.update({str(ORIGINAL/'capture'/n):h for n,h in original_captures.items()})
 def verify_pins():
  for p,h in pins.items():assert sha(p)==h,p
  for p in dependency_pins.values():assert sha(p['path'])==p['sha256']
  assert sha(ORIGINAL/'receipt.json')==original_receipt_sha
 verify_pins()
 if (OUT/'capture').exists() or (OUT/'recovery-receipt.json').exists():raise RuntimeError('fresh recovery capture/receipt required')
 (OUT/'capture').mkdir()
 for n,h in original_captures.items():
  shutil.copy2(ORIGINAL/'capture'/n,OUT/'capture'/n);assert sha(OUT/'capture'/n)==h
 rec={'status':'STARTED_REPLAY_ONLY','executed_script_sha256':sha(Path(__file__)),'reviewed_plan_sha256':sha(PLAN),'original_v3_receipt_sha256':original_receipt_sha,'dependency_import_pins':dependency_pins,'original_capture_sha256':original_captures,'copied_capture_sha256':{n:sha(OUT/'capture'/n) for n in names},'no_wrf_or_variants':True,'strict_reference':plan['strict_reference'],'strict_reference_source':plan['strict_reference_source'],'phase_reports':[]}
 write(OUT/'recovery-receipt.json',rec)
 try:
  env={'PATH':'/usr/bin:/bin','LD_LIBRARY_PATH':str(ROOT/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu','OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OPENBLAS_NUM_THREADS':'1','WRF_RRTMGP_FROZEN_TABLE':next(p for p in plan['external_asset_sha256'] if p.endswith('frozen-ice-psd-moments.nc'))}
  os.environ.clear();os.environ.update(env)
  resource.setrlimit(resource.RLIMIT_STACK,(536870912,resource.getrlimit(resource.RLIMIT_STACK)[1]))
  rec['controlled_environment']=env;rec['master_stack_bytes']=resource.getrlimit(resource.RLIMIT_STACK)
  sys.path.insert(0,str(validator.parent))
  imports={}
  for name in dependency_names:
   module=importlib.import_module(name);actual=Path(module.__file__).resolve();expected=Path(dependency_pins[name]['path']).resolve()
   assert actual==expected and sha(actual)==dependency_pins[name]['sha256']
   imports[name]={'loaded_path':str(actual),'sha256':sha(actual)}
  verify_pins();rec['successful_imports_before_reference_calls']=imports
  write(OUT/'dependency-import-receipt.json',imports);write(OUT/'recovery-receipt.json',rec)
  replay=sys.modules['test_column_replay'];replay.DATA_DIR=Path(next(p for p in plan['external_asset_sha256'] if p.endswith('rrtmgp-gas-lw-g128.nc'))).parent
  # Full source verification uses the already pinned execution helper.
  helper_path=ROOT/'build/udm-selected-real-audit/run_selected_column_audit.py'
  spec=importlib.util.spec_from_file_location('audit',helper_path);audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
  task=ROOT/'build/udm-phase-path-statistics-real-wrf';audit.SOURCE_MANIFEST_REL=task.relative_to(ROOT)/'source-manifest.json';audit.BUILD_RECEIPT_REL=task.relative_to(ROOT)/'build-receipt.json'
  rec['source_before']=audit.verify_build_manifest(ROOT,source,Path(plan['executable']['path']))
  for phase in ['LW','SW']:
   report=replay.validate_capture(OUT,phase,27,Path(plan['strict_reference']['path']))
   rec['phase_reports'].append(report);write(OUT/('strict-'+phase.lower()+'.json'),report)
   write(OUT/'recovery-receipt.json',rec)
  rec['source_after']=audit.verify_build_manifest(ROOT,source,Path(plan['executable']['path']));assert rec['source_after']==rec['source_before']
  rec['status']='STRICT_LW_SW_REPLAY_RECOVERY_PASS'
 except Exception as e:rec.update(status='RECOVERY_FAIL_PRESERVED',error=repr(e))
 finally:
  try:
   verify_pins()
   for n,h in original_captures.items():assert sha(OUT/'capture'/n)==h,n
   rec.update(all_pins_and_original_receipt_unchanged=True,copied_capture_sha256_after={n:sha(OUT/'capture'/n) for n in names})
  except Exception as e:rec.update(status='RECOVERY_FAIL_PRESERVED',postflight_error=repr(e))
  rec['output_hashes']={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='recovery-receipt.json'}
  write(OUT/'recovery-receipt.json',rec)
 print(rec['status']);assert rec['status']=='STRICT_LW_SW_REPLAY_RECOVERY_PASS'
if __name__=='__main__':main()
