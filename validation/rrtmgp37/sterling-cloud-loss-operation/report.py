from pathlib import Path
import json,csv,importlib.util
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
from surface import evaluate as sf_evaluate
from summarize import summarize

def main():
 O=B/'udm37-sterling-cloud-loss-analysis-v1';a=json.loads((O/'analysis.json').read_text());ex=json.loads((O/'extracted.json').read_text());th=json.loads((B/'udm37-sterling-cloud-loss-thermo-v1/result.json').read_text());old=json.loads((P.parent/'sterling-interior-day-evaluation/result.json').read_text());obs=[(P.parent/f'solrad-boundary-site-48h/raw/ste16{n}.dat').read_bytes() for n in [280,281]]
 surface=sf_evaluate(ex,obs,old);r=summarize(a,surface,th,ex);(P/'result.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
 rows=[]
 for step in a['steps']:
  c=step['species'][1]['layers'][5];v=step['species'][0]['layers'][5]
  rows.append({'source_seconds':step['source_seconds'],'end_seconds':step['end_seconds'],'QCLOUD_start_g_m2':1000*c['start_kg_m2'],'QCLOUD_end_g_m2':1000*c['end_kg_m2'],**{n:1000*c[n] for n in ['delta_kg_m2','PD_source_actual_kg_m2','PBL_formal_kg_m2','horizontal_diffusion_formal_kg_m2','RK_advection_actual_kg_m2','advection_x_kg_m2','advection_y_kg_m2','advection_z_kg_m2','microphysics_actual_kg_m2']},'vapor_delta_g_m2':1000*v['delta_kg_m2'],'vapor_PD_g_m2':1000*v['PD_source_actual_kg_m2'],'vapor_RK_g_m2':1000*v['RK_advection_actual_kg_m2'],'vapor_micro_g_m2':1000*v['microphysics_actual_kg_m2'],'micro_RAINNC_increment_mm':step['micro_layer6']['micro_RAINNC_increment_mm']})
 # The source field names remain the analysis keys; this CSV uses g/m2 as declared here.
 rows=[{k.replace('_kg_m2','_g_m2'):v for k,v in row.items()} for row in rows]
 with (P/'cloud-loss-steps.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(r['status']);print(json.dumps(r['decision'],indent=2))
if __name__=='__main__':main()
