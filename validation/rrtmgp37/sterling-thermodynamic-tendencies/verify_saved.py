"""Exact standard-library replay, no native process or large NetCDF dependency."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import json,hashlib,gzip,io,tarfile,copy,csv
from analyze import analyze,require
from report import summarize,step_rows
import instrument
P=Path(__file__).resolve().parent;R=P.parents[2]
sha=lambda x:hashlib.sha256(x).hexdigest()
def load():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'] and len(raw)==ident['archive']['bytes'],'archive identity')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  require(set(t.getnames())==set(ident['files']) and len(t.getmembers())==len(ident['files']) and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in t),'archive roster/type')
  data={n:t.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(data[n])==p['sha256'] and len(data[n])==p['bytes'],'payload '+n)
 for group in ['current_sources','unchanged_production_sources','dependencies']:
  for n,p in ident[group].items():require(sha((R/n).read_bytes())==p['sha256'],'source/dependency '+n)
 for n,p in ident['outputs'].items():require(sha((P/n).read_bytes())==p['sha256'],'output '+n)
 require(sha((P/'probe.f90').read_bytes())==ident['probe_source']['sha256'] and data['plan.json']==(P/'plan.json').read_bytes(),'probe/plan')
 require(not any(ident[n] for n in ['new_cold24h_WRF_processes','production_calculation_changes','coefficient_or_policy_changes','physical_accuracy_approved','original_seven_conditions_changed','new_model_runs_in_saved_replay']),'scope promotion')
 return data
def documents(data):
 before204=json.loads(data['before/validation/rrtmgp37/sterling-independent-atmosphere/identity.json']);after204=json.loads((P.parent/'sterling-independent-atmosphere/identity.json').read_text());expected=copy.deepcopy(before204);old=expected['current_documents'].pop('README.md');snap='validation/rrtmgp37/historical-source/root-README-after-PR204.md';current=after204['current_documents'][snap]
 require(old['sha256']==sha(data['before/README.md'])==sha((R/snap).read_bytes()) and old['bytes']==len(data['before/README.md']),'exact old root README snapshot')
 old['path']=current['path'];require(old['path'].endswith(snap),'historical doc locator');expected['current_documents'][snap]=old;expected['historical_document_scope']=after204['historical_document_scope'];require(expected==after204 and after204['historical_document_scope']['exact_snapshot_path']==snap,'PR204 identity changed beyond doc relocation')
 before205=json.loads(data['before/validation/rrtmgp37/sterling-low-level-evolution/identity.json']);after205=json.loads((P.parent/'sterling-low-level-evolution/identity.json').read_text());expected=copy.deepcopy(before205);n='validation/rrtmgp37/sterling-independent-atmosphere/identity.json';raw=(R/n).read_bytes();expected['dependencies'][n].update(sha256=sha(raw),bytes=len(raw));expected['documentation_dependency_rebinding']=after205['documentation_dependency_rebinding'];require(expected==after205,'PR205 dependency changed beyond doc identity pin')
 published=data['publication/root-README.md'].decode();require('sterling-low-level-evolution/README.md' in published and 'sterling-thermodynamic-tendencies/README.md' in published and '12시 기존 상태 오차' in published,'root publication progress/navigation missing')
def verify():
 data=load();j=lambda n:json.loads(data[n]);documents(data);run=j('run/receipt.json');build=j('build/receipt.json');ex=j('extract/extracted.json');eq=j('extract/history-comparison.json')
 require(run['status']=='SUCCESS' and not run['error'] and len(run['commands'])==1,'bounded run status/roster')
 require(len(build['commands'])==9 and len(build['sources'])==7,'private build process count')
 for r in run['commands']+build['commands']:require(r['pid']>0 and r['status']=='TERMINAL' and r['actual_returncode']==0 and not r['timed_out'],'actual process receipt')
 require('SUCCESS COMPLETE WRF' in data['run/command-01.stdout'].decode() and sha(data['run/namelist.input'])==run['namelist']['sha256'] and sha(data['run/radiation_iofields.txt'])==run['iofields']['sha256'],'run terminal/namelist identity')
 require(run['executable']['sha256']==build['executable']['sha256'] and ex['observed_operations']['sha256']==sha(data['native/thermodynamic_operations.txt']),'actual executable/native observations')
 for n,p in build['sources'].items():require(sha(data['build/sources/'+n])==p['sha256'],'actual compiled source '+n)
 require(data['build/sources/thermodynamic_probe.f90']==(P/'probe.f90').read_bytes(),'probe source')
 for n,s in instrument.transform(R).items():require(s.encode()==data['build/sources/'+n],'native source differs beyond private observer '+n)
 require(eq['pairs']==1350 and not eq['differences'] and sorted(eq['inventory'])==[f'2016-10-06_{h:02d}:00:00' for h in range(12,18)],'cold array comparison scope')
 require(all(len(v)==225 and all(x['equal'] and x['left_sha256']==x['right_sha256'] for x in v.values()) for v in eq['inventory'].values()),'missing/different native arrays')
 require(ex['native_read'] and ex['pid']>0 and eq['files'][0]['sha256']==ex['cold_history']['sha256'] and eq['files'][1]['sha256']==ex['observed_history']['sha256'],'actual history read linkage')
 with tarfile.open(P.parent/'sterling-low-level-evolution/saved/evidence.tar.gz','r:gz') as t:qualified=json.loads(t.extractfile('read/extracted.json').read())
 require(ex['cold_history']['sha256']==qualified['history']['sha256'] and run['initial']['sha256']==qualified['input']['sha256'] and run['forcing']['sha256']==qualified['boundary']['sha256'],'not the qualified fixed cold/forcing')
 old=json.loads((P.parent/'sterling-low-level-evolution/result.json').read_text());a=analyze(data['native/thermodynamic_operations.txt'].decode());result=summarize(a,ex,old)
 require(result==json.loads((P/'result.json').read_text()),'actual process result replay')
 with (P/'step-processes.csv').open() as f:rows=list(csv.DictReader(f))
 expected=list(step_rows(a));require(len(rows)==len(expected)==2400,'step CSV roster')
 for x,y in zip(rows,expected):
  for n,v in y.items():require(x[n]==str(v),'step CSV field '+n)
 return result
if __name__=='__main__':
 r=verify();print(json.dumps({k:r[k] for k in ['status','source_steps','replay_counts','cold_history_array_pairs_equal','decision','physical_accuracy_approved','new_model_runs_in_saved_replay']}))
