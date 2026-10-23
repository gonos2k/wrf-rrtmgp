"""Replay only observed phase/step reductions; never infer a missing night value."""
import math

def require(ok,msg):
 if not ok:raise ValueError(msg)

def analyze(text,seconds=86400):
 rows={};geometry=None
 for line in text.splitlines():
  x=line.split();require(len(x)>=3,'malformed observation');t=float(x[0]);tag=x[1];v=list(map(float,x[2:]));require(all(math.isfinite(z) for z in [t,*v]),'nonfinite observation')
  if tag=='geometry':require(geometry is None and t==0 and len(v)==6,'geometry');geometry=v;continue
  require(tag in ['call_begin','coverage','phase_flux','held'],'unknown observation')
  key=(t,tag,int(v[0]) if tag=='phase_flux' else 0);require(key not in rows,'duplicate observation');rows[key]=v
 require(geometry is not None,'missing geometry');A,nx,ny,nz,g,cp=geometry;cols=int(nx*ny);inner=int((nx-2)*(ny-2))
 require((nx,ny,nz)==(90,99,44),'wrong native physical domain')
 phases=[];steps=[];latest=None;count=0
 for t in range(0,seconds,60):
  held=rows.get((t,'held',0));require(held is not None and len(held)==14,'missing held-source step')
  called=(t,'call_begin',0) in rows
  if called:
   begin=rows[(t,'call_begin',0)];require(len(begin)==3 and begin[0]==t and begin[1]==t//60+1 and begin[2]==count+1,'call phase/count')
   cov=rows.get((t,'coverage',0));require(cov is not None and len(cov)==13,'missing returned coverage')
   require(cov[:2]==begin[:2] and cov[2]+cov[3]==cols and cov[4]==cols,'missing or wrong returned column support')
   require(cov[5]+cov[6]==inner and 0<=cov[5]<=cov[2] and 0<=cov[6]<=cov[3],'interior support mismatch')
   require(cov[7]==0,'nonzero actual night return');require(cov[9]==0,'solver/native return assignment mismatch')
   require(cov[11]<=cov[12],'solar range')
   if cov[2]==0:require(cov[12]<=0,'night-only branch range')
   if cov[3]==0:require(cov[11]>0,'day-only branch range')
   fs=[]
   for zone in [1,2]:
    v=rows.get((t,'phase_flux',zone));require(v is not None and len(v)==13 and v[0]==zone,'missing phase flux zone')
    a=v[1:];require(math.isclose(a[10],a[3]-a[2]-a[1]+a[0],rel_tol=0,abs_tol=64*math.ulp(max(1,*map(abs,a)))),'native signed boundary sum')
    if cov[2]==0:require(all(z==0 for z in a),'night phase filled with nonzero flux/source')
    fs.append(dict(zip(['surface_up','surface_down','native_top_up','native_top_down','extended_TOA_up','extended_TOA_down','pressure_mass_heating','dry_mass_solver_heating','native_assignment_convergence','dry_mass_returned_heating','native_convergence','raw_solver_flux_minus_pressure_heating'],a)))
   classification='all_night_actual_zero' if cov[2]==0 else 'all_day_computed' if cov[3]==0 else 'mixed_day_night_complete'
   latest={'source_time_s':t,'audit_step':int(begin[1]),'classification':classification,'day_columns':int(cov[2]),'night_columns':int(cov[3]),'returned_columns':int(cov[4]),'interior_day_columns':int(cov[5]),'interior_night_columns':int(cov[6]),'actual_night_max_abs':cov[7],'max_native_flux_pressure_heating_difference_W_m2':cov[8],'max_return_replay_difference':cov[9],'max_boundary_and_GSW_double_reconstruction_difference_W_m2':cov[10],'consumed_mu0_min_max':cov[11:13],'zones':fs}
   phases.append(latest);count+=1
  require(latest is not None,'unobserved initial held phase')
  require(held[:4]==[latest['source_time_s'],float(count),60.,float(called)],'call/no-call or held source phase mismatch')
  for zone in [0,1]:
   expected=latest['zones'][zone]
   require(held[8+zone]==expected['native_convergence'] and held[10+zone]==expected['pressure_mass_heating'] and held[12+zone]==expected['dry_mass_returned_heating'],'stale or replaced held flux')
  steps.append({'source_time_s':t,'end_time_s':t+60,'new_SW_call':called,'held_phase_source_s':held[0],'phase_classification':latest['classification'],'raw_SW_dry_source_W_m2':held[4:6],'native_coupled_SW_linear_component_W_m2':held[6:8],'native_flux_convergence_W_m2':held[8:10],'pressure_mass_heating_W_m2':held[10:12],'call_returned_dry_heating_W_m2':held[12:14]})
 expected_keys={(float(t),'held',0) for t in range(0,seconds,60)}
 for p in phases:
  t=float(p['source_time_s']);expected_keys.update([(t,'call_begin',0),(t,'coverage',0),(t,'phase_flux',1),(t,'phase_flux',2)])
 require(set(rows)==expected_keys,'unexpected or unconsumed trace row')
 require([p['source_time_s'] for p in phases]==list(range(0,seconds,600)),'missing/extra scheduled actual phase')
 hours=[]
 for start in range(0,seconds,3600):
  xs=[s for s in steps if start<=s['source_time_s']<start+3600];integ={}
  for name in ['native_flux_convergence_W_m2','pressure_mass_heating_W_m2','call_returned_dry_heating_W_m2','raw_SW_dry_source_W_m2','native_coupled_SW_linear_component_W_m2']:
   integ[name.replace('_W_m2','_J_m2')]=[math.fsum(z[name][i]*60 for z in xs) for i in [0,1]]
  hours.append({'start_s':start,'end_s':xs[-1]['end_time_s'],'steps':len(xs),**integ})
 totals={n:[math.fsum(h[n][i] for h in hours) for i in [0,1]] for n in hours[0] if n.endswith('_J_m2')}
 boundary_keys=['surface_up','surface_down','native_top_up','native_top_down','extended_TOA_up','extended_TOA_down']
 for hour in hours:
  ss=[step for step in steps if hour['start_s']<=step['source_time_s']<hour['end_s']]
  pp={p['source_time_s']:p for p in phases}
  hour['boundary_integrals_J_m2']={key:[math.fsum(pp[step['held_phase_source_s']]['zones'][zone][key]*60 for step in ss) for zone in [0,1]] for key in boundary_keys}
 boundary_totals={key:[math.fsum(hour['boundary_integrals_J_m2'][key][zone] for hour in hours) for zone in [0,1]] for key in boundary_keys}
 for position in ['surface','native_top','extended_TOA']:
  boundary_totals[position+'_net_down']=[boundary_totals[position+'_down'][z]-boundary_totals[position+'_up'][z] for z in [0,1]]

 decomposition=[]
 names=list(totals)
 for zone in [0,1]:
  vals=[totals[n][zone] for n in names]
  parts=[vals[i]-vals[i+1] for i in range(4)]
  require(abs(math.fsum(parts)-(vals[0]-vals[-1]))<=32*math.ulp(max(1,*map(abs,vals))),'signed flux/source decomposition')
  decomposition.append({'native_minus_pressure':parts[0],'pressure_minus_call_dry_return':parts[1],'call_dry_minus_current_held_dry':parts[2],'held_dry_minus_native_coupled_linear':parts[3],'native_minus_coupled_linear':vals[0]-vals[-1]})
 return {'status':'NATIVE_SW_RETURN_AND_HOLD_COVERAGE_COMPLETE','component_scope':'all-sky native SW UP/DN/net and native-layer heating','geometry':{'area_m2':A,'physical_columns':cols,'interior_applied_columns':inner,'native_layers':int(nz)},'completed_steps':len(steps),'actual_SW_calls':len(phases),'no_new_call_steps':len(steps)-len(phases),'fully_night_calls':sum(p['classification']=='all_night_actual_zero' for p in phases),'fully_day_calls':sum(p['classification']=='all_day_computed' for p in phases),'mixed_complete_calls':sum(p['classification']=='mixed_day_night_complete' for p in phases),'missing_phase_seconds':0,'partially_observed_seconds':0,'day_column_returns':sum(p['day_columns'] for p in phases),'night_actual_zero_column_returns':sum(p['night_columns'] for p in phases),'same_area_normalization':'both full and applied interior normalized by the same whole physical-domain area','zone_order':['whole physical domain','applied interior excluding prescribed outer one-row strip'],'hourly':hours,'totals':totals,'boundary_integrals_J_m2':boundary_totals,'boundary_reduction_minus_column_convergence_J_m2':[boundary_totals['native_top_net_down'][z]-boundary_totals['surface_net_down'][z]-totals['native_flux_convergence_J_m2'][z] for z in [0,1]],'signed_decomposition_J_m2':decomposition,'decomposition_scope':'signed accounting identity between the declared quantities, not isolated physical-error attribution; call-versus-held includes weighting and arithmetic differences','phases':phases,'steps':steps,'SW_component_isolation':'native coupled SW is a declared linear component; actual add is observed for combined LW+SW, not an independently measured SW-only acoustic state increment','whole_energy_approved':False,'physical_accuracy_approved':False,'new_model_runs_in_saved_replay':0}

def prior_observer_and_applied_source(text,result):
 """Use actual old-observer and combined-source records on the same trajectory."""
 raw={};added={};coupled={}
 for row in text.splitlines():
  x=row.split()
  if len(x)<4:continue
  t=float(x[0]);tag=x[1]
  target=raw if tag=='rad_raw' else added if tag=='radiation_actual_add' else coupled if tag=='rad_coupled' else None
  if target is not None:
   require(t not in target,'duplicate actual source observation');target[t]=list(map(float,x[3:]))
 require(set(raw)==set(added)==set(coupled)==set(s['source_time_s'] for s in result['steps']),'actual source time support')
 phases={p['source_time_s']:p for p in result['phases']};missing=partial=0;A=result['geometry']['area_m2'];native=result['geometry']['physical_columns']
 for step in result['steps']:
  t=step['source_time_s'];r=raw[t];p=phases[step['held_phase_source_s']]
  valid=r[4]>=0 and r[4]==r[3]
  if not valid:
   missing+=60;require(p['day_columns']==0,'unobserved solver call rather than night-only native branch')
  else:
   require(int(r[20])==p['day_columns'],'day-only old observer does not match actual day branches')
   if int(r[20])!=native:partial+=60
 actual=math.fsum(added[t][0]*60/A for t in sorted(added))
 coupled_eq=math.fsum(coupled[t][1]*60/A for t in sorted(coupled))
 raw_eq=math.fsum(raw[t][1]*60/A for t in sorted(raw))
 return {'prior_missing_phase_seconds':missing,'prior_partial_observation_seconds':partial,'all_prior_missing_phases_are_actual_all_night_returns':True,'all_prior_partial_phases_match_actual_day_subset_of_complete_mixed_returns':True,'actual_combined_LW_SW_add_equivalent_J_m2':actual,'raw_combined_interior_J_m2':raw_eq,'actual_add_minus_raw_combined_J_m2':actual-raw_eq,'raw_coupled_combined_interior_J_m2':coupled_eq,'actual_add_minus_raw_coupled_combined_J_m2':actual-coupled_eq,'SW_component_isolation':'SW-only source is an explicit native linear component; combined add is directly observed; no isolated SW acoustic state increment is claimed'}
