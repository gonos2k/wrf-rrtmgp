#!/usr/bin/env python3
"""Verify retained byte pins and scoped winter evidence without running WRF."""
from pathlib import Path, PurePosixPath
import hashlib,json,math,csv
P=Path(__file__).resolve().parent
def check(ok,msg):
 if not ok:raise ValueError(msg)
def read(rel):return json.loads((P/rel).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def zeros(d,keys):
 for k in keys:check(d[k]==0,'nonzero '+k)
def main():
 manifest=read('manifest.json');entries=manifest['files'];paths=[]
 for e in entries:
  rel=e['path'];q=PurePosixPath(rel)
  check(not q.is_absolute() and '..' not in q.parts,'unsafe path')
  f=P/rel;check(f.is_file() and not f.is_symlink(),'missing/symlink '+rel)
  check(f.stat().st_size==e['bytes'] and sha(f)==e['sha256'],'pin mismatch '+rel);paths.append(rel)
 check(len(paths)==len(set(paths)),'duplicate paths')
 check(set(paths)=={str(f.relative_to(P)) for f in P.rglob('*') if f.is_file()}-{'manifest.json'},'manifest coverage')
 for e in read('provenance.json')['copied_artifacts']:
  f=P/e['retained_path'];check(sha(f)==e['sha256'] and f.stat().st_size==e['bytes'],'original provenance '+str(f))
 summary=read('summary.json');check(summary['status']=='WINTER_RA37_FAILURE_OPEN','failure scope')
 check(summary['ra37_full_winter_validation_claim'] is False and summary['restart_byte_equivalence_claim'] is False,'overclaim')
 archive=read('archive/download-receipt.json');coverage=archive['coverage_from_actual_members']
 check(archive['archive_sha256']=='c60a0dc5cff57ceae1555b68c06b184314b54dcbee09bf6da9511dd990d693d8','archive pin')
 check(coverage['duration_hours']==24 and coverage['interval_hours']==3 and len(coverage['times'])==9,'actual archive coverage')
 check(coverage['times'][0]=='2000-01-24_12:00:00' and coverage['times'][-1]=='2000-01-25_12:00:00','archive times')
 v1=read('v1/run-receipt.json');check(v1['status']=='FORECAST_FAILED' and set(v1['arms'])=={'ra4'},'v1 execution scope')
 check(v1['arms']['ra4']['returncode']==1,'v1 failure')
 check(any('CAMtr' in f.read_text() for f in (P/'v1/ra4').glob('rsl.error.*')),'CAM setup evidence')
 plan=read('v2/pair-plan.json');assets=read('v2/runtime-link-manifest.json')
 check(plan['source_commit']=='e7c97ed661403b3922fcf752300c052611ef89cd','winter source commit')
 check(assets['runtime_source_file_count']==94,'runtime source count')
 for arm,a in assets['arms'].items():
  check(len(a)==94,'runtime arm count')
  for e in a:
   if e['kind']=='arm_owned_file':check(e['name']=='namelist.input' and e['case_regular_file'] and not e['case_is_symlink'],'case owned namelist')
   elif e['kind']=='pinned_executable_override':check(e['name']=='wrf.exe' and e['matches_plan_expected'] and e['sha256']==plan['wrf_executable_sha256'],'exe override')
   else:check(e['matches_plan_expected'] and e['matches_source'],'common asset')
 for arm,ra,mode in [('ra4',4,0),('ra37',37,1)]:
  a=plan['arms'][arm];check(a['ra_lw']==a['ra_sw']==ra and a['mode']==mode,'physics policy')
 check(plan['common_case_settings']['mp_physics']==27 and plan['common_case_settings']['use_mp_re']==1,'microphysics policy')
 check(sha(P/'v2/run_pair.py')==plan['run_pair.py_sha256'] and sha(P/'v2/runtime-link-manifest.json')==plan['runtime-link-manifest.json_sha256'],'executed runner/assets pins')
 run=read('v2/run-receipt.json');check(run['status']=='FORECAST_FAILED' and run['errors']==[],'paired failure')
 for k in ['pins_unchanged','runner_plan_namelists_unchanged','runtime_directory_files_unchanged']:check(run[k] is True,k)
 for field,pin in [('wrfinput','0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637'),('wrfbdy','ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4')]:
  check(run['input_sha256']['ra4'][field]==run['input_sha256']['ra37'][field]==pin,'common '+field)
 for arm in ['ra4','ra37']:check(sha(P/'v2'/arm/'namelist.input')==run['input_sha256'][arm]['namelist'],'namelist pin')
 ra4=run['arms']['ra4'];ra37=run['arms']['ra37']
 check(ra4['status']=='FORECAST_PASS' and ra4['returncode']==0 and len(ra4['success_ranks'])==4,'RA4 completion')
 check(ra37['status']=='FORECAST_FAILED' and ra37['returncode']==1 and ra37['success_ranks']==[],'RA37 incomplete')
 out=ra4['outputs'];check(len(out['history_times'])==25 and out['history_times'][-1]=='2000-01-25_12:00:00','RA4 times')
 check(out['history_numeric_variables']==221,'history variable count')
 zeros(out,['history_decoded_nonfinite','history_raw_nonfinite','history_fill_hits','history_masked'])
 for r in out['restart_numeric_validation']:
  check(r['numeric_validation']['numeric_variables']==663,'restart variables');zeros(r['numeric_validation'],['decoded_nonfinite','raw_nonfinite','fill_value_hits','masked_values'])
 check(read('real/root-real-output-readback.json')['all_numeric_raw_and_decoded_finite_unmasked_nonfill'] is True,'real root checks')
 check(read('v2/root-ra4-24h-readback.json')['status']=='PASS_SCOPED_RA4_ONLY','root RA4 scope')
 ca=read('analysis-original/causality-analysis.json');fatal=ca['fatal']
 check(fatal['model_time_from_driver_log']=='2000-01-24_14:50:00' and fatal['rank']=='rsl.error.0002','fatal time/rank')
 check(fatal['fatal_cell_fortran_1based']=={'i_fortran':17,'j_fortran':58,'k_fortran':7},'fatal cell')
 check(fatal['fatal_mixing_ratio_kgkg']==-5.623554244493789e-8 and fatal['allowed_native_negative_only_limit_kgkg']==9.999999960041972e-13,'fatal values')
 check(math.isclose(fatal['fatal_magnitude_over_limit'],abs(fatal['fatal_mixing_ratio_kgkg'])/1e-12,rel_tol=1e-14),'original ratio uses nominal 1e-12 ceiling')
 check(read('summary.json')['fatal_ratio_using_printed_limit']==abs(fatal['fatal_mixing_ratio_kgkg'])/fatal['allowed_native_negative_only_limit_kgkg'],'printed-limit ratio')
 check(fatal['exact_line'] in (P/'v2/ra37/rsl.error.0002').read_text(),'actual fatal log')
 check([r['time'] for r in ca['ra37_partial']['records']]==['2000-01-24_12:00:00','2000-01-24_13:00:00','2000-01-24_14:00:00'],'partial times')
 check(sha(P/'analysis-original/analyze_partial.py')==ca['artifacts']['analysis_script_sha256'],'analysis script pin')
 eq=read('source/source-equivalence.json')
 check(eq['status']=='PR26_BASE_MATCHES_ACTUAL_TRACKED_PRODUCTION_SOURCE' and eq['production_differences']==[] and eq['all_runtime_tracked_WRF_regular_file_bytes_match_runtime_commit'] is True,'production match')
 check(len(eq['all_WRF_differences'])==4 and all(e['path'].startswith('WRF/test/') for e in eq['all_WRF_differences']),'test-only differences')
 actual=read('source/actual-winter-call-order-recheck.json');check(actual['preserved_analysis_sha256']==sha(P/'analysis-original/causality-analysis.json'),'analysis erratum link')
 check(actual['actual_commit']=='e7c97ed661403b3922fcf752300c052611ef89cd','actual source pin')
 extracts=actual['files']['WRF/dyn_em/module_first_rk_step_part1.F']['extracts']
 check(any('CALL radiation_driver' in l for e in extracts for l in e['lines']),'actual radiation source')
 check(any('CALL microphysics_driver' in l for e in actual['files']['WRF/dyn_em/solve_em.F']['extracts'] for l in e['lines']),'actual MP source')
 official=read('official-ra4/posthoc-comparison.json');check(official['status']=='POSTHOC_RUNTIME_AND_RAW_COMPARISON_COMPLETE','official posthoc')
 check(sha(P/'official-ra4/prepare-pristine-jan-ra4.py')==official['runner_sha256'],'official executed runner pin')
 check(sha(P/'official-ra4/build/configure.wrf')==official['official_source']['configure_sha256'],'official configure pin')
 check(sha(P/'source/configure.wrf')==plan['configure_sha256'],'winter configure pin')
 check(read('official-ra4/run-receipt.json')['status']=='RUN_FAILED_OR_VALIDATION_FAILED','original guard preserved')
 check(official['original_runner_receipt_sha256']==sha(P/'official-ra4/run-receipt.json'),'original receipt link')
 check(official['static_recheck']['all_pre_post_fields_equal_except_raw_ldd_addresses'] is True,'ASLR-only guard')
 deps=official['runtime_dependency_recheck'];check(deps['normalized_dependencies_equal'] and deps['unique_paths_and_hashes_equal'] and len(deps['pre_run'])==52,'dependency recheck')
 for v in official['run_completion']['four_rank_success_logs'].values():check(v['success_complete'] and v['fatal_markers']==[],'official rank completion')
 check(len(official['run_completion']['four_rank_success_logs'])==4,'official four ranks')
 cmp=official['comparison'];check(cmp['common_variable_count']==cmp['variable_metadata_exact_count']==222,'all vars metadata')
 check(cmp['asymmetric_variables']==[] and cmp['global_attribute_differences']==[] and cmp['variable_metadata_differences']==[] and cmp['raw_byte_difference_count']==0,'official parity')
 check(cmp['candidate_times']==cmp['reference_times']==out['history_times'],'official times')
 h='edf0cfbf4efeecbbf69e979c8f4fc21a19a436f4329a3e11330a2c569ea0bcc4'
 check(cmp['candidate_sha256']==cmp['reference_sha256']==out['history']['sha256']==h,'whole history pin')
 hv=official['history_validation'];check(hv['numeric_variable_count']==221,'official numeric count');zeros(hv,['fill_hits','nonfinite'])
 check([hv['dimension_lengths'][n] for n in ['west_east','south_north','bottom_top']]==[73,60,32],'geometry')
 root=read('official-ra4/root-whole-file-identity.json');check(root['whole_file_byte_identity'] and root['bytes']==192549864 and root['official_history_sha256']==root['patched_ra4_history_sha256']==h,'root whole file')
 for name,r in official['restart_validations'].items():
  check(r['numeric_variable_count']==663,'official restart count');zeros(r,['fill_hits','nonfinite'])
  check(r['sha256'] not in [v['sha256'] for v in out['restarts']],'no restart equality claim')
 rootobs=read('observations/root-observation-hourly-readback.json')
 check(rootobs['comparison_rows']==234 and rootobs['independent_raw_observation_samples_per_station']==480 and rootobs['negative_QC0_samples_preserved'] and rootobs['max_obs_mean_discrepancy_W_m2']<=1.14e-13,'root raw observation reaggregation')
 obs=read('observations/verified_observations.json');metrics=read('observations/model_observation_comparison.json')
 check(obs['record_interval_seconds']==180 and obs['expected_records_per_hour_channel']==20 and obs['negative_qc0_values_are_retained'] is True,'observation policy')
 check(obs['no_fill_or_interpolation'] is True,'observation interpolation policy')
 check(metrics['immutable_inputs_sha256_before_after']['same'] and metrics['offline_fixture_checks']['status']=='PASS' and not metrics['offline_fixture_checks']['engine_executed'],'observational guard/fixture')
 check(metrics['analysis_script']['sha256']==sha(P/'observations/compare_wrf_outputs.py'),'comparison source pin')
 check(obs['parser_sha256']==sha(P/'observations/verify_surfrad.py') and obs['test_sha256']==sha(P/'observations/test_verify_surfrad.py'),'observation parser/test pins')
 check(metrics['observation_provenance']['verified_receipt_sha256']==sha(P/'observations/verified_observations.json'),'observation receipt link')
 check(metrics['observation_provenance']['hourly_csv_sha256']==sha(P/'observations/hourly_observations.csv'),'observation csv pin')
 check(metrics['csv_sha256']==sha(P/'observations/model_hourly_comparison.csv'),'model interval csv pin')
 check(metrics['model_provenance']['pair_plan_sha256']==sha(P/'v2/pair-plan.json') and metrics['model_provenance']['run_receipt_sha256']==sha(P/'v2/run-receipt.json'),'observation model link')
 external=read('observations/external-observation-artifacts.json')['files'];check(len(external)==8,'external observation/doc inventory')
 raw={PurePosixPath(e['path']).name:e['sha256'] for e in external if e['path'].endswith('.dat')}
 check(raw==metrics['observation_provenance']['raw_sha256'] and len(raw)==6,'raw six-file pins')
 def close(a,b,label):check(math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-10),'CSV arithmetic '+label)
 with (P/'observations/hourly_observations.csv').open(newline='') as f:orows=list(csv.DictReader(f))
 check(len(orows)==432,'observed hourly rows')
 omap={}
 for r in orows:
  check(r['complete']=='True' and all(int(r[k])==20 for k in ['expected_records','records_present','qc0_usable']),'complete QC0 hour')
  k=(r['station'],r['channel'],r['hour_start_utc'],r['hour_end_utc']);check(k not in omap,'duplicate observation interval');omap[k]=r
  x=float(r['mean_flux_W_m-2']);check(math.isfinite(x),'finite observation mean');close(x*3600,float(r['energy_J_m-2']),'observation energy')
 with (P/'observations/model_hourly_comparison.csv').open(newline='') as f:rows=list(csv.DictReader(f))
 check(len(rows)==234,'all RA4/RA37 comparison rows')
 groups={};windows={}
 for r in rows:
  arm,site,var=r['arm'],r['station'],r['variable'];check(arm in ['RA4','RA37'] and site in ['GWN','PSU','BON'] and var in ['down_sw','down_lw','net_sw_surface'],'comparison labels')
  vals=[float(r[k]) for k in ['obs_mean_W_m-2','obs_energy_J_m-2','model_accumulator_delta_J_m-2','model_mean_W_m-2','bias_model_minus_obs_W_m-2']];check(all(math.isfinite(v) for v in vals),'finite CSV')
  ob,oe,delta,model,error=vals;close(delta/3600,model,'model accumulator');close(ob*3600,oe,'observed energy');close(model-ob,error,'bias')
  a,b=r['interval_start_utc'],r['interval_end_utc'];base=(site,'dw_solar' if var!='down_lw' else 'dw_ir',a,b);expected=float(omap[base]['mean_flux_W_m-2'])
  if var=='net_sw_surface':expected-=float(omap[(site,'uw_solar',a,b)]['mean_flux_W_m-2'])
  close(ob,expected,'observed channel mapping');key=(arm,site,var);groups.setdefault(key,[]).append(error)
  wk=(arm,site,var,a,b);check(wk not in windows,'duplicate model interval');windows[wk]=model
  if arm=='RA37':check(b in ['2000-01-24T13:00:00Z','2000-01-24T14:00:00Z'],'partial RA37 window')
 def score(v):return {'n':len(v),'bias_model_minus_obs_W_m-2':sum(v)/len(v),'MAE_W_m-2':sum(abs(x) for x in v)/len(v),'RMSE_W_m-2':math.sqrt(sum(x*x for x in v)/len(v)),'min_error_W_m-2':min(v),'max_error_W_m-2':max(v)}
 for (arm,site,var),v in groups.items():
  check(len(v)==(24 if arm=='RA4' else 2),'available interval count')
  for k,x in score(v).items():close(x,metrics['scores_all_available_intervals'][arm][site][var][k],k)
 check(len(groups)==18,'all sites/phases/variables')
 for site,variables in metrics['scores_common_two_hours_and_pair_difference'].items():
  for var,m in variables.items():
   check(m['n_intervals']==2,'paired partial scope');diff=[];common={'RA4':[],'RA37':[]}
   for r in rows:
    if r['station']==site and r['variable']==var and r['interval_end_utc'] in ['2000-01-24T13:00:00Z','2000-01-24T14:00:00Z']:
     common[r['arm']].append(float(r['bias_model_minus_obs_W_m-2']))
     if r['arm']=='RA37':diff.append(float(r['model_mean_W_m-2'])-windows[('RA4',site,var,r['interval_start_utc'],r['interval_end_utc'])])
   for arm,v in common.items():
    for k,x in score(v).items():close(x,m[arm+'_common_2h'][k],k)
   close(sum(diff)/2,m['RA37_minus_RA4_mean_W_m-2'],'paired difference')
 print('PASS:',len(entries),'retained artifacts; archive24h, RA4 baseline identity, RA37 failure OPEN; CSV score arithmetic checked; no runtime calls')
if __name__=='__main__':main()
