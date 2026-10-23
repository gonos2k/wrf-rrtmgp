"""UTC support-matched comparison with independent signed SOLRAD measurements."""
import datetime as dt,math,struct
SITE=(38.97203,-77.48690,85.)
START=dt.datetime(2016,10,6);END=dt.datetime(2016,10,7)
def require(ok,msg):
 if not ok:raise ValueError(msg)
def observations(blobs):
 rows={};negative={'DNI':0,'DHI':0,'global_PSP':0}
 for day,data in zip((280,281),blobs):
  lines=data.decode('ascii').splitlines();require(lines[0].strip()=='Sterling' and tuple(map(float,lines[1].split()[:3]))==SITE,'actual station header differs')
  for line in lines[2:]:
   x=list(map(float,line.split()));require(len(x)==22 and all(math.isfinite(v) for v in x),'invalid observation shape/finite values')
   require(all(x[k]==int(x[k]) for k in (0,1,2,3,4,5,9,11,13)),'noninteger date/QC')
   t=dt.datetime(*(int(x[k]) for k in (0,2,3,4,5)));require(t not in rows and t.timetuple().tm_yday==int(x[1])==day,'duplicate or shifted UTC observation')
   require(0<=x[7]<=180,'invalid supplied SZA')
   primary_ok=x[11]==0 and x[13]==0 and x[10]!=-9999.9 and x[12]!=-9999.9;secondary_ok=x[9]==0 and x[8]!=-9999.9
   row={'primary':x[10]*max(math.cos(math.radians(x[7])),0.)+x[12] if primary_ok else None,'secondary':x[8] if secondary_ok else None,'daylight':x[7]<90,'SZA_degrees':x[7]}
   rows[t]=row
   if START<t<=END:
    for name,index in [('DNI',10),('DHI',12),('global_PSP',8)]:negative[name]+=int(x[index]<0 and x[index]!=-9999.9)
 return rows,negative

def hour(rows,start):
 end=start+dt.timedelta(hours=1);selected=[rows.get(start+dt.timedelta(minutes=m)) for m in range(1,61)]
 out={'start_utc':start.isoformat(),'end_utc':end.isoformat(),'present_minutes':sum(v is not None for v in selected),'daylight_minutes':sum(v['daylight'] for v in selected if v)}
 out['daylight_hour']=out['daylight_minutes']>=30
 for name in ['primary','secondary']:
  values=[v[name] for v in selected if v is not None and v[name] is not None];out[name+'_good_minutes']=len(values);out[name+'_W_m2']=math.fsum(values)/60 if len(values)==60 else None
 return out

def statistics(rows,field,daylight=False):
 chosen=[r for r in rows if r[field] is not None and (not daylight or r['daylight_hour'])];require(bool(chosen),'no scored observations')
 x=[r['model_W_m2'] for r in chosen];y=[r[field] for r in chosen];e=[a-b for a,b in zip(x,y)];n=len(e)
 return {'hours':n,'mean_model_W_m2':math.fsum(x)/n,'mean_reference_W_m2':math.fsum(y)/n,'bias_W_m2':math.fsum(e)/n,'MAE_W_m2':math.fsum(abs(z) for z in e)/n,'RMSE_W_m2':math.sqrt(math.fsum(z*z for z in e)/n),'max_abs_hour_error_W_m2':max(map(abs,e)),'model_energy_MJ_m2':math.fsum(x)*3600/1e6,'reference_energy_MJ_m2':math.fsum(y)*3600/1e6}

def ulp32(x):
 require(struct.unpack('<f',struct.pack('<f',x))[0]==x,'accumulator is not original REAL32')
 return 2.**max(-149,math.frexp(abs(x))[1]-24)

def match_grid(g):
 lat,lon=g['latitude'],g['longitude'];require(g['shape_j_i']==[99,90] and len(lat)==len(lon)==99 and all(len(r)==90 for r in lat+lon),'grid shape differs')
 require(g['MAP_PROJ']==3 and all(r==[r[0]]*90 for r in lat) and all(r==lon[0] for r in lon),'not actual rectilinear Mercator grid')
 require(all(lat[j][0]<lat[j+1][0] for j in range(98)) and all(lon[0][i]<lon[0][i+1] for i in range(89)),'grid order')
 require(lat[0][0]<SITE[0]<lat[-1][0] and lon[0][0]<SITE[1]<lon[0][-1],'observation outside actual grid')
 def distance(j,i):
  p,p0=map(math.radians,(lat[j][i],SITE[0]));a=math.sin((p-p0)/2)**2+math.cos(p)*math.cos(p0)*math.sin(math.radians(lon[j][i]-SITE[1])/2)**2
  return 2*6371000*math.asin(math.sqrt(a))
 j,i=min(((j,i) for j in range(99) for i in range(90)),key=lambda ij:distance(*ij));require([j,i]==g['selected_j_i_zero_based']==[96,36],'score-tuned or wrong grid cell')
 require(abs(distance(j,i)-g['distance_m'])<1e-8 and g['selected_landmask']==1 and g['spec_bdy_width']==5,'grid/station support mismatch')
 edge=min(j,i,98-j,89-i);require(edge==2,'boundary scope differs')
 return {'station_lat_lon_height':list(SITE),'model_i_j_1based':[i+1,j+1],'model_lat_lon':[lat[j][i],lon[j][i]],'distance_m':distance(j,i),'model_height_m':g['selected_height_m'],'height_difference_m':g['selected_height_m']-SITE[2],'cells_to_nearest_edge':edge,'spec_bdy_width':5,'inside_boundary_zone':True,'interior_forecast_validation':False}

