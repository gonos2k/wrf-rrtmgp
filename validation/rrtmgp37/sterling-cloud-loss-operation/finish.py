"""Wait for the one authorized bounded run, then extract and replay it; no rerun."""
from pathlib import Path
import json,subprocess,sys,time,importlib.util
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent

def main():
 while True:
  r=json.loads((B/'udm37-sterling-cloud-loss-run-v1/receipt.json').read_text())
  if r['status']!='STARTING':break
  time.sleep(5)
 if r['status']!='SUCCESS':raise RuntimeError(r)
 subprocess.run([sys.executable,P/'extract.py'],cwd=R,check=True)
 import analyze as A
 raw=(B/'udm37-sterling-cloud-loss-run-v1/host/cloud_operations.txt').read_text();a=A.analyze(raw)
 out=B/'udm37-sterling-cloud-loss-analysis-v1';(out/'analysis.json').write_text(json.dumps(a,indent=2,allow_nan=False)+'\n')
 print(json.dumps({k:a[k] for k in ['status','replay_counts','primary_hour_processes_kg_m2','first_complete_loss_step','largest_cloud_loss_step']},indent=2),flush=True)
 import thermodynamics as T
 T.evaluate(raw,B/'udm37-sterling-cloud-loss-thermo-v1')
 print('ACTUAL_OPERATORS_AND_NATIVE_SATURATION_COMPLETE',flush=True)
if __name__=='__main__':main()
