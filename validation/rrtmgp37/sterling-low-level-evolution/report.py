"""Compute the actual comparison once from retained reads and prior observations."""
from common import *
from analyze import analyze
import json,tarfile,csv
def dependencies():
 prior=P.parent/'sterling-independent-atmosphere'
 with tarfile.open(prior/'saved/evidence.tar.gz','r:gz') as t:obs=json.loads(t.extractfile('derived/enriched.json').read())
 return obs,json.loads((prior/'result.json').read_text())
def tables(result):
 rows=[]
 for r in result['hourly_profiles']:
  for p in r['pressure_rows']:rows.append(dict(hour_UTC=r['hour_UTC'],**p))
 return rows
def main():
 data=json.loads((B/'udm37-sterling-low-level-extract-v2/enriched.json').read_text());obs,old=dependencies();result=analyze(data,obs,old)
 (P/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 rows=tables(result)
 with (P/'hourly-pressure.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 print(result['status'])
 print('hour T925-T950 theta925-theta950 columnQc_g_m2')
 for r in result['fixed_pressure_and_native_inversion_development']:print(r['hour_UTC'],r['T925_minus_T950_K'],r['theta925_minus_theta950_K'],r['column_cloudwater_g_m2'])
 print('900hPa hourly T_C qv_g_kg')
 for r in result['hourly_profiles']:
  if 11<=r['hour_UTC']<=18:
   v=next(x for x in r['pressure_rows'] if x['pressure_Pa']==90000);print(r['hour_UTC'],v['T_K']-273.15,v['qv_kg_kg']*1000)
 print('source and model deviations')
 for r in result['local_met_em_initial_history_chain']:
  if r['pressure_Pa'] in [95000,92500,90000,85000] and r['hour_UTC'] in [0,12,18]:print(r)
if __name__=='__main__':main()
