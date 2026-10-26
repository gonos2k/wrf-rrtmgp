"""One new geometry, unchanged historical observation/scoring functions."""
from pathlib import Path
import importlib.util,datetime as dt,json,math,struct
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('original_solrad_scoring',P.parent/'real-output-independent-comparison/analyze.py');S=importlib.util.module_from_spec(s);s.loader.exec_module(S)
require=S.require
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]

def match_grid(g):
 lat,lon=g['latitude'],g['longitude']
 require(g['shape_j_i']==[143,90] and len(lat)==len(lon)==143 and all(len(r)==90 for r in lat+lon),'new grid shape differs')
 require(g['MAP_PROJ']==3 and all(r==[r[0]]*90 for r in lat) and all(r==lon[0] for r in lon),'new native Mercator grid')
 require(all(lat[j][0]<lat[j+1][0] for j in range(142)) and all(lon[0][i]<lon[0][i+1] for i in range(89)),'native grid order')
 require(lat[0][0]<S.SITE[0]<lat[-1][0] and lon[0][0]<S.SITE[1]<lon[0][-1],'station outside native grid')
 def distance(j,i):
  p,p0=map(math.radians,(lat[j][i],S.SITE[0]));a=math.sin((p-p0)/2)**2+math.cos(p)*math.cos(p0)*math.sin(math.radians(lon[j][i]-S.SITE[1])/2)**2
  return 2*6371000*math.asin(math.sqrt(a))
 j,i=min(((j,i) for j in range(143) for i in range(90)),key=lambda ij:distance(*ij))
 require([j,i]==g['selected_j_i_zero_based']==[118,36],'wrong or score-selected interior cell')
 edge=min(j,i,142-j,89-i);require(edge==24 and g['spec_bdy_width']==5 and g['selected_landmask']==1 and abs(distance(j,i)-g['distance_m'])<1e-8,'new spatial support mismatch')
 return dict(station_lat_lon_height=list(S.SITE),model_i_j_1based=[i+1,j+1],model_lat_lon=[lat[j][i],lon[j][i]],distance_m=distance(j,i),model_height_m=g['selected_height_m'],height_difference_m=g['selected_height_m']-S.SITE[2],cells_to_nearest_edge=edge,spec_bdy_width=5,inside_direct_boundary_zone=False,indirect_boundary_influence_excluded=False)