def evaluate(model,grid,blobs,plan):
 require(plan['physical_acceptance_tolerance_W_m2'] is None and plan['no_new_WRF_Mie_RTE_runs'] and not plan['original_seven_conditions_changed'],'scope or post-hoc tolerance changed')
 site=match_grid(grid);require(model['selected_j_i_zero_based']==grid['selected_j_i_zero_based'],'model series from wrong grid')
 require(model['times_utc']==[(START+dt.timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(25)],'model UTC endpoint shift/missing record')
 ac=model['ACSWDNB_J_m2'];require(len(ac)==25 and all(math.isfinite(z) for z in ac) and all(a<=b for a,b in zip(ac,ac[1:])),'invalid accumulator/reset')
 require(model['ACSWDNB_units']=='J m-2' and model['ACSWDNB_storage_dtype']=='float32' and model['DT_s']==60.,'wrong model averaging contract')
 require(model['attributes']==dict(MP_PHYSICS=27,RA_LW_PHYSICS=37,RA_SW_PHYSICS=37,UDM_NUMBER_POLICY=1,UDM_POPULATION_POLICY=0,UDM_SPECIFIED_NUMBER_CONTRACT=1),'wrong current model policy')
 obs,negative=observations(blobs);rows=[]
 for h in range(24):
  r=hour(obs,START+dt.timedelta(hours=h));r['model_W_m2']=(ac[h+1]-ac[h])/3600;r['primary_error_W_m2']=r['model_W_m2']-r['primary_W_m2'] if r['primary_W_m2'] is not None else None;r['secondary_error_W_m2']=r['model_W_m2']-r['secondary_W_m2'] if r['secondary_W_m2'] is not None else None;r['endpoint_only_half_ULP_scale_W_m2']=(ulp32(ac[h])+ulp32(ac[h+1]))/7200;rows.append(r)
 require(all(r['present_minutes']==r['primary_good_minutes']==r['secondary_good_minutes']==60 for r in rows),'current comparison has missing/QC-invalid support; no filling')
 totals={n:{subset:statistics(rows,n+'_W_m2',subset=='daylight') for subset in ['all','daylight']} for n in ['primary','secondary']}
 delta=[r['primary_W_m2']-r['secondary_W_m2'] for r in rows]
 return {'status':'ACTUAL_CORRECTED_OUTPUT_INDEPENDENT_BOUNDARY_SITE_COMPARISON_COMPLETE','target':'all-sky downward surface shortwave hourly mean','window_start_utc':START.isoformat(),'window_end_utc':END.isoformat(),'observed_period_end_minutes':1440,'complete_hours':24,'site':site,'statistics':totals,'hourly':rows,'reference_channel_difference':{'primary_minus_secondary_mean_W_m2':math.fsum(delta)/24,'RMSE_between_channels_W_m2':math.sqrt(math.fsum(x*x for x in delta)/24),'is_instrument_uncertainty_bound':False},'negative_measured_minutes_preserved':negative,'uncertainties':{'maximum_endpoint_only_half_ULP_scale_W_m2':max(r['endpoint_only_half_ULP_scale_W_m2'] for r in rows),'total_model_numerical_error_bound_W_m2':None,'calibrated_reference_uncertainty_W_m2':None,'point_grid_spectral_representativeness_uncertainty_W_m2':None,'approved_use_tolerance_W_m2':None,'channel_spread_or_endpoint_scale_is_total_error_bound':False},'engineering_baseline_decision':'close the declared fixed serial research implementation scope using existing completed evidence; do not reopen its solved numerical/return/boundary/restart tasks','scientific_decision':'independent comparison completed; retain restricted experimental research use; quantitative forecast acceptance deferred without use-based tolerance and uncertainty, and no interior/general accuracy approval from this boundary site','radiation_error_attribution':'coupled forecast difference; cannot isolate optics, cloud occurrence, frozen properties, host physics or boundary forcing','production_changes':False,'current_frozen_physical_accuracy_approved':False,'whole_water_energy_approved':False,'general_forecast_accuracy_approved':False,'original_seven_conditions_changed':False,'new_model_build_solver_processes':0}
