#!/usr/bin/env python3
"""Verify portable text artifacts; model/dependency payloads are not included."""
import hashlib,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parent
def read(name):return json.loads((ROOT/name).read_text())
def digest(name):return hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
manifest=read('file-manifest.json')
actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p.name!='file-manifest.json'}
assert actual==set(manifest['files']),'unlisted or missing packaged file'
for name,entry in manifest['files'].items():
 assert '..' not in pathlib.PurePosixPath(name).parts and not pathlib.PurePosixPath(name).is_absolute(),name
 assert digest(name)==entry['sha256'] and (ROOT/name).stat().st_size==entry['bytes'],name
 assert pathlib.PurePosixPath(name).suffix not in {'.nc','.exe','.o','.a','.so','.mod','.bin','.pyc'},name
summary=read('receipts/summary.json');assert summary['status']=='BOUNDED_INTEL_SERIAL_COMPATIBILITY_PASS'
assert summary['compiler']=='Intel ifx/icx2025.3.3 (ifx20260319)';assert summary['netcdf_fortran']=='4.6.2' and summary['netcdf_c']=='4.9.3'
pins=read('inventories/source-pins.json');assert pins['tested_commit']=='6f0f3ea3e73fbd43325fdad1050b000eecd70138';assert pins['pr_base']=='bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291'
assert pins['full_source_manifest']['entry_count']==6639 and pins['full_generated_artifact_manifest']['entry_count']==9157
assert len(pins['production_files'])==3
deps=read('inventories/shared-dependency-sha256.json');assert deps['count']==len(deps['files'])==870 and deps['all_unchanged']
assert all(re.fullmatch('[0-9a-f]{64}',h) for h in deps['files'].values())
inventory=read('receipts/tool-inventory.json');assert inventory['netcdf_probe']['compile_pass'] and inventory['netcdf_probe']['run_pass'];assert inventory['source_unchanged'] and inventory['dependencies_unchanged']
for path,e in inventory['dependencies'].items():assert deps['files'][path]==e['sha256'],path
assert any('2025.3.3 20260319' in c['stdout'] for c in inventory['commands'] if c['argv'][0].endswith('/ifx'))
build=read('receipts/build.json');assert build['status']=='BUILD_PASS';assert not build['source_files_modified_or_missing'];assert build['shared_dependencies_unchanged'];assert build['configcheck_returncode']==0
assert build['base_commit']==pins['tested_commit'];assert digest('config/configure.wrf')==build['configure_sha256']==build['configure_after_sha256']
assert any(c['argv']==['csh','-f','./compile','-j','12','em_real'] and c['returncode']==0 and not c['timed_out'] for c in build['commands'])
assert build['vendor_objects_actual']==sorted(build['vendor_objects_expected']) and len(build['vendor_objects_actual'])==25
assert all(e['exists'] and re.fullmatch('[0-9a-f]{64}',e['sha256']) for e in build['executables'].values())
assert digest('scripts/build_intel_serial_v1.py')==build['launcher_sha256']
assert digest('scripts/build_intel_serial.py')==build['validator_correction']['corrected_launcher_sha256']
for case,expected in [('ra37-stack1g-v3',(211,210,1342)),('ra4-stack1g-v2',(208,207,1324))]:
 prefix='receipts/runs/'+case;d=read(prefix+'/receipt.json');info=read(prefix+'/history-inspection.json');live=read(prefix+'/live-process-evidence.json')
 assert d['status']=='COMPATIBILITY_SMOKE_PASS' and d['returncode']==0 and d['success_marker'] and not d['timed_out']
 assert d['inputs_unchanged'] and d['assets_unchanged'] and d['source_unchanged'];assert d['diagnostics_environment_empty'];assert d['stack_bytes'][0]==1073741824
 assert 'Max stack size            1073741824' in live['actual_proc_limits'];assert live['exe_sha256']==build['executables']['wrf.exe']['sha256']
 assert d['source_before']==d['source_after'];assert d['inputs_before']==d['inputs_after'];assert d['assets_before']==d['assets_after']
 assert d['inputs_before']['wrf.exe']==build['executables']['wrf.exe']['sha256'];assert d['input_pins']['wrfrst_d01_2010-06-11_12:00:00']=='943a53db058f2d9560c6f0d571f3ff9bb8efb407010c5eea2026922a6eeee7b8'
 assert digest(prefix+'/history-inspection.json')==d['history_inspection_sha256'];assert info['sha256']==d['history_sha256'];assert info['times']==['2010-06-11_12:01:00']
 assert (info['total_variables'],info['numeric_variables'],info['total_attributes'])==expected
 assert len(info['variables'])==expected[0] and info['all_numeric_raw_finite'] and info['physical_layout_matches_approved_case']
 assert [info['dimensions'][n]['size'] for n in ['west_east','south_north','bottom_top','seed_dim_stag']]==[289,189,39,2]
 numeric=[v for v in info['variables'].values() if 'finite_all_raw' in v];assert len(numeric)==expected[1]
 assert all(v['finite_all_raw'] and v['nonfinite_count']==0 for v in numeric)
 assert all(re.fullmatch('[0-9a-f]{64}',v['raw_sha256']) for v in info['variables'].values())
 assert len(info['compiler_dependent_seed_layout_differences'])==6
 assert 'SUCCESS COMPLETE WRF' in (ROOT/prefix/'wrf.stdout.log').read_text()
 original=read(prefix+'/receipt-v1-inspector-fail.json');assert original['status']=='FAIL' and original['returncode']==0 and original['success_marker']
 assert digest('scripts/run_intel_smoke_v2.py')==d['inspection_correction']['initial_launcher_sha256'];assert not d['inspection_correction']['wrf_rerun']
