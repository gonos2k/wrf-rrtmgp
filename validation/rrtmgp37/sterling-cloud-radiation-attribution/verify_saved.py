"""Portable saved attribution and exact zero-only diagnostic correction."""
from pathlib import Path
import json,hashlib,tarfile,io,gzip,importlib.util,re
P=Path(__file__).resolve().parent;R=P.parents[2]
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('sterling_saved_analysis',P/'analyze.py');I=load('sterling_private_source',P/'instrument.py');require=A.require;sha=lambda b:hashlib.sha256(b).hexdigest()
def comparison_check(c):
 require(c['pairs']==1350 and not c['differences'],'actual cold/restart observation mismatch')
 expected=['2016-10-06_%02d:00:00'%h for h in range(12,18)];require(sorted(c['inventory'])==expected and all(len(r)==225 for r in c['inventory'].values()),'omitted actual time/variable')
 require(all(v['equal'] and v['left_sha256']==v['right_sha256'] for r in c['inventory'].values() for v in r.values()),'actual native array changed')
def data():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'],'archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  require(set(t.getnames())==set(ident['files']),'archive roster');d={n:t.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(d[n])==p['sha256'] and len(d[n])==p['bytes'],'payload '+n)
 for n,p in ident['outputs'].items():require(sha((P/n).read_bytes())==p['sha256'],'output artifact '+n)
 for group in ['dependencies','current_sources']:
  for n,p in ident[group].items():require(sha((R/n).read_bytes())==p['sha256'],'source/evidence '+n)
 require(d['plan.json']==(P/'plan.json').read_bytes(),'plan changed')
 j=lambda n:json.loads(d[n]);v=json.loads((P.parent/'vapor-first-operation/identity.json').read_text())
 for name,key in [('baseline-public-receipt.json','public/receipt.json'),('baseline-day-receipt.json','day/receipt.json')]:require(sha(d[name])==v['files'][key]['sha256'],'baseline run identity changed')
 run=j('run/receipt.json');build=j('build/receipt.json');pub=j('baseline-public-receipt.json');day=j('baseline-day-receipt.json')
 require(run['status']=='SUCCESS' and not run['error'] and run['executable']['sha256']==build['executable']['sha256'],'actual bounded run failure/wrong executable')
 require(build['base_library']['sha256']==pub['library']['sha256'] and run['initial']['sha256']==day['initial']['sha256'] and run['forcing']['sha256']==day['forcing']['sha256'],'base library or forcing changed')
 for r in [run,build]:
  for c in r['commands']:require(c['actual_returncode']==0 and not c['timed_out'],'command failed')
 for name,text in I.transform(R).items():require(d['build/'+name]==text.encode(),'private source contains unrelated edit')
 require(d['build/sterling_cloud_probe.f90']==(P/'probe.f90').read_bytes(),'compiled helper changed')
 for name,pin in build['sources'].items():require(sha(d['build/'+name])==pin['sha256'],'compiled source pin')
 require(run['checkpoint']['path'].endswith('wrfrst_d01_2016-10-06_11:58:00'),'wrong checkpoint')
 comp=j('history-comparison.json');comparison_check(comp);existing=j('existing.json')
 require(comp['files'][0]['sha256']==existing['history_sha256']=='3da760fb50fa18b5ead1248ca684f72e22625524896d37a1bc2aa432c01fd72c' and existing['forcing_sha256']==day['forcing']['sha256'],'wrong native extraction history/forcing')
 nml=d['run/host/namelist.input'].decode();original_nml=Path(P.parent/'real-output-independent-comparison').joinpath('saved/evidence.tar.gz')
 with tarfile.open(original_nml) as t:original=t.extractfile('namelist.input').read().decode()
 changes=dict(run_seconds='18120',start_hour='11',start_minute='58',end_day='06',end_hour='17',end_minute='0',end_second='0',history_begin_s='120',history_interval_s='3600',restart_interval_s='1000000',restart='.true.',override_restart_timers='.true.')
 for name,value in changes.items():
  if not re.search(r'(?im)^\s*'+name+r'\s*=',original):original=original.replace('&time_control','&time_control\n '+name+' = '+value+',',1)
  original,count=re.subn(r'(?im)^(\s*'+name+r'\s*=\s*)[^,\n]+',lambda m:m[1]+value,original);require(count==1,'runtime time/IO key')
 require(nml==original,'bounded run changed non-time/IO policy')
 old=j('historical/result.json');current=json.loads((P.parent/'real-output-independent-comparison/result.json').read_text());require(old['statistics']==current['statistics'] and old['uncertainties']==current['uncertainties'],'ULP fix changed scores/max scale')
 old_source=d['historical/analyze.py'].decode();needle=" require(struct.unpack('<f',struct.pack('<f',x))[0]==x,'accumulator is not original REAL32')\n";require(old_source.count(needle)==1 and old_source.replace(needle,needle+' if x==0.:return 2.**-149\n')==(P.parent/'real-output-independent-comparison/analyze.py').read_text(),'ULP fix is not zero-only')
 for before,after in zip(old['hourly'],current['hourly']):
  require({k:x for k,x in before.items() if k!='endpoint_only_half_ULP_scale_W_m2'}=={k:x for k,x in after.items() if k!='endpoint_only_half_ULP_scale_W_m2'},'ULP changed physical comparison')
 historical_identity=j('historical/identity.json');require(sha(d['historical/analyze.py'])==historical_identity['current_sources']['validation/rrtmgp37/real-output-independent-comparison/analyze.py']['sha256'],'historical ULP source identity')
 require(sha((P.parent/'real-output-independent-comparison/sterling-corrected-day-sw.png').read_bytes())==historical_identity['outputs']['sterling-corrected-day-sw.png']['sha256'],'original score plot changed')
 require(not ident['production_changes'] and not ident['original_seven_conditions_changed'] and not ident['physical_accuracy_approved'],'scope promotion')
 return d,current,[(P.parent/f'solrad-boundary-site-48h/raw/ste16{n}.dat').read_bytes() for n in [280,281]]
if __name__=='__main__':
 d,c,o=data();r=A.evaluate(d,c,o);r.update(continuous_cold_array_pairs_equal=1350,ULP_fix_only_diagnostic_scores_unchanged=True);require(r==json.loads((P/'result.json').read_text()),'saved attribution changed')
 print(json.dumps({k:r[k] for k in ['status','actual_target_SW_calls','actual_input_layer_samples','actual_held_column_steps','continuous_cold_array_pairs_equal','received_site_cloud_and_CU_paths_all_zero','boundary_causality_proven','production_changes','new_model_runs_in_saved_replay']}))
