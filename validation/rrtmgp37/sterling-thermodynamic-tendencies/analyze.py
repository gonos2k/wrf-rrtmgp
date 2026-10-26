"""Actual native updates and explicit finite-change diagnostic attribution.

No predictor-timescale summation, endpoint fitting, or physical accuracy approval.
"""
import math,struct
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
RATIO=f32(f32(461.6)/287.)
def require(ok,msg):
 if not ok:raise ValueError(msg)
def parse(text,partial=False):
 d={};neighbors=[];lines=0
 for line in text.splitlines():
  x=line.split()
  if partial and len(x)<6:continue
  require(len(x)>=6,'truncated observation');t=int(float(x[0]));tag=x[1];rk,s,k=map(int,x[2:5]);v=list(map(float,x[5:]));require(all(math.isfinite(z) for z in v),'nonfinite observation')
  require(43200<=t<61200 and t%60==0,'time support')
  if tag.startswith('neighbor_'):neighbors.append([t,tag,rk,s,k,*v]);continue
  key=(t,tag,rk,s,k);require(key not in d,'duplicate '+str(key));d[key]=v;lines+=1
 times=sorted(t for t in {k[0] for k in d} if (t,'end',0,0,12) in d)
 if not partial:require(times==list(range(43200,61200,60)),'missing primary steps')
 return d,neighbors,lines,times
def dry(stock):return (stock[0]+300)/(1+RATIO*stock[1])
def native_rhs(pre,tf,h,a,my):return f32(f32(pre+f32(tf/my))+f32(f32(a*h)/my))
def acoustic_flux(v):
 dt,my,mx,dy,dx,dz,vn,vs,ue,uw,tn,tc,ts,te,tw,zt,zb=v
 y=f32(f32(.5*dy)*f32(f32(vn*f32(tn+tc))-f32(vs*f32(tc+ts))))
 x=f32(f32(.5*dx)*f32(f32(ue*f32(te+tc))-f32(uw*f32(tc+tw))))
 h=f32(mx*f32(y+x));z=f32(dz*f32(zt-zb))
 return h,z,f32(f32(dt*my)*f32(h+z))