def score(model,grid,blobs):
 site=match_grid(grid);require(model['selected_j_i_zero_based']==[118,36],'series extracted from wrong cell')
 require(model['times_utc']==[(S.START+dt.timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(25)],'model missing/shifted UTC endpoint')
 ac=model['ACSWDNB_J_m2'];require(len(ac)==25 and all(math.isfinite(x) for x in ac) and all(a<=b for a,b in zip(ac,ac[1:])),'invalid/reset model accumulator')
 require(model['ACSWDNB_storage_dtype']=='float32' and model['ACSWDNB_units']=='J m-2' and model['DT_s']==60.,'wrong model time/units contract')
 require(model['attributes']==dict(MP_PHYSICS=27,RA_LW_PHYSICS=37,RA_SW_PHYSICS=37,UDM_NUMBER_POLICY=1,UDM_POPULATION_POLICY=0,UDM_SPECIFIED_NUMBER_CONTRACT=1),'wrong physical/number configuration')
 obs,negative=S.observations(blobs);rows=[]
 for h in range(24):
  r=S.hour(obs,S.START+dt.timedelta(hours=h));r['model_W_m2']=(ac[h+1]-ac[h])/3600
  for n in ['primary','secondary']:r[n+'_error_W_m2']=r['model_W_m2']-r[n+'_W_m2'] if r[n+'_W_m2'] is not None else None
  r['endpoint_only_half_ULP_scale_W_m2']=(S.ulp32(ac[h])+S.ulp32(ac[h+1]))/7200
  r['model_clear_W_m2']=(model['ACSWDNBC_J_m2'][h+1]-model['ACSWDNBC_J_m2'][h])/3600;r['model_all_minus_clear_W_m2']=r['model_W_m2']-r['model_clear_W_m2'];rows.append(r)
 require(all(r['present_minutes']==r['primary_good_minutes']==r['secondary_good_minutes']==60 for r in rows),'missing/QC-invalid observation support; no fill')
 totals={n:{sub:S.statistics(rows,n+'_W_m2',sub=='daylight') for sub in ['all','daylight']} for n in ['primary','secondary']}
 return dict(site=site,statistics=totals,hourly=rows,negative_measured_minutes_preserved=negative)

def surface_hour(surface,model):
 expected=[(S.START+dt.timedelta(seconds=57600+60*m)).strftime('%Y-%m-%d_%H:%M:%S') for m in range(61)]
 require(surface['times_utc']==expected and surface['selected_j_i_zero_based']==[118,36],'surface record support or cell')
 names=['SWDNB','SWDNBC','SWDDIR','SWDDIRC','SWDDIF','SWDDNI','COSZEN','ACSWDNB','ACSWDNBC'];r=surface['values'];require(set(r)==set(names) and all(len(v)==61 and all(math.isfinite(x) for x in v) for v in r.values()),'surface native record/finite/schema')
 require(r['ACSWDNB'][0]==model['ACSWDNB_J_m2'][16] and r['ACSWDNB'][-1]==model['ACSWDNB_J_m2'][17] and r['ACSWDNBC'][0]==model['ACSWDNBC_J_m2'][16] and r['ACSWDNBC'][-1]==model['ACSWDNBC_J_m2'][17],'surface and hourly endpoints not same run/cell')
 for n in range(1,61):
  for flux,acc in [('SWDNB','ACSWDNB'),('SWDNBC','ACSWDNBC')]:require(f32(r[acc][n-1]+f32(60*r[flux][n]))==r[acc][n],'surface end-of-step flux not applied to actual accumulator')
  require(r['SWDDIF'][n]==f32(r['SWDNB'][n]-r['SWDDIR'][n]),'native physical diffuse not all-minus-horizontal-direct')
 avg=lambda n:math.fsum(r[n][1:])/60
 mean={n:avg(n) for n in ['SWDNB','SWDNBC','SWDDIR','SWDDIRC','SWDDIF','SWDDNI']};mean['all_minus_clear_W_m2']=mean['SWDNB']-mean['SWDNBC'];mean['diffuse_fraction']=mean['SWDDIF']/mean['SWDNB'] if mean['SWDNB'] else None
 return dict(hour_UTC='2016-10-06T16:00:00/17:00:00',interval_contract='60period-end native states16:01–17:00; each flux independently replays its actual60s accumulator update',means=mean,accumulator_hour_W_m2=(r['ACSWDNB'][-1]-r['ACSWDNB'][0])/3600,held_minus_accumulator_W_m2=mean['SWDNB']-(r['ACSWDNB'][-1]-r['ACSWDNB'][0])/3600,native_accumulator_updates_replayed=120,model_direct_convention='SWDDIR is unscaled horizontal physical direct; SWDDNI is its native per-call normal conversion. Mean DNI is not multiplied by mean cosine.',state_samples_are_end_of_step_not_exact_adapter_capture=True)


def observed_components(blobs,start):
 end=start+dt.timedelta(hours=1);seen={}
 for data in blobs:
  for line in data.decode().splitlines()[2:]:
   x=list(map(float,line.split()));t=dt.datetime(*(int(x[k]) for k in [0,2,3,4,5]))
   if not start<t<=end:continue
   require(t not in seen and x[9]==x[11]==x[13]==0,'component UTC/QC support')
   direct=x[10]*max(math.cos(math.radians(x[7])),0.)
   seen[t]={'DNI_W_m2':x[10],'horizontal_direct_W_m2':direct,'DHI_W_m2':x[12],'primary_W_m2':direct+x[12],'PSP_W_m2':x[8]}
 require(set(seen)=={start+dt.timedelta(minutes=m) for m in range(1,61)},'missing component minutes')
 r={k:math.fsum(x[k] for x in seen.values())/60 for k in next(iter(seen.values()))};r['diffuse_fraction']=r['DHI_W_m2']/r['primary_W_m2'];return r

def evaluate(d,blobs,plan,old):
 require(plan['physical_tolerance_W_m2'] is None and plan['new_24h_WRF_process_budget']==1 and not plan['production_changes'] and not plan['existing_seven_closure_conditions_changed'],'new scope/tolerance changed')
 r=score(d['model'],d['grid'],blobs);surf=surface_hour(d['surface'],d['model']);surf['observed_components_reused']=old['observed_16_17UTC_components'];require(r['hourly'][16]['primary_W_m2']==old['observed_16_17UTC_components']['primary_W_m2'],'reused component support differs from actual scoring');h=d['history'];require(h['records']==25 and h['numeric_nonfinite_elements']==0,'incomplete/nonfinite hourly history')
 require(d['run_summary']['status']=='SUCCESS' and d['run_summary']['steps']==1440 and d['run_summary']['LW_source_seconds']==list(range(600,86400,600)),'incomplete actual trajectory/phase')
 delta={subset:{k:r['statistics']['primary'][subset][k]-old['statistics']['primary'][subset][k] for k in ['bias_W_m2','MAE_W_m2','RMSE_W_m2','model_energy_MJ_m2']} for subset in ['all','daylight']}
 maxhour=max(r['hourly'],key=lambda x:abs(x['primary_error_W_m2']));cloud=[row for row in d['hourly_state'] if row['hour_UTC'] in [16,17]];require(len(cloud)==2,'missing predetermined-hour cloud states')
 aux=d['cloud_states'];require(aux['times_utc']==[(S.START+dt.timedelta(seconds=57600+600*n)).strftime('%Y-%m-%d_%H:%M:%S') for n in range(7)] and len(aux['profiles'])==7,'missing native cloud-state support')
 for p in aux['profiles']:
  require(all(len(v)==44 and all(math.isfinite(x) for x in v) for v in p.values()) and all(0<=x<=1 for x in p['CLDFRA']),'invalid native cloud profiles')
 positive=any(any(c>0 and math.fsum(p[n][k] for n in ['QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL','QC_CU','QI_CU'])>0 for k,c in enumerate(p['CLDFRA'])) for p in aux['profiles'])
 better=r['statistics']['primary']['all']['RMSE_W_m2']<old['statistics']['primary']['all']['RMSE_W_m2'];attenuated=surf['means']['all_minus_clear_W_m2']<0 and surf['means']['SWDDIR']<old['original_16_17UTC_direct_W_m2']
 hourly_valid=all(v['negative_elements']==v['nonfinite_elements']==0 for row in h['hourly_validity'] for v in row['water_number'].values())
 if not hourly_valid:
  next_action='Prioritize the first invalid prognostic-state update in this new configuration; preserve all scored output and do not approve state validity.'
 elif better and attenuated and positive:
  next_action='Use a same-WPS/same-geography small-domain control only if separating domain distance from preprocessing is required; do not tune optics. The new configuration has lower error and cloudy attenuation at the preselected hour.'
 elif not positive and surf['means']['SWDDIR']>old['observed_16_17UTC_horizontal_direct_W_m2']:
  next_action='Prioritize local saturation/advection/cloud-formation source at the preselected interior site; preserve this score and current optics.'
 else:
  next_action='Prioritize cloud time/space representativeness and supplied grid-path/CF support at the preselected hour; lower error alone does not identify optical accuracy or a pure boundary effect.'
 peak_start=dt.datetime.fromisoformat(maxhour['start_utc']);components=observed_components(blobs,peak_start);require(components['primary_W_m2']==maxhour['primary_W_m2'],'peak component/scoring support mismatch')
 peak_hour=peak_start.hour;ends=[d['hourly_state'][h] for h in [peak_hour,peak_hour+1]]
 remaining={'scope':'exploratory post-score attribution; original full24h scores/selection unchanged','hour_start_UTC':maxhour['start_utc'],'hour_end_UTC':maxhour['end_utc'],'model_all_W_m2':maxhour['model_W_m2'],'model_clear_W_m2':maxhour['model_clear_W_m2'],'model_all_minus_clear_W_m2':maxhour['model_all_minus_clear_W_m2'],'observed_components':components,'endpoints':[{'hour_UTC':x['hour_UTC'],'max_CLDFRA':x['max_CLDFRA'],'six_condensate_grid_paths_g_m2':x['six_condensate_grid_paths_g_m2']} for x in ends],'native_mean_direct_or_diffuse_model_in_this_new_peak_not_measured':True}
 if hourly_valid and better and attenuated and positive and all(x['max_CLDFRA']==0 for x in ends):
  next_action='Prioritize cloud disappearance/persistence timing around17–19UTC at the same interior cell, using saved humidity/temperature/advection and cloud-formation support. The new peak has clear-like modeled flux while observed diffuse dominates. Do not tune optics; a matched-preprocessing domain control is only needed for a later isolated-domain causal claim.'
 return dict(status='ACTUAL_INTERIOR_DOMAIN_COLD24H_OBSERVATION_EVALUATION_COMPLETE',window_start_UTC=S.START.isoformat(),window_end_UTC=S.END.isoformat(),**r,surface_16_17UTC=surf,hourly_state=d['hourly_state'],auxiliary_cloud_states=d['cloud_states'],history_validity=h,hourly_water_number_valid=hourly_valid,actual_run=d['run_summary'],LW_trace_scope='143positive-native-condensate path phases600–85800s; zero-native-path initial clear phase is not emitted by this conditional trace; total LW invocation counter not observed',total_LW_invocations_directly_observed=None,original_statistics_preserved=old['statistics'],new_minus_original_configuration=delta,maximum_absolute_error_hour=maxhour,remaining_error_boundary=remaining,at_preselected_hour_positive_cloud_state=positive,at_preselected_hour_cloud_attenuation_and_weaker_direct=attenuated,new_all_hour_RMSE_lower=better,decision=next_action,interpretation='difference between two coupled domain+preprocessing/geography configurations; not a pure boundary-distance or RRTMGP-code effect',uncertainties=dict(physical_tolerance_W_m2=None,reference_calibrated_W_m2=None,point_grid_representativeness_W_m2=None,model_total_numerical_error_W_m2=None),original_24h_scores_changed=False,production_changes=False,original_seven_conditions_changed=False,physical_accuracy_approved=False,isolated_domain_causality_proven=False,optical_code_improvement_claimed=False,whole_water_energy_approved=False,new_24h_WRF_processes=1,new_bounded_diagnostic_WRF_processes=1,new_model_runs_in_saved_replay=0)
