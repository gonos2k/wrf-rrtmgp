"""Finalize completed actual observations; this command never launches WRF."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-native-sw-analysis-v1';D=B/'udm37-native-sw-day-v2';baseline=B/'udm37-vapor-corrected-day-v2'
assert json.loads((D/'receipt.json').read_text())['status']=='SUCCESS','wait for the actual full period; do not crop it'
def run(*args):subprocess.run([sys.executable,*map(str,args)],cwd=R,check=True)
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
run(P.parent/'vapor-first-operation/compare_history.py',baseline/'host/wrfout_d01_2016-10-06_00:00:00',D/'host/wrfout_d01_2016-10-06_00:00:00',D/'history-comparison.json')
run(P/'capture_coefficients.py','--stage','after')
pins=json.loads((O/'baseline-pins-partial.json').read_text())
for name,directory,count in [('short',B/'udm37-native-sw-short-v2',675),('day',D,5625)]:
 comp=json.loads((directory/'history-comparison.json').read_text());assert comp['pairs']==count and not comp['differences'],'observations changed numerical results'
 pins[name+'_comparison_baseline_file_sha256']=comp['files'][0]['sha256'];pins[name+'_comparison_new_file_sha256']=comp['files'][1]['sha256']
for name,key in [('real-budget.txt','baseline_budget_trace'),('vapor-first.txt','baseline_vapor_trace')]:
 assert pin(D/'host'/name)==pins[key],'existing actual numerical trace changed'
(O/'baseline-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
run(P/'deposit.py')
s=importlib.util.spec_from_file_location('native_sw_final_evaluation',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
r=V.evaluate(V.data());(P/'result.json').write_text(json.dumps(r,indent=2)+'\n')
run(P/'render_readme.py');run('-I','-S',P/'verify_saved.py');run('-I','-S',P/'test_saved.py')
print('NATIVE_SW_ACTUAL_OBSERVATIONS_FINALIZED')
