#!/usr/bin/env python3
"""Proposed single-case executor. Default validates pins only; root review required before --execute."""
import argparse, hashlib, importlib.util, json, os, resource, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, chartostring
HERE=Path(__file__).resolve().parent
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
sys.dont_write_bytecode=True
VALIDATOR_ROOT=ROOT/'build/udm-frozen-replay-validator-work/WRF/test/rrtmgp'
REPLAY_PINS={
 'test_column_replay':'823120117dc9f9b47578c8626b4ef40d89ea415cc889f27aa07b1e7fd94e0671',
 'test_cloud_scm':'f58163c6d530851aa9f830a1b7a42b4bd6a4aa16245643ef0b66ae19315d889d',
 'test_surface_scm':'67870eb8ab3e844ab8272ec5c6aeec700b560c0730de3f3205a1304ed0ea85b1',
 'compare_column_replay':'300c25de26330c0ac413c6e3d82434374457b10fbae1da77680d2d9db3601454'}
REMAINING={'cf0_snow_high_cloud_proxy','ice_clip_low_cloud_proxy','ice_clip_high_cloud_proxy','clear_control','unclipped_cloud_control'}
OUTPUT_ROOT=ROOT/'build/udm-stratified-captures-v4'
HISTORY_SHA='7a76a430f1d37ba88ee2692c5cb076a271f3d525a1190b5cd824df3790225025'
REVIEWED_PLAN_SHA256='4f9e642fad9b648f352805ac6f9d71363945df0388c1e0acc608b3740f374279'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def write(p,o):p.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
def verify_support(plan):
 for path,pin in plan['executor_support_scripts'].items():
  assert path==pin['path'] and sha(path)==pin['sha256'],path

def verify_replay_imports():
 import importlib
 for name,pin in REPLAY_PINS.items():assert sha(VALIDATOR_ROOT/(name+'.py'))==pin,name
 sys.path.insert(0,str(VALIDATOR_ROOT))
 modules={}
 for name,pin in REPLAY_PINS.items():
  m=importlib.import_module(name)
  assert Path(m.__file__).resolve()==(VALIDATOR_ROOT/(name+'.py')).resolve()
  assert sha(m.__file__)==pin
  modules[name]=m
 return modules

