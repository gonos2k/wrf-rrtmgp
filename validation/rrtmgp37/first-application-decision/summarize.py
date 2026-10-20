#!/usr/bin/env python3
"""Extract intended observables and refinement indicators; never infer accuracy."""
from pathlib import Path
import argparse,gzip,hashlib,importlib.util,json,math
P=Path(__file__).resolve().parent;R=P.parents[2]
s=importlib.util.spec_from_file_location('first_application_trace',R/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py');trace=importlib.util.module_from_spec(s);s.loader.exec_module(trace)

def read_ref(refs,name):
 row=refs[name];p=(R/row['path']).resolve()
 if not p.is_relative_to(R) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('prior evidence differs '+name)
 return gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()

def result():
 refs=json.loads((P/'evidence.json').read_text());decision=json.loads((P/'decision.json').read_text())
 for n in refs:read_ref(refs,n)
 targets={};boundary_rows=[]
 for case in decision['state_scope']['source_cases']:
  target,ph=case.rsplit('_',1);data={}
  for mode in ['A','B','B_coarse','C','C_coarse']:
   data[mode]=trace.trace(read_ref(refs,f'liquid-endpoint-optics/saved/{case}_{mode}/{ph}.result.gz'),'result')[1]
  raw=trace.trace(read_ref(refs,f'lut-exposure-assessment/saved/capture/{target}/{ph}.raw.gz'),'raw')[1]
  inp=trace.trace(read_ref(refs,f'lut-exposure-assessment/saved/capture/{target}/{ph}.input.gz'),'input')[1]
  if len(data['A']['NATIVE_CAPACITY_J_M2_K']['values'])!=59:raise ValueError('native extent')
  def values(mode,quantity):
   if quantity=='heating':return [x*86400 for x in data[mode]['HEAT_WP_K_S']['values'][:59]]
   up=data[mode]['UP_WP']['values'][:60];dn=data[mode]['DN_WP']['values'][:60]
   return up if quantity=='up' else dn if quantity=='down' else [d-u for d,u in zip(dn,up)]
  profiles={}
  for quantity in ['up','down','net_down','heating']:
   arrays={m:values(m,quantity) for m in data};rows=[]
   for k in range(len(arrays['A'])):
    a,b,c=[arrays[m][k] for m in ['A','B','C']];bc=arrays['B_coarse'][k];cc=arrays['C_coarse'][k]
    definition=b-a;radius=c-b;total=c-a
    if abs(definition+radius-total)>1e-10:raise ValueError('signed identity')
    rb=b-bc;rc=c-cc;indicator=abs((c-b)-(cc-bc));between_grid_bound=abs(rb)+abs(rc)
    if indicator>between_grid_bound+1e-10:raise ValueError('paired refinement inequality')
    row={'position_1based':k+1,'unit':'K/day' if quantity=='heating' else 'W/m2','A':a,'B':b,'C':c,'definition_B_minus_A':definition,'radius_C_minus_B':radius,'total_C_minus_A':total,'last_two_grid_radius_change':indicator,'last_two_grid_triangle_bound':between_grid_bound}
    rows.append(row)
   if quantity=='heating':
    for k,row in enumerate(rows):row.update(temperature_K=raw['SOURCE_T']['values'][k],pressure_Pa=raw['SOURCE_P_PA']['values'][k])
   profiles[quantity]=rows
   if quantity!='heating':
    for boundary,index in decision['target_contract']['boundaries'].items():boundary_rows.append({'case':case,'boundary':boundary,'quantity':quantity,**rows[index]})
  selected=[k for k,r in enumerate(inp['REL']['values'][:59]) if r>21.5 and inp['LWP']['values'][k]>0]
  supported={'source_seconds':raw['SOURCE_TIME_SECONDS']['values'][0],'selected_layers':[k+1 for k in selected],'discrete_actual_radius_um':[inp['REL']['values'][k] for k in selected],'selected_cloud_path_g_m2':[inp['LWP']['values'][k] for k in selected],'selected_CF':[inp['CF']['values'][k] for k in selected],'selected_host_temperature_K':[raw['SOURCE_T']['values'][k] for k in selected],'selected_host_qc_kg_kg_dry':[raw['SOURCE_QC']['values'][k] for k in selected],'selected_host_eta_number_kg_dry':[raw['SOURCE_QNC']['values'][k] for k in selected],'selected_host_dry_rho_kg_m3':[raw['SOURCE_DRY_RHO']['values'][k] for k in selected]}
  targets[case]={'evaluated_state':supported,'native_heating_profile':profiles['heating']}
 return {'status':'FIRST_CANDIDATE_LIQUID_OPTICS_APPLICATION_WITHHELD','purpose':decision['purpose'],'boundary_observables':boundary_rows,'native_profiles':targets,'uncertainty_budget':decision['error_budget'],'acceptance':decision['acceptance'],'two_coefficients_action':decision['two_unconverged_absorption_coefficients'],'new_WRF_UDM_RTE_Mie_LBLRTM_runs':0,'new_acceptance_gate_or_test_count':0,'production_accepted':False}

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();x=result();out=P/'observables.json'
 if args.check:
  if x!=json.loads(out.read_text()):raise SystemExit('stored observable/decision differs')
  print(json.dumps({'status':x['status'],'new_model_runs':0,'boundary_metrics':len(x['boundary_observables']),'native_heating_profiles':len(x['native_profiles']),'epsilon_authority':x['uncertainty_budget']['epsilon_authority'],'production_accepted':False},indent=2))
 else:out.write_text(json.dumps(x,indent=2)+'\n')
