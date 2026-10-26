"""Standard-library replay of archived actual faces and immutable prior attribution."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import json,gzip,io,tarfile,hashlib,csv
from analyze import analyze,require,f32
import instrument
P=Path(__file__).resolve().parent;R=P.parents[2]
sha=lambda x:hashlib.sha256(x).hexdigest()
def load():
 ident=json.loads((P/'identity.json').read_text());arc=(P/'saved/evidence.tar.gz').read_bytes();require(sha(arc)==ident['archive']['sha256'] and len(arc)==ident['archive']['bytes'],'archive identity')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(arc)),mode='r:') as t:
  require(set(t.getnames())==set(ident['files']) and len(t.getmembers())==len(ident['files']) and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in t),'archive roster/type');data={n:t.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(data[n])==p['sha256'] and len(data[n])==p['bytes'],'payload '+n)
 for group in ['current_sources','unchanged_production_sources','dependencies']:
  for n,p in ident[group].items():require(sha((R/n).read_bytes())==p['sha256'] and len((R/n).read_bytes())==p['bytes'],'source/dependency '+n)
 for n,p in ident['outputs'].items():require(sha((P/n).read_bytes())==p['sha256'] and len((P/n).read_bytes())==p['bytes'],'output '+n)
 require(sha((P/'probe.f90').read_bytes())==ident['probe_source']['sha256'] and data['plan.json']==(P/'plan.json').read_bytes(),'probe/plan')
 require(not any(ident[n] for n in ['new_cold24h_WRF_processes','production_calculation_changes','coefficient_or_policy_changes','physical_accuracy_approved','original_seven_conditions_changed','new_model_runs_in_saved_replay']),'scope promotion')
 return data

def inputs(data):
 with tarfile.open(P.parent/'sterling-thermodynamic-tendencies/saved/evidence.tar.gz','r:gz') as t:oldtext=t.extractfile('native/thermodynamic_operations.txt').read().decode();oldex=json.loads(t.extractfile('extract/extracted.json').read());oldrun=json.loads(t.extractfile('run/receipt.json').read());oldbuild=json.loads(t.extractfile('build/receipt.json').read())
 return oldtext,(P.parent/'sterling-thermodynamic-tendencies/step-processes.csv').read_text(),json.loads((P.parent/'sterling-thermodynamic-tendencies/result.json').read_text()),oldex,oldrun,oldbuild

def verify_state_table(result,text):
 header='| UTC | history θd8−θd7, K | qv8−qv7, g/kg dry | 질량점 높이8−7, m |'
 require(text.count(header)==1,'README state table header')
 profiles=result['prior_state_evidence']['hourly_central_states']
 require([x['hour_UTC'] for x in profiles]==list(range(12,18)),'README state table time support')
 expected=[header,'|---|---:|---:|---:|']
 for profile in profiles:
  lower,upper=[next(x for x in profile['profiles'] if x['record']==k) for k in [7,8]]
  expected.append(f"| {profile['hour_UTC']} | {upper['dry_theta_K']-lower['dry_theta_K']:+.6f} | {1000*(upper['qv_kg_kg']-lower['qv_kg_kg']):+.6f} | {upper['z_msl_m']-lower['z_msl_m']:.3f} |")
 actual=text[text.index(header):].split('\n\n',1)[0].splitlines()
 require(actual==expected,'README state table must contain six numeric rows matching existing JSON')

def verify():
 data=load();j=lambda n:json.loads(data[n]);run=j('run/receipt.json');build=j('build/receipt.json');ex=j('extract/extracted.json');eq=j('extract/history-comparison.json');prior=j('prior/prior-state-and-coordinate.json');oldtext,oldcsv,oldresult,oldex,oldrun,oldbuild=inputs(data)
 require(run['status']=='SUCCESS' and not run['error'] and len(run['commands'])==1 and len(build['commands'])==6 and len(build['sources'])==4,'actual run/build scope')
 for r in run['commands']+build['commands']:require(r['pid']>0 and r['status']=='TERMINAL' and r['actual_returncode']==0 and not r['timed_out'],'actual process receipt')
 require('SUCCESS COMPLETE WRF' in data['run/command-01.stdout'].decode() and sha(data['run/namelist.input'])==run['namelist']['sha256'] and sha(data['run/radiation_iofields.txt'])==run['iofields']['sha256'],'terminal/namelist')
 require(build['base_library']['sha256']==oldbuild['base_library']['sha256'] and build['executable']['sha256']==run['executable']['sha256'],'unchanged public base library and actual executable')
 for n in ['checkpoint','initial','forcing','namelist','iofields']:require(run[n]['sha256']==oldrun[n]['sha256'],'same qualified checkpoint/input/time '+n)
 for n,p in build['sources'].items():require(sha(data['build/sources/'+n])==p['sha256'],'compiled source '+n)
 require(data['build/sources/transport_probe.f90']==(P/'probe.f90').read_bytes(),'compiled probe')
 for n,s in instrument.transform(R).items():require(data['build/sources/'+n]==s.encode(),'private-only source transform '+n)
 require(ex['native_read'] and ex['pid']>0 and prior['native_read'] and prior['pid']>0,'actual NetCDF reads')
 require(sha(data['native/transport_faces.txt'])==ex['observed_operations']['sha256'],'native face identity')
 require(eq['pairs']==1350 and not eq['differences'] and sorted(eq['inventory'])==[f'2016-10-06_{h:02d}:00:00' for h in range(12,18)],'noninterference scope')
 require(all(len(v)==225 and all(x['equal'] and x['left_sha256']==x['right_sha256'] for x in v.values()) for v in eq['inventory'].values()),'actual cold arrays')
 require(eq['files'][0]['sha256']==ex['cold_history']['sha256']==prior['history']['sha256']==oldex['cold_history']['sha256'] and eq['files'][1]['sha256']==ex['observed_history']['sha256'],'qualified actual histories')
 require(len(prior['original_neighbor_records'])==2450 and len(prior['fixed_neighborhood_states'])==294 and len(prior['hourly_central_states'])==6,'prior neighborhood/coordinate scope')
 original_neighbors=[]
 for line in oldtext.splitlines():
  x=line.split()
  if x[1]=='neighbor_start':original_neighbors.append({'source_seconds':int(float(x[0])),'k':int(x[4]),'i':int(float(x[5])),'j':int(float(x[6])),'values':list(map(float,x[7:]))})
 require(prior['original_neighbor_records']==original_neighbors,'exact existing neighborhood reuse')
 for profile,previous in zip(prior['hourly_central_states'],oldex['hourly_states']):
  require(previous['time_UTC']==f"2016-10-06_{profile['hour_UTC']:02d}:00:00",'existing state time support')
  fields=previous['native_layers5_12']
  for k in range(5,13):
   row=next(x for x in profile['profiles'] if x['record']==k);n=k-5
   require(row['dry_theta_K']==fields['T'][n]+300 and row['qv_kg_kg']==fields['QVAPOR'][n] and row['QCLOUD']==fields['QCLOUD'][n] and row['p_Pa']==f32(fields['P'][n]+fields['PB'][n]),'same prior history thermodynamics')
  context=next(x for x in prior['fixed_neighborhood_states'] if x['hour_UTC']==profile['hour_UTC'] and x['i_j_one_based']==[37,119]);require(context==profile,'fixed center/neighborhood bridge')
 require(prior['history_velocity_roster']=={'W':True,'WW':False,'WWM':False,'OMEGA':False,'U':True,'V':True},'why additional capture was necessary')
 published=data['publication/root-README.md'].decode();require('sterling-transport-state/README.md' in published and '12시 기존 상태 오차' in published,'publication progress navigation')
 result,rows=analyze(data['native/transport_faces.txt'].decode(),prior,oldtext,oldcsv,oldresult,eq)
 require(result==json.loads((P/'result.json').read_text()),'result replay')
 verify_state_table(result,(P/'README.md').read_text())
 with (P/'step-faces.csv').open() as f:stored=list(csv.DictReader(f))
 require(len(stored)==len(rows)==600,'step CSV roster')
 for x,y in zip(stored,rows):
  for n,v in y.items():require(x[n]==('' if v is None else str(v)),'CSV field '+n)
 return result
if __name__=='__main__':
 r=verify();print(json.dumps({k:r[k] for k in ['status','source_steps','replay_counts','cold_history_array_pairs_equal','decision','physical_accuracy_approved','new_model_runs_in_saved_replay']}))
