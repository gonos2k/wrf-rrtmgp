"""Replay actual local operators. State ledgers do not certify global conservation."""
import math,struct,datetime as dt
SPEC=['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL']
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
G=f32(9.81)
NATIVE_SPECIES_TAGS={'pd_before','pd_source','pd_after','scalar_before','scalar_after','rk_base','rk_source','rk_advect','rk_factors','rk_after','adv_pre','adv_z','adv_x','adv_y','faces'}
STOCK_TAGS={'start','pd_before','pd_after','rk_base','rk_after','after_rk','micro_before','micro_after','end'}
def require(ok,msg):
 if not ok:raise ValueError(msg)
def parse(text):
 d={};neighbors={};count=0
 for line in text.splitlines():
  x=line.split();require(len(x)>=6,'truncated native observation');t=int(float(x[0]));tag=x[1];rk,sp,k=map(int,x[2:5]);v=list(map(float,x[5:]));require(all(math.isfinite(a) for a in v),'nonfinite observation')
  require(60600<=t<65400 and t%60==0,'operator time support')
  if tag.startswith('neighbor_'):
   i,j=map(int,v[:2]);key=(t,tag,k,i,j);require(key not in neighbors,'duplicate neighborhood');neighbors[key]=v[2:]
  else:
   if tag in NATIVE_SPECIES_TAGS:sp-=1
   # RK metadata on post-loop stocks is immaterial; retain only meaningful RK context.
   if tag not in NATIVE_SPECIES_TAGS:rk=0
   key=(t,tag,rk,sp,k);require(key not in d,'duplicate operator sample '+str(key));d[key]=v
  count+=1
 times=sorted({k[0] for k in d});require(times==list(range(60600,65400,60)),'missing source steps')
 for t in times:
  for tag in ['start','after_rk','micro_before','micro_after','end']:
   for sp in range(1,8):
    for k in range(1,45):require((t,tag,0,sp,k) in d,'incomplete state column')
  for tag in ['neighbor_start','neighbor_end']:
   require(sum(key[:2]==(t,tag) for key in neighbors)==147,'incomplete fixed neighborhood')
 return d,neighbors,count

