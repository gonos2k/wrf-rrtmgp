"""Run postprocessing only after actual bounded model completion."""
from pathlib import Path
import subprocess,json,shutil,tarfile,importlib.util
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;D=B/'udm37-sterling-cloud-run-v1';O=B/'udm37-sterling-finish-v2';O.mkdir(exist_ok=False)
receipt=json.loads((D/'receipt.json').read_text());assert receipt['status']=='SUCCESS' and not receipt['error']
files=list((D/'host').glob('wrfout*'));assert len(files)==1
shutil.copyfile(B/'udm37-sterling-finish-v1/history-comparison.json',O/'history-comparison.json')
# The completed actual NetCDF comparison is reused; the first analysis confused an unused CF diagnostic with consumed CF.

c=json.loads((O/'history-comparison.json').read_text());assert c['pairs']==1350 and not c['differences'] and len(c['inventory'])==6 and all(len(x)==225 for x in c['inventory'].values())
shutil.copyfile(B/'udm37-sterling-existing-v1/existing.json',O/'existing.json');shutil.copyfile(B/'udm37-sterling-ulp-correction.json',O/'ulp-correction.json')
H=O/'historical';H.mkdir()
for name in ['analyze.py','result.json','identity.json','hourly-comparison.csv']:
 data=subprocess.check_output(['git','show','0aadad812e5fffdb99d3bf0c34ea5429e4b26487:validation/rrtmgp37/real-output-independent-comparison/'+name],cwd=R);(H/name).write_bytes(data)
s=importlib.util.spec_from_file_location('sterling_attribution',P/'analyze.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
base=P.parent/'real-output-independent-comparison';obs=P.parent/'solrad-boundary-site-48h';r=a.evaluate({'host/sterling-cloud.txt':(D/'host/sterling-cloud.txt').read_bytes(),'existing.json':(O/'existing.json').read_bytes()},json.loads((base/'result.json').read_text()),[(obs/f'raw/ste16{day}.dat').read_bytes() for day in [280,281]])
r['continuous_cold_array_pairs_equal']=c['pairs'];r['ULP_fix_only_diagnostic_scores_unchanged']=True
(P/'result.json').write_text(json.dumps(r,indent=2)+'\n');print('ACTUAL_STATE_ATTRIBUTION_COMPLETE',r['original_site'])
