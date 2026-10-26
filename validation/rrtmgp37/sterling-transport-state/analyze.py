"""Replay native face divergence and connect it to PR206, without repeating attribution.

A center-reference split is an exact diagnostic identity, not parcel motion,
physical causal separation, or a stand-alone conservative mass budget.
"""
import math,struct,csv,io
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
RATIO=f32(f32(461.6)/287.)
def require(ok,msg):
 if not ok:raise ValueError(msg)
def parse(text):
 d={}
 for line in text.splitlines():
  x=line.split();require(len(x)>=6,'truncated native row');t=int(float(x[0]));tag=x[1];rk,s,k=map(int,x[2:5]);v=list(map(float,x[5:]));require(rk==3 and 43200<=t<61200 and t%60==0 and all(math.isfinite(z) for z in v),'time/stage/finite native row')
  require((tag=='geometry' and s==0 and 4<=k<=12) or (tag.startswith('theta_') and s==1 and k in [7,8]) or (tag.startswith('q_') and s==2 and k in [7,8]),'variable/stencil scope')
  key=t,tag,k;require(key not in d,'duplicate row');d[key]=v
 return d
def old_operands(text):
 wanted={'start','after_rk','q_rk_factors','q_rk_after','q_adv_pre','q_adv_z','theta_adv_h','theta_adv_z'};d={}
 for l in text.splitlines():
  x=l.split();tag=x[1];k=int(x[4]);rk=int(x[2])
  if tag in wanted and k in [7,8] and rk==(0 if tag in ['start','after_rk'] else 3):d[int(float(x[0])),tag,k]=list(map(float,x[5:]))
 return d
def flux3(values,velocity):
 a,b,c,d=values;four=f32(f32(f32(7*f32(c+b))-f32(d+a))/12)
 corr=f32(f32((1 if -velocity>=0 else -1)*f32(f32(d-a)-f32(3*f32(c-b))))/12)
 return f32(four+corr)
def split_faces(lower,upper,mb,mt,reference):
 # Ftop-Fbottom = relative-to-center transport + center*mass convergence.
 contrast=(upper-reference*mt)-(lower-reference*mb);convergence=reference*(mt-mb)
 require(math.isclose(contrast+convergence,upper-lower,rel_tol=1e-11,abs_tol=1e-14),'face identity')
 return contrast,convergence

def neighborhood(prior):
 records=prior.get('original_neighbor_records',[]);d={(x['source_seconds'],x['k'],x['i'],x['j']):x['values'] for x in records};out=[]
 for hour in range(12,17):
  for k in [7,8]:
   t=hour*3600
   if (t,k,37,119) not in d:continue
   dry=lambda v:(v[0]+300)/(1+RATIO*v[1]);west,east,south,north,center=[d[t,k,i,j] for i,j in [(36,119),(38,119),(37,118),(37,120),(37,119)]];allrows=[d[t,k,i,j] for j in range(116,123) for i in range(34,41)]
   out.append({'source_hour_UTC':hour,'k':k,'dry_theta_east_minus_west_two_native_cells_K':dry(east)-dry(west),'dry_theta_north_minus_south_two_native_cells_K':dry(north)-dry(south),'qv_east_minus_west_two_native_cells_g_kg':1000*(east[1]-west[1]),'qv_north_minus_south_two_native_cells_g_kg':1000*(north[1]-south[1]),'grid_U_masspoint_mean_of_two_staggered_faces_m_s':(center[3]+east[3])/2,'grid_V_masspoint_mean_of_two_staggered_faces_m_s':(center[4]+north[4])/2,'fixed_7x7_dry_theta_min_max_K':[min(map(dry,allrows)),max(map(dry,allrows))],'fixed_7x7_qv_min_max_g_kg':[1000*min(x[1] for x in allrows),1000*max(x[1] for x in allrows)]})
 return out

