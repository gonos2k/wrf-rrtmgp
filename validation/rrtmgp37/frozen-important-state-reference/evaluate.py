"""Recompute the declared conditional result; preserve physical nonapproval."""
from pathlib import Path
import importlib.util,json,math
P=Path(__file__).resolve().parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('frozen_effect_analysis',P/'analyze.py');F=load('frozen_packets',P/'packets.py');require=A.require

def reference_check(ref,target):
 require(ref['completed'] and ref['all_numerical_axes_qualified'] and not ref['remaining_unqualified_bands'],'incomplete or unqualified reference')
 require(ref['miepython_version']=='3.0.2' and ref['state']==target,'reference definition/state differs')
 require(ref['physical_tolerance'] is None and not ref['physical_accuracy_approved'],'physical scope promotion')
 require([x['band'] for x in ref['records']]==list(range(1,17)),'wrong band roster')
 replay_max=0
 for row in ref['records']:
  level=row['levels'][-1];fine=level['fine'];rh=level['radius_half'];vh=level['spectral_half']
  require(fine['radius_nodes']==2*rh['radius_nodes'] and fine['spectral_degree']==rh['spectral_degree'],'radius-only refinement changed spectrum')
  require(fine['radius_nodes']==vh['radius_nodes'] and fine['spectral_degree']==2*vh['spectral_degree'],'spectral-only refinement changed radius')
  for grid in row['levels']:
   for key in ['fine','radius_half','spectral_half']:
    q=grid[key];nu=q['nu_cm_1'];w=q['spectral_weights_cm_1'];b=q['planck_shape'];mono=q['monochromatic_kappa_m2_kg'];n=len(nu)
    require(n==len(w)==len(b)==len(mono)==q['spectral_nodes'],'spectral record shape')
    require(q['lambda_m_1']==target['lambda_m_1'] and q['temperature_K']==target['temperature_K'],'reference query shifted')
    require(all(math.isfinite(z) and z>0 for a in [nu,w,b] for z in a),'invalid quadrature/source')
    require(all(nu[i]<nu[i+1] for i in range(n-1)),'spectral order')
    c2=6.62607015e-34*299792458/1.380649e-23*100
    for v,source in zip(nu,b):require(math.isclose(source,v**3/math.expm1(c2*v/target['temperature_K']),rel_tol=5e-12,abs_tol=1e-24),'Planck source mismatch')
    norm=math.fsum(a*z for a,z in zip(w,b))
    for j,name in enumerate(['ext','sca','abs','sca_g']):
     value=math.fsum(m[j]*a*z for m,a,z in zip(mono,w,b))/norm;reported=q['moments_m2_kg'][name]
     require(math.isclose(value,reported,rel_tol=5e-12,abs_tol=1e-24),'moment replay mismatch')
     replay_max=max(replay_max,abs(value-reported))
    for m in mono:
     require(len(m)==4 and all(math.isfinite(z) for z in m) and m[0]>0 and m[1]>=0 and m[2]>=0 and abs(m[3])<=m[1]+1e-14,'invalid raw moments')
     require(math.isclose(m[0]-m[1],m[2],rel_tol=5e-12,abs_tol=1e-24),'absorption/extinction/scattering closure')
   a=grid['fine']['moments_m2_kg']['abs'];dr=abs(a-grid['radius_half']['moments_m2_kg']['abs'])/a;dv=abs(a-grid['spectral_half']['moments_m2_kg']['abs'])/a
   require(dr==grid['absorption_radius_relative_change'] and dv==grid['absorption_spectral_relative_change'],'axis summary mismatch')
   require(grid['qualified_numerical_axes']==(dr<=.01 and dv<=.01),'unqualified absorption promoted')
  require(level['qualified_numerical_axes'],'last independent level not qualified')
 require(len(ref['actual_state_JIT_nonJIT_parity'])==9,'actual-state kernel parity roster')
 for row in ref['actual_state_JIT_nonJIT_parity']:
  for a,b in zip(row['JIT'],row['non_JIT']):require(abs(a-b)<=2e-9+2e-9*abs(b),'actual-state JIT parity')
 return replay_max

