"""PR192 operator accounting, with the explicit corrected KF Eta expiry contract.
No source field or boundary term is removed from the original ledger.
"""
import math
from collections import defaultdict

def require(x,m):
 if not x:raise ValueError(m)

def parse(text):
 d={};bad=[]
 for line in text.splitlines():
  a=line.split();t=int(float(a[0]));k=(t,a[1],int(a[2]));v=list(map(float,a[3:]));require(k not in d,'duplicate runtime record')
  if not all(math.isfinite(x) for x in v):bad.append(k)
  d[k]=v
 return d,bad

def analyze(text,receipt):
 d,bad=parse(text);require(not bad,'nonfinite runtime reductions')
 starts=sorted(t for t,k,i in d if k=='start' and i==1)
 times=[t for t in starts if all((t,'end',i) in d for i in range(1,8))]
 require(times,'no completed model steps')
 require(all(b-a==60 for a,b in zip(times,times[1:])),'noncontiguous physical steps')
 A=d[(0,'geometry',0)][0];get=lambda t,k,i=0:d[(t,k,i)]
 allv=lambda t,k:math.fsum(get(t,k,i)[0] for i in range(1,8))
 native=lambda t,k:math.fsum(get(t,k,i)[0] for i in range(2,9))
 water=[];radiation=[];frozen=[];categories=[];expiry=[]
 for t in times:
  dt=get(t,'pd_tendency',2)[1];require(dt==60,'physical final-PD time changed')
  rate=lambda k:native(t,k)*dt
  s0=allv(t,'start');s1=allv(t,'end');dw=s1-s0
  p0=get(t,'precip_start');p1=get(t,'precip_end');pm=get(t,'precip_micro_before');pma=get(t,'precip_micro_after');pa=get(t,'precip_after_advance');pb=get(t,'precip_before_advance')
  P=(p1[0]-p0[0])+(p1[3]-p0[3]);E=pm[10]*dt
  pc_all=pa[0]-pb[0];pc_i=pa[1]-pb[1];pc_b=pa[2]-pb[2]
  mp_p=(pma[3]-pm[3]);pbl=(allv(t,'pbl_after')-allv(t,'pbl_before'))*dt
  cu=(allv(t,'cumulus_after')-allv(t,'cumulus_before'))*dt
  phy=rate('before_relax');relax=rate('after_relax')-phy;spec=rate('after_spec_tend')-rate('after_relax')
  pdformal=rate('pd_tendency');source_change=pdformal-rate('after_spec_tend');pdactual=native(t,'pd_after')-native(t,'pd_before');pd_num=pdactual-pdformal
  adv=rate('advection_rate');other_rk=rate('rk_other_tendency');rkactual=native(t,'rk_after')-native(t,'rk_base');rk_num=rkactual-adv-other_rk
  mp=allv(t,'micro_after')-allv(t,'micro_before');fm=allv(t,'final_mu_after')-allv(t,'final_mu_before');fq=native(t,'final_q_after')-native(t,'final_q_before')
  bridges={'start_to_PD':native(t,'pd_before')-s0,'PD_to_RK_base':native(t,'rk_base')-native(t,'pd_after'),'RK_to_all':allv(t,'after_rk')-native(t,'rk_after'),'RK_to_microphysics':allv(t,'micro_before')-allv(t,'after_rk'),'microphysics_to_final_MU':allv(t,'final_mu_before')-allv(t,'micro_after'),'MU_to_final_q':native(t,'final_q_before')-allv(t,'final_mu_after'),'final_q_to_end':s1-native(t,'final_q_after')}
  explained=math.fsum([phy,relax,spec,source_change,adv,other_rk,mp,fm,fq,pd_num,rk_num,*bridges.values()]);closure=dw-explained
  cat=[get(t,'cu_column_category',i) for i in range(1,5)]
  require(sum(c[2] for c in cat)==88*97,'CU interior column coverage')
  cu_input=math.fsum(c[0] for c in cat)*dt;p_input=math.fsum(c[1] for c in cat)*dt
  # Counters are REAL32 accumulated products; keep their difference from the actual rate integral.
  p_round=pc_i-p_input
  cu_add_round=cu-cu_input
  cat_res=[(c[0]+c[1])*dt for c in cat]
  decomposition=math.fsum(cat_res)+p_round+cu_add_round
  require(abs((cu+pc_i)-decomposition)<=64*math.ulp(max(abs(s0),abs(s1))),'CU category accounting')
  wr={'source_time_s':t,'end_time_s':t+60,'W_start_kg_m2':s0/A,'W_end_kg_m2':s1/A,'dW':dw/A,'P_full':P/A,'E_native_support':E/A,'QFX_outer_unapplied':(pm[9]-pm[10])*dt/A,'advection_operator':adv/A,'relaxation':relax/A,'specified_tendency':spec/A,'final_MU':fm/A,'final_q':fq/A,'PBL':pbl/A,'CU':cu/A,'other_physics_mixing':(phy-pbl-cu)/A,'microphysics':mp/A,'PD_arithmetic':pd_num/A,'RK_arithmetic':rk_num/A,'source_assembly_to_PD_change':source_change/A,'other_final_RK_source':other_rk/A,'evaluation_bridges':math.fsum(bridges.values())/A,'operator_reconstruction_residual':closure/A,'stock_surface_boundary_residual':(dw-E+P-adv-relax-spec-fm-fq)/A,'PBL_minus_E':(pbl-E)/A,'CU_plus_RAINC_full':(cu+pc_all)/A,'CU_plus_RAINC_interior':(cu+pc_i)/A,'RAINC_outer_kept':pc_b/A,'RAINC_change_outside_advance_ppt':((p1[0]-p0[0])-pc_all)/A,'RAINNC_change_outside_microphysics':((p1[3]-p0[3])-mp_p)/A,'microphysics_plus_its_RAINNC':(mp+mp_p)/A,'CU_rate_counter_rounding':p_round/A,'CU_addition_rounding':cu_add_round/A,'CU_active_paired_residual':cat_res[0]/A,'CU_inactive_positive_rain':cat_res[1]/A,'CU_tendency_without_positive_rain':cat_res[2]/A,'CU_none':cat_res[3]/A,'RAINSH_increment_full':(p1[6]-p0[6])/A}
  water.append(wr)
  components=['PBL_minus_E','CU_plus_RAINC_full','microphysics_plus_its_RAINNC','other_physics_mixing','PD_arithmetic','RK_arithmetic','source_assembly_to_PD_change','other_final_RK_source','evaluation_bridges','RAINC_change_outside_advance_ppt','RAINNC_change_outside_microphysics']
  require(abs(wr['stock_surface_boundary_residual']-math.fsum(wr[k] for k in components))<=64*math.ulp(max(abs(s0),abs(s1)))/A,'stock/surface residual partition')
  previous_inactive=(get(t-60,'expiry_after')[3]*dt/A) if t-60 in times else None
  driver_due=t==0 or ((t//60+1)%5==0)
  categories.append({'source_time_s':t,'CU_driver_scheduled':driver_due,'previous_post_expiry_inactive_rain_kg_m2_for_60s':previous_inactive,'inactive_rain_change_across_step_start_kg_m2':(cat[1][1]*dt/A-previous_inactive) if previous_inactive is not None else None,'columns':[{'category':i+1,'source_kg_m2':c[0]*dt/A,'rain_kg_m2':c[1]*dt/A,'columns':int(c[2]),'rain_on_NCA_nonpositive_kg_m2':c[3]*dt/A} for i,c in enumerate(cat)]})
  ex0=get(t,'expiry_before');ex1=get(t,'expiry_after')
  require(ex0[2]==ex1[2],'expiry mask changed between pre/post observations')
  require(ex1[0]==0,'selected native expiry did not zero water tendencies')
  require(ex1[1]==0,'corrected KF Eta expiry retained selected PRATEC')
  expiry.append({'source_time_s':t,'expired_interior_columns':int(ex0[2]),'water_tendency_before_kg_s':ex0[0],'water_tendency_after_kg_s':ex1[0],'selected_PRATEC_before_kg_s':ex0[1],'selected_PRATEC_after_kg_s':ex1[1],'new_inactive_positive_rain_kg_m2_per_next_60s':(ex1[3]-ex0[3])*dt/A})
  raw=get(t,'rad_raw');add=get(t,'radiation_actual_add')[0];rhs=[get(t,'actual_thermal_rhs',i) for i in range(1,4)]
  require(all(math.isclose(x[1],add,rel_tol=64*44*2.220446049250313e-16) for x in rhs),'linear radiation component changed across RK source consumers')
  flux=[];phase=raw[3]
  for i,label in enumerate(['LW','SW']):
   stamp=raw[3+i];valid=stamp>=0 and stamp==phase
   f=[raw[5+2*k+i]/A for k in range(6)]
   flux.append({'component':label,'last_observed_source_s':stamp if stamp>=0 else None,'current_radiation_phase_observed':valid,'observed_columns':int(raw[19+i]),'unobserved_physical_columns':8910-int(raw[19+i]),'complete_spatial_observation':int(raw[19+i])==8910,'surface_net':f[0] if valid else None,'native_top_net':f[1] if valid else None,'extended_TOA_net':f[2] if valid else None,'native_convergence':f[1]-f[0] if valid else None,'pressure_mass_heating':f[3] if valid else None,'dry_mass_heating':f[4] if valid else None,'native_interior_convergence':f[5] if valid else None,'max_column_flux_heating_difference':raw[17+i] if valid else None})
  radiation.append({'source_time_s':t,'RHS_radiation_equivalent_J_m2':add*dt/A,'actual_radiation_add_W_m2':add/A,'raw_source_full_W_m2':raw[0]/A,'raw_source_interior_W_m2':raw[1]/A,'native_flux':flux,'isolated_acoustic_state_increment_measured':False})
  for species in [1,2]:
   if (t,'frozen_consumption',species) not in d:continue
   f=get(t,'frozen_consumption',species);require(f[7]==t,'stale frozen input phase')
   frozen.append({'source_time_s':t,'species':'graupel' if species==1 else 'hail','path_kg_m2':f[0]/A,'positive_layers':int(f[1]),'lambda_min_max':f[2:4] if f[1] else None,'temperature_min_max':f[4:6] if f[1] else None,'outside_table_path_kg_m2':f[6]/A,'lambda_20000_endpoint_path_kg_m2':f[8]/A,'above_273_15K_path_kg_m2':f[9]/A})
 hours=[]
 for hour in sorted({int(w['source_time_s']//3600) for w in water}):
  a=[w for w in water if int(w['source_time_s']//3600)==hour]
  sums={k:math.fsum(x[k] for x in a) for k in a[0] if k not in ['source_time_s','end_time_s','W_start_kg_m2','W_end_kg_m2']}
  hours.append({'hour':hour,'completed_steps':len(a),'start_s':a[0]['source_time_s'],'end_s':a[-1]['end_time_s'],'W_start_kg_m2':a[0]['W_start_kg_m2'],'W_end_kg_m2':a[-1]['W_end_kg_m2'],**sums})
 achieved=receipt['status']=='SUCCESS' and times==list(range(0,86400,60))
 return {'status':'FIXED_REAL_24H_EVALUATED' if achieved else 'FIXED_REAL_EVALUATION_STOPPED','planned_seconds':86400,'completed_steps':len(times),'completed_end_s':times[-1]+60,'partial_step_sources_preserved':[t for t in starts if t not in times],'target_period_completed':achieved,'hourly_water':hours,'water_steps':water,'CU_categories':categories,'expiry_events':expiry,'radiation_steps':radiation,'frozen_calls':frozen,'water_conservation_approved':False,'full_energy_approved':False,'frozen_accuracy_approved':False,'forecast_skill_assessed':False,'new_model_runs_in_saved_replay':0,'units':'water terms kg/m2 per stated interval; flux W/m2, source equivalent J/m2; all means normalized by the whole physical-domain area','missing':['independently reconstructed lateral face flux','isolated radiation-only acoustic state increment','frozen independent optical accuracy','observations and purpose-specific physical tolerances']}
