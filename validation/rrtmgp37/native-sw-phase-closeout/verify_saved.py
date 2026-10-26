"""Verify stored native returns; no model launch or inferred missing flux."""
from pathlib import Path
import gzip,hashlib,importlib.util,io,json,tarfile,math,re
P=Path(__file__).resolve().parent;R=P.parents[2]
# Replay the retained cloudy campaign against its exact pre-cloud-off sources.
# This does not certify the modified runtime; current wrappers have separate tests.
import runpy
R = runpy.run_path(str(P.parent/'historical-source/binding.py'))['SnapshotRoot'](
    R, 'snapshot-789188e2.json')
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('native_sw_analysis',P/'analyze.py');I=load('native_sw_instrument',P/'instrument.py');W=load('native_sw_existing_budget',P/'assess_existing.py');require=A.require
sha=lambda b:hashlib.sha256(b).hexdigest()
def compare_inventory(comp,expected):
 require(comp['pairs']==expected and not comp['differences'],'observation changed history')
 require(sum(map(len,comp['inventory'].values()))==expected,'comparison inventory incomplete')
 require(all(x['equal'] and x['left_sha256']==x['right_sha256'] for rows in comp['inventory'].values() for x in rows.values()),'comparison byte hash')

def data():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'],'archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as tar:
  require(set(tar.getnames())==set(ident['files']),'archive roster');d={n:tar.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(d[n])==p['sha256'] and len(d[n])==p['bytes'],'payload '+n)
 for n,p in ident['current_sources'].items():require(sha((R/n).read_bytes())==p['sha256'],'current source '+n)
 require(d['plan.json']==(P/'plan.json').read_bytes(),'plan differs')
 build=json.loads(d['build/receipt.json']);generated=I.transform(R)
 for n in ['solve_em.F','module_ra_rrtmg_sw.F','module_first_rk_step_part1.F']:
  require(d['build/'+n]==generated[n].encode(),'private observation changes '+n)
 require(d['build/sw_phase_probe.f90']==(P/'probe.f90').read_bytes(),'compiled SW observer differs')
 for n,p in build['sources'].items():require(sha(d['build/'+n])==p['sha256'],'compiled source pin')
 for n,p in build['public_sources'].items():require(sha((R/n).read_bytes())==p['sha256'],'underlying public source pin')
 for command in build['commands']:require(command['actual_returncode']==0 and not command['timed_out'],'build failed')
 for name in ['short','day']:
  run=json.loads(d[name+'/receipt.json']);require(run['status']=='SUCCESS' and not run['error'],'actual model failed')
  require(run['executable']['sha256']==build['executable']['sha256'],'runtime executable differs')
  require(run['same_original_forcing'] and not run['new_physical_policy'],'forcing or numerical policy changed')
  for command in run['commands']:require(command['actual_returncode']==0 and not command['timed_out'],'model return')
 pins=json.loads(d['baseline-pins.json']);day=json.loads(d['day/receipt.json'])
 prior_ident=json.loads((P.parent/'vapor-first-operation/identity.json').read_text())
 require(pins['baseline_observed_build_receipt']==prior_ident['files']['observed_build/receipt.json'],'retained observer source chain differs')
 require(build['base_observed_library']['sha256']==pins['baseline_observed_library']['sha256'],'base observation archive changed')
 baseline=json.loads(d['baseline-budget.json']);current=json.loads((P.parent/'vapor-first-operation/result.json').read_text())
 require(baseline=={k:current[k] for k in baseline},'baseline scientific result reinterpreted')
 require(sha(d['day/host/namelist.input'])==pins['namelist']['sha256'],'changed day namelist')
 require(day['initial']['sha256']==pins['initial']['sha256'] and day['forcing']['sha256']==pins['forcing']['sha256'],'changed input/forcing')
 for stage in ['during','after']:
  coeff=json.loads(d['coefficients-'+stage+'.json'])
  for n,p in coeff['files'].items():require(p['sha256']==pins['coefficients']['files'][n]['sha256'],'gas/cloud coefficient changed')
  require(coeff['frozen_table']['sha256']==pins['coefficients']['frozen_table']['sha256'],'frozen table changed')
 for name in ['short','day']:
  comp=json.loads(d[name+'/history-comparison.json']);expected=675 if name=='short' else 5625
  compare_inventory(comp,expected)
  require(comp['files'][1]['sha256']==pins[name+'_comparison_new_file_sha256'],'new compared history pin')
  require(comp['files'][0]['sha256']==pins[name+'_comparison_baseline_file_sha256'],'baseline compared history pin')
 require(sha(d['day/host/real-budget.txt'])==pins['baseline_budget_trace']['sha256'],'actual operator/source trace changed')
 require(sha(d['day/host/vapor-first.txt'])==pins['baseline_vapor_trace']['sha256'],'existing final-stage vapor trace changed')
 require(re.search(r'(?im)^\s*SWINT_OPT\s*=\s*0\s*,',d['day/host/namelist.output'].decode()),'actual SW interpolation unsupported')
 require(not ident['production_changes'] and not ident['scientific_approval'],'scope promotion')
 return d

def evaluate(d):
 r=A.analyze(d['day/host/sw-phase.txt'].decode());short=A.analyze(d['short/host/sw-phase.txt'].decode(),120)
 processes=[]
 for name,raw in d.items():
  if not name.endswith('/receipt.json'):continue
  rec=json.loads(raw)
  for command in rec.get('commands',[]):
   argv=command['argv']
   if argv and argv[0]=='bash' and any(str(x).endswith('/wrf') for x in argv):
    processes.append({'deposit':name[:-13],'returncode':command['actual_returncode'],'status':rec['status'],'executable_sha256':rec['executable']['sha256']})
 require(len(processes)==3 and sum(x['status']=='SUCCESS' for x in processes)==2,'actual model-process inventory')
 r['actual_new_WRF_processes']=processes;r['independent_meteorological_cases']=1

 r['short_observer_noninterference_pairs']=675;r['whole_day_observer_noninterference_pairs']=5625
 r['prior_observer_reclassification_and_combined_source']=A.prior_observer_and_applied_source(d['day/host/real-budget.txt'].decode(),r)
 baseline=json.loads(d['baseline-budget.json']);actual=r['prior_observer_reclassification_and_combined_source']
 require(actual['actual_combined_LW_SW_add_equivalent_J_m2']==baseline['radiation_source_equivalent_J_m2'],'actual combined source changed')
 require(actual['raw_combined_interior_J_m2']==baseline['raw_source_interior_equivalent_J_m2'],'raw combined source changed')
 r['existing_water_support_decision']=W.assess((P.parent/'vapor-first-operation/result.json').read_bytes())
 r['important_frozen_call_selection']=W.frozen_targets(d['day/host/real-budget.txt'].decode(),r['geometry']['area_m2'])
 r['frozen_independent_optical_accuracy_approved']=False
 r['short_actual_night_calls']=short['fully_night_calls'];r['production_changes']=False
 r['current_runtime_source_matches']=True
 return r
if __name__=='__main__':
 r=evaluate(data());require(r==json.loads((P/'result.json').read_text()),'saved result differs')
 print(json.dumps(R.summary({k:r[k] for k in ['status','actual_SW_calls','completed_steps','fully_night_calls','fully_day_calls','mixed_complete_calls','missing_phase_seconds','partially_observed_seconds','whole_day_observer_noninterference_pairs','current_runtime_source_matches','whole_energy_approved','new_model_runs_in_saved_replay']})))
