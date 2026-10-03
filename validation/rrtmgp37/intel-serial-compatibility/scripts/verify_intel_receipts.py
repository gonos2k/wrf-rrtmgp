#!/usr/bin/env python3
"""Read-only verification of pinned Intel build and bounded smoke evidence."""
import concurrent.futures,hashlib,json,os,pathlib
import numpy as np
from netCDF4 import Dataset
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
SUMMARY=ROOT/'build/udm-workspace-intel-validation-summary.json'
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
summary=json.loads(SUMMARY.read_text());assert summary['status']=='BOUNDED_INTEL_SERIAL_COMPATIBILITY_PASS'
for p,h in summary['evidence_files'].items():assert sha(ROOT/p)==h,p
build=ROOT/'build/udm-workspace-intel-serial';receipt=json.loads((build/'build-receipt.json').read_text())
assert receipt['status']=='BUILD_PASS';assert receipt['base_commit']=='6f0f3ea3e73fbd43325fdad1050b000eecd70138'
assert receipt['shared_dependencies_unchanged'] and not receipt['source_files_modified_or_missing']
assert sha(build/'source-manifest.json')==receipt['source_manifest_sha256']
entries=json.loads((build/'source-manifest.json').read_text())['files'];assert len(entries)==6639
for e in entries:
 p=build/'source'/e['path']
 if e['kind']=='symlink':assert p.is_symlink() and os.readlink(p)==e['target'],e['path']
 else:assert sha(p)==e['sha256'],e['path']
assert sha(build/'source/WRF/configure.wrf')==receipt['configure_sha256']
for n,e in receipt['executables'].items():assert sha(build/'source/WRF/main'/n)==e['sha256']
deps=json.loads((build/'shared-dependencies-before.json').read_text());assert len(deps)==870
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for p,h in zip(deps,pool.map(sha,deps)):assert h==deps[p]['sha256'],p
reports=[]
for name,d in summary['cases'].items():
 out=ROOT/'build/udm-workspace-intel-runtime'/name;actual=json.loads((out/'receipt.json').read_text());assert actual==d
 assert d['status']=='COMPATIBILITY_SMOKE_PASS' and d['returncode']==0 and d['success_marker']
 assert d['inputs_unchanged'] and d['assets_unchanged'] and d['source_unchanged']
 assert d['stack_bytes'][0]==1073741824 and d['diagnostics_environment_empty']
 live=json.loads((out/'live-process-evidence.json').read_text());assert 'Max stack size            1073741824' in live['actual_proc_limits']
 for n,h in d['inputs_before'].items():assert sha(out/'run'/n)==h,n
 for n,h in d['assets_before'].items():assert sha(out.parent/'assets'/n)==h,n
 info=json.loads((out/'history-inspection.json').read_text());assert info['times']==['2010-06-11_12:01:00'];assert info['physical_layout_matches_approved_case']
 assert info['dimensions']['seed_dim_stag']['size']==2
 histories=list((out/'run').glob('wrfout_d01_*'));assert len(histories)==1;assert sha(histories[0])==d['history_sha256']==info['sha256']
 with Dataset(histories[0]) as ds:
  ds.set_auto_maskandscale(False);assert set(ds.variables)==set(info['variables']);numeric=0;attrs=len(ds.ncattrs())
  assert {n:len(dim) for n,dim in ds.dimensions.items()}=={n:e['size'] for n,e in info['dimensions'].items()}
  for n,v in ds.variables.items():
   a=np.asarray(v[:]);e=info['variables'][n];assert hashlib.sha256(a.tobytes()).hexdigest()==e['raw_sha256'],n
   assert list(v.dimensions)==e['dimensions'] and list(v.shape)==e['shape'] and str(v.dtype)==e['dtype'],n
   assert set(v.ncattrs())==set(e['attributes']),n
   attrs+=len(v.ncattrs())
   if a.dtype.kind in 'biufc':numeric+=1;assert np.isfinite(a).all(),n
  assert numeric==d['numeric_variables']==info['numeric_variables'];assert attrs==d['total_attributes']==info['total_attributes']
 reports.append(dict(case=name,variables=d['total_variables'],numeric_finite=numeric,attributes=attrs,history_sha256=d['history_sha256']))
debug=json.loads((ROOT/'build/udm-workspace-intel-runtime/gdb-solve-entry/actual-inferior-evidence.json').read_text())
assert debug['frame_delta_bytes']==568806032;assert 'Max stack size            536870912' in debug['actual_inferior_proc_limits']
print(json.dumps(dict(status='READ_ONLY_VERIFY_PASS',source_entries=len(entries),shared_dependencies=len(deps),histories=reports),indent=2))
