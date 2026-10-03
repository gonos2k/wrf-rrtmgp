#!/usr/bin/env python3
"""Bounded Intel compatibility smoke; preserves every raw array/metadata digest."""
import argparse,hashlib,json,os,pathlib,re,resource,shutil,signal,subprocess,time
import numpy as np
from netCDF4 import Dataset
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
BUILD=ROOT/'build/udm-workspace-intel-serial'
SOURCE=BUILD/'source'
OUT=ROOT/'build/udm-workspace-intel-runtime'
BASE='6f0f3ea3e73fbd43325fdad1050b000eecd70138'
CHECKPOINT='wrfrst_d01_2010-06-11_12:00:00'
PIN={CHECKPOINT:'943a53db058f2d9560c6f0d571f3ff9bb8efb407010c5eea2026922a6eeee7b8','wrfinput_d01':'5ef7abe34c516fba107f346bdbdb3777edacb5d48493df467ea2dd8bcf6a75ff','wrfbdy_d01':'e687b73730ab9a2cee4842e1a92b225a4edb074ba080b6053d96d81ec1731a2d','selected_audit_iofields.txt':'871b7d06d4a9665913fbf48dc0d0f250d40d61b032f6b993048ae9f00b53946e'}
EXES={'wrf.exe','real.exe','ndown.exe','tc.exe'}
MUTABLE=re.compile(r'^(wrfout_|wrfrst_|rsl\.|namelist\.output$|.*\.log$)')
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def check_source():
 d=json.loads((BUILD/'build-receipt.json').read_text());assert d['status']=='BUILD_PASS';assert d['base_commit']==BASE
 assert sha(BUILD/'source-manifest.json')==d['source_manifest_sha256']
 entries=json.loads((BUILD/'source-manifest.json').read_text())['files']
 for e in entries:
  p=SOURCE/e['path']
  if e['kind']=='symlink':assert p.is_symlink() and os.readlink(p)==e['target'],e['path']
  else:assert p.is_file() and sha(p)==e['sha256'],e['path']
 assert sha(SOURCE/'WRF/configure.wrf')==d['configure_sha256']
 for name in EXES:assert sha(SOURCE/'WRF/main'/name)==d['executables'][name]['sha256']
 return dict(entries_checked=len(entries),source_manifest_sha256=d['source_manifest_sha256'],build_receipt_sha256=sha(BUILD/'build-receipt.json'),configure_sha256=d['configure_sha256'],executables=d['executables'])
def fixed_hashes(run):
 return {p.name:sha(p) for p in sorted(run.iterdir()) if p.is_file() and (p.name==CHECKPOINT or not MUTABLE.match(p.name))}
def normalized(v):
 if isinstance(v,np.ndarray):return dict(dtype=str(v.dtype),shape=list(v.shape),values=normalized(v.tolist()),raw_sha256=hashlib.sha256(v.tobytes()).hexdigest())
 if isinstance(v,np.generic):return normalized(v.item())
 if isinstance(v,bytes):return dict(bytes_hex=v.hex())
 if isinstance(v,(tuple,list)):return [normalized(x) for x in v]
 if isinstance(v,float) and not np.isfinite(v):return repr(v)
 return v
