"""Classify existing residual support without deleting terms or claiming closure."""
from decimal import Decimal
import json,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent

def assess(raw):
 r=json.loads(raw,parse_float=Decimal);w=r['whole_period_water_terms_kg_m2']
 residual=w['stock_surface_boundary_residual'];outer=w['RAINC_outer_kept']
 convert=lambda x:float(x) if isinstance(x,Decimal) else x
 return {'source_sha256':hashlib.sha256(raw).hexdigest(),'units':'kg/m2 over the original corrected 24-hour interval, whole physical-area normalization',
 'support_split':{'reported_comparison_residual':convert(residual),'reported_outer_RAINC_kept':convert(outer),'comparison_remainder_after_separating_outer_RAINC':convert(residual-outer),'is_recomputed_interior_domain_water_budget':False,'outer_precipitation_deleted':False},
 'process_terms':{n:convert(w[n]) for n in ['PBL_minus_E','CU_active_paired_residual','CU_tendency_without_positive_rain','microphysics_plus_its_RAINNC','CU_inactive_positive_rain']},
 'active_CU_plus_PBL_signed_sum':convert(w['CU_active_paired_residual']+w['PBL_minus_E']),
 'decisions':[
 {'scope':'prescribed outer precipitation','decision':'preserve as a distinct support term; do not remove from full-domain precipitation','production_correction_justified':False},
 {'scope':'remaining CU/PBL and microphysics paired terms','decision':'retain separate signed process diagnostics; cancellation does not establish individual physical conservation','production_correction_justified':False},
 {'scope':'operator reconstruction','decision':'complete for declared applied-operator accounting; not an independent lateral face-flux conservation test','independent_conservation_approved':False},
 {'scope':'serial research baseline','decision':'retain the corrected fixed configuration for component evaluation; do not add an empirical residual correction'}],
 'water_conservation_approved':False,'new_model_runs':0}

def frozen_targets(text,area):
 """Select actual important calls; independent optical adequacy remains unassessed."""
 import math
 samples={1:[],2:[]}
 for row in text.splitlines():
  x=row.split()
  if len(x)<4 or x[1]!='frozen_consumption':continue
  t=float(x[0]);species=int(x[2]);v=list(map(float,x[3:]));assert len(v)==10 and v[7]==t
  samples[species].append({'source_time_s':t,'path_kg_m2':v[0]/area,'above_273_15K_ambient_path_kg_m2':v[9]/area,'lambda_20000_endpoint_path_kg_m2':v[8]/area,'positive_layer_samples':int(v[1]),'supplied_lambda_min_max_m_1':v[2:4] if v[1] else None,'ambient_temperature_min_max_K':v[4:6] if v[1] else None,'outside_supplied_table_path_kg_m2':v[6]/area})
 out=[]
 for i,name in [(1,'graupel'),(2,'hail')]:
  rows=samples[i];assert [r['source_time_s'] for r in rows]==list(range(0,86400,600))
  selected=[]
  for key in ['path_kg_m2','above_273_15K_ambient_path_kg_m2','lambda_20000_endpoint_path_kg_m2']:
   target=max(rows,key=lambda x:x[key]);selected.append({'selection':key,**target})
  exposure=math.fsum(r['path_kg_m2']*600 for r in rows)
  out.append({'species':name,'selected_actual_calls':selected,'warm_ambient_path_exposure_fraction':math.fsum(r['above_273_15K_ambient_path_kg_m2']*600 for r in rows)/exposure,'decision':'retain only as an explicit experimental component of this fixed serial research baseline; real melting-particle optical accuracy is not approved','independent_optical_comparison_performed':False,'ranges_are_colocated_particle_state':False,'limits':['ambient temperature is not particle liquid fraction or melting rate','call-wide extrema are not a colocated size-temperature sample','supplied lambda is not the pre-limit PSD','component optical contribution and independent reference uncertainty still required']})
 return out
