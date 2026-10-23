"""Actual one-hour state/bridge/return/hold attribution; no optical tuning."""
import json,math,datetime as dt,struct

def require(ok,msg):
 if not ok:raise ValueError(msg)
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]

def parse(text):
 records={'input':{},'return':{},'held':{}}
 for line in text.decode().splitlines():
  words=line.split();t=float(words[0]);tag=words[1];x=list(map(float,words[2:]));require(tag in records and len(x)=={'input':37,'return':9,'held':12}[tag] and all(math.isfinite(v) for v in x),'observer shape/tag/finite')
  require(57600<=t<61200,'wrong source window')
  if tag=='input':
   require(x[0]==37. and x[1].is_integer() and x[2].is_integer(),'input position');key=(t,int(x[1]),int(x[2]))
  elif tag=='return':
   require(x[0]==37. and x[1].is_integer(),'return position');key=(t,int(x[1]))
  else:require(x[0].is_integer(),'held position');key=(t,int(x[0]))
  require(key not in records[tag],'duplicate actual sample');records[tag][key]=x
 calls=[57600+600*k for k in range(6)];steps=[57600+60*k for k in range(60)]
 require(set(records['input'])=={(t,j,k) for t in calls for j in range(89,100) for k in range(1,45)},'missing actual input layer/column/call')
 require(set(records['return'])=={(t,j) for t in calls for j in range(89,100)},'missing actual return')
 require(set(records['held'])=={(t,j) for t in steps for j in range(89,100)},'missing held step')
 return records

def observed_components(blobs):
 rows=[];seen=set()
 for data in blobs:
  for line in data.decode().splitlines()[2:]:
   x=list(map(float,line.split()));t=dt.datetime(*(int(x[k]) for k in [0,2,3,4,5]))
   if not dt.datetime(2016,10,6,16)<t<=dt.datetime(2016,10,6,17):continue
   require(t not in seen and x[9]==x[11]==x[13]==0 and len(x)==22,'observed duplicate/QC/schema');seen.add(t)
   projected=x[10]*max(math.cos(math.radians(x[7])),0.)
   rows.append({'end_utc':t.isoformat(),'SZA_degrees':x[7],'DNI_W_m2':x[10],'horizontal_direct_W_m2':projected,'DHI_W_m2':x[12],'primary_W_m2':projected+x[12],'PSP_W_m2':x[8]})
 require(seen=={dt.datetime(2016,10,6,16)+dt.timedelta(minutes=m) for m in range(1,61)},'observed minute support missing')
 rows.sort(key=lambda r:r['end_utc']);means={name:math.fsum(r[name] for r in rows)/60 for name in ['DNI_W_m2','horizontal_direct_W_m2','DHI_W_m2','primary_W_m2','PSP_W_m2']};means['diffuse_fraction']=means['DHI_W_m2']/means['primary_W_m2']
 return rows,means