def analyze(text,prior,oldtext,oldcsv,oldresult,comparison=None,partial=False):
 d=parse(text);old=old_operands(oldtext);times=sorted({k[0] for k in d});require(times and (partial or times==list(range(43200,61200,60))),'primary time roster')
 priorrows={(int(r['source_seconds']),int(r['k'])):r for r in csv.DictReader(io.StringIO(oldcsv))}
 counts={'native_theta_vertical_divergence':0,'native_qv_PD_vertical_divergence':0,'native_theta_third_order_faces':0,'PR206_matching_vertical_updates':0};rows=[]
 for t in times:
  for k in [7,8]:
   get=lambda tag,kk=k:d[t,tag,kk];og=lambda tag:old[t,tag,k]
   th=get('theta_before');ta=get('theta_after')[0];q=get('q_before');qa=get('q_after')[0];st=get('theta_stencil');qs=get('q_stencil');qo=get('q_old_stencil');geom=get('geometry');geo_up=get('geometry',k+1)
   require(len(th)==8 and len(q)==11 and len(st)==len(qs)==len(qo)==7 and len(geom)==19,'operand roster')
   before,dz,mb,mt,fb,ft,order,time_step=th;require(order==3 and time_step==60,'actual theta stencil/time order')
   require(f32(before-f32(dz*f32(ft-fb)))==ta,'native theta divergence');counts['native_theta_vertical_divergence']+=1
   for fields,mass,actual in [(st[1:5],mb,fb),(st[2:6],mt,ft)]:
    require(f32(mass*flux3(fields,mass))==actual,'native third-order theta face');counts['native_theta_third_order_faces']+=1
   qb,qdz,qmb,qmt,ab,at,lb,lt,dt,my,qorder=q;require(qorder==3 and dt==60 and qdz==dz,'actual PD order/source interval')
   require(f32(qb-f32(dz*f32(f32(f32(at-ab)+lt)-lb)))==qa,'native PD vertical divergence');counts['native_qv_PD_vertical_divergence']+=1
   require([before,ta,qb,qa]==[og('theta_adv_h')[0],og('theta_adv_z')[0],og('q_adv_pre')[0],og('q_adv_z')[0]],'new observer differs from PR206 vertical update');counts['PR206_matching_vertical_updates']+=1
   require(og('q_rk_factors')==[dt,my] and geom[0]==st[3] and geom[1]==qs[3] and geom[7]==mb and geo_up[7]==mt,'actual consumed state/coordinate bridge')
   require(all(st[n]==get('geometry',k-3+n)[0] and qs[n]==get('geometry',k-3+n)[1] for n in range(7)),'full consumed predictor stencil bridge')
   a,qark=og('after_rk')[2],og('after_rk')[1];theta_scale=dt*my/(a*(1+RATIO*qark));qscale=dt*my/og('q_rk_after')[1]
   qfb,qft=ab+lb,at+lt;qr,qc=split_faces(qfb,qft,qmb,qmt,qs[3]);tr,tc=split_faces(fb,ft,mb,mt,st[3]);p=priorrows[t,k]
   qdelta=dt*my*(qa-qb)/og('q_rk_after')[1];qnative=qdelta*1000;thetanative=theta_scale*(ta-before)
   require(qnative==float(p['qv_transport_vertical_g_kg']),'prior qv allocation scale')
   require(math.isclose(thetanative,float(p['theta_slow_transport_vertical_K']),rel_tol=1e-14,abs_tol=1e-14),'prior theta allocation scale')
   dry0=(og('start')[0]+300)/(1+RATIO*og('start')[1]);qconvert=-RATIO*dry0/(1+RATIO*qark)*qdelta
   acoustic=float(p['theta_acoustic_transport_vertical_K']);priorqconv=float(p['theta_qv_conversion_transport_vertical_K']);require(qconvert==priorqconv,'paired qv conversion')
   z0=(geom[4]+geom[5])/f32(9.81);z1=(geo_up[4]+geo_up[5])/f32(9.81);dry=(st[3]+300)/(1+RATIO*qs[3]);dryup=(st[4]+300)/(1+RATIO*qs[4]);require(z1>z0 and geo_up[16]<geom[16],'eta/height orientation')
   qrel=-qscale*dz*qr*1000;qmass=-qscale*dz*qc*1000;threl=-theta_scale*dz*tr;thmass=-theta_scale*dz*tc
   rows.append({'source_seconds':t,'end_seconds':t+60,'k':k,'qv_vertical_g_kg':qnative,'qv_horizontal_g_kg':float(p['qv_transport_horizontal_g_kg']),'qv_center_relative_face_g_kg':qrel,'qv_center_mass_convergence_g_kg':qmass,'qv_native_divergence_roundoff_g_kg':qnative-(qrel+qmass),'dry_theta_slow_vertical_K':thetanative,'dry_theta_slow_center_relative_face_K':threl,'dry_theta_slow_center_mass_convergence_K':thmass,'dry_theta_slow_native_divergence_roundoff_K':thetanative-(threl+thmass),'dry_theta_acoustic_vertical_K':acoustic,'dry_theta_qv_conversion_vertical_K':qconvert,'dry_theta_paired_vertical_K':thetanative+acoustic+qconvert,'dry_theta_paired_horizontal_K':float(p['theta_slow_transport_horizontal_K'])+float(p['theta_acoustic_transport_horizontal_K'])+float(p['theta_qv_conversion_transport_horizontal_K']),'qv_PDeffective_face_lower':qfb/qmb if qmb else None,'qv_PDeffective_face_upper':qft/qmt if qmt else None,'qv_pred_center_minus_below_g_kg':1000*(qs[3]-qs[2]),'qv_pred_above_minus_center_g_kg':1000*(qs[4]-qs[3]),'qv_old_above_minus_center_g_kg':1000*(qo[4]-qo[3]),'dry_theta_pred_above_minus_center_K':dryup-dry,'theta_eta_mass_flux_lower_native_Pa_s':mb,'theta_eta_mass_flux_upper_native_Pa_s':mt,'qv_eta_mass_flux_lower_native_Pa_s':qmb,'qv_eta_mass_flux_upper_native_Pa_s':qmt,'geometric_W_lower_m_s':geom[6],'geometric_W_upper_m_s':geo_up[6],'pred_layer_thickness_geopotential_m':z1-z0,'pred_eta_layer_thickness':geom[15],'pred_mass_eta':geom[16],'pred_interface_eta':geom[17],'mapfactor_y':geom[18],'theta_pred_center_K':dry,'qv_pred_center_g_kg':1000*qs[3]})
 sums=['qv_vertical_g_kg','qv_horizontal_g_kg','qv_center_relative_face_g_kg','qv_center_mass_convergence_g_kg','qv_native_divergence_roundoff_g_kg','dry_theta_slow_vertical_K','dry_theta_slow_center_relative_face_K','dry_theta_slow_center_mass_convergence_K','dry_theta_slow_native_divergence_roundoff_K','dry_theta_acoustic_vertical_K','dry_theta_qv_conversion_vertical_K','dry_theta_paired_vertical_K','dry_theta_paired_horizontal_K']
 means=['qv_pred_center_minus_below_g_kg','qv_pred_above_minus_center_g_kg','qv_old_above_minus_center_g_kg','dry_theta_pred_above_minus_center_K','theta_eta_mass_flux_lower_native_Pa_s','theta_eta_mass_flux_upper_native_Pa_s','qv_eta_mass_flux_lower_native_Pa_s','qv_eta_mass_flux_upper_native_Pa_s','geometric_W_lower_m_s','geometric_W_upper_m_s','pred_layer_thickness_geopotential_m']
 def summary(selected):
  out=[]
  for k in [7,8]:
   rr=[r for r in selected if r['k']==k];item={'k':k,'steps':len(rr),'sums':{n:math.fsum(r[n] for r in rr) for n in sums},'means':{n:math.fsum(r[n] for r in rr)/len(rr) for n in means},'qv_vertical_positive_steps':sum(r['qv_vertical_g_kg']>0 for r in rr),'qv_mass_flux_both_positive_steps':sum(r['qv_eta_mass_flux_lower_native_Pa_s']>0 and r['qv_eta_mass_flux_upper_native_Pa_s']>0 for r in rr),'geometric_W_both_negative_steps':sum(r['geometric_W_lower_m_s']<0 and r['geometric_W_upper_m_s']<0 for r in rr),'qv_pred_above_drier_steps':sum(r['qv_pred_above_minus_center_g_kg']<0 for r in rr),'effective_PD_face_undefined_count':sum(r[n] is None for r in rr for n in ['qv_PDeffective_face_lower','qv_PDeffective_face_upper'])};out.append(item)
  return out
 hourly=[{'start_hour_UTC':h,'end_hour_UTC':h+1,'layers':summary([r for r in rows if h*3600<=r['source_seconds']<(h+1)*3600])} for h in range(12,17) if any(h*3600<=r['source_seconds']<(h+1)*3600 for r in rows)]
 if not partial:
  for interval in hourly:
   priorhour=next(x for x in oldresult['hourly_layers'] if x['start_seconds']==interval['start_hour_UTC']*3600)
   for layer in interval['layers']:
    priorlayer=next(x for x in priorhour['layers'] if x['k']==layer['k'])
    require(math.isclose(layer['sums']['dry_theta_paired_vertical_K'],priorlayer['dry_theta_paired_processes_K']['vertical_transport'],rel_tol=1e-13,abs_tol=1e-13),'hourly paired theta bridge')
    require(math.isclose(layer['sums']['qv_vertical_g_kg'],priorlayer['qv_components_g_kg']['transport_vertical'],rel_tol=1e-13,abs_tol=1e-13),'hourly vapor bridge')
 result={'status':'NATIVE_TRANSPORT_FACES_STATE_COORDINATES_CONNECTED' if not partial else 'PARTIAL_DEVELOPMENT_ONLY','source_steps':len(times),'selected_i_j_one_based':[37,119],'native_layers':[7,8],'replay_counts':counts,'hourly':hourly,'five_hour_layers':summary(rows),'source_hour_horizontal_context':neighborhood(prior),'prior_state_evidence':prior,'original_daily_SOLRAD_statistics_unchanged':oldresult['original_daily_SOLRAD_statistics_unchanged'],'cold_history_array_pairs_equal':comparison['pairs'] if comparison else None,'decision':{'completed_boundary':'actual final-RK native7–8 mass-coordinate vertical face transport connected to consumed states, gradients, instantaneous theta flux and time-averaged PD vapor flux; hourly reversal retained','action':'retain current production physics; restrict afternoon forecast applicability. No optical or PBL coefficient correction is justified by this same-case coordinate/face diagnosis','vertical_motion_accuracy_approved':False,'vertical_flow_error_uniquely_confirmed':False,'production_defect_confirmed':False,'coefficient_change_justified':False,'next_single_boundary':'If pursuing physical cause, connect actual horizontal face transport and mass normalization to the warm/dry layer7–8 neighborhood and observed/driving thermodynamics and winds before interpreting air origin; the existing observations do not validate native eta mass flux or geometric vertical velocity'},'definitions':{'native_mass_flux':'rom is the actually consumed map-coupled eta vertical mass flux in native pressure units per second; eta decreases with increasing k. Positive flux points toward increasing eta. It is neither geometric W nor pressure omega','distinct_stages':'theta slow transport uses final-RK predictor instantaneous wwE; PD qv uses acoustic-time-averaged ww_m after WW_SPLIT. Predictor field and source-updated field_old are separately retained','reference_split':'Ftop-Fbottom = [(Ftop-qcenter*Mtop)-(Fbottom-qcenter*Mbottom)] + qcenter*(Mtop-Mbottom). Central actual transported field is the declared reference. Split depends on reference and includes mass convergence; neither part is a unique material heating or moisture source. Native rounding reported separately','paired_theta':'slow theta is transported moist perturbation, not full dry theta. PR206 dry conversion and acoustic vertical terms are separately retained; face split alone does not equal paired dry-theta total','coordinate_velocity':'No W-to-WW conversion or -W*dtheta/dz replacement; native eta and geopotential heights stored. Hourly history drytheta and geometric W are state context, not substep truth','independent_constraints':'PR204 IGRA/METAR and PR205 forcing constrain sampled thermodynamics/cloud presence with time, balloon drift and point/grid limitations, not vertical-motion truth. Analysis and forecast profiles are not identical time intervals'},'original_24h_scores_changed':False,'production_calculation_changes':False,'coefficient_or_policy_changes':False,'physical_accuracy_approved':False,'global_water_conservation_approved':False,'whole_energy_approved':False,'original_seven_conditions_changed':False,'new_bounded_WRF_processes':1,'new_cold24h_WRF_processes':0,'private_build_compile_archive_link_processes':6,'new_WPS_REAL_standalone_RTE_Mie_or_saturation_processes':0,'new_model_runs_in_saved_replay':0}
 return result,rows
