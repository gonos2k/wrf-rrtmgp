"""Match states and sampling supports; their differences are not process tendencies."""
from common import *
import datetime as dt
def value(profile,p,n):
 r=interpolate(profile,p,n)
 return r['value'] if r else None
def press(profile):
 out=[]
 for p in PRESSURES:
  row={'pressure_Pa':p}
  for n in ['T_K','dry_theta_K','qv_kg_kg','RH_water_ratio','wind_u_east_m_s','wind_v_north_m_s','U_grid_m_s','V_grid_m_s','W_geometric_m_s','QCLOUD','QRAIN','CLDFRA_held_diagnostic','z_agl_m']:
   row[n]=value(profile,p,n)
  if row['dry_theta_K'] is None and row['T_K'] is not None:row['dry_theta_K']=theta(row['T_K'],p)
  out.append(row)
 return out
def analyze(data,obs,old):
 require(data['selected_i_j_one_based']==[37,119] and data['shape_j_i']==[143,90] and data['new_model_runs']==0,'fixed geometry/experiment changed')
 model={r['hour_UTC']:r for r in data['model']};require(sorted(model)==[0,6,11,12,13,14,15,16,17,18,19,20,23,24],'hour selection');rows={h:press(r['profiles']) for h,r in model.items()};sondes={s['nominal_UTC']:s for s in obs['soundings']}
 profiles=[{'hour_UTC':h,'pressure_rows':rows[h],'surface':model[h]['surface'],'low_native_levels':[r for r in model[h]['profiles'] if 0<=r['z_agl_m']<=2500],'scope':'hourly state, not native process tendency or fresh radiation sample mask'} for h in model]
 pairs=[]
 for nominal,hours in [('2016-10-06T12:00:00+00:00',[11,12]),('2016-10-06T18:00:00+00:00',[17,18]),('2016-10-07T00:00:00+00:00',[23,24])]:
  s=sondes[nominal];release=dt.datetime.fromisoformat(s['release_UTC'])
  for h in hours:
   mt=dt.datetime.fromisoformat(model[h]['time_UTC'].replace('_','T')).replace(tzinfo=dt.timezone.utc)
   for p in PRESSURES:
    elapsed=interpolate(s['levels'],p,'elapsed_s');when=release+dt.timedelta(seconds=elapsed['value']) if elapsed else None;fields={}
    for of,mf in [('T_K','T_K'),('qv_from_dewpoint_kg_kg','qv_kg_kg'),('RH_water_from_dewpoint_ratio','RH_water_ratio')]:
     o=interpolate(s['levels'],p,of);m=interpolate(model[h]['profiles'],p,mf);fields[mf]={'observation':o,'model':m,'model_minus_observation':m['value']-o['value'] if o and m else None}
    pairs.append({'nominal_sounding_UTC':nominal,'release_UTC_HHMM_second00':s['release_UTC'],'model_hour_UTC':h,'pressure_Pa':p,'observed_level_UTC_HHMM_second00_and_logp_elapsed':when.isoformat() if when else None,'model_minus_observation_time_s':(mt-when).total_seconds() if when else None,'fields':fields})
 # Select no best-performing time: retain both near-release and old nominal pairs.
 state=[]
 for h in range(11,19):
  a,b=[next(r for r in rows[h] if r['pressure_Pa']==p) for p in [95000,92500]];native=model[h]['profiles'];low=[(x,y) for x,y in zip(native,native[1:]) if 300<=x['z_agl_m']<y['z_agl_m']<=2500];strong=max(low,key=lambda z:z[1]['T_K']-z[0]['T_K'])
  state.append({'hour_UTC':h,'T925_minus_T950_K':b['T_K']-a['T_K'],'theta925_minus_theta950_K':theta(b['T_K'],92500)-theta(a['T_K'],95000),'strongest_adjacent_native_T_increase_K':strong[1]['T_K']-strong[0]['T_K'],'strongest_native_lower_upper_AGL_m':[strong[0]['z_agl_m'],strong[1]['z_agl_m']],'column_cloudwater_g_m2':sum(r['QCLOUD']*r['layer_dry_mass_kg_m2']*1000 for r in native),'PBLH_m_not_observed_inversion':model[h]['surface']['PBLH']})
 development=[]
 for p in PRESSURES:
  rec={'pressure_Pa':p};s0=sondes['2016-10-06T12:00:00+00:00'];s1=sondes['2016-10-06T18:00:00+00:00']
  for field,of in [('T_K','T_K'),('qv_kg_kg','qv_from_dewpoint_kg_kg')]:
   a=value(s0['levels'],p,of);b=value(s1['levels'],p,of);rec['observation_change_'+field]=b-a if a is not None and b is not None else None
   for start in [11,12]:
    a=value(model[start]['profiles'],p,field);b=value(model[18]['profiles'],p,field);rec[f'model_{start}_18_change_'+field]=b-a if a is not None and b is not None else None
  rec['scope']='observed actual level times differ from model endpoint hours; state changes, not identical-period process sources';development.append(rec)
 source=[];mapping={'t':'TT','r':'RH','u':'UU','v':'VV','gh':'HGT'}
 for forcing in data['forcing']:
  differences=[];matched=[]
  for g in forcing['GRIB']['rows']:
   im=next((r for r in forcing['intermediate'] if r['field']==mapping[g['shortName']] and r['p_Pa']==g['p_Pa']),None)
   if im is None:continue
   for a in g['corners']:
    b=next(r for r in im['corners'] if r['lat']==a['lat'] and r['lon']==a['lon']);delta=b['value']-f32(a['value']);differences.append({'field':im['field'],'p_Pa':im['p_Pa'],'lat_lon':[a['lat'],a['lon']],'GRIB_decoded_to_REAL32':f32(a['value']),'intermediate_REAL32':b['value'],'difference':delta})
   matched.append({'field':im['field'],'p_Pa':im['p_Pa'],'GRIB_bilinear':g['bilinear_value'],'intermediate_bilinear':im['bilinear_value']})
  byp={}
  for row in forcing['met_em']['profiles']:
   p=row['p_Pa'];gc={r['shortName']:r['bilinear_value'] for r in forcing['GRIB']['rows'] if r['p_Pa']==p};ic={r['field']:r['bilinear_value'] for r in forcing['intermediate'] if r['p_Pa']==p}
   byp[p]={'pressure_Pa':p,'GRIB_bilinear_T_K':gc.get('t'),'GRIB_bilinear_RH_percent':gc.get('r'),'GRIB_bilinear_qv_REAL_method1_diagnostic':real_qv(gc['t'],p,gc['r']) if 't' in gc and 'r' in gc else None,'intermediate_bilinear_T_K':ic.get('TT'),'intermediate_bilinear_RH_percent':ic.get('RH'),'met_em_T_K':row['T_K'],'met_em_RH_percent':row['source_RH_percent'],'met_em_qv_REAL_method1_diagnostic':row['qv_kg_kg_REAL_method1_diagnostic'],'met_em_native_water_RH':row['RH_water_ratio'],'met_em_minus_GRIB_T_K':row['T_K']-gc['t'] if 't' in gc else None,'met_em_minus_GRIB_RH_percentage_points':row['source_RH_percent']-gc['r'] if 'r' in gc else None}
  source.append({'hour_UTC':forcing['hour_UTC'],'matched_GRIB_intermediate_corner_values':len(differences),'corner_differences':differences,'max_absolute_GRIB_to_intermediate_difference_by_field':{f:max(abs(r['difference']) for r in differences if r['field']==f) for f in set(r['field'] for r in differences)},'matched_bilinear_fields':matched,'pressure_rows':[byp[p] for p in PRESSURES if p in byp],'scope':'GRIB/intermediate share surrounding global points; met_em uses its actual horizontal interpolation. Small differences are described, not a proof of complete ungrib identity or a new physical tolerance'})
 source_observation=[]
 for nominal,h in [('2016-10-06T12:00:00+00:00',12),('2016-10-06T18:00:00+00:00',18),('2016-10-07T00:00:00+00:00',24)]:
  s=sondes[nominal];forcing=next(x for x in source if x['hour_UTC']==h)
  for x in forcing['pressure_rows']:
   p=x['pressure_Pa'];T=value(s['levels'],p,'T_K');q=value(s['levels'],p,'qv_from_dewpoint_kg_kg')
   source_observation.append({'source_hour_UTC':h,'pressure_Pa':p,'observed_T_K':T,'observed_qv':q,'GRIB_minus_observed_T_K':x['GRIB_bilinear_T_K']-T if T is not None and x['GRIB_bilinear_T_K'] is not None else None,'met_em_minus_observed_T_K':x['met_em_T_K']-T if T is not None else None,'met_em_minus_observed_qv_g_kg':1000*(x['met_em_qv_REAL_method1_diagnostic']-q) if q is not None else None,'scope':'same fixed horizontal sample and pressure, different nominal source vs actual sounding ascent time; source is not ground truth'})
 chains=[]
 for forcing in source:
  h=forcing['hour_UTC']
  for s in forcing['pressure_rows']:
   p=s['pressure_Pa'];m=next(r for r in rows[h] if r['pressure_Pa']==p);ini=press(data['initial']['profiles']);initial=next(r for r in ini if r['pressure_Pa']==p)
   chains.append({'hour_UTC':h,'pressure_Pa':p,'met_em_T_K':s['met_em_T_K'],'met_em_qv_REAL_method1_diagnostic':s['met_em_qv_REAL_method1_diagnostic'],'history_T_K':m['T_K'],'history_qv':m['qv_kg_kg'],'history_minus_met_em_T_K':m['T_K']-s['met_em_T_K'],'history_minus_met_em_qv_g_kg':1000*(m['qv_kg_kg']-s['met_em_qv_REAL_method1_diagnostic']),'initial_T_K_if_hour0':initial['T_K'] if h==0 else None,'initial_qv_if_hour0':initial['qv_kg_kg'] if h==0 else None,'interpretation':'hour0 is actual initialization comparison; later local met_em is a driving-analysis state comparison, not a prescribed interior forcing or a restarted REAL column'})
 bdy=[]
 for target in data['boundary_data']['targets']:
  if target['hour_UTC'] not in [12,18]:continue
  w=next(x for x in data['boundary_data']['history_face_wind'] if x['hour_UTC']==target['hour_UTC'] and x['side']==target['side'])
  bdy.append({'side':target['side'],'hour_UTC':target['hour_UTC'],'i_j_one_based':target['i_j_one_based'],'lat_lon':target['lat_lon'],'native_levels_5_10':[dict(r,inward_history_grid_face_m_s=w['inward_normal_grid_velocity_m_s'][r['record']-1]) for r in target['decoded'] if 5<=r['record']<=10],'scope':target['scope']})
 transect=[{'hour_UTC':r['hour_UTC'],'i_j_one_based':r['i_j_one_based'],'lat_lon':r['lat_lon'],'pressure_rows':press(r['profiles'])} for r in data['transect']]
 # No change to historical scored output; these values are context only.
 unchanged=old['original_daily_SOLRAD_statistics_unchanged']
 f12=next(x for x in source if x['hour_UTC']==12);f18=next(x for x in source if x['hour_UTC']==18)
 m12=next(x for x in f12['pressure_rows'] if x['pressure_Pa']==90000);m18=next(x for x in f18['pressure_rows'] if x['pressure_Pa']==90000)
 summary={'first_positive_950_to_925_T_difference_in_11_18_hourly_samples':next((x['hour_UTC'] for x in state if x['T925_minus_T950_K']>0),None),'all_11_18_dry_theta_925_minus_950_positive':all(x['theta925_minus_theta950_K']>0 for x in state),'900hPa_met_em_12_18_T_change_K':m18['met_em_T_K']-m12['met_em_T_K'],'900hPa_met_em_12_18_qv_diagnostic_change_g_kg':1000*(m18['met_em_qv_REAL_method1_diagnostic']-m12['met_em_qv_REAL_method1_diagnostic']),'900hPa_model_vs_met_em_18_qv_difference_g_kg':next(x['history_minus_met_em_qv_g_kg'] for x in chains if x['hour_UTC']==18 and x['pressure_Pa']==90000),'900hPa_model_vs_met_em_18_T_difference_K':next(x['history_minus_met_em_T_K'] for x in chains if x['hour_UTC']==18 and x['pressure_Pa']==90000),'ruling':'forcing already has part of the afternoon thermal mismatch, but contains strong moistening that the free interior forecast does not follow; observed differences are not explained by an all-dry driving profile or a newly established preprocessing/optical defect','next_bounded_interval_UTC':[12,17],'interval_scope':'captures strengthening from an already biased12UTC state through first hourly 950/925 inversion at14 and its17UTC maximum; it is not the onset time of all forecast error or an exact substep transition'}
 return {'status':'EXISTING_LOW_LEVEL_STATE_DEVELOPMENT_AND_INPUT_CHAIN_COMPARED','base_main':data['base_main'],'grid_shape_j_i':[143,90],'selected_i_j_one_based':[37,119],'fixed_model_grid_lat_lon':data['fixed_lat_lon'],'hourly_profiles':profiles,'release_near_and_nominal_observation_pairs':pairs,'state_changes_with_time_support_limits':development,'fixed_pressure_and_native_inversion_development':state,'source_to_met_em_chain':source,'source_vs_observation_context':source_observation,'local_met_em_initial_history_chain':chains,'native_boundary_targets_and_actual_face_wind_context':bdy,'fixed_north_transect':transect,'development_ruling':summary,'original_daily_SOLRAD_statistics_unchanged':unchanged,'decision':{'action':'retain_engineering_baseline_and_compare_bounded_low_level_temperature_and_vapor_advection_vs_physical_tendencies_during_state_development','production_correction_supported':False,'optical_or_PBL_coefficient_tuning_supported':False,'unique_PBL_fault_confirmed':False,'direct_boundary_causality_proven':False,'scope':'unapproved quantitative afternoon cloud persistence and all-skySW; same diagnostic station-day and fixed cell, not a new independent forecast case','next_comparison':'use existing cold checkpoint only if needed to separate temperature/qv advection and physics over12–17UTC, native layers5–12 and their actual transport stencil; retain existing12UTC error and do not repeat the17:35cloud-loss reaction trace'},'limitations':{'local_later_met_em_is_not_direct_interior_forcing':True,'decoded_boundary_has_no_interior_pressure_or_station_error_assigned':True,'boundary_wind_is_not_a_back_trajectory_or_flux_budget':True,'source_RH_percent_preserved':True,'REAL_method1_conversion_is_REAL64_diagnostic_not_new_native_REAL_run':True,'CLDFRA_is_held_history_diagnostic_not_fresh_radiation_mask':True,'observed_temperature_lapse_does_not_mean_negative_dry_theta_gradient':True,'radiosonde_release_HHMM_assumes_second00_for_display':True,'balloon_drift_unknown':True,'assimilation_withholding_not_verified':True,'physical_tolerance':None},'production_calculation_changes':False,'coefficient_or_policy_changes':False,'original_seven_conditions_changed':False,'physical_accuracy_approved':False,'new_model_runs':0,'new_model_runs_in_saved_replay':0}
