"""Connect native causes, corrections, and the unchanged real-data evaluation."""
from pathlib import Path
import importlib.util,json,math
from datetime import datetime
P=Path(__file__).resolve().parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('vapor_actual_operands',P/'analyze.py');B=load('corrected_actual_budget',P/'analyze_run_corrected.py')
require=A.require

def evaluate(d):
 model_processes=[]
 for name,raw in d.items():
  if not name.endswith('/receipt.json'):continue
  receipt=json.loads(raw)
  for command in receipt.get('commands',[]):
   argv=command['argv']
   if argv and argv[0]=='bash' and any(str(x).endswith('/wrf') for x in argv):
    model_processes.append({'deposit':name[:-13],'kind':command['kind'],'returncode':command['actual_returncode'],'executable_sha256':receipt['executable']['sha256']})
 require(len(model_processes)==12,'actual model-process inventory changed')
 causes=A.causes(d['original/host/vapor-first.txt'].decode(),d['components/host/vapor-components.txt'].decode())
 faces=A.face_replay(d['flux/host/vapor-flux.txt'].decode(),causes['first_final_transport'])
 comp=A.comparisons({n:json.loads(d[p]) for n,p in [('original_first','original/history-comparison.json'),('original_components','components/history-comparison.json'),('corrected_observer','short_observed/history-comparison.json'),('corrected_restart','restart/history-comparison.json')]})
 copy_comparison=json.loads(d['copy-comparison.json']);require(copy_comparison['pairs']==5625 and not copy_comparison['differences'],'tile-local copy changed the serial full-day trajectory')
 for rows in copy_comparison['inventory'].values():
  require(len(rows)==225,'tile copy array omission')
  for row in rows.values():require(row['equal'] and row['left_sha256']==row['right_sha256'],'tile-copy hash mismatch')
 native_source=A.native_source(d['public/command-08.stdout'].decode());native_flux=A.native_transport(d['native_transport/command-03.stdout'].decode())
 day=json.loads(d['day/receipt.json']);run=B.analyze(d['day/host/real-budget.txt'].decode(),day)
 state=A.vapor(d['day/host/vapor-first.txt'].decode());history=json.loads(d['history.json'])
 require(run['target_period_completed'] and run['completed_steps']==1440,'same real-data day incomplete')
 require(state['source_steps']==1440,'final-stage vapor coverage incomplete')
 for tag,rk in [('pd',3),('rk',3),('micro',0),('final_bdy',4)]:
  require([x['source_s'] for x in state['summaries'] if x['tag']==tag and x['rk']==rk]==list(range(0,86400,60)),'missing or duplicated final-stage observations '+tag)
 require(history['records']==25,'hourly/terminal history coverage incomplete')
 require(all(len(x)==225 for x in history['array_inventory'].values()),'history variable omission')
 totals={k:math.fsum(w[k] for w in run['water_steps']) for k in run['water_steps'][0] if k not in ['source_time_s','end_time_s','W_start_kg_m2','W_end_kg_m2']}
 quality={n:{'minimum':min(s['quality'][n]['min'] for s in history['states']),'negative_samples':sum(s['quality'][n]['negative_elements'] for s in history['states']),'nonfinite_samples':sum(s['quality'][n]['nonfinite_elements'] for s in history['states'])} for n in history['states'][0]['quality']}
 numeric_nonfinite=sum(x['nonfinite_numeric_elements'] for rows in history['array_inventory'].values() for x in rows.values())
 stocks={w['source_time_s']:w['W_start_kg_m2'] for w in run['water_steps']};stocks[86400]=run['water_steps'][-1]['W_end_kg_m2']
 history_stocks=[]
 for sample in history['states']:
  t=int((datetime.strptime(sample['time'],'%Y-%m-%d_%H:%M:%S')-datetime(2016,10,6)).total_seconds())
  require(t in stocks,'history outside operator period')
  history_stocks.append({'time':sample['time'],'history_minus_operator_W_kg_m2':sample['W_kg_m2']-stocks[t]})
 old=json.loads((P.parent/'convective-support/result.json').read_text())
 oldwater=old['whole_period_water_terms_kg_m2'];change={k:{'original':oldwater[k],'corrected':totals[k],'difference':totals[k]-oldwater[k]} for k in oldwater if k in totals}
 rad=math.fsum(r['RHS_radiation_equivalent_J_m2'] for r in run['radiation_steps'])
 raw=math.fsum(r['raw_source_interior_W_m2']*60 for r in run['radiation_steps'])
 coverage={}
 for i,n in enumerate(['LW','SW']):
  known=[r['native_flux'][i] for r in run['radiation_steps'] if r['native_flux'][i]['current_radiation_phase_observed']]
  coverage[n]={'observed_phase_seconds':len(known)*60,'missing_phase_seconds':86400-len(known)*60,'spatially_incomplete_observed_seconds':sum(not x['complete_spatial_observation'] for x in known)*60,'isolated_acoustic_state_increment_measured':False}
 frozen=[]
 for species in ['graupel','hail']:
  ff=[f for f in run['frozen_calls'] if f['species']==species]
  exposure=lambda field:math.fsum(f[field]*min(600,86400-f['source_time_s']) for f in ff)
  path=exposure('path_kg_m2')
  frozen.append({'species':species,'LW_calls':len(ff),'call_hold_weighted_path_kg_s_m2':path,'above_273_15K_ambient_layer_path_fraction':exposure('above_273_15K_path_kg_m2')/path if path else None,'endpoint_20000_path_fraction':exposure('lambda_20000_endpoint_path_kg_m2')/path if path else None,'outside_table_path_kg_s_m2':exposure('outside_table_path_kg_m2'),'optical_accuracy_approved':False})
 nca_nonpositive_rain=math.fsum(col['rain_on_NCA_nonpositive_kg_m2'] for c in run['CU_categories'] for col in c['columns'])
 expiry=run['expiry_events'];require(any(e['selected_PRATEC_before_kg_s']>0 for e in expiry),'no positive expiry event observed');require(all(e['selected_PRATEC_after_kg_s']==0 for e in expiry),'expired rate retained')
 return {'status':'CORRECTED_SAME_REAL_DAY_EVALUATED','actual_model_processes_in_this_deposit':model_processes,'independent_meteorological_cases':1,'causes':causes,'actual_face_replay':faces,'history_comparisons':comp,'tile_local_copy_serial_full_day_pairs':copy_comparison['pairs'],'native_source_cases':native_source,'native_shared_flux_cases':native_flux,'corrected_period_seconds':86400,'model_steps':1440,'history_records':25,
 'final_stage_vapor':{k:v for k,v in state.items() if k not in ['events','summaries']},'hourly_quality':quality,'hourly_numeric_nonfinite_samples':numeric_nonfinite,'hourly_water_and_number_nonnegative':all(q['negative_samples']==0 for q in quality.values()),
 'vapor_final_nonnegative_criterion_passed':state['final_stage_negative_samples']==0 and state['final_stage_minimum']>=0 and quality['QVAPOR']['negative_samples']==0,
 'KFETA_expired_rate_criterion_passed':all(e['selected_PRATEC_after_kg_s']==0 for e in expiry),'NCA_nonpositive_precipitation_kg_m2':nca_nonpositive_rain,'expired_interior_column_events':sum(e['expired_interior_columns'] for e in expiry),
 'whole_period_water_terms_kg_m2':totals,'comparison_to_original_water':change,'hourly_water':run['hourly_water'],'history_operator_stock_comparison':history_stocks,
 'radiation_source_equivalent_J_m2':rad,'raw_source_interior_equivalent_J_m2':raw,'actual_minus_raw_source_equivalent_J_m2':rad-raw,'radiation_phase_coverage':coverage,'frozen_input_exposure':frozen,
 'original_trajectory_differences':history['original_overlap'],'restart_scope':'corrected cold run checkpoint at original 05:59; public restart compared at 06:00 and 07:00, all 225 arrays at both times; distinct from historical PR189 675/675',
 'source_accounting':'actual applied relaxation delta retained in B_relax; shared face flux limiter before divergence, no scalar clipping source; predictor RK undershoots preserved separately',
 'water_conservation_approved':False,'whole_energy_approved':False,'frozen_accuracy_approved':False,'forecast_skill_approved':False,'original_seven_conditions_changed':False,'missing':run['missing'],'new_model_runs_in_saved_replay':0}
