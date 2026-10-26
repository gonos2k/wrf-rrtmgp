"""Qualify the bounded observed run against all cold arrays before attribution."""
from pathlib import Path
import json,hashlib,subprocess,sys,os
from netCDF4 import Dataset,chartostring
import numpy as np
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-thermodynamic-analysis-v1'
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return {'path':str(p),'sha256':h.hexdigest(),'bytes':p.stat().st_size}
def main():
 O.mkdir(exist_ok=False);run=B/'udm37-sterling-thermodynamic-run-v1';receipt=json.loads((run/'receipt.json').read_text());assert receipt['status']=='SUCCESS' and not receipt['error'];cold=B/'udm37-sterling-interior-day-v1';prior=json.loads((cold/'receipt.json').read_text())
 assert receipt['initial']['sha256']==prior['initial']['sha256'] and receipt['forcing']['sha256']==prior['forcing']['sha256']
 for n in ['checkpoint','initial','forcing','namelist','executable','iofields','private_readonly_build']:assert pin(Path(receipt[n]['path']))['sha256']==receipt[n]['sha256']
 native=next((cold/'host').glob('wrfout*'));observed=next((run/'host').glob('wrfout*'));subprocess.run([sys.executable,R/'validation/rrtmgp37/vapor-first-operation/compare_history.py',native,observed,O/'history-comparison.json'],check=True,cwd=R)
 eq=json.loads((O/'history-comparison.json').read_text());assert eq['pairs']==1350 and not eq['differences'];assert sorted(eq['inventory'])==[f'2016-10-06_{h:02d}:00:00' for h in range(12,18)]
 states=[]
 with Dataset(observed) as d:
  d.set_auto_maskandscale(False);times=chartostring(d['Times'][:]).astype(str).tolist()
  for n,t in enumerate(times):
   states.append({'time_UTC':t,'native_layers5_12':{name:np.asarray(d[name][n,4:12,118,36],float).tolist() for name in ['T','THM','QVAPOR','QCLOUD','P','PB'] if name in d.variables},'surface':{name:float(d[name][n,118,36]) for name in ['PBLH','HGT']}})
 raw=run/'host/thermodynamic_operations.txt';assert raw.stat().st_size>0
 ex={'native_read':True,'pid':os.getpid(),'cold_history':pin(native),'observed_history':pin(observed),'observed_operations':pin(raw),'history_comparison':pin(O/'history-comparison.json'),'hourly_states':states,'original_24h_scores_changed':False,'new_model_runs_in_extraction':0}
 (O/'extracted.json').write_text(json.dumps(ex,indent=2)+'\n');print('ACTUAL_OBSERVED_THERMODYNAMIC_OUTPUT_QUALIFIED',eq['pairs'])
if __name__=='__main__':main()
