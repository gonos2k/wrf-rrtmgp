from pathlib import Path
import hashlib,json,shutil,subprocess
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
task=ROOT/'build/udm-workspace-real-wrf'
baseline=ROOT/'build/udm-selected-real-wrf'
integrated=ROOT/'build/udm-workspace-selected-work'
source=task/'source'
if source.exists(): raise SystemExit('fresh source required')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
old=json.loads((baseline/'source-manifest.json').read_text())
source.mkdir()
files=[];changes=[]
production={'WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F'}
for entry in old['files']:
 e=entry.copy();rel=e['path'];src=baseline/'source'/rel;dst=source/rel
 dst.parent.mkdir(parents=True,exist_ok=True)
 if e['kind']=='symlink':
  if not src.is_symlink() or src.readlink().as_posix()!=e['target']:raise RuntimeError(rel)
  dst.symlink_to(e['target'])
 else:
  if sha(src)!=e['sha256']:raise RuntimeError('baseline changed '+rel)
  shutil.copy2(src,dst)
  if rel in production:
   shutil.copy2(integrated/rel,dst)
   e['sha256']=sha(dst);e['bytes']=dst.stat().st_size
   changes.append({'path':rel,'baseline_sha256':entry['sha256'],'candidate_sha256':e['sha256']})
 files.append(e)
if {e['path'] for e in changes}!=production:raise RuntimeError('production manifest missing')
base=subprocess.check_output(['git','-C',str(integrated),'rev-parse','HEAD'],text=True).strip()
patch=subprocess.check_output(['git','-C',str(integrated),'diff','--binary','--',*sorted(production)])
(task/'workspace-production.patch').write_bytes(patch)
manifest={'base_commit':base,'source_tree':str(source),'files':files}
(task/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
receipt={'status':'SOURCE_FROZEN','base_commit':base,'root_review_receipt_sha256':sha(ROOT/'build/root-workspace-review-v1.json'),'baseline_source_manifest_sha256':sha(baseline/'source-manifest.json'),'baseline_build_receipt_sha256':sha(baseline/'build-receipt-v2.json'),'baseline_executable_sha256':sha(baseline/'source/WRF/main/wrf.exe'),'source_manifest_sha256':sha(task/'source-manifest.json'),'workspace_patch_sha256':sha(task/'workspace-production.patch'),'source_entries':len(files),'source_differences_from_tested_baseline':changes,'all_other_source_entries_identical':True,'baseline_configure_sha256':sha(baseline/'source/WRF/configure.wrf'),'stage_script_sha256':sha(task/'stage.py'),'build_script_sha256':sha(task/'build_serial_em_real.sh')}
(task/'stage-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
