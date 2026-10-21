"""Stdlib replay of actual independent reductions; no fitted closing source."""
import math
FIELDS=['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL']
def require(x,m):
 if not x:raise ValueError(m)
def analyze(text,surface_rows):
 rows=[];d={}
 for line in text.splitlines():
  a=line.split();t=int(float(a[0]));kind=a[1];idx=int(a[2]);v=list(map(float,a[3:]));require(all(math.isfinite(x) for x in v),'nonfinite reduction')
  key=(t,kind,idx);require(key not in d,'duplicate source reduction');d[key]=v;rows.append(key)
 times=sorted({k[0] for k in rows});require(times==[21540,21600,21660],'original source times')
 area=d[(21540,'geometry',0)][0];get=lambda t,k,i=0:d[(t,k,i)]
 total=lambda t,k:math.fsum(get(t,k,i)[0] for i in range(1,8))
 native=lambda t,k:math.fsum(get(t,k,i)[0] for i in range(2,9))
 water=[];radiation=[];frozen=[]
 for t in times:
  dt=get(t,'pd_tendency',2)[1];require(dt==60,'final PD dt')
  rate=lambda kind:native(t,kind)*dt
  start=total(t,'start');end=total(t,'end');dw=end-start
  surface=next(x for x in surface_rows if x['source_time_s']==t)
  sf0=get(t,'surface_start');sf1=get(t,'surface_end');p=sf1[0]-sf0[0];e=sf1[1]-sf0[1];eqfx=get(t,'surface_physics')[2]*dt
  require(math.isclose(surface['QFX_full_kg_s'],get(t,'surface_physics')[2],rel_tol=64*44*2.220446049250313e-16),'history QFX is not actual call-time QFX')
  ei=surface['QFX_interior_kg_s']*dt
  pbl=(total(t,'pbl_after')-total(t,'pbl_before'))*dt;cu=(total(t,'cumulus_after')-total(t,'cumulus_before'))*dt
  pm=get(t,'surface_micro_before')[0]-sf0[0];pmp=sf1[0]-get(t,'surface_micro_before')[0]
  phy=rate('before_relax');relax=rate('after_relax')-phy;spec=rate('after_spec_tend')-rate('after_relax')
  pdformal=rate('pd_tendency');pdactual=native(t,'pd_after')-native(t,'pd_before');pdround=pdactual-pdformal
  require(abs(pdformal-rate('after_spec_tend'))<1e-3,'tendency changed between boundary assembly and final PD')
  adv=rate('advection_rate');other=rate('rk_other_tendency');require(other==0,'unhandled final RK source')
  rkactual=native(t,'rk_after')-native(t,'rk_base');rkround=rkactual-adv
  mp=total(t,'micro_after')-total(t,'micro_before')
  fm=total(t,'final_mu_after')-total(t,'final_mu_before')
  fq=native(t,'final_q_after')-native(t,'final_q_before')
  bridges={
   'start_to_PD_base':native(t,'pd_before')-start,
   'PD_to_RK_base':native(t,'rk_base')-native(t,'pd_after'),
   'RK_species_to_all':total(t,'after_rk')-native(t,'rk_after'),
   'RK_to_microphysics':total(t,'micro_before')-total(t,'after_rk'),
   'microphysics_to_final_MU':total(t,'final_mu_before')-total(t,'micro_after'),
   'final_MU_to_moisture':native(t,'final_q_before')-total(t,'final_mu_after'),
   'final_moisture_to_end':end-native(t,'final_q_after')}
  # These are independently observed operator/evaluation transitions, never fitted from the final residual.
  applied=math.fsum([pdactual,rkactual,mp,fm,fq,*bridges.values()]);arithmetic_closure=dw-applied
  sources=math.fsum([phy,relax,spec,adv,mp,fm,fq,pdround,rkround,*bridges.values()])
  physical=dw-ei+p-adv-relax-spec-fm-fq
  explanation=math.fsum([phy-ei,mp+p,pdround,rkround,*bridges.values()])
  reduction_check=64*math.ulp(max(abs(start),abs(end)))
  require(abs(arithmetic_closure)<=reduction_check,'operator ledger does not telescope at domain kg resolution')
  require(abs(physical-explanation)<=reduction_check,'source attribution identity')
  water.append({'source_time_s':t,'end_time_s':t+60,'dt_s':dt,'all_units':'domain-mean kg/m2 except source_time, dt and raw_kg; primary E is actual QFX*dt on native PBL interior support, ACLHF/2501000 kept only as historical proxy',
   **{k:v/area for k,v in {'dW':dw,'P':p,'E_ACLHF_proxy_2501000':e,'E_ACLHF_native_2500000':e*2501000/2500000,'E_QFX_full_dt':eqfx,'E_QFX_native_PBL_support_dt':ei,'QFX_excluded_outer_strip_dt':eqfx-ei,'nonboundary_physics_and_mixing':phy,'PBL_applied_tendency_integral':pbl,'cumulus_applied_tendency_integral':cu,'other_physics_mixing':phy-pbl-cu,'P_before_microphysics':pm,'P_during_microphysics':pmp,'PBL_minus_QFX_interior_dt':pbl-ei,'PBL_minus_QFX_full_dt':pbl-eqfx,'cumulus_plus_its_P':cu+pm,'microphysics_plus_its_P':mp+pmp,'boundary_relaxation':relax,'boundary_specified_tendency':spec,'advection_actual_tendency_integral':adv,'microphysics_state_increment':mp,'final_MU_mass_increment':fm,'final_moisture_overwrite':fq,'PD_arithmetic_difference':pdround,'RK_arithmetic_difference':rkround,'physical_residual_before_host_source_attribution':physical,'nonboundary_physics_minus_QFX_interior_dt':phy-ei,'residual_if_QFX_full_domain_is_used':physical-(eqfx-ei),'microphysics_plus_P':mp+p,'operator_closure_residual':arithmetic_closure,'attributed_source_closure_residual':dw-sources}.items()},
   'bridges':{k:v/area for k,v in bridges.items()},'raw_kg':{'dW':dw,'predicted_from_independent_source_terms':sources},
   'advection_note':'integral of actual final-RK applied advection tendency on its native interior update region; not an independently reconstructed velocity-times-water face flux',
   'water_conservation_approved':False})
  raw=get(t,'rad_raw');coupled=get(t,'rad_coupled');added=get(t,'radiation_actual_add')[0]
  require(abs(added-coupled[1])/max(abs(coupled[1]),1)<2e-7,'actual radiation add does not match coupled interior source')
  native_flux=[]
  for kind,label in enumerate(['LW','SW']):
   call=raw[3+kind];f=[raw[5+2*j+kind]/area for j in range(6)]
   native_flux.append({'component':label,'last_observed_call_time_s':call if call>=0 else None,'available':call>=0,'surface_net_W_m2':f[0] if call>=0 else None,'native_top_net_W_m2':f[1] if call>=0 else None,'extended_TOA_net_W_m2':f[2] if call>=0 else None,'native_column_convergence_W_m2':f[1]-f[0] if call>=0 else None,'pressure_mass_heating_W_m2':f[3] if call>=0 else None,'max_column_flux_heating_residual_W_m2':raw[17+kind] if call>=0 else None,'native_dry_mass_heating_W_m2':f[4] if call>=0 else None,'native_interior_convergence_W_m2':f[5] if call>=0 else None,'column_count':int(raw[19+kind])})
  for f in native_flux:
   if not f['available']:continue
   require(f['last_observed_call_time_s']==21600 and f['column_count']==8910,'fresh/held radiation phase or column count')
   mean_res=abs(f['native_column_convergence_W_m2']-f['pressure_mass_heating_W_m2'])
   require(mean_res<=f['max_column_flux_heating_residual_W_m2']+1e-10,'native top substituted or flux/heating mismatch')
  rhs=[get(t,'actual_thermal_rhs',rk) for rk in [1,2,3]]
  require(all(math.isclose(r[1],added,rel_tol=64*44*2.220446049250313e-16) and r[2]==60 for r in rhs),'held radiation component changed across RK RHS consumption')
  radiation.append({'source_time_s':t,'end_time_s':t+60,'dry_mass_raw_full_W_m2':raw[0]/area,'dry_mass_raw_interior_W_m2':raw[1]/area,'coupled_interior_W_m2':coupled[1]/area,'actual_phy_ra_add_W_m2':added/area,'actual_rhs_total_W_m2_each_RK':[r[0]/area for r in rhs],'inferred_linear_radiation_component_W_m2_each_RK':[r[1]/area for r in rhs],'radiation_RHS_equivalent_60s_J_m2':added*dt/area,'native_flux':native_flux,'source_contract':'dry-theta equivalent at the actual physics Exner state; native radiation addition measured from actual RHS arrays; total actual RK RHS addition measured; isolated radiation component inferred through declared linear theta_m/map-factor conversion; final RK time extent once, predictors not summed','acoustic_radiation_only_state_increment_measured':False,'full_energy_approved':False})
  for species in [1,2]:
   if (t,'frozen_consumption',species) not in d:continue
   v=get(t,'frozen_consumption',species);require(v[7]==t,'stale frozen call')
   frozen.append({'source_time_s':t,'species':'graupel' if species==1 else 'hail','actual_LW_native_path_domain_mean_kg_m2':v[0]/area,'positive_layers':int(v[1]),'lambda_min_max_m_inv':v[2:4] if v[1] else None,'temperature_min_max_K':v[4:6] if v[1] else None,'outside_table_domain_mean_path_kg_m2':v[6]/area,'physical_accuracy_approved':False})
 return {'status':'BOUNDED_REAL_CASE_BUDGET_EVALUATED','area_m2':area,'water_steps':water,'radiation_steps':radiation,'frozen_actual_consumption':frozen,'water_conservation_approved':False,'full_energy_budget_approved':False,'production_accepted':False,'missing':['six-hour independently separated boundary source history','initial held native-top flux for 05:59 step','isolated radiation-only acoustic prognostic state increment','frozen optical accuracy and component-removal transport contribution'],'record_count':len(rows)}
if __name__=='__main__':
 from pathlib import Path
 import json
 p=Path(__file__).resolve();b=p.parents[4];o=b/'udm37-real-budget-analysis-v1';o.mkdir(exist_ok=True)
 r=analyze((b/'udm37-real-budget-host-v2/host/real-budget.txt').read_text(),json.loads((o/'surface_domains.json').read_text()));(o/'analysis.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
