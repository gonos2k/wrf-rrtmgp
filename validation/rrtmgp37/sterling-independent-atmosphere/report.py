from pathlib import Path
import json,csv
from analyze import evaluate
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent

def main():
 ex=json.loads((B/'udm37-sterling-independent-atmosphere-analysis-v1/enriched.json').read_text());old=json.loads((P.parent/'sterling-cloud-loss-operation/result.json').read_text());r=evaluate(ex,old);(P/'result.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n');rows=[]
 for pair in r['fixed_pressure_profile_comparisons']:
  for x in pair['fixed_pressure_rows']:
   row={'nominal_UTC':pair['nominal_UTC'],'release_UTC':pair['actual_release_UTC'],'observed_level_time_UTC':x['observed_level_time_UTC_from_release_elapsed'],'model_UTC':x['model_time_UTC'],'model_minus_level_time_s':x['model_minus_observed_level_time_s'],'pressure_hPa':x['pressure_Pa']/100}
   for n,label,scale in [('T_K','T_K',1),('qv_kg_kg','qv_g_kg',1000),('RH_water_ratio','RH_water_percent',100),('wind_u_east_m_s','wind_u_east_m_s',1),('wind_v_north_m_s','wind_v_north_m_s',1)]:
    f=x['fields'][n]
    for arm in ['observation','model']:row[label+'_'+arm]=f[arm]['value']*scale if f[arm] else None
    row[label+'_model_minus_observation']=None if f['model_minus_observation'] is None else f['model_minus_observation']*scale
   rows.append(row)
 with (P/'pressure-comparison.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(r['status'],len(rows))
if __name__=='__main__':main()
