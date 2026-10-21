"""Decisions and bounded claims from actual spatial and fixed-period evidence."""
import math
from datetime import datetime

def require(x,m):
 if not x:raise ValueError(m)
def summarize(spatial,run,history):
 fields=['dW','P_full','E_native_support','QFX_outer_unapplied','advection_operator','relaxation','specified_tendency','final_MU','final_q','PBL','CU','microphysics','PBL_minus_E','CU_plus_RAINC_full','CU_plus_RAINC_interior','RAINC_outer_kept','CU_active_paired_residual','CU_inactive_positive_rain','CU_tendency_without_positive_rain','microphysics_plus_its_RAINNC','other_physics_mixing','PD_arithmetic','RK_arithmetic','source_assembly_to_PD_change','other_final_RK_source','evaluation_bridges','operator_reconstruction_residual','stock_surface_boundary_residual','CU_rate_counter_rounding','CU_addition_rounding','RAINC_change_outside_advance_ppt','RAINNC_change_outside_microphysics','RAINSH_increment_full']
 total={k:math.fsum(w[k] for w in run['water_steps']) for k in fields}
 rad=[]
 for h in run['hourly_water']:
  rr=[r for r in run['radiation_steps'] if h['start_s']<=r['source_time_s']<h['end_s']];dur=len(rr)*60
  item={'hour':h['hour'],'seconds':dur,'actual_RHS_radiation_equivalent_J_m2':math.fsum(r['RHS_radiation_equivalent_J_m2'] for r in rr)}
  for scope in ['full','interior']:
   item['raw_source_'+scope+'_equivalent_J_m2']=math.fsum(r['raw_source_'+scope+'_W_m2']*60 for r in rr)
  for i,name in enumerate(['LW','SW']):
   known=[r['native_flux'][i] for r in rr if r['native_flux'][i]['current_radiation_phase_observed']]
   item[name]={'observed_phase_seconds':60*len(known),'missing_phase_seconds':dur-60*len(known),'native_convergence_integral_of_observed_phases_J_m2':math.fsum(x['native_convergence']*60 for x in known),'extended_TOA_net_integral_of_observed_phases_J_m2':math.fsum(x['extended_TOA_net']*60 for x in known),'observed_column_count_min_max':[min(x['observed_columns'] for x in known),max(x['observed_columns'] for x in known)] if known else None}
   item[name]['incomplete_spatial_phase_seconds']=60*sum(not x['complete_spatial_observation'] for x in known)
   for field in ['native_interior_convergence','pressure_mass_heating','dry_mass_heating']:
    item[name][field+'_integral_of_observed_phases_J_m2']=math.fsum(x[field]*60 for x in known)
  rad.append(item)
 frozen=[]
 for species in ['graupel','hail']:
  ff=[f for f in run['frozen_calls'] if f['species']==species];positive=[f for f in ff if f['path_kg_m2']>0]
  weight=lambda f:min(600,run['completed_end_s']-f['source_time_s'])
  path=math.fsum(f['path_kg_m2']*weight(f) for f in ff)
  end=math.fsum(f['lambda_20000_endpoint_path_kg_m2']*weight(f) for f in ff)
  warm=math.fsum(f['above_273_15K_path_kg_m2']*weight(f) for f in ff)
  frozen.append({'species':species,'LW_calls':len(ff),'call_hold_weighted_path_kg_s_m2':path,'endpoint_20000_path_fraction':end/path if path else None,'above_273_15K_ambient_layer_path_fraction':warm/path if path else None,'outside_table_path_kg_s_m2':math.fsum(f['outside_table_path_kg_m2']*weight(f) for f in ff),'lambda_min_max':[min(f['lambda_min_max'][0] for f in positive),max(f['lambda_min_max'][1] for f in positive)] if positive else None,'ambient_temperature_min_max_K':[min(f['temperature_min_max'][0] for f in positive),max(f['temperature_min_max'][1] for f in positive)] if positive else None,'largest_path_call':max(positive,key=lambda f:f['path_kg_m2']) if positive else None,'note':'Actual supplied LW input exposure weighted by the source hold interval. Not actual hydrometeor residence-time integration, optical error, or pre-limit PSD proof.'})
 joined=[]
 for old in spatial['steps']:
  t=old['source_time_s'];matches=[w for w in run['water_steps'] if w['source_time_s']==t]
  if not matches:continue
  w=matches[0];cat=next(c for c in run['CU_categories'] if c['source_time_s']==t)
  require(abs(w['CU']-old['actual_CU_moisture_increment_kg_m2'])<1e-12,'original actual CU source changed')
  require(abs(w['CU_plus_RAINC_interior']-old['CU_plus_interior_precipitation_kg_m2'])<1e-12,'same-support result changed in sustained run')
  joined.append({'source_time_s':t,'same_support_CU_residual':w['CU_plus_RAINC_interior'],'active_paired_residual':w['CU_active_paired_residual'],'inactive_positive_rain':w['CU_inactive_positive_rain'],'source_without_positive_rain':w['CU_tendency_without_positive_rain'],'counter_rounding':w['CU_rate_counter_rounding'],'tendency_addition_rounding':w['CU_addition_rounding'],'column_categories':cat,'expiry':next(e for e in run['expiry_events'] if e['source_time_s']==t)})
 states=history['states'];qnames=list(states[0]['quality'])
 quality={n:{'min':min(s['quality'][n]['min'] for s in states),'max':max(s['quality'][n]['max'] for s in states),'negative_elements':sum(s['quality'][n]['negative_elements'] for s in states),'nonfinite_elements':sum(s['quality'][n]['nonfinite_elements'] for s in states)} for n in qnames}
 retained=[c for c in run['CU_categories'] if not c['CU_driver_scheduled'] and c['previous_post_expiry_inactive_rain_kg_m2_for_60s'] is not None]
 maxmemory=max((abs(c['inactive_rain_change_across_step_start_kg_m2']) for c in retained),default=0)
 stocks={w['source_time_s']:w['W_start_kg_m2'] for w in run['water_steps']}
 stocks[run['completed_end_s']]=run['water_steps'][-1]['W_end_kg_m2']
 stock_comparison=[]
 for s in states:
  t=int((datetime.strptime(s['time'],'%Y-%m-%d_%H:%M:%S')-datetime(2016,10,6)).total_seconds())
  if t in stocks:stock_comparison.append({'time':s['time'],'history_minus_operator_stock_kg_m2':s['W_kg_m2']-stocks[t]})
 numeric_nonfinite=sum(pin['nonfinite_numeric_elements'] for rows in history['array_inventory'].values() for pin in rows.values())
 negative_vapor=[{'time':s['time'],**s['negative_vapor']} for s in states if s['negative_vapor'] is not None]
 return {'status':run['status'],'target_period_completed':run['target_period_completed'],'planned_seconds':86400,'completed_seconds':run['completed_end_s'],'model_steps':run['completed_steps'],'history_records':history['records'],'completed_spatial_comparison':spatial,'original_three_minute_timing_attribution':joined,'whole_period_water_terms_kg_m2':total,'hourly_water':run['hourly_water'],'hourly_radiation':rad,'history_operator_stock_comparison':stock_comparison,'frozen_input_exposure':frozen,'hourly_history_quality':quality,'hourly_history_numeric_nonfinite_elements':numeric_nonfinite,'hourly_negative_vapor_states':negative_vapor,'history_temperature_min_max_K':[min(s['temperature_from_history_K_min_max'][0] for s in states),max(s['temperature_from_history_K_min_max'][1] for s in states)],'original_trajectory_overlap':history['original_overlap'],'off_schedule_CU_memory_checks':len(retained),'max_off_schedule_inactive_rain_change_kg_m2':maxmemory,'decisions':{'spatial_question':'closed: preserve outer precipitation separately and native counter-sum rounding separately; the remaining interior residual is real as a source/counter comparison','time_question':'actual native expiry zeros five moisture tendencies while retaining PRATEC; off-schedule next-step positive precipitation on inactive columns is measured separately','paired_columns':'remaining active paired and source-without-positive-rain differences retained; mass normalization/process adequacy not approved','runtime_scope':'the planned fixed real-data period is evaluated as recorded; no policy, source, coefficient, time-step or guard changes','physical_application':'research-only configuration retained; no empirical correction or physical conservation approval'},'water_conservation_approved':False,'whole_energy_approved':False,'frozen_accuracy_approved':False,'forecast_skill_approved':False,'missing':run['missing'],'original_seven_conditions_changed':False,'new_model_runs_in_saved_replay':0}
