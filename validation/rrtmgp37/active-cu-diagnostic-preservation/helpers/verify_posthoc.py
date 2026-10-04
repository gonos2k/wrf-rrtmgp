#!/usr/bin/env python3
"""Read-only recovery of validation after the frozen runner's tuple-key JSON failure."""
import importlib.util, json, hashlib, pathlib, sys
runner=pathlib.Path(__file__).resolve().parents[1]/'run_candidate.py'
spec=importlib.util.spec_from_file_location('candidate_runner',runner); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
OUT=pathlib.Path(__file__).resolve().parent
orig=json.loads((m.OUT/'execution.json').read_text())
case=m.CASE; base=m.BASE
sha=lambda p:m.sha(p)
report={
 'schema':'udm37-pr60-active-cu-posthoc-v1',
 'status':'POSTHOC_EXACT_VALIDATION',
 'original_runner_status':orig['status'],
 'original_runner_json_sha256':sha(m.OUT/'execution.json'),
 'original_runner_tmp_sha256':sha(m.OUT/'execution.json.tmp'),
 'original_runner_tmp_parse_error':'JSONDecodeError: tuple keys in diagnostics.native_cf0_detail_aggregate are not JSON object keys; original RUNNING receipt and truncated .tmp preserved',
 'model_invocations':orig.get('model_invocations'),
 'launcher_returncode':{'observed':False,'value':None,'evidence':'not durably written; do not infer numeric RC'},
 'case':str(case), 'baseline':str(base),
 'runner_sha256':orig['runner_sha256'], 'preflight_receipt_sha256':orig['preflight_receipt_sha256'],
 'rank_success':[],
}
for p in sorted(case.glob('rsl.error.[0-9][0-9][0-9][0-9]')):
 txt=p.read_text(errors='strict')
 report['rank_success'].append({'file':p.name,'sha256':sha(p),'success_marker':'SUCCESS COMPLETE WRF' in txt})
if len(report['rank_success'])!=4 or not all(r['success_marker'] for r in report['rank_success']): raise SystemExit('rank markers failed')
report['history_quality']=m.validate_times(case,m.EXPECTED_TIMES)
report['checkpoint_quality']=m.validate_checkpoints(case)
report['diagnostics_summary']={}
d=m.diagnostics(case)
for k in ('record_count','per_rank_tag_counts','native_phase_records','native_cf0_detail_records','cu_population_records','cu_clip_records','positive_cu_accepted_grid_sum_g_m2','positive_cu_rejected_grid_sum_g_m2','positive_cu_clip_path_sum_g_m2','all_native_omissions_bounded'):
 report['diagnostics_summary'][k]=d[k]
report['native_cf0_detail_aggregate']=[{'rank':int(k[0]),'band':k[1],'phase':k[2],**v} for k,v in sorted(d['native_cf0_detail_aggregate'].items())]
report['historical_native_cu_diagnostics']=m.compare_legacy_diagnostics(d['records'],m.legacy_summary_diagnostics(base))
comparison=m.validate_case_pair(base,case)
report['comparison']={'status':comparison['status'],'history_count':comparison['history_count'],'difference_count':len(comparison['differences']),'differences':comparison['differences'],'history':[],'checkpoints':[]}
for h in comparison['history']:
 report['comparison']['history'].append({'file':h['file'],'times':h['candidate_quality'].get('times'),'baseline_sha256':h['baseline_sha256'],'candidate_sha256':h['candidate_sha256'],'exact_difference_count':len(h['exact_differences'])})
for label in ('baseline_checkpoints','candidate_checkpoints'):
 report['comparison']['checkpoints'].extend([{'side':label,'file':x['file'],'times':x['times'],'quality':x['quality'],'variables':x['quality']['variables'],'numeric_values':x['quality']['numeric_values'],'sha256':sha(case/x['file']) if label.startswith('candidate') else sha(base/x['file'])} for x in comparison[label]])
# Independently recheck immutability using the original runner's pinned source/dependency/input baselines.
report['source_integrity_after']=m.source_integrity()
report['source_unchanged']=report['source_integrity_after']==orig['source_integrity_before']
prep_path=m.ROOT/'build/udm37-restart-cloud-diagnostics-gnu-v1/prepare_restart_source_v4.py'
spec2=importlib.util.spec_from_file_location('pinned_deps',prep_path); dep=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(dep)
deps=dep.deps_inventory(); report['shared_dependencies_after_sha256']=deps['manifest_sha256']; report['dependencies_unchanged']=deps['manifest_sha256']==orig['shared_dependencies_before']['manifest_sha256']
report['candidate_executable_after']={'path':orig['candidate_executable']['path'],'sha256':sha(pathlib.Path(orig['candidate_executable']['path']))}
report['candidate_executable_unchanged']=report['candidate_executable_after']['sha256']==orig['candidate_executable']['sha256']
report['baseline_history_after']={p.name:sha(p) for p in m.histories(base)}
report['baseline_checkpoints_after']={p.name:sha(p) for p in sorted(base.glob('wrfrst_d01_*'))}
report['baseline_outputs_unchanged']=(report['baseline_history_after']==orig['baseline_history_hashes_before'] and report['baseline_checkpoints_after']==orig['baseline_checkpoint_hashes_before'])
inputs_after={p.name:(m.target_record(p) if p.is_symlink() else m.pin(p)) for p in sorted(case.iterdir()) if p.is_symlink() or p.name=='namelist.input'}
report['candidate_inputs_after_unchanged']=inputs_after==orig['candidate_inputs_before']
checks=[report['comparison']['status']=='EXACT_ALL_OUTPUTS',report['historical_native_cu_diagnostics']['status']=='UNCHANGED',report['source_unchanged'],report['dependencies_unchanged'],report['candidate_executable_unchanged'],report['baseline_outputs_unchanged'],report['candidate_inputs_after_unchanged'],all(q['quality']['masked']==0 and q['quality']['nonfinite']==0 and q['quality']['fill_values']==0 for q in report['history_quality']),all(q['quality']['masked']==0 and q['quality']['nonfinite']==0 and q['quality']['fill_values']==0 for q in report['checkpoint_quality'])]
report['posthoc_checks_passed']=all(checks)
report['launcher_returncode']['inference_only']='All four rank logs contain SUCCESS COMPLETE WRF and expected output files exist; numeric launcher RC was not retained.'
out=OUT/'posthoc-result-v1.json'; out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(json.dumps({'status':report['status'],'posthoc_checks_passed':report['posthoc_checks_passed'],'comparison':report['comparison']['status'],'history_times':[t for f in report['history_quality'] for t in f['times']],'checkpoint_quality':[{'masked':x['quality']['masked'],'nonfinite':x['quality']['nonfinite'],'fill_values':x['quality']['fill_values']} for x in report['checkpoint_quality']],'diagnostics_summary':report['diagnostics_summary'],'historical_native_cu':report['historical_native_cu_diagnostics']['status'],'source_unchanged':report['source_unchanged'],'dependencies_unchanged':report['dependencies_unchanged'],'candidate_inputs_after_unchanged':report['candidate_inputs_after_unchanged'],'launcher_returncode':report['launcher_returncode'],'receipt':str(out),'receipt_sha256':sha(out)},indent=2))
if not report['posthoc_checks_passed']: raise SystemExit(1)