def evaluate(d):
 j=lambda n:json.loads(d[n]);target=j('selection/target.json');reference=j('reference/result.json');original=j('original/result.json')
 head,inp=F.read(d['capture/host/capture/lw.input'],'input');rawhead,raw=F.read(d['capture/host/capture/lw.raw'],'raw');_,actual=F.read(d['capture/host/capture/lw.result'],'result')
 require(rawhead==['LW',target['i'],target['j'],44],'wrong actual column/native levels')
 require(raw['SOURCE_TIME_SECONDS']['values']==[3000.] and raw['RADIATION_STEP']['values']==[51.],'wrong actual source')
 require(head==['LW',1,57,2,57023497,4],'wrong consumed dimensions/seed/overlap')
 require(inp['FROZEN_MODE']['values']==[1.] and inp['FROZEN_OCCURRENCE']['values']==[1.],'frozen contract changed')
 require(inp['CU_POPULATION_POLICY']['values']==[1.] and 'NATIVE_CAPACITY_J_M2_K' not in actual,'actual CU/capacity contract changed')
 k=target['native_layer']-1;nl=head[2];native=44
 for name,key in [('TLAY','temperature_K'),('LAMBDA_H','lambda_m_1'),('HWP','layer_hail_path_g_m2')]:require(inp[name]['values'][k]==target[key],'selected actual layer shifted')
 replay=reference_check(reference,target)
 results={};receipt=j('rte/receipt.json')
 require(len(receipt['runs'])==6,'RTE process roster')
 for mode in ['public_A','diagnostic_A','original_direct','fine','radius_half','spectral_half']:
  hh,xx=F.read(d['rte/'+mode+'/capture/lw.input'],'input');_,got=F.read(d['rte/'+mode+'/capture/lw.result'],'result');require(hh==head and xx==inp,'caller consumed different inputs')
  if mode in ['public_A','diagnostic_A']:
   for name,v in actual.items():
    if not name.startswith('WRF_'):require(got[name]==v,'caller does not reproduce actual WRF '+name)
  for name in ['GAS_COL_DRY','VMR_N2','GAS_TAU','NATIVE_CLOUD_TAU','CU_CLOUD_TAU','PRECIP_TAU','CLOUD_TAU','PREPARED_TAU','RL_USED','DI_USED','DS_USED','MASK','GRAUPEL_TAU_ABS','UPC','DNC','HRC']:
   require(got[name]==actual[name],'nonselected component changed '+name)
  for b in range(16):
   for layer in range(nl):
    if layer!=k:require(got['HAIL_TAU_ABS']['values'][layer+nl*b]==actual['HAIL_TAU_ABS']['values'][layer+nl*b],'nonselected hail layer changed')
  if mode not in ['public_A','diagnostic_A']:
   words=d['rte/'+mode+'/coefficients.dat'].decode().split();require(list(map(float,words[:4]))==[target[n] for n in ['native_layer','temperature_K','lambda_m_1','layer_hail_path_g_m2']],'coefficient state header mismatch')
   expected=[original['bands'][b]['moments'][3][0]/912. for b in range(16)] if mode=='original_direct' else [reference['records'][b]['levels'][-1][mode]['moments_m2_kg']['abs'] for b in range(16)]
   require(list(map(float,words[4:]))==expected,'coefficient file not the qualified reference')
   require(got['REFERENCE_HAIL_BEFORE']==actual['HAIL_TAU_ABS'] and got['REFERENCE_HAIL_AFTER']==got['HAIL_TAU_ABS'],'wrong replacement boundary')
   for b,value in enumerate(expected):require(got['HAIL_TAU_ABS']['values'][k+nl*b]==target['layer_hail_path_g_m2']*.001*value,'path/density units mismatch')
  results[mode]=got
 table_tau=[actual['HAIL_TAU_ABS']['values'][k+nl*b] for b in range(16)];coeff=A.coefficient_record(table_tau,target['layer_hail_path_g_m2'],original,reference);tr=A.transport(results,native)
 decisions=[{'scope':'same fixed ice-Ih sphere/exponential-PSD mathematical problem at the selected actual lambda/T','decision':'conditional independent numerical reference qualified in all16LW bands; calculation and propagation complete','physical_representativeness_approved':False},{'scope':'existing frozen1 production coefficients','decision':'retain unchanged for the fixed experimental serial research baseline; no demonstrated port/input defect or justified production replacement','table_scientific_accuracy_approved':False},{'scope':'real melting/wet hail and general forecasts','decision':'application restricted; require qualified phase/liquid-fraction or particle-property evidence and independent optical accuracy before broadening','ambient_temperature_is_liquid_fraction':False,'new_temperature_guard':False}]
 return {'status':'ACTUAL_FROZEN_STATE_CONDITIONAL_REFERENCE_AND_PROPAGATION_COMPLETE','actual_state':target,'native_layers':native,'reference_LW_bands':16,'independent_axis_evaluations':sum(3*len(r['levels']) for r in reference['records']),'original_direct_evaluations':16,'actual_state_JIT_nonJIT_pairs':9,'maximum_saved_moment_replay_difference_m2_kg':replay,'coefficient_comparisons':coeff,'max_current_reference_relative_absorption_difference':max(abs(c['current_minus_reference_relative']) for c in coeff),'max_reference_radius_axis_relative_change':max(c['radius_axis_relative_change'] for c in coeff),'max_reference_spectral_axis_relative_change':max(c['spectral_axis_relative_change'] for c in coeff),'transport':tr,'WRF_selection_array_pairs_equal':450,'WRF_capture_array_pairs_equal':450,'actual_WRF_processes':2,'actual_column_processes':6,'independent_meteorological_cases':1,'decisions':decisions,'only_selected_hail_absorption_changed':True,'production_changes':False,'physical_tolerance':None,'reference_representativeness_uncertainty':None,'frozen_real_particle_accuracy_approved':False,'whole_water_energy_approved':False,'forecast_skill_approved':False,'original_seven_conditions_changed':False,'new_model_runs_in_saved_replay':0}