def analyze(text,parsed=None):
 d,nb,count=parse(text) if parsed is None else parsed;get=lambda t,tag,s,k,r=0:d[t,tag,r,s,k]
 mass=lambda t,tag,s,k,r=0: -get(t,tag,s,k,r)[2]/G*get(t,tag,s,k,r)[1]*get(t,tag,s,k,r)[0]
 checks={'PD_source_updates':0,'final_RK_updates':0,'native_directional_divergences':0,'PD_to_final_RK_base':0,'no_implicit_advection_addition':0}
 steps=[]
 for t in range(60600,65400,60):
  species=[]
  for s in range(1,8):
   layers=[]
   for k in range(1,45):
    pd0=get(t,'pd_before',s,k,3);pd1=get(t,'pd_after',s,k,3);src=get(t,'pd_source',s,k,3)[0];base=get(t,'rk_base',s,k,3);end=get(t,'rk_after',s,k,3);adv=get(t,'rk_advect',s,k,3)[0];other=get(t,'rk_source',s,k,3)[0];dt_s,my=get(t,'rk_factors',s,k,3)
    require(dt_s==60 and pd0[1]>0 and pd1[1]>0 and base[1]>0 and end[1]>0,'invalid dt/coupling')
    pd_replay=f32(f32(f32(pd0[1]*pd0[0])+f32(dt_s*src))/pd1[1]);require(pd_replay==pd1[0],'native PD scalar replay');checks['PD_source_updates']+=1
    require(pd1==base,'PD state changed before final RK base');checks['PD_to_final_RK_base']+=1
    rhs=f32(f32(adv*my)+other);q=f32(f32(f32(base[1]*base[0])+f32(dt_s*rhs))/end[1]);require(q==end[0],'native final RK replay');checks['final_RK_updates']+=1
    pre,z,x,y=[get(t,tag,s,k,3)[0] for tag in ['adv_pre','adv_z','adv_x','adv_y']]
    fl=get(t,'faces',s,k,3);require(len(fl)==17,'face schema');wx,ex,wxl,exl,sy,ny,syl,nyl,bz,tz,bzl,tzl,rdx,rdy,rdz,mx,myf=fl
    zr=f32(pre-f32(rdz*f32(f32(f32(tz-bz)+tzl)-bzl)))
    xr=f32(z-f32(mx*f32(rdx*f32(f32(f32(ex-wx)+exl)-wxl))))
    yr=f32(x-f32(mx*f32(rdy*f32(f32(f32(ny-sy)+nyl)-syl))))
    require((zr,xr,yr)==(z,x,y),'native limited directional divergence replay');checks['native_directional_divergences']+=3
    require(other==0,'unhandled final RK other source');require(y==adv and my==myf,'unobserved implicit/advection or mapfactor addition');checks['no_implicit_advection_addition']+=1
    w=-base[2]/G
    mm=lambda tag:mass(t,tag,s,k)
    m0=mm('start');m1=mm('end');pdactual=mass(t,'pd_after',s,k,3)-mass(t,'pd_before',s,k,3);rkactual=mass(t,'rk_after',s,k,3)-mass(t,'rk_base',s,k,3)
    pdformal=w*dt_s*src;rkformal=w*dt_s*(adv*my+other)
    pbl=(get(t,'pbl_after',s,k)[0]-get(t,'pbl_before',s,k)[0])*w*dt_s
    cu=(get(t,'cumulus_after',s,k)[0]-get(t,'cumulus_before',s,k)[0])*w*dt_s
    mixing=(get(t,'scalar_after',s,k,1)[0]-get(t,'scalar_before',s,k,1)[0])*w*dt_s
    # Independently observed state bridges, not a source fitted from residual.
    bridges={'start_to_PD':mass(t,'pd_before',s,k,3)-m0,'PD_to_RK':mass(t,'rk_base',s,k,3)-mass(t,'pd_after',s,k,3),'RK_to_afterloop':mm('after_rk')-mass(t,'rk_after',s,k,3),'afterloop_to_micro':mm('micro_before')-mm('after_rk'),'micro_to_end':m1-mm('micro_after')}
    micro=mm('micro_after')-mm('micro_before');pred=math.fsum([pdactual,rkactual,micro,*bridges.values()]);closure=(m1-m0)-pred
    # This diagnostic telescoping residual is reported unchanged. An endpoint-only
    # ULP test is invalid when intermediate stocks exceed near-zero endpoints.
    # Native PD, final RK and limited-face operations above still replay exactly.
    layers.append({'k':k,'start_kg_m2':m0,'end_kg_m2':m1,'delta_kg_m2':m1-m0,'PD_source_actual_kg_m2':pdactual,'PD_source_formal_kg_m2':pdformal,'PD_arithmetic_difference_kg_m2':pdactual-pdformal,'PBL_formal_kg_m2':pbl,'CU_formal_kg_m2':cu,'horizontal_diffusion_formal_kg_m2':mixing,'other_PD_sources_kg_m2':pdformal-pbl-cu-mixing,'RK_advection_actual_kg_m2':rkactual,'RK_advection_formal_kg_m2':rkformal,'RK_arithmetic_difference_kg_m2':rkactual-rkformal,'advection_pre_kg_m2':w*dt_s*my*pre,'advection_z_kg_m2':w*dt_s*my*(z-pre),'advection_x_kg_m2':w*dt_s*my*(x-z),'advection_y_kg_m2':w*dt_s*my*(y-x),'RK_other_source_kg_m2':w*dt_s*other,'microphysics_actual_kg_m2':micro,'bridges_kg_m2':bridges,'operator_identity_residual_kg_m2':closure,'start_q':get(t,'start',s,k)[0],'before_micro_q':get(t,'micro_before',s,k)[0],'after_micro_q':get(t,'micro_after',s,k)[0],'end_q':get(t,'end',s,k)[0]})
   species.append({'species':SPEC[s-1],'layers':layers})
  e0=get(t,'micro_env_before',0,6);e1=get(t,'micro_env_after',0,6)
  p0=get(t,'micro_env_before_precip',0,0);p1=get(t,'micro_env_after_precip',0,0)
  steps.append({'source_seconds':t,'end_seconds':t+60,'species':species,'micro_layer6':{'theta_before_after_K':[e0[0],e1[0]],'Exner_before_after':[e0[1],e1[1]],'pressure_before_after_Pa':[e0[2],e1[2]],'actual_temperature_before_after_K':[e0[0]*e0[1],e1[0]*e1[1]],'grid_precip_before_after_mm':[p0,p1],'micro_RAINNC_increment_mm':p1[1]-p0[1]}})
 primary=[r for r in steps if 61200<=r['source_seconds']<64800];require(len(primary)==60,'primary one-hour support')
 # Continuity requires the actual end of the previous step, not hourly interpolation.
 for a,b in zip(steps,steps[1:]):
  for s in range(7):
   for k in range(44):require(a['species'][s]['layers'][k]['end_q']==b['species'][s]['layers'][k]['start_q'],'step boundary state discontinuity')
 keys=[k for k in primary[0]['species'][0]['layers'][0] if k.endswith('_kg_m2') and k!='bridges_kg_m2']
 def integrate(selected):
  return {key:math.fsum(r['species'][s]['layers'][k][key] for r in primary for s,k in selected) for key in keys if key not in ['start_kg_m2','end_kg_m2']}
 summaries={}
 for s,n in enumerate(SPEC):
  summaries[n]={'layer6':integrate([(s,5)]),'column':integrate([(s,k) for k in range(44)])}
 summaries['all_seven_species']={'layer6':integrate([(s,5) for s in range(7)]),'column':integrate([(s,k) for s in range(7) for k in range(44)])}
 def qc(r):return r['species'][1]['layers'][5]
 first_zero=next((r for r in primary if qc(r)['start_q']>0 and qc(r)['end_q']==0),None)
 biggest=min(primary,key=lambda r:qc(r)['delta_kg_m2'])
 first_decline=next((r for r in primary if qc(r)['delta_kg_m2']<0),None)
 neighborhood=[]
 for t in [61200,primary[-1]['source_seconds']]:
  tag='neighbor_start' if t==61200 else 'neighbor_end'
  neighborhood.append({'state_seconds':t if tag=='neighbor_start' else t+60,'layer6': [{'i':i,'j':j,'qv':nb[t,tag,6,i,j][0],'qc':nb[t,tag,6,i,j][1],'qr':nb[t,tag,6,i,j][2],'native_staggered_u':nb[t,tag,6,i,j][3],'native_staggered_v':nb[t,tag,6,i,j][4],'native_staggered_w':nb[t,tag,6,i,j][5]} for j in range(116,123) for i in range(34,41)]})
 witness=lambda r:None if r is None else {'source_seconds':r['source_seconds'],'end_seconds':r['end_seconds'],'cloud_layer6':qc(r),'all_species_layer6':[{'species':a['species'],**a['layers'][5]} for a in r['species']],'micro_layer6':r['micro_layer6'],'cloud_layer6_stage_chain':[{'stage':tag,'q':get(r['source_seconds'],tag,2,6,rr)[0],'kg_m2':mass(r['source_seconds'],tag,2,6,rr)} for tag,rr in [('start',0),('pd_before',3),('pd_after',3),('rk_base',3),('rk_after',3),('after_rk',0),('micro_before',0),('micro_after',0),('end',0)]]}
 return {'status':'LOCAL_CLOUD_LOSS_OPERATORS_REPLAYED','species':SPEC,'source_window_seconds':[60600,65400],'primary_window_seconds':[61200,64800],'observed_lines':count,'replay_counts':checks,'primary_hour_processes_kg_m2':summaries,'first_decline_step':witness(first_decline),'largest_cloud_loss_step':witness(biggest),'first_complete_loss_step':witness(first_zero),'neighborhood_at_hour_endpoints':neighborhood,'steps':steps,'diagnostic_mass_convention':'nativeREAL32pressurecoupling from actualMUandMUB, diagnosticREAL64products with-DNW/nativeg; no fixed-layer-mass approximation, no claim of identical arithmetic to the conserved scalar update','new_model_runs_in_saved_replay':0,'production_changes':False,'physical_accuracy_approved':False,'global_water_conservation_approved':False,'original_seven_conditions_changed':False}
