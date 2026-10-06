#!/usr/bin/env python3
"""Curate text-only receipts; preserve executed originals and their provenance."""
import copy,hashlib,json,pathlib,shutil
from netCDF4 import Dataset
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
WORK=ROOT/'build/udm-intel-serial-pr-work'
PKG=WORK/'validation/rrtmgp37/intel-serial-compatibility'
assert not PKG.exists(),'fresh package required'
PKG.mkdir(parents=True)
provenance={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(dest,value):
 p=PKG/dest;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');return p
def retain(source,dest):
 p=ROOT/source;q=PKG/dest;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 provenance[dest]=dict(original_path=source,original_sha256=sha(p),exact_original=True)
 return q
def derived(source,dest,value,note):
 p=ROOT/source;write(dest,value);provenance[dest]=dict(original_path=source,original_sha256=sha(p),exact_original=False,derivation=note)
build=ROOT/'build/udm-workspace-intel-serial';probe=ROOT/'build/udm-intel-feasibility';runtime=ROOT/'build/udm-workspace-intel-runtime'
inventory=json.loads((probe/'inventory-probe-receipt.json').read_text());compact=copy.deepcopy(inventory)
compact['source_manifest']={'canonical_sha256':inventory['source_manifest']['canonical_sha256'],'entry_count':len(inventory['source_manifest']['entries']),'entries_omitted':'Full tracked file inventory authenticated by original receipt hash; live source check retained separately.'}
for step in compact['commands']:
 if step['argv']==['git','ls-files','-z']:
  text=step.pop('stdout');step.update(stdout_bytes=len(text.encode()),stdout_sha256=hashlib.sha256(text.encode()).hexdigest(),stdout_omitted='NUL-delimited Git filename inventory omitted for compactness.')
derived('build/udm-intel-feasibility/inventory-probe-receipt.json','receipts/tool-inventory.json',compact,'Remove only the full source-entry map and large git filename stdout; retain their digests/counts and every other tool command/result.')
for source,dest in [
 ('build/udm-workspace-intel-serial/build-receipt.json','receipts/build.json'),
 ('build/udm-workspace-intel-serial/build-receipt-v1-validator-fail.json','failures/build-validator-v1.json'),
 ('build/udm-workspace-intel-serial/configure-serial76.log','logs/configure-serial76.log'),
 ('build/udm-workspace-intel-serial/configcheck-postbuild.log','logs/configcheck-postbuild.log'),
 ('build/udm-workspace-intel-serial/source/WRF/configure.wrf','config/configure.wrf'),
 ('build/udm-intel-feasibility/wrf-stanza-compiler-probe.json','receipts/wrf-stanza-compiler-probes.json'),
 ('build/udm-intel-feasibility/random-seed-metadata-proof.json','receipts/random-seed-metadata-proof.json'),
 ('build/udm-intel-feasibility/standalone-probe-receipt.json','receipts/standalone/initial.json'),
 ('build/udm-intel-feasibility/standalone-stack64-test.json','receipts/standalone/stack64-retry.json'),
 ('build/udm-intel-feasibility/standalone-1.log','logs/standalone-configure.log'),
 ('build/udm-intel-feasibility/standalone-2.log','logs/standalone-build.log'),
 ('build/udm-intel-feasibility/standalone-3.log','failures/standalone-stack8.log'),
 ('build/udm-workspace-intel-verify-receipt.json','receipts/live-validator.json'),
 ('build/udm-workspace-intel-validation-current.md','REPORT.md'),
]:retain(source,dest)
for n in ['wrf.exe','real.exe','ndown.exe','tc.exe']:retain('build/udm-workspace-intel-serial/ldd-'+n+'.log','logs/ldd-'+n+'.log')
for name in ['inventory_probe.py','standalone_probe.py','build_intel_serial_v1.py','build_intel_serial.py','run_intel_smoke_v1.py','run_intel_smoke_v2.py','run_intel_smoke.py','gdb_stack_probe.py','verify_intel_receipts.py','netcdf_probe.f90','netcdf_c_probe.c','random_seed_size.f90']:
 retain('build/udm-intel-feasibility/'+name,'scripts/'+name)
cases=['ra37','ra37-stack512-v2','ra4-stack512-v1','ra37-stack1g-v3','ra4-stack1g-v2']
for case in cases:
 prefix='receipts/runs/'+case if 'stack1g' in case else 'failures/'+case
 for name in ['receipt.json','receipt-v1-inspector-fail.json','history-inspection.json','live-process-evidence.json']:
  source='build/udm-workspace-intel-runtime/'+case+'/'+name
  if (ROOT/source).is_file():retain(source,prefix+'/'+name)
 retain('build/udm-workspace-intel-runtime/'+case+'/run/wrf.stdout.log',prefix+'/wrf.stdout.log')
 retain('build/udm-workspace-intel-runtime/'+case+'/run/namelist.input',prefix+'/namelist.input')
for p in (runtime/'gdb-solve-entry').iterdir():
 if p.is_file():retain(str(p.relative_to(ROOT)),'receipts/gdb/'+p.name)
for name in ['solve-em-stack-disassembly.txt','full-solve-entry-disassembly.txt','stack-failure-evidence.json']:
 for case in ['ra37','ra37-stack512-v2']:
  p=runtime/case/name
  if p.is_file():retain(str(p.relative_to(ROOT)),'receipts/gdb/'+name)
deps=json.loads((build/'shared-dependencies-before.json').read_text());after=json.loads((build/'shared-dependencies-after.json').read_text());last=json.loads((runtime/'shared-dependencies-after-runtime.json').read_text());assert deps==after;assert last['unchanged'];assert all(last['files'][p]==v['sha256'] for p,v in deps.items())
derived('build/udm-workspace-intel-serial/shared-dependencies-before.json','inventories/shared-dependency-sha256.json',dict(files={p:v['sha256'] for p,v in deps.items()},count=len(deps),original_before_sha256=sha(build/'shared-dependencies-before.json'),original_after_build_sha256=sha(build/'shared-dependencies-after.json'),original_after_runtime_sha256=sha(runtime/'shared-dependencies-after-runtime.json'),all_unchanged=True),'Hash-only inventory of870 shared files; drop sizes/resolved duplicate paths. Original before/after receipt hashes are pinned.')
source_manifest=json.loads((build/'source-manifest.json').read_text());source_files=['WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F'];production={}
for name in source_files:
 p=build/'source'/name;data=p.read_bytes();assert data==(WORK/name).read_bytes()
 production[name]=dict(sha256=sha(p),git_blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest())
generated=json.loads((build/'postbuild-full-artifact-manifest.json').read_text())
write('inventories/source-pins.json',dict(tested_commit='6f0f3ea3e73fbd43325fdad1050b000eecd70138',pr_base='bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291',base_difference='Only standalone CMake default-path ordering and registration receipt follow-up; full model production bytes identical.',production_files=production,full_source_manifest=dict(original_path=str(build/'source-manifest.json'),sha256=sha(build/'source-manifest.json'),entry_count=len(source_manifest['files'])),full_generated_artifact_manifest=dict(original_path=str(build/'postbuild-full-artifact-manifest.json'),sha256=sha(build/'postbuild-full-artifact-manifest.json'),entry_count=len(generated['files']))))
formats={}
for case in ['ra37-stack1g-v3','ra4-stack1g-v2']:
 receipt=json.loads((runtime/case/'receipt.json').read_text());candidate=runtime/case/'run/wrfout_d01_2010-06-11_12:01:00';baseline=pathlib.Path(receipt['approved_template_run'])/candidate.name
 with Dataset(candidate) as c,Dataset(baseline) as b:
  formats[case]=dict(candidate=dict(path=str(candidate),sha256=sha(candidate),data_model=c.data_model,seed_dim=len(c.dimensions['seed_dim_stag'])),gnu_reference=dict(path=str(baseline),sha256=sha(baseline),data_model=b.data_model,seed_dim=len(b.dimensions['seed_dim_stag'])),comparison_scope='File format and native seed metadata only; no cross-compiler data equality assertion.')
write('receipts/format-seed-observation.json',formats)
log=(build/'build-em_real.log').read_text(errors='replace').splitlines(keepends=True)
excerpt=''.join(log[:80])+ '\n[Middle of full1778666-byte build log omitted; full SHA256 pinned in build receipt.]\n'+''.join(log[-35:])
p=PKG/'logs/build-excerpt.log';p.write_text(excerpt);provenance['logs/build-excerpt.log']=dict(original_path='build/udm-workspace-intel-serial/build-em_real.log',original_sha256=sha(build/'build-em_real.log'),exact_original=False,derivation='Exact first80/final35 lines plus explicit omission marker; full build log remains in isolated validation tree.')
original_summary=json.loads((ROOT/'build/udm-workspace-intel-validation-summary.json').read_text())
write('receipts/summary.json',dict(status=original_summary['status'],original_summary_sha256=sha(ROOT/'build/udm-workspace-intel-validation-summary.json'),tested_commit=source_manifest['base_commit'],source_entries=6639,shared_dependency_files=870,compiler='Intel ifx/icx2025.3.3 (ifx20260319)',netcdf_fortran='4.6.2',netcdf_c='4.9.3',master_stack_build_mib=64,master_stack_pass_runs_mib=1024,case_scope='Serial em_real, two one-minute smokes, no cross-compiler parity/full Intel MPI/OpenMP/long forecast/universal stack minimum claim.',runs={case:dict(receipt='runs/'+case+'/receipt.json',history_inspection='runs/'+case+'/history-inspection.json',status=original_summary['cases'][case]['status'],history_sha256=original_summary['cases'][case]['history_sha256']) for case in ['ra37-stack1g-v3','ra4-stack1g-v2']}))
write('provenance.json',dict(originals=provenance,curation_source_script_sha256=sha(pathlib.Path(__file__)),raw_payloads_excluded=True,source_and_history_live_validation='Retained live validator requires original isolated model/dependency/output trees. Portable packaged verifier checks only artifact integrity and recorded evidence contracts.'))
(PKG/'.gitattributes').write_text('# Preserve exact historical raw logs/configuration without trimming their bytes.\nlogs/*.log whitespace=-blank-at-eol,-blank-at-eof\nfailures/**/*.log whitespace=-blank-at-eol,-blank-at-eof\nreceipts/runs/**/*.log whitespace=-blank-at-eol,-blank-at-eof\nreceipts/gdb/gdb.log whitespace=-blank-at-eol,-blank-at-eof\nreceipts/gdb/*.txt whitespace=-blank-at-eol,-blank-at-eof\nconfig/configure.wrf whitespace=-blank-at-eol,-blank-at-eof\n')
print('curated',sum(p.is_file() for p in PKG.rglob('*')),'files',sum(p.stat().st_size for p in PKG.rglob('*') if p.is_file()),'bytes')