for case,stack in [('ra37',67108864),('ra37-stack512-v2',536870912),('ra4-stack512-v1',536870912)]:
 prefix='failures/'+case;d=read(prefix+'/receipt.json');assert d['status']=='FAIL' and d['returncode']==174 and d['stack_bytes'][0]==stack
 assert d['source_unchanged'] and d['inputs_unchanged'] and d['assets_unchanged'];assert d['inputs_before']['wrf.exe']==build['executables']['wrf.exe']['sha256']
 log=(ROOT/prefix/'wrf.stdout.log').read_text();assert 'SIGSEGV' in log and '0000000000F2D65B' in log
assert read('failures/ra37/receipt.json')['inputs_before']==read('failures/ra37-stack512-v2/receipt.json')['inputs_before']==read('receipts/runs/ra37-stack1g-v3/receipt.json')['inputs_before']
gdb=read('receipts/gdb/receipt.json');actual_gdb=read('receipts/gdb/actual-inferior-evidence.json');frame=read('receipts/gdb/stack-frame-analysis.json')
assert gdb['status']=='ENTRY_ONLY_PROBE_PASS' and not gdb['integration_executed'] and gdb['inferior_terminated_by_debugger'] and gdb['inputs_unchanged']
assert 'Max stack size            536870912' in actual_gdb['actual_inferior_proc_limits'];assert actual_gdb['memory_extents']==[298,40,198]
assert actual_gdb['frame_delta_bytes']==frame['observed_frame_bytes']==frame['derived_frame_bytes']==568806032
assert 60*(298*40*198*4)+10*(298*198*4)+7472==frame['derived_frame_bytes'];assert frame['dynamic_rsp_assignments']==50 and frame['formula_matches_observed']
assert actual_gdb['before_fault_rip']==0xf2d65b;assert actual_gdb['frame_delta_bytes']>536870912
assert read('receipts/standalone/initial.json')['steps'][2]['returncode']==8
retry=read('receipts/standalone/stack64-retry.json');assert retry['returncode']==0 and retry['stack_bytes'][0]==67108864;assert '100% tests passed, 0 tests failed out of 11' in retry['stdout']
assert read('receipts/wrf-stanza-compiler-probes.json')['all_pass']
seed=read('receipts/random-seed-metadata-proof.json');assert seed['intel_seed_size']==2 and seed['gnu_seed_size']==8
for e in read('receipts/format-seed-observation.json').values():assert e['candidate']['data_model']=='NETCDF4' and e['candidate']['seed_dim']==2;assert e['gnu_reference']['data_model']=='NETCDF3_64BIT_OFFSET' and e['gnu_reference']['seed_dim']==8
root_review=read('receipts/root-history-recheck.json');assert root_review['status']=='PASS'
assert 'executed inline' in root_review['method'] and 'no original standalone script retained' in root_review['method']
assert len(root_review['cases'])==2
for case in root_review['cases']:
 info=read('receipts/runs/'+case['case']+'/history-inspection.json')
 assert case['sha256']==info['sha256'] and case['Times']=='2010-06-11_12:01:00'
 assert case['all_numeric_finite_unmasked'] and case['numeric_variables']==info['numeric_variables']
 assert case['geometry']==[289,189,39] and case['mp_physics']==27
 assert case['radiation']==(37 if case['case']=='ra37-stack1g-v3' else 4)
assert read('failures/build-validator-v1.json')['status']=='BUILD_FAIL';assert not build['validator_correction']['full_build_rerun']
for name,e in read('provenance.json')['originals'].items():
 if e['exact_original']:assert digest(name)==e['original_sha256'],name
print('PORTABLE_ARTIFACT_VERIFY_PASS: Intel serial build, 2 one-minute histories, 11 standalone tests, retained failures and stack proof; model payloads not reopened.')
