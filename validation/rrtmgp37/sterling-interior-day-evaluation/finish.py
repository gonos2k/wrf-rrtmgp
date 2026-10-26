"""Complete the actual native extraction and independent scores only after24h success."""
from pathlib import Path
import importlib.util,json,subprocess,sys,time,hashlib
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent

def main():
 receipt=json.loads((B/'udm37-sterling-interior-day-v1/receipt.json').read_text());assert receipt['status']=='SUCCESS'
 while True:
  diagnostic=json.loads((B/'udm37-sterling-interior-components-v1/receipt.json').read_text())
  if diagnostic['status']!='STARTING':break
  time.sleep(5)
 assert diagnostic['status']=='SUCCESS' and not diagnostic['error']
 native=next((B/'udm37-sterling-interior-day-v1/host').glob('wrfout*'));diag=next((B/'udm37-sterling-interior-components-v1/host').glob('wrfout*'))
 subprocess.run([sys.executable,R/'validation/rrtmgp37/vapor-first-operation/compare_history.py',native,diag,B/'udm37-sterling-interior-components-comparison.json'],cwd=R,check=True)
 comparison=json.loads((B/'udm37-sterling-interior-components-comparison.json').read_text());assert comparison['pairs']==1350 and not comparison['differences']

 if '--reuse-extraction' in sys.argv:
  er=json.loads((B/'udm37-sterling-interior-day-extract-v1/receipt.json').read_text());assert er['status']=='SUCCESS' and er['native_read'] and er['source']['sha256']==hashlib.sha256((P/'extract.py').read_bytes()).hexdigest()
 else:subprocess.run([sys.executable,P/'extract.py'],cwd=R,check=True)
 s=importlib.util.spec_from_file_location('interior_analysis',P/'analyze.py');A=importlib.util.module_from_spec(s);s.loader.exec_module(A)
 old=json.loads((P.parent/'real-output-independent-comparison/result.json').read_text());prior=json.loads((P.parent/'sterling-cloud-radiation-attribution/result.json').read_text());context={'statistics':old['statistics'],'original_16_17UTC_direct_W_m2':prior['original_site']['physical_horizontal_direct_held_W_m2'],'observed_16_17UTC_horizontal_direct_W_m2':prior['observed_hour_components']['horizontal_direct_W_m2'],'observed_16_17UTC_components':prior['observed_hour_components']}
 d=json.loads((B/'udm37-sterling-interior-day-extract-v1/extracted.json').read_text());blobs=[(P.parent/f'solrad-boundary-site-48h/raw/ste16{n}.dat').read_bytes() for n in [280,281]];plan=json.loads((P/'plan.json').read_text());r=A.evaluate(d,blobs,plan,context)
 r['input_contrast']=json.loads((B/'udm37-sterling-interior-input-contrast-v2/input-contrast.json').read_text());(P/'result.json').write_text(json.dumps(r,indent=2)+'\n');(B/'udm37-sterling-interior-day-extract-v1/old-context.json').write_text(json.dumps(context,indent=2)+'\n')
 print(r['status']);print(json.dumps({'new_statistics':r['statistics'],'16_17UTC':r['surface_16_17UTC'],'decision':r['decision']},indent=2))
 for script in ['plot.py','report.py','deposit.py','verify_saved.py','test_saved.py']:
  subprocess.run([sys.executable,P/script],cwd=R,check=True)
 with (B/'udm37-sterling-interior-day-acceptance.log').open('w') as log:
  subprocess.run([sys.executable,R/'validation/rrtmgp37/acceptance/verify.py','--output',B/'udm37-sterling-interior-day-acceptance-index.json'],cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
  subprocess.run([sys.executable,R/'validation/rrtmgp37/acceptance/test_verify.py'],cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
 print('POSTRUN_REPLAY_AND_ACCEPTANCE_COMPLETE',flush=True)

if __name__=='__main__':main()
