from pathlib import Path
import hashlib,json,shutil,subprocess
repo=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
task=repo/'build/udm-phase-path-statistics-real-wrf'
if task.exists(): raise SystemExit(f'refusing existing task directory: {task}')
task.mkdir(parents=True)
base=repo/'build/udm-workspace-real-wrf/source'
base_manifest=repo/'build/udm-workspace-real-wrf/source-manifest.json'
candidate=repo/'build/udm-phase-path-workspace'
source=task/'source'

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

manifest=json.loads(base_manifest.read_text())
entries=[]
for item in manifest['files']:
 rel=item['path']; src=base/rel; dst=source/rel
 dst.parent.mkdir(parents=True,exist_ok=True)
 e=item.copy()
 if item['kind']=='symlink':
  if not src.is_symlink() or src.readlink().as_posix()!=item['target']: raise RuntimeError('base symlink mismatch '+rel)
  dst.symlink_to(item['target'])
 else:
  if sha(src)!=item['sha256']:raise RuntimeError('base hash mismatch '+rel)
  replacement=candidate/rel
  if rel in {'WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F','WRF/phys/module_ra_rrtmgp_input.F','WRF/test/rrtmgp/CMakeLists.txt'}:
   src=replacement
  shutil.copy2(src,dst)
  e['sha256']=sha(dst);e['bytes']=dst.stat().st_size
 entries.append(e)
# Add the new source test and docs to the staged inventory (not production/model files).
for rel in ['WRF/test/rrtmgp/test_phase_path_stats.f90','WRF/doc/rrtmgp/PHASE_PATH_DIAGNOSTICS.md']:
 src=candidate/rel; dst=source/rel
 dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 entries.append({'path':rel,'kind':'file','bytes':dst.stat().st_size,'sha256':sha(dst)})
# Assert workspace baseline differs from the integrated tree only in the named four production files.
prod=['WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F','WRF/phys/module_ra_rrtmgp_input.F']
diffs=[]
for rel in prod:
 b=base/rel; c=source/rel
 if sha(b)!=sha(c):diffs.append({'path':rel,'workspace_baseline_sha256':sha(b),'candidate_sha256':sha(c)})
if [d['path'] for d in diffs]!=prod:raise RuntimeError(f'expected exact four production changes; got {diffs}')
# Copy the preconfigured GNU32 serial configuration exactly from the workspace build.
shutil.copy2(base/'WRF/configure.wrf',source/'WRF/configure.wrf')
base_commit=subprocess.check_output(['git','-C',str(candidate),'rev-parse','HEAD'],text=True).strip()
obj={'base_commit':base_commit,'source_tree':str(source),'files':entries}
(task/'source-manifest.json').write_text(json.dumps(obj,indent=2)+'\n')
(task/'production-diff-vs-workspace.json').write_text(json.dumps({'workspace_base_commit':base_commit,'workspace_source_manifest_sha256':sha(base_manifest),'production_changed_files':diffs,'production_change_count':len(diffs),'other_runtime_sources_identical_to_workspace':True},indent=2)+'\n')
print(json.dumps({'task':str(task),'source_entries':len(entries),'production_diff':diffs,'workspace_configure_sha256':sha(base/'WRF/configure.wrf')},indent=2))
