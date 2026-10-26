"""Read actual bounded native output, and compare all overlapping cold arrays first."""
from pathlib import Path
import hashlib,json,importlib.util,subprocess,sys,datetime as dt,os
import numpy as np
from netCDF4 import Dataset,chartostring
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-cloud-loss-analysis-v1';RUN=B/'udm37-sterling-cloud-loss-run-v1';C=B/'udm37-sterling-interior-day-v1'
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return {'path':str(p),'sha256':h.hexdigest(),'bytes':p.stat().st_size}
def times(d):return chartostring(d['Times'][:]).astype(str).tolist()
def main():
 O.mkdir(exist_ok=False);run=json.loads((RUN/'receipt.json').read_text());require=lambda x: x or (_ for _ in ()).throw(ValueError('run/asset mismatch'))
 require(run['status']=='SUCCESS' and not run['error']);c=json.loads((C/'receipt.json').read_text());require(run['initial']['sha256']==c['initial']['sha256'] and run['forcing']['sha256']==c['forcing']['sha256'])
 for n in ['checkpoint','initial','forcing','namelist','executable','iofields','private_readonly_observer_build']:require(pin(Path(run[n]['path']))['sha256']==run[n]['sha256'])
 native=next((C/'host').glob('wrfout*'));observed=next((RUN/'host').glob('wrfout*'))
 subprocess.run([sys.executable,R/'validation/rrtmgp37/vapor-first-operation/compare_history.py',native,observed,O/'history-comparison.json'],cwd=R,check=True)
 eq=json.loads((O/'history-comparison.json').read_text());require(eq['pairs']==1800 and not eq['differences']);require(sorted(eq['inventory'])==[f'2016-10-06_{h:02d}:00:00' for h in range(12,20)])
 file=next((RUN/'host').glob('sterling_surface_*'))
 with Dataset(file) as d:
  d.set_auto_maskandscale(False);surface={'file':pin(file),'times_utc':times(d),'selected_j_i_zero_based':[118,36],'values':{n:np.asarray(d[n][:,118,36],float).tolist() for n in ['SWDNB','SWDNBC','SWDDIR','SWDDIRC','SWDDIF','SWDDNI','COSZEN','ACSWDNB','ACSWDNBC']}}
 require(surface['times_utc']==[(dt.datetime(2016,10,6,17)+dt.timedelta(minutes=m)).strftime('%Y-%m-%d_%H:%M:%S') for m in range(121)])
 cloud=next((RUN/'host').glob('sterling_state_*'))
 with Dataset(cloud) as d:
  d.set_auto_maskandscale(False);states={'file':pin(cloud),'times_utc':times(d),'profiles':[{n:np.asarray(d[n][h,:,118,36],float).tolist() for n in ['CLDFRA','UDM_CLDFRA','QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL','QC_CU','QI_CU']} for h in range(len(d.dimensions['Time']))]}
 require(len(states['times_utc'])==13)
 with Dataset(native) as d:
  d.set_auto_maskandscale(False);original={'history':pin(native),'times_utc':times(d),'ACSWDNB_J_m2':np.asarray(d['ACSWDNB'][:,118,36],float).tolist(),'ACSWDNBC_J_m2':np.asarray(d['ACSWDNBC'][:,118,36],float).tolist(),'hour17_layer6':{n:float(d[n][17,5,118,36]) for n in ['QVAPOR','QCLOUD','QRAIN','T','P','PB']},'hour18_layer6':{n:float(d[n][18,5,118,36]) for n in ['QVAPOR','QCLOUD','QRAIN','T','P','PB']}}
 raw=RUN/'host/cloud_operations.txt';require(raw.exists() and raw.stat().st_size>0)
 ex={'surface':surface,'cloud_snapshots':states,'original':original,'observer':pin(raw),'history_comparison':pin(O/'history-comparison.json'),'native_read':True,'pid':os.getpid(),'new_model_processes':0,'original_24h_scores_changed':False}
 (O/'extracted.json').write_text(json.dumps(ex,indent=2,allow_nan=False)+'\n');print('ACTUAL_BOUNDED_OUTPUT_EXTRACTED',eq['pairs'],raw.stat().st_size)
if __name__=='__main__':main()