def analyze(text,partial=False):
 d,neighbors,lines,times=parse(text,partial);steps=[];counts={'native_PD':0,'native_RK_qv':0,'native_moist_theta_conversion':0,'native_theta_RHS':0,'native_acoustic_RHS':0,'native_acoustic_flux':0,'native_acoustic_finish':0,'actual_step_continuity':0};get=lambda t,tag,r,s,k:d[t,tag,r,s,k]
 acoustic_roster={}
 for t,tag,rk,iteration,k in d:
  if tag=='ac_before' and rk==3:acoustic_roster.setdefault((t,k),[]).append(iteration)
 for t in times:
  layers=[]
  for k in range(5,13):
   g=lambda tag,r=0,s=0:get(t,tag,r,s,k)
   start=g('start');end=g('end');ark=g('after_rk');micro0=g('micro_before');micro1=g('after_moistfinish');q0=g('q_pd_before',3,2);q1=g('q_pd_after',3,2);base=g('q_rk_base',3,2);qend=g('q_rk_after',3,2);src=g('q_pd_source',3,2)[0];adv=g('q_rk_advect',3,2)[0];other=g('q_rk_source',3,2)[0];dt,my=g('q_rk_factors',3,2)
   require(dt==60 and min(q0[1],q1[1],base[1],qend[1])>0 and q0[1]==q1[1],'source time/coupling')
   require(f32(f32(f32(q0[1]*q0[0])+f32(dt*src))/q1[1])==q1[0],'native PD update');counts['native_PD']+=1
   require(q1==base,'PD/RK base bridge')
   require(f32(f32(f32(base[1]*base[0])+f32(dt*f32(f32(adv*my)+other)))/qend[1])==qend[0],'native final RK qv update');counts['native_RK_qv']+=1
   require(other==0,'unhandled final RK other source')
   qpre,qz,qx,qy=[g(tag,3,2)[0] for tag in ['q_adv_pre','q_adv_z','q_adv_x','q_adv_y']];require(qy==adv,'qv advection bridge')
   qcomp={}
   for tag,label in [('rad','radiation'),('pbl','PBL'),('cu','cumulus')]:qcomp[label]=dt*(g(tag+'_after_qv',1,2)[0]-g(tag+'_before_qv',1,2)[0])/q0[1]
   qcomp['horizontal_diffusion']=dt*(g('q_scalar_after',1,2)[0]-g('q_scalar_before',1,2)[0])/q0[1]
   qcomp['remaining_PD_source']=dt*src/q0[1]-math.fsum(qcomp.values())
   qcomp['transport_horizontal']=dt*my*(qy-qz)/qend[1];qcomp['transport_vertical']=dt*my*(qz-qpre)/qend[1]
   qcomp['transport_preexisting']=dt*my*qpre/qend[1]
   qcomp['pressure_normalization']=base[0]*(base[1]-qend[1])/qend[1]
   qcomp['native_PD_arithmetic']=(q1[0]-q0[0])-dt*src/q0[1]
   qcomp['native_RK_arithmetic']=(qend[0]-base[0])-(dt*my*adv/qend[1]+qcomp['pressure_normalization'])
   qcomp['start_to_PD_bridge']=q0[0]-start[1];qcomp['RK_to_afterloop_bridge']=ark[1]-qend[0]
   qcomp['pre_micro_bridge']=micro0[1]-ark[1];qcomp['microphysics']=micro1[1]-micro0[1];qcomp['post_micro_bridge']=end[1]-micro1[1]
   qres=(end[1]-start[1])-math.fsum(qcomp.values())
   before=g('convert_before_theta',1,1)[0];qsrc=g('convert_before_qv',1,2)[0];qo=g('convert_old_qv',1,2)[0];to=g('convert_old_t',1,1)[0];converted=g('convert_after_theta',1,1)[0]
   den32=f32(1+f32(RATIO*qo));c32=f32(f32(RATIO*f32(to+300))/den32);reconv=f32(f32(den32*before)+f32(c32*qsrc));require(reconv==converted,'native moist theta tendency conversion');counts['native_moist_theta_conversion']+=1
   den=1+RATIO*qo;theta_old=(to+300)/den;theta_phys={}
   for tag,label in [('rad','radiation'),('pbl','PBL'),('cu','cumulus')]:
    ft=g(tag+'_after_theta',1,1)[0]-g(tag+'_before_theta',1,1)[0];fq=g(tag+'_after_qv',1,2)[0]-g(tag+'_before_qv',1,2)[0]
    theta_phys[label]=dt*(den*ft+RATIO*theta_old*fq)
   theta_phys['remaining_converted_physics']=dt*(den*before+RATIO*theta_old*qsrc)-math.fsum(theta_phys.values())
   theta_phys['conversion_arithmetic']=dt*converted-math.fsum(theta_phys.values())
   rhs0=g('theta_rhs_before',3,1)[0];rhs=g('theta_rhs_after',3,1)[0];tf,h,apred,myt=g('theta_rhs_operands',3,1)
   require(native_rhs(rhs0,tf,h,apred,myt)==rhs,'native theta RHS');counts['native_theta_RHS']+=1
   pre,th,tz=[g(tag,3,1)[0] for tag in ['theta_adv_pre','theta_adv_h','theta_adv_z']];require(tz==rhs0 and myt==my,'theta advection/RHS bridge')
   theta_phys['slow_transport_horizontal']=dt*my*(th-pre);theta_phys['slow_transport_vertical']=dt*my*(tz-th);theta_phys['slow_transport_preexisting']=dt*my*pre
   mix=math.fsum(g('tf_after_rktendency',r,1)[0]-g('tf_before_rktendency',r,1)[0] for r in [1,2,3])
   theta_phys['thermal_diffusion']=dt*mix;theta_phys['saved_or_other_held_thermal_source']=dt*(tf-converted-mix)
   theta_phys['RHS_assembly_arithmetic']=dt*my*rhs-(dt*my*rhs0+dt*tf+dt*apred*h)
   acsteps=sorted(acoustic_roster[t,k]);require(acsteps==list(range(1,len(acsteps)+1)),'acoustic step roster')
   dt_total=0.;acH=acZ=acround=0.;prev=None
   for n in acsteps:
    a=get(t,'ac_before',3,n,k);b=get(t,'ac_rhs_after',3,n,k)[0];v=get(t,'ac_flux_operands',3,n,k);c=get(t,'ac_flux_after',3,n,k)[0]
    require(f32(a[0]+f32(f32(a[1]*a[2])*a[3]))==b,'native acoustic RHS addition');counts['native_acoustic_RHS']+=1
    H,Z,sub=acoustic_flux(v);require(f32(b-sub)==c,'native acoustic flux update');counts['native_acoustic_flux']+=1
    require(a[3]==rhs and a[1]==my and a[2]==v[0] and (prev is None or prev==a[0]),'acoustic stage continuity')
    dt_total+=a[2];acH-=a[2]*my*H;acZ-=a[2]*my*Z;acround+=(b-a[0])-a[2]*my*rhs+(c-b)+a[2]*my*(H+Z);prev=c
   require(dt_total==60,'do not sum predictor intervals')
   prep=g('smallprep',3,1);finish=g('smallfinish_before',3,1);b0,save,ap,af,hold,dts,n=finish;require(prev==b0 and ap==apred and int(n)==len(acsteps),'final acoustic bridge')
   correction=f32(f32(f32(dts*n)*ap)*hold);product=f32(save*ap);finish_q=f32(f32(f32(b0-correction)+product)/af)
   require(finish_q==g('after_smallfinish',3,0)[0],'native acoustic finish');counts['native_acoustic_finish']+=1
   theta_phys['acoustic_transport_horizontal']=acH;theta_phys['acoustic_transport_vertical']=acZ;theta_phys['acoustic_update_arithmetic']=acround
   # Independently observed reset/reconstruction and cancellation operations.
   theta_phys['acoustic_reset_arithmetic']=prep[0]+save*ap-start[2]*start[0]
   theta_phys['held_microphysics_cancellation']=dt*apred*h-dts*n*ap*hold
   theta_phys['acoustic_finish_arithmetic']=af*finish_q-(b0-dts*n*ap*hold+save*ap)
   theta_phys['finish_to_afterloop_bridge']=ark[2]*ark[0]-af*finish_q
   theta_phys['pressure_normalization']=-start[0]*(ark[2]-start[2])
   ftheta=1/(ark[2]*(1+RATIO*ark[1]));fq=-RATIO*dry(start)/(1+RATIO*ark[1]);drycomp={n:ftheta*v for n,v in theta_phys.items()}
   # Pair the accepted vapor source/transport with moist theta. This is an
   # explicitly declared finite-change diagnostic allocation, not a rerun.
   q_rk={n:v for n,v in qcomp.items() if n not in ['pre_micro_bridge','microphysics','post_micro_bridge']}
   for n,v in q_rk.items():drycomp['qv_conversion_'+n]=fq*v
   native_micro=g('micro_env_after')[0]-g('micro_env_before')[0]
   drycomp['pre_micro_bridge']=dry(micro0)-dry(ark);drycomp['microphysics']=native_micro;drycomp['moist_finish_conversion_arithmetic']=(dry(micro1)-dry(micro0))-native_micro;drycomp['post_micro_bridge']=dry(end)-dry(micro1)
   dry_delta=dry(end)-dry(start);dry_res=dry_delta-math.fsum(drycomp.values())
   p0=f32(start[4]+start[5]);p1=f32(end[4]+end[5]);pi0=(p0/100000)**(287/1004.5);pi1=(p1/100000)**(287/1004.5)
   layers.append({'k':k,'start_dry_theta_diagnostic_K':dry(start),'end_dry_theta_diagnostic_K':dry(end),'dry_theta_change_K':dry_delta,'dry_theta_components_K':drycomp,'dry_theta_identity_residual_K':dry_res,'qv_change_kg_kg':end[1]-start[1],'qv_components_kg_kg':qcomp,'qv_identity_residual_kg_kg':qres,'T_change_diagnostic_K':dry(end)*pi1-dry(start)*pi0,'T_theta_part_K':pi1*dry_delta,'T_pressure_part_K':dry(start)*(pi1-pi0),'start_end_pressure_Pa':[p0,p1],'microphysics_native_dry_theta_change_K':g('micro_env_after')[0]-g('micro_env_before')[0]})
  steps.append({'source_seconds':t,'end_seconds':t+60,'layers':layers})
 for a,b in zip(times,times[1:]):
  if b!=a+60:continue
  for k in range(5,13):require(get(a,'end',0,0,k)[:2]==get(b,'start',0,0,k)[:2],'actual consecutive theta/qv continuity');counts['actual_step_continuity']+=1
 def summary(selected):
  result=[]
  for k in range(5,13):
   rows=[x['layers'][k-5] for x in selected];dc={n:math.fsum(r['dry_theta_components_K'][n] for r in rows) for n in rows[0]['dry_theta_components_K']};qc={n:math.fsum(r['qv_components_kg_kg'][n] for r in rows) for n in rows[0]['qv_components_kg_kg']}
   paired={}
   for n in ['radiation','PBL','cumulus']:paired[n]=dc[n]+dc['qv_conversion_'+n]
   paired['horizontal_diffusion']=dc['thermal_diffusion']+dc['qv_conversion_horizontal_diffusion']
   paired['horizontal_transport']=dc['slow_transport_horizontal']+dc['acoustic_transport_horizontal']+dc['qv_conversion_transport_horizontal']
   paired['vertical_transport']=dc['slow_transport_vertical']+dc['acoustic_transport_vertical']+dc['qv_conversion_transport_vertical']
   paired['pressure_normalization']=dc['pressure_normalization']+dc['qv_conversion_pressure_normalization']
   paired['microphysics']=dc['microphysics'];paired['other_observed_operations_and_arithmetic']=math.fsum(v for n,v in dc.items() if n not in ['radiation','PBL','cumulus','qv_conversion_radiation','qv_conversion_PBL','qv_conversion_cumulus','thermal_diffusion','qv_conversion_horizontal_diffusion','slow_transport_horizontal','acoustic_transport_horizontal','qv_conversion_transport_horizontal','slow_transport_vertical','acoustic_transport_vertical','qv_conversion_transport_vertical','pressure_normalization','qv_conversion_pressure_normalization','microphysics'])
   result.append({'k':k,'dry_theta_change_K':math.fsum(r['dry_theta_change_K'] for r in rows),'qv_change_g_kg':1000*math.fsum(r['qv_change_kg_kg'] for r in rows),'T_change_diagnostic_K':math.fsum(r['T_change_diagnostic_K'] for r in rows),'T_theta_part_K':math.fsum(r['T_theta_part_K'] for r in rows),'T_pressure_part_K':math.fsum(r['T_pressure_part_K'] for r in rows),'dry_theta_paired_processes_K':paired,'dry_theta_detailed_components_K':dc,'qv_components_g_kg':{n:1000*v for n,v in qc.items()},'dry_theta_identity_residual_K':math.fsum(r['dry_theta_identity_residual_K'] for r in rows),'qv_identity_residual_g_kg':1000*math.fsum(r['qv_identity_residual_kg_kg'] for r in rows)})
  return result
 return {'status':'ACTUAL_THERMODYNAMIC_TENDENCIES_REPLAYED' if not partial else 'PARTIAL_DEVELOPMENT_ONLY','observed_lines':lines,'primary_source_seconds':[43200,61200],'source_steps':len(times),'native_layers':[5,12],'selected_i_j_one_based':[37,119],'replay_counts':counts,'five_hour_layers':summary(steps) if steps else [],'hourly_layers':[{'start_seconds':h,'end_seconds':h+3600,'layers':summary([r for r in steps if h<=r['source_seconds']<h+3600])} for h in range(43200,61200,3600) if any(h<=r['source_seconds']<h+3600 for r in steps)],'steps':steps,'neighborhood_records':len(neighbors),'native_moist_theta_Rv_over_Rd':RATIO,'diagnostic_convention':'finite-change allocation for drytheta=(pert_theta_m+300)/(1+r*qv), evaluated inREAL64 from actual native operands. End-point denominators explicitly shared by source/transport components; not counterfactual causal experiments. Temperature adds separate Exner-pressure term. Native arithmetic is replayed exactly and diagnostic residuals reported without fitted physical tolerance','production_calculation_changes':False,'coefficient_or_policy_changes':False,'physical_accuracy_approved':False,'whole_energy_approved':False,'global_water_conservation_approved':False,'original_seven_conditions_changed':False,'new_model_runs_in_saved_replay':0}