def inspect_history(p,reference):
 result=dict(file=p.name,sha256=sha(p),bytes=p.stat().st_size,variables={},dimensions={},global_attributes={})
 with Dataset(p) as ds:
  ds.set_auto_maskandscale(False)
  result['dimensions']={n:dict(size=len(d),unlimited=d.isunlimited()) for n,d in ds.dimensions.items()}
  result['global_attributes']={n:normalized(ds.getncattr(n)) for n in ds.ncattrs()}
  times=np.asarray(ds['Times'][:]); result['times']=[b''.join(row.tolist()).decode('ascii') for row in times]
  assert result['times']==['2010-06-11_12:01:00'],result['times']
  numeric=0; attrs=len(ds.ncattrs())
  for name,v in ds.variables.items():
   data=np.asarray(v[:]);rec=dict(dtype=str(v.dtype),array_dtype=str(data.dtype),dimensions=list(v.dimensions),shape=list(v.shape),raw_bytes=data.nbytes,raw_sha256=hashlib.sha256(data.tobytes()).hexdigest(),attributes={k:normalized(v.getncattr(k)) for k in v.ncattrs()})
   attrs+=len(v.ncattrs())
   if data.dtype.kind in 'biufc':
    numeric+=1;finite=np.isfinite(data);rec.update(finite_all_raw=bool(finite.all()),nonfinite_count=int((~finite).sum()))
    if data.size:rec.update(minimum=normalized(data.min()),maximum=normalized(data.max()))
    assert finite.all(),name
   result['variables'][name]=rec
  for n in ['RTHRATEN','RTHRATLW','RTHRATSW','SWDDIR','SWDDIF','GSW','SWUPB','ALBEDO']:assert n in ds.variables,n
  with Dataset(reference) as ref:
   expected_dims={n:dict(size=len(d),unlimited=d.isunlimited()) for n,d in ref.dimensions.items()}
   # RANDOM_SEED(SIZE=...) is compiler-dependent (registry.stoch). Preserve
   # its native metadata; physical dimensions must still match the case.
   assert {n:v for n,v in result['dimensions'].items() if n!='seed_dim_stag'}=={n:v for n,v in expected_dims.items() if n!='seed_dim_stag'},'physical history geometry differs'
   result['compiler_dependent_seed_dimension']=dict(candidate=result['dimensions'].get('seed_dim_stag'),gnu_reference=expected_dims.get('seed_dim_stag'))
   assert set(ds.variables)==set(ref.variables),'history variable names differ'
   layout_differences=[]
   for name,v in ds.variables.items():
    expected=ref.variables[name]
    assert v.dtype==expected.dtype and v.dimensions==expected.dimensions,name
    if v.shape!=expected.shape:
     assert 'seed_dim_stag' in v.dimensions,name
     assert all(a==b for dim,a,b in zip(v.dimensions,v.shape,expected.shape) if dim!='seed_dim_stag'),name
     layout_differences.append(dict(variable=name,candidate_shape=list(v.shape),gnu_reference_shape=list(expected.shape)))
   result['compiler_dependent_seed_layout_differences']=layout_differences
  result['physical_layout_matches_approved_case']=True
  result.update(numeric_variables=numeric,total_variables=len(ds.variables),total_attributes=attrs,all_numeric_raw_finite=True)
 return result
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['ra37','ra4'],required=True);ap.add_argument('--attempt',default='');ap.add_argument('--stack-mib',type=int,default=64);a=ap.parse_args()
 case=OUT/(a.phase+('-'+a.attempt if a.attempt else ''));run=case/'run';assert not case.exists(),'fresh output directory required';case.mkdir(parents=True);run.mkdir()
 receipt=dict(status='STAGING',phase=a.phase,base_commit=BASE,launcher_sha256=sha(__file__),comparison_scope='Intel compatibility smoke; no GNU bitwise assertion')
 try:
  receipt['source_before']=check_source()
  prior=json.loads((ROOT/f'build/udm-workspace-real-runtime/{a.phase}-candidate/receipt.json').read_text())
  baseline=pathlib.Path(prior['baseline_run']);receipt['approved_template_run']=str(baseline)
  for p in sorted(baseline.iterdir()):
   if p.is_file() and p.name not in EXES and (p.name==CHECKPOINT or not MUTABLE.match(p.name)):shutil.copy2(p,run/p.name)
  for name in EXES:shutil.copy2(SOURCE/'WRF/main'/name,run/name)
  assert all(not p.is_symlink() for p in run.iterdir()),'materialized copies required'
  for name,h in PIN.items():assert sha(run/name)==h,name
  assets=OUT/'assets';assets.mkdir(exist_ok=True)
  asset_pins={pathlib.Path(p).name:h for p,h in prior['external_assets_before'].items()}
  for original,h in prior['external_assets_before'].items():
   p=pathlib.Path(original);dest=assets/p.name
   if not dest.exists():shutil.copy2(p,dest)
   assert sha(dest)==h,p.name
  # Verify own checked-out coefficients/table exactly match the approved assets.
  for name,h in asset_pins.items():
   p=SOURCE/('validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/'+name if name=='frozen-ice-psd-moments.nc' else 'WRF/run/'+name)
   assert sha(p)==h,str(p)
  text=(run/'namelist.input').read_text();receipt['template_namelist_sha256']=sha(run/'namelist.input')
  values={'run_minutes':'1','end_minute':'1, 1, 1','rrtmgp_data_path':"'"+str(assets)+"'"}
  if a.phase=='ra37':values['rrtmgp_udm_frozen_table']="'"+str(assets/'frozen-ice-psd-moments.nc')+"'"
  for key,value in values.items():
   text,count=re.subn(r'(?m)^(\s*'+key+r'\s*=)[^\n]*$',lambda m:m[1]+' '+value,text);assert count==1,key
  (run/'namelist.input').write_text(text)
  lw=37 if a.phase=='ra37' else 4
  for key,value in {'ra_lw_physics':lw,'ra_sw_physics':lw,'mp_physics':27,'use_mp_re':1,'rrtmgp_udm_frozen_optics':1 if a.phase=='ra37' else 0}.items():assert re.search(r'(?m)^\s*'+key+r'\s*=\s*'+str(value)+r'\s*$',text),key
  if a.phase=='ra4':assert re.search(r"(?m)^\s*rrtmgp_udm_frozen_table\s*=\s*''\s*$",text)
  receipt.update(input_pins=PIN,asset_pins=asset_pins,inputs_before=fixed_hashes(run),assets_before={p.name:sha(p) for p in assets.iterdir()},namelist_sha256=sha(run/'namelist.input'),namelist_changes=values)
  # Non-executable, non-namelist bytes exactly match the approved runtime.
  assert all(sha(p)==sha(baseline/p.name) for p in run.iterdir() if p.is_file() and p.name not in EXES|{'namelist.input'})
  inv=json.loads((ROOT/'build/udm-intel-feasibility/inventory-probe-receipt.json').read_text());env=os.environ.copy();env.update(inv['controlled_environment']);env['OPENBLAS_NUM_THREADS']='1'
  for key in list(env):
   if key.startswith('WRF_RRTMGP_') or key=='WRF_UDM_BOUNDARY_CAPTURE':env.pop(key)
  original=resource.getrlimit(resource.RLIMIT_STACK);resource.setrlimit(resource.RLIMIT_STACK,(a.stack_mib*1024*1024,original[1]))
  receipt.update(status='RUNNING',controlled_environment=inv['controlled_environment'],stack_bytes=resource.getrlimit(resource.RLIMIT_STACK),diagnostics_environment_empty=not any(k.startswith('WRF_RRTMGP_') or k=='WRF_UDM_BOUNDARY_CAPTURE' for k in env));write(case/'receipt.json',receipt)
  start=time.monotonic();timed_out=False
  with (run/'wrf.stdout.log').open('wb') as f:
   proc=subprocess.Popen(['./wrf.exe'],cwd=run,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
   try:proc.wait(timeout=600)
   except subprocess.TimeoutExpired:
    timed_out=True;os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
  receipt.update(returncode=proc.returncode,timed_out=timed_out,elapsed_s=time.monotonic()-start,log_sha256=sha(run/'wrf.stdout.log'))
  logs=[run/'wrf.stdout.log',*run.glob('rsl.error.*')];success=any('SUCCESS COMPLETE WRF' in p.read_text(errors='replace') for p in logs);receipt['success_marker']=success
  receipt.update(source_after=check_source(),inputs_after=fixed_hashes(run),assets_after={p.name:sha(p) for p in assets.iterdir()})
  receipt['inputs_unchanged']=receipt['inputs_after']==receipt['inputs_before'];receipt['assets_unchanged']=receipt['assets_after']==receipt['assets_before'];receipt['source_unchanged']=receipt['source_after']==receipt['source_before']
  assert receipt['inputs_unchanged'] and receipt['assets_unchanged'] and receipt['source_unchanged']
  assert proc.returncode==0 and success and not timed_out,'WRF run failed'
  history=list(run.glob('wrfout_d01_*'));assert len(history)==1,[p.name for p in history]
  reference=baseline/'wrfout_d01_2010-06-11_12:01:00';assert reference.is_file()
  info=inspect_history(history[0],reference);write(case/'history-inspection.json',info);receipt.update(status='COMPATIBILITY_SMOKE_PASS',history_inspection_sha256=sha(case/'history-inspection.json'),numeric_variables=info['numeric_variables'],total_variables=info['total_variables'],total_attributes=info['total_attributes'],history_sha256=info['sha256'])
 except Exception as error:receipt.update(status='FAIL',error=repr(error))
 write(case/'receipt.json',receipt);print(receipt['status'],receipt.get('error',''),case/'receipt.json',flush=True)
 return 0 if receipt['status']=='COMPATIBILITY_SMOKE_PASS' else 1
if __name__=='__main__':raise SystemExit(main())
