"""Independent atmosphere constraints on one fixed diagnostic station-day."""
import datetime as dt,math
from parse import require,interpolate,distance,UTC
PRESSURES=[97500,95000,92500,90000,87500,85000,82500,80000]
FIELDS={'T_K':'T_K','qv_from_dewpoint_kg_kg':'qv_kg_kg','RH_water_from_dewpoint_ratio':'RH_water_ratio','z_msl_m':'z_msl_m','wind_u_east_m_s':'wind_u_east_m_s','wind_v_north_m_s':'wind_v_north_m_s'}
def compare_profile(obs,model):
 rows=[];release=dt.datetime.fromisoformat(obs['release_UTC']) if obs['release_UTC'] else None;mt=dt.datetime.fromisoformat(model['time_UTC'])
 for p in PRESSURES:
  values={}
  for of,mf in FIELDS.items():
   a=interpolate(obs['levels'],p,of);b=interpolate(model['profiles'],p,mf)
   values[mf]={'observation':a,'model':b,'model_minus_observation':b['value']-a['value'] if a and b else None}
  elapsed=interpolate(obs['levels'],p,'elapsed_s');actual=(release+dt.timedelta(seconds=elapsed['value'])) if release and elapsed else None
  values['IGRA_reported_RH_ratio']=interpolate(obs['levels'],p,'reported_RH_ratio')
  rows.append({'pressure_Pa':p,'nominal_sounding_UTC':obs['nominal_UTC'],'observed_level_time_UTC_from_release_elapsed':actual.isoformat() if actual else None,'observed_elapsed_bracket':elapsed,'model_time_UTC':model['time_UTC'],'model_minus_observed_level_time_s':(mt-actual).total_seconds() if actual else None,'fields':values})
 return rows

def warm_segments(profile):
 p=sorted([r for r in profile if r.get('T_K') is not None and r.get('z_agl_m') is not None and 300<=r['z_agl_m']<=2500],key=lambda r:r['z_agl_m'])
 rows=[]
 for a,b in zip(p,p[1:]):
  if b['T_K']>a['T_K'] and b['z_agl_m']>a['z_agl_m']:
   rows.append({'lower_record':a['record'],'upper_record':b['record'],'lower_upper_AGL_m':[a['z_agl_m'],b['z_agl_m']],'lower_upper_MSL_m':[a['z_msl_m'],b['z_msl_m']],'lower_upper_pressure_Pa':[a['p_Pa'],b['p_Pa']],'lower_upper_T_K':[a['T_K'],b['T_K']],'warming_K':b['T_K']-a['T_K']})
 return rows