def evaluate(d,comparison,blobs):
 rec=parse(d['host/sterling-cloud.txt']);existing=json.loads(d['existing.json']);rows,obs=observed_components(blobs)
 calls=[57600+600*k for k in range(6)];steps=[57600+60*k for k in range(60)];transect=[]
 for j in range(99,88,-1):
  held=[rec['held'][t,j] for t in steps];ret=[rec['return'][t,j] for t in calls];profiles=[rec['input'][t,j,k] for t in calls for k in range(1,45)]
  for t,h in zip(steps,held):
   require(h[1]==60. and h[2]==57600+(t-57600)//600*600,'held interval/phase mismatch')
   returned=rec['return'][h[2],j]
   require(h[3:7]==[returned[2],returned[3],returned[4],returned[5]] and h[8:10]==returned[5:7],'held fields not actual physical returns')
   require(h[7]==f32(h[4]-h[6]),'native diffuse not all-minus-unscaled-direct')
  avg=lambda n:math.fsum(h[n]*h[1] for h in held)/3600
  by_call=[]
  for t in calls:
   layer=[rec['input'][t,j,k] for k in range(1,45)]
   by_call.append({'source_seconds':t,'max_used_CF':max(p[13] for p in layer),'max_RAD_source_CF':max(p[14] for p in layer),'max_UDM_CF_diagnostic_not_consumed_here':max(p[15] for p in layer),'maximum_received_condensate_mixing_ratio':max(max(p[7:13]) for p in layer),'native_grid_paths_g_m2':[math.fsum(p[n] for p in layer) for n in range(16,22)],'native_radiation_incloud_or_uniform_paths_g_m2':[math.fsum(p[n] for p in layer) for n in range(22,28)],'CU_grid_paths_g_m2':[math.fsum(p[n] for p in layer) for n in range(31,33)],'CU_incloud_paths_g_m2':[math.fsum(p[n] for p in layer) for n in range(33,35)],'dry_mass_weighted_water_vapor_kg_m2':math.fsum(p[5]*p[6] for p in layer)})
  snap16=next(r for r in existing['snapshots'] if r['hour_UTC']==16 and r['j']==j);snap17=next(r for r in existing['snapshots'] if r['hour_UTC']==17 and r['j']==j)
  ac=snap16['ACSWDNB_J_m2'];acc=snap16['ACSWDNBC_J_m2']
  for h in held:
   ac=f32(ac+f32(h[4]*h[1]));acc=f32(acc+f32(h[5]*h[1]))
   require(ac==h[10] and acc==h[11],'actual REAL32 accumulator update mismatch')
  require(ac==snap17['ACSWDNB_J_m2'] and acc==snap17['ACSWDNBC_J_m2'],'actual original-hour accumulator endpoint mismatch')
  actual_hour=(snap17['ACSWDNB_J_m2']-snap16['ACSWDNB_J_m2'])/3600;clear_hour=(snap17['ACSWDNBC_J_m2']-snap16['ACSWDNBC_J_m2'])/3600
  transect.append({'i':37,'j':j,'latitude':snap16['lat'],'longitude':snap16['lon'],'cells_from_north_edge':99-j,'inside_specified_boundary_zone':99-j<5,'model_allsky_hour_from_original_accumulator_W_m2':actual_hour,'model_clearsky_hour_from_original_accumulator_W_m2':clear_hour,'all_minus_clear_accumulator_W_m2':actual_hour-clear_hour,'model_allsky_held_W_m2':avg(4),'model_clearsky_held_W_m2':avg(5),'physical_horizontal_direct_held_W_m2':avg(8),'physical_diffuse_native_held_W_m2':avg(7),'physical_direct_normal_held_W_m2':math.fsum(h[8]/h[3]*h[1] for h in held)/3600,'physical_clear_horizontal_direct_held_W_m2':avg(9),'held_minus_original_accumulator_W_m2':avg(4)-actual_hour,'actual_call_inputs':by_call})
 site=next(x for x in transect if x['j']==97);target=comparison['hourly'][16]
 require(site['model_allsky_hour_from_original_accumulator_W_m2']==target['model_W_m2'] and obs['primary_W_m2']==target['primary_W_m2'] and obs['PSP_W_m2']==target['secondary_W_m2'],'original score/support changed')
 station_profiles=[rec['input'][t,97,k] for t in calls for k in range(1,45)]
 require(all(all(x==0. for x in p[7:15]+p[16:28]) and all(x==0. for x in p[31:35]) for p in station_profiles),'positive received cloud/path contradicts no-cloud-at-site decision')
 require(site['model_allsky_hour_from_original_accumulator_W_m2']==site['model_clearsky_hour_from_original_accumulator_W_m2'] and all(rec['return'][t,97][3]==rec['return'][t,97][4] for t in calls),'cloud attenuation exists at original site')
 require(any(r['j']<=94 and any(c['max_used_CF']>0 and sum(c['native_grid_paths_g_m2'])+sum(c['CU_grid_paths_g_m2'])>0 for c in r['actual_call_inputs']) for r in transect),'no measured cloudy interior control')
 errors=[r['primary_error_W_m2'] for r in comparison['hourly']];sse=math.fsum(e*e for e in errors)
 bzero=True
 for b in existing['boundary_records']:
  for name,row in b['raw_stored_values_not_decoupled'].items():
   if not name.startswith('QVAPOR'):bzero=bzero and all(v==0 for a in row['values_width_layer'] for v in a)
 require(bzero,'boundary condensate target not zero')
 return {'status':'STERLING_MAX_ERROR_STATE_AND_RADIATION_ATTRIBUTION_COMPLETE','observed_hour_components':obs,'observed_minutes':rows,'original_site':site,'fixed_north_transect':transect,'actual_target_SW_calls':6,'actual_target_columns_per_call':11,'actual_input_layer_samples':len(rec['input']),'actual_held_column_steps':len(rec['held']),'native_all_and_clear_accumulator_steps_replayed':2*len(rec['held']),'received_site_cloud_and_CU_paths_all_zero':True,'site_allsky_equals_clear_at_every_target_call':True,'cloudy_interior_control_present':True,'north12_and18UTC_raw_condensate_value_and_tendency_zero':bzero,'SSE_fraction_15_19UTC':math.fsum(e*e for e in errors[15:19])/sse,'SSE_fraction_16_18UTC':math.fsum(e*e for e in errors[16:18])/sse,'interpretation':'original-site cloud suppression is already present in the atmospheric/radiation input, not evidence of a cloudy-input optical attenuation failure at this site; cloudy rows occur toward the interior','next_investigation_boundary':'prioritize local cloud occurrence and lateral forcing/relaxation/state evolution, retaining the original station score; an interior-site domain configuration is a separate subsequent experiment, not an optical coefficient fix','boundary_causality_proven':False,'optical_coefficient_change_justified':False,'model_direct_is_unscaled_horizontal_before_DNI_conversion':True,'model_clear_sky_error_against_cloudy_observation_claimed':False,'physical_accuracy_approved':False,'original_24h_scores_changed':False,'production_changes':False,'new_WRF_processes':1,'bounded_restart_seconds':18120,'new_standalone_RTE_Mie_processes':0,'new_model_runs_in_saved_replay':0,'independent_weather_cases':1}