def inspect_history(path):
 assert sha(path)==HISTORY_SHA,'complete history file differs from pinned audit-OFF baseline'
 with Dataset(path) as n:
  assert [len(n.dimensions[k]) for k in ['west_east','south_north','bottom_top']]==[289,189,39]
  assert [int(n.getncattr(k)) for k in ['MP_PHYSICS','RA_LW_PHYSICS','RA_SW_PHYSICS']]==[27,37,37]
  n.set_auto_maskandscale(True);assert chartostring(n['Times'][:]).tolist()==['2010-06-11_12:01:00']
  numeric=[]
  for k,v in n.variables.items():
   if v.dtype.kind in 'fiu':
    decoded=v[:];assert not np.ma.getmaskarray(decoded).any(),k+':decoded mask'
    assert np.isfinite(np.asarray(decoded)).all(),k+':decoded nonfinite'
    v.set_auto_maskandscale(False);raw=np.asarray(v[:]);assert np.isfinite(raw).all(),k+':raw nonfinite'
    for attr in ['_FillValue','missing_value']:
     if attr in v.ncattrs():
      for sentinel in np.asarray(v.getncattr(attr)).ravel():assert not np.any(raw==sentinel),k+':'+attr
    numeric.append(k)
  return {'history_sha256':sha(path),'numeric_variables':len(numeric),'all_numeric_raw_finite_unmasked':True,'all_numeric_decoded_finite_unmasked':True,'history_geometry':[289,189,39],'history_physics':[27,37,37]}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--case',required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 assert a.case in REMAINING,'only five remaining reviewed points may run'
 assert sha(HERE/'plan.json')==REVIEWED_PLAN_SHA256,'reviewed plan hash mismatch'
 plan=json.loads((HERE/'plan.json').read_text());point=next(x for x in plan['points'] if x['name']==a.case)
 verify_support(plan)
 for key in ['source_manifest','build_receipt','executable','configure','original_namelist','planned_namelist','strict_reference','strict_reference_source','replay_validator']:
  assert sha(plan[key]['path'])==plan[key]['sha256'],key
 checkpoint=Path(plan['state_identity']['checkpoint']['path'])
 checkpoint_sha=plan['state_identity']['checkpoint']['sha256']
 assert checkpoint.is_file() and sha(checkpoint)==checkpoint_sha,'source checkpoint pin mismatch'
 baseline=Path(plan['runtime_template'])
 for name,h in plan['runtime_asset_sha256'].items():assert sha(baseline/name)==h,name
 for p,h in plan['external_asset_sha256'].items():assert sha(p)==h,p
 audit=load('audit',ROOT/'build/udm-selected-real-audit/run_selected_column_audit.py')
 task=ROOT/'build/udm-phase-path-statistics-real-wrf'
 audit.SOURCE_MANIFEST_REL=task.relative_to(ROOT)/'source-manifest.json';audit.BUILD_RECEIPT_REL=task.relative_to(ROOT)/'build-receipt.json'
 verify_support(plan)
 pre_source=audit.verify_build_manifest(ROOT,task/'source',Path(plan['executable']['path']))
 verify_support(plan)
 modules=verify_replay_imports()
 preflight={'status':'PIN_PREFLIGHT_PASS_NO_RUNTIME','case':a.case,'runner_sha256':sha(Path(__file__)),'plan_sha256':sha(HERE/'plan.json'),'explicit_validator_and_unchanged_sibling_pins':REPLAY_PINS,'validator_root':str(VALIDATOR_ROOT),'plan_validator_pin_retained':plan['replay_validator'],'source_before':pre_source,'checkpoint':plan['state_identity']['checkpoint'],'strict_reference':plan['strict_reference'],'strict_reference_source':plan['strict_reference_source'],'executor_support_scripts':plan['executor_support_scripts'],'external_asset_sha256':plan['external_asset_sha256'],'runtime_asset_sha256':plan['runtime_asset_sha256'],'planned_namelist':plan['planned_namelist'],'fixed_output_dir':str(OUTPUT_ROOT/a.case),'whole_history_sha256_required':HISTORY_SHA,'maximum_fresh_wrf_runs':5,'maximum_strict_reference_calls':10,'case_maximum_strict_reference_calls':2,'remaining_cases':sorted(REMAINING),'no_autoextension_or_retry':True}
 preflight=json.loads(json.dumps(preflight)) # Compare canonical JSON values on repeat validation.
 (HERE/'preflight').mkdir(exist_ok=True)
 preflight_path=HERE/'preflight'/(a.case+'.json')
 if preflight_path.exists():assert json.loads(preflight_path.read_text())==preflight,'preflight changed; preserve prior receipt'
 else:write(preflight_path,preflight)
 if not a.execute:
  verify_support(plan)
  print('PLAN_PIN_VALIDATION_PASS; no staging, WRF, or replay launched:',a.case);return
 out=OUTPUT_ROOT/a.case
 if out.exists():raise RuntimeError('fresh fixed case directory required; no retry or overwrite')
 if OUTPUT_ROOT.exists():assert {p.name for p in OUTPUT_ROOT.iterdir()}<=REMAINING
 run=out/'run';capture=out/'capture';run.mkdir(parents=True);capture.mkdir()
 rec={'status':'RUNNING','plan_sha256':sha(HERE/'plan.json'),'runner_sha256':sha(Path(__file__)),'case':point['name'],'i':point['i'],'j':point['j'],'source_before':pre_source,'audit_enabled':False,'explicit_validator_and_unchanged_sibling_pins':REPLAY_PINS,'pin_preflight':preflight,'reference_invocations':[]}
 try:
  for name in plan['runtime_asset_sha256']:shutil.copy2(baseline/name,run/name)
  shutil.copy2(plan['planned_namelist']['path'],run/'namelist.input');shutil.copy2(plan['executable']['path'],run/'wrf.exe')
  assert sha(checkpoint)==checkpoint_sha,'source checkpoint changed before staging'
  staged_checkpoint=run/checkpoint.name
  shutil.copy2(checkpoint,staged_checkpoint)
  assert staged_checkpoint.is_file() and sha(staged_checkpoint)==checkpoint_sha,'staged checkpoint mismatch'
  write(out/'staged-checkpoint.json',{'status':'STAGED_CHECKPOINT_PIN_PASS','source_path':str(checkpoint),'source_sha256':sha(checkpoint),'staged_path':str(staged_checkpoint),'staged_sha256':sha(staged_checkpoint),'expected_sha256':checkpoint_sha,'runner_sha256':sha(Path(__file__)),'plan_sha256':sha(HERE/'plan.json'),'wrf_invoked_yet':False})
  before={p.name:sha(p) for p in run.iterdir() if p.is_file()}
  env={k:v for k,v in os.environ.items() if not k.startswith(tuple(plan['environment']['clear_prefixes'])) and k not in plan['environment']['clear_keys'] and not k.startswith(('OMP_','KMP_','GOMP_'))}
  env.update(plan['environment']['explicit_each_case']);env.update(WRF_RRTMGP_COLUMN_I=str(point['i']),WRF_RRTMGP_COLUMN_J=str(point['j']),WRF_RRTMGP_CAPTURE_DIR=str(capture),WRF_RRTMGP_CAPTURE_CALL='1')
  assert 'WRF_RRTMGP_AUDIT_DIR' not in env
  rec.update(inputs_before=before,explicit_environment={k:env[k] for k in plan['environment']['explicit_each_case']},model_openmp=False,model_mpi=False,master_stack_bytes=536870912)
  write(out/'receipt.json',rec)
  def limits():resource.setrlimit(resource.RLIMIT_STACK,(536870912,resource.getrlimit(resource.RLIMIT_STACK)[1]))
  start=time.monotonic()
  with (run/'wrf.stdout.log').open('wb') as f:
   p=subprocess.run([str(run/'wrf.exe')],cwd=run,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900,preexec_fn=limits)
  rec.update(returncode=p.returncode,elapsed_seconds=time.monotonic()-start,log_sha256=sha(run/'wrf.stdout.log'))
  assert p.returncode==0 and 'SUCCESS COMPLETE WRF' in (run/'wrf.stdout.log').read_text(errors='replace')
  histories=list(run.glob('wrfout_d01_*'));assert len(histories)==1 and histories[0].name=='wrfout_d01_2010-06-11_12:01:00'
  rec.update(inspect_history(histories[0]))
  verify_support(plan)
  compare_module=load('compare_module',task/'run_integrated_candidate.py')
  verify_support(plan)
  with tempfile.TemporaryDirectory(prefix='stratified-baseline-') as td:
   ref=Path(td);(ref/histories[0].name).symlink_to(baseline/histories[0].name)
   comp=compare_module.compare(ref,run);write(out/'history-comparison.json',comp);assert comp['status']=='BITWISE_PASS'
  assert sha(plan['replay_validator']['path'])==plan['replay_validator']['sha256']
  modules=verify_replay_imports();replay=modules['test_column_replay'];replay.DATA_DIR=Path(next(p for p in plan['external_asset_sha256'] if p.endswith('rrtmgp-gas-lw-g128.nc'))).parent
  # The retained validator starts its reference from the inherited environment.
  # This isolated process supplies a clean controlled environment and pinned LUT.
  os.environ.clear();os.environ.update({k:v for k,v in env.items() if not k.startswith('WRF_RRTMGP_')})
  os.environ['WRF_RRTMGP_FROZEN_TABLE']=next(p for p in plan['external_asset_sha256'] if p.endswith('frozen-ice-psd-moments.nc'))
  resource.setrlimit(resource.RLIMIT_STACK,(536870912,resource.getrlimit(resource.RLIMIT_STACK)[1]))
  reports=[]
  original_subprocess_run=subprocess.run
  def bounded_reference(command,**kwargs):
   index=len(rec['reference_invocations']);assert index<2,'only two strict calls per case'
   phase=['LW','SW'][index]
   expected=[plan['strict_reference']['path'],str(replay.DATA_DIR),str(capture/(phase.lower()+'.input')),str(capture/(phase.lower()+'.reference.result'))]
   assert command==expected and kwargs['cwd']==out,command
   verify_support(plan);verify_replay_imports()
   rec['reference_invocations'].append({'phase':phase,'command':command,'cwd':str(out)})
   write(out/'receipt.json',rec)
   result=original_subprocess_run(command,**kwargs);rec['reference_invocations'][-1]['returncode']=result.returncode
   return result
  subprocess.run=bounded_reference
  for phase,version in [('LW','RRTMGP_REPLAY_V8'),('SW','RRTMGP_REPLAY_V9')]:
   raw_phase,i,j,raw=replay.read_raw(capture/(phase.lower()+'.raw'));assert (raw_phase,i,j)==(phase,point['i'],point['j'])
   assert all(np.isfinite(v).all() for v in raw.values())
   assert raw['DP_HPA'].shape==(39,) and raw['RADIATION_STEP'].shape==(1,) and raw['RADIATION_STEP'].item()==721
   assert raw['SOURCE_TIME_SECONDS'].shape==(1,) and abs(raw['SOURCE_TIME_SECONDS'].item()-43200)<.001
   assert raw['MP_PHYSICS'].shape==(1,) and raw['MP_PHYSICS'].item()==27
   assert all(k in raw and raw[k].shape==(39,) for k in ['CF','REL','REI','RES'])
   assert (capture/(phase.lower()+'.input')).read_text().splitlines()[0]==version
   input_phase,nc,nl,overlap,seed,iceflag,adapter=replay.read_input(capture/(phase.lower()+'.input'))
   assert input_phase==phase and nc==1 and nl>=39
   assert adapter['NATIVE_DRY_LAYER_MASS_KG_M2'].shape==(1,39)
   assert adapter['FROZEN_MODE'].shape==(1,1) and adapter['FROZEN_MODE'].item()==1
   assert adapter['FROZEN_OCCURRENCE'].shape==(1,1) and adapter['FROZEN_OCCURRENCE'].item()==1
   expected_table=next(h for p,h in plan['external_asset_sha256'].items() if p.endswith('frozen-ice-psd-moments.nc'))
   captured_table=''.join(chr(int(x)) for x in adapter['FROZEN_TABLE_SHA256_BYTES'].ravel())
   assert captured_table==expected_table
   identity={}
   required={'QC':'QCLOUD','QI':'QICE','QR':'QRAIN','QS':'QSNOW','QG':'QGRAUP','QH':'QHAIL'}
   required.update({'SOURCE_QC':'QCLOUD','SOURCE_QI':'QICE','SOURCE_QR':'QRAIN','SOURCE_QS':'QSNOW','SOURCE_RE_CLOUD':'RE_CLOUD','SOURCE_RE_ICE':'RE_ICE','SOURCE_RE_SNOW':'RE_SNOW','RAD_CF_SOURCE':'CLDFRA','DRY_LAYER_MASS_KG_M2':'native_dry_mass_kg_m2'})
   assert set(required)<=set(raw),'missing required identity fields: '+str(set(required)-set(raw))
   for rk,pk in required.items():
    actual=np.asarray(raw[rk]);expected=np.asarray(point['profiles'][pk]);assert actual.shape==expected.shape and np.isfinite(actual).all()
    identity[rk]={'captured_values':actual.tolist(),'checkpoint_proxy_max_abs_difference':float(np.max(abs(actual-expected))),'exact_checkpoint_proxy_equal':bool(np.array_equal(actual,expected))}
   write(out/(phase.lower()+'-actual-state-identity.json'),identity)
   production=modules['compare_column_replay'].read_result(capture/(phase.lower()+'.result'))
   assert np.all((production['sections']['MASK']==0.)|(production['sections']['MASK']==1.))
   for q in ['QC','QI','QR','QS']:assert np.array_equal(raw[q],raw['SOURCE_'+q]),q
   if phase=='SW':
    assert np.array_equal(adapter['MCICA_MASK'],production['sections']['MASK'])
    serialized=production['sections']['GAS_TAU'].astype(np.float32).astype(np.float64)
    assert np.array_equal(adapter['RAW_GAS_TAU'],serialized)
    write(out/'sw-serialization-check.json',{'exact_default_REAL_serialization':True,'numeric_values_checked':int(serialized.size),'max_serialization_only_abs_difference':float(np.max(abs(adapter['RAW_GAS_TAU']-production['sections']['GAS_TAU']))),'source_proof':'module_ra_rrtmgp.F lines920/923/1055; GNU RWORDSIZE=4','optical_tolerances_unchanged':True})
   # Actual adapter inputs determine optical size/path; checkpoint values are
   # selection proxies only, especially when a background-radius fallback fires.
   reports.append(replay.validate_capture(out,phase,27,Path(plan['strict_reference']['path'])))
   write(out/('strict-'+phase.lower()+'.json'),reports[-1])
   write(out/'strict-replay.json',reports)
   assert reports[-1]['reference_comparison']['passed']
   reference=modules['compare_column_replay'].read_result(capture/(phase.lower()+'.reference.result'))
   assert np.array_equal(production['sections']['MASK'],reference['sections']['MASK'])
   assert sha(plan['replay_validator']['path'])==plan['replay_validator']['sha256']
   verify_support(plan)
  subprocess.run=original_subprocess_run
  assert len(rec['reference_invocations'])==2
  write(out/'strict-replay.json',reports)
  assert sha(checkpoint)==checkpoint_sha,'original checkpoint changed after run'
  after={name:sha(run/name) for name in before};assert after==before
  post_source=audit.verify_build_manifest(ROOT,task/'source',Path(plan['executable']['path']));assert post_source==pre_source
  for p,h in plan['external_asset_sha256'].items():assert sha(p)==h,p
  rec.update(status='CAPTURE_HISTORY_NONINTERFERENCE_AND_STRICT_REPLAY_PASS',inputs_after=after,source_after=post_source,strict_replay_sha256=sha(out/'strict-replay.json'))
 except Exception as e:rec.update(status='FAIL_PRESERVED',error=repr(e))
 finally:
  if 'original_subprocess_run' in locals():subprocess.run=original_subprocess_run
  try:
   verify_replay_imports()
   verify_support(plan)
   assert checkpoint.is_file() and sha(checkpoint)==checkpoint_sha,'original checkpoint changed in final check'
   for key in ['source_manifest','build_receipt','executable','configure','strict_reference','strict_reference_source','replay_validator']:
    assert sha(plan[key]['path'])==plan[key]['sha256'],key
   for path,h in plan['external_asset_sha256'].items():assert sha(path)==h,path
   rec['source_after']=audit.verify_build_manifest(ROOT,task/'source',Path(plan['executable']['path']))
   assert rec['source_after']==pre_source
   if 'before' in locals():
    rec['inputs_after']={name:sha(run/name) for name in before}
    assert rec['inputs_after']==before
   rec['postflight_pins_unchanged']=True
  except Exception as e:rec.update(status='FAIL_PRESERVED',postflight_pin_error=repr(e))
 write(out/'receipt.json',rec);print(rec['status']);assert rec['status']=='CAPTURE_HISTORY_NONINTERFERENCE_AND_STRICT_REPLAY_PASS'
if __name__=='__main__':main()