def evaluate(enriched,prior):
 sonde={r['nominal_UTC']:r for r in enriched['soundings']};model={r['hour_UTC']:r for r in enriched['model']['profiles']};require(set(model)=={0,12,17,18,19,20,24},'fixed model profile hours')
 primary=sonde['2016-10-06T18:00:00+00:00'];require(primary['release_UTC']=='2016-10-06T17:34:00+00:00','actual sounding release changed')
 require(enriched['model']['selected_i_j_one_based']==[37,119] and enriched['model']['shape_j_i']==[143,90],'station grid changed')
 targets=[r for r in enriched['surface_reports'] if '2016-10-06T17:00:00'<=r['time_UTC']<'2016-10-06T20:00:00'];station_context=[]
 site=[38.97203,-77.4869];grid=enriched['model']['selected_lat_lon']
 for st in ['IAD','DCA','BWI']:
  records=[r for r in targets if r['station']==st];require(records,'missing independent station')
  station_context.append({'station':st,'records':records,'count':len(records),'distance_to_SOLRAD_m_from_archive_metadata':distance(site,records[0]['metadata_lat_lon']),'distance_to_fixed_model_grid_m_from_archive_metadata':distance(grid,records[0]['metadata_lat_lon']),'sampling':'actual report instants; no carry-forward, hourly fraction or continuous cloud-duration reconstruction','BKN_OVC_ceiling_reports':sum(r['ceiling_agl_m'] is not None for r in records)})
 profile_pairs=[]
 for nominal,hour in [('2016-10-06T00:00:00+00:00',0),('2016-10-06T12:00:00+00:00',12),('2016-10-06T18:00:00+00:00',18),('2016-10-07T00:00:00+00:00',24)]:
  profile_pairs.append({'nominal_UTC':nominal,'actual_release_UTC':sonde[nominal]['release_UTC'],'fixed_pressure_rows':compare_profile(sonde[nominal],model[hour])})
 micro=[r for r in prior['selected_native_saturation_states'] if r['source_seconds']==63300 and r['stage']=='before'];require(len(micro)==3,'prior actual micro state missing')
 near=[]
 for m in sorted(micro,key=lambda x:x['k']):
  p=m['p_Pa'];obs={f:interpolate(primary['levels'],p,f) for f in ['T_K','qv_from_dewpoint_kg_kg','RH_water_from_dewpoint_ratio','reported_RH_ratio','z_msl_m','elapsed_s','wind_u_east_m_s','wind_v_north_m_s']}
  require(all(obs[f] is not None for f in ['T_K','qv_from_dewpoint_kg_kg','elapsed_s']),'missing pressure support near cloud layer')
  when=dt.datetime.fromisoformat(primary['release_UTC'])+dt.timedelta(seconds=obs['elapsed_s']['value'])
  near.append({'native_k':m['k'],'model_source_UTC':'2016-10-06T17:35:00+00:00','model_end_UTC':'2016-10-06T17:36:00+00:00','model_actual_microphysics_before':m,'observed_at_same_pressure':obs,'observed_level_time_UTC_from_release_elapsed':when.isoformat(),'displayed_level_time_inside_model_step_if_release_second00':dt.datetime(2016,10,6,17,35,tzinfo=UTC)<=when<=dt.datetime(2016,10,6,17,36,tzinfo=UTC),'T_model_minus_observed_K':m['actual_T_from_native_product_K']-obs['T_K']['value'],'qv_model_minus_observed_g_kg':1000*(m['qv']-obs['qv_from_dewpoint_kg_kg']['value'])})
 k6,k7=near[1:];gradient={'model_k6_to_k7_T_difference_K':k7['model_actual_microphysics_before']['actual_T_from_native_product_K']-k6['model_actual_microphysics_before']['actual_T_from_native_product_K'],'observed_T_difference_over_same_pressure_interval_K':k7['observed_at_same_pressure']['T_K']['value']-k6['observed_at_same_pressure']['T_K']['value'],'pressure_interval_Pa':[k6['model_actual_microphysics_before']['p_Pa'],k7['model_actual_microphysics_before']['p_Pa']]}
 require(gradient['model_k6_to_k7_T_difference_K']>0 and gradient['observed_T_difference_over_same_pressure_interval_K']<0,'inversion-sign ruling unsupported')
 obs_warm=warm_segments(primary['levels']);mod_warm={str(h):warm_segments(model[h]['profiles']) for h in [12,17,18,19,20]};require(obs_warm and mod_warm['18'],'missing reported/model inversion support')
 lowp=[r for r in primary['levels'] if r['p_Pa'] and r['p_Pa']>=80000 and r['actual_UTC']];micro_times=[r['observed_level_time_UTC_from_release_elapsed'] for r in near]
 surf_pairs=[]
 for r in targets:
  if r['station']!='IAD' or r['T_C'] is None:continue
  time=dt.datetime.fromisoformat(r['time_UTC']);match=min([model[h] for h in [17,18,19,20]],key=lambda m:abs((dt.datetime.fromisoformat(m['time_UTC'])-time).total_seconds()));offset=(dt.datetime.fromisoformat(match['time_UTC'])-time).total_seconds()
  if abs(offset)>1800:continue
  surf_pairs.append({'observed_report_UTC':r['time_UTC'],'model_UTC':match['time_UTC'],'time_offset_s':offset,'observed_T_C':r['T_C'],'observed_Td_C':r['Td_C'],'model_T2_C':match['surface']['T2']-273.15,'model_minus_observed_T_K':match['surface']['T2']-273.15-r['T_C'],'model_PBLH_m_not_observed_inversion_height':match['surface']['PBLH'],'observed_wind_variable':r['wind_variable'],'observed_wind_from_deg':r['wind_from_deg'],'observed_wind_speed_m_s':r['wind_speed_m_s'],'model_U10_east':match['surface']['U10_east'],'model_V10_north':match['surface']['V10_north'],'scope':'nearest declared hour within30min, fixed original SOLRAD model cell vs nearby airport point; context, not a new surface skill score'})
 iad=station_context[0]['records'];require(any(r['time_UTC']=='2016-10-06T18:52:00+00:00' and r['ceiling_agl_m'] is not None for r in iad),'post-loss observed cloud evidence absent')
 return {'status':'INDEPENDENT_ATMOSPHERE_CONSTRAINTS_AND_RESEARCH_SCOPE_DECIDED','site_SOLRAD_lat_lon':site,'fixed_model_grid_lat_lon':grid,'grid_shape_j_i':[143,90],'selected_i_j_one_based':[37,119],'radiosonde_nominal_UTC':primary['nominal_UTC'],'radiosonde_actual_release_UTC':primary['release_UTC'],'IGRA_lower_800hPa_reported_level_time_range_UTC':[min(r['actual_UTC'] for r in lowp),max(r['actual_UTC'] for r in lowp)],'archive_nominal_radiosonde_coordinate_lat_lon':primary['archive_coordinate_lat_lon'],'radiosonde_coordinate_scope':primary['coordinate_scope'],'nominal_sonde_distance_to_SOLRAD_m':distance(site,primary['archive_coordinate_lat_lon']),'surface_station_context':station_context,'fixed_pressure_profile_comparisons':profile_pairs,'same_pressure_near_loss_actual_microphysics_comparisons':near,'near_loss_vertical_T_structure':gradient,'reported_observed_positive_T_segments_300_2500m_AGL':obs_warm,'native_model_positive_T_segments_300_2500m_AGL':mod_warm,'surface_temperature_wind_context':surf_pairs,'original_daily_SOLRAD_statistics_unchanged':prior['surface_components']['old_whole_day_statistics_unchanged'],'existing_same_period_radiation_components':prior['surface_components']['hours'],'microphysics_loss_operation_reopened':False,'decision':{'action':'retain_engineering_baseline_and_prioritize_lower_tropospheric_T_qv_and_inversion_structure_before_any_optical_or_PBL_coefficient_change','independent_cloud_ruling':'nearby IAD still reports low BKN/OVC at17:52and18:52 after model loss; DCA remains overcast while BWI becomes scattered, so spatial variability is real and the fixed-cell all-sky forecast remains unapproved','thermodynamic_ruling':'the actual17:34release sounding and prior17:35microphysics states disagree in temperature-gradient sign across native6–7pressures. Independent constraints now identify the low-level thermodynamic/capping structure as the next state boundary, beyond merely repeating a source trace','scope_action':'limit quantitative Sterling afternoon cloud-persistence and surface all-sky SW applicability; keep the validated serial research implementation and unchanged original scores','unique_parameter_fault_established':False,'why_no_tuning':'point/balloon representativeness, sounding resolution and drift, forcing history and turbulence observations do not uniquely separate YSU mixing strength from pre-existing/advected thermodynamic-state error','next_single_discriminating_comparison':'compare the existing input/boundary thermodynamic profiles and model-state evolution against these fixed observed profiles, keeping the original grid and production physics fixed; choose an input correction only if its provenance supports one'},'uncertainties':{'physical_tolerance':None,'temperature_dewpoint_reporting_resolution_K':0.1,'measurement_total_uncertainty':None,'representation_error':None,'observed_turbulent_cloud_water_flux':None,'balloon_per_level_horizontal_position':None,'inversion_height_is_not_direct_observed_PBLH':True,'sounding_temporal_interpolation_into_target_hour':False,'station_metadata_is_not_verified2016launch_location':True,'IGRA_release_is_HHMM_without_seconds':True,'displayed_level_times_assume_release_second00_and_interpolate_elapsed_vertically':True,'same_diagnostic_day_not_new_independent_forecast_case':True,'observations_independent_of_WRF_output':True,'observation_withholding_from_driving_analysis_verified':False},'engineering_completion_scoped':True,'general_forecast_accuracy_approved':False,'physical_accuracy_approved':False,'PBL_parameter_fault_confirmed':False,'production_calculation_changes':False,'coefficient_or_policy_changes':False,'original_seven_conditions_changed':False,'new_model_runs':0,'new_model_runs_in_saved_replay':0}
