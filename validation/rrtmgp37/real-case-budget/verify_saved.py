#!/usr/bin/env python3
"""Stdlib replay: no compiler, model, external dependency, or new scientific PASS."""
from pathlib import Path
import argparse,difflib,gzip,hashlib,importlib.util,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('real_budget_analysis',P/'analyze.py');I=load('real_budget_instrument',P/'instrument.py')
H=load('historical_budget_sources',P.parent/'historical-source/binding.py')
def sha(x):return hashlib.sha256(x).hexdigest()
def readonly(public,private):
 a=public.splitlines(keepends=True);b=private.splitlines(keepends=True)
 for op,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
  A.require(op in ['equal','insert'],'native numerical statements changed')
  if op=='insert' and i:
   prev=next((x.rstrip() for x in reversed(a[:i]) if x.strip() and not x.lstrip().startswith(('!','#'))),'')
   A.require(not prev.endswith('&'),'observer inserted inside native continuation')
 return True

def data():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();A.require(sha(raw)==ident['archive']['sha256'],'archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  A.require(set(t.getnames())==set(ident['files']),'unindexed archive');d={n:t.extractfile(n).read() for n in ident['files']}
 for n,pin in ident['files'].items():A.require(sha(d[n])==pin['sha256'] and len(d[n])==pin['bytes'],'payload '+n)
 root=H.HistoricalRoot(R,ident['current_sources'])
 for n,pin in ident['current_sources'].items():A.require(sha((root/n).read_bytes())==pin['sha256'],'historical source '+n)
 for n,s in I.transform(root).items():
  A.require(d['build/'+n]==s.encode(),'generated read-only source differs '+n)
  pub=root/('WRF/dyn_em' if n in ['solve_em.F','module_em.F'] else 'WRF/phys')/n
  readonly(pub.read_text(),s)
 A.require([x.rstrip() for x in d['build/probe.f90'].splitlines()]==[x.rstrip() for x in (P/'probe.f90').read_bytes().splitlines()],'compiled helper differs beyond trailing whitespace')
 b=json.loads(d['build/receipt.json']);h=json.loads(d['host/receipt.json'])
 A.require(b['executable']['sha256']==h['executable']['sha256'],'wrong runtime executable')
 for n,pin in b['private_sources'].items():A.require(sha(d['build/'+n])==pin['sha256'],'compiled private source receipt')
 for n,pin in b['public_sources'].items():A.require(sha((root/n).read_bytes())==pin['sha256'],'compiled historical public source receipt')
 for x in b['commands']+h['commands']:A.require(x['actual_returncode']==0 and not x['timed_out'],'qualified command failed')
 A.require('SUCCESS COMPLETE WRF' in d['host/command-01.stdout'].decode() and 'FATAL CALLED' not in d['host/command-01.stdout'].decode(),'host did not complete')
 old=load('retained_restart_evidence',P.parent/'restart-first-step/verify_saved.py').data();base=json.loads(old['build/receipt.json'])
 A.require(b['base_library']['path'] in base['commands'][-1]['argv'],'not public corrected library')
 oldana=json.loads(old['analysis.json']);original=json.loads(old['nonzero/receipt.json'])
 A.require(h['checkpoint']['sha256']==original['checkpoint']['sha256'],'original checkpoint changed')
 A.require(h['forcing']['sha256']==original['original_forcing']['sha256'],'original real forcing changed')
 A.require(h['reference_history']['sha256']==oldana['fixed_restart']['right_file']['sha256'],'reference is not the original corrected restart')
 inventory=json.loads(d['inventory.json'])
 A.require(inventory['availability'][1]['file']['sha256']==oldana['fixed_restart']['left_file']['sha256'],'six-hour inventory history detached from original corrected continuous run')
 for time,rows in h['observer_inventory'].items():
  for n,row in rows.items():A.require(row['reference_sha256']==oldana['fixed_restart']['inventory'][time][n]['right_sha256'],'reference array detached from PR189 '+n)
 A.require(d['host/host/namelist.input']==old['fixed/restart/namelist.input'],'original real namelist changed')
 close=load('retained_closeout',P.parent/'boundary-closeout/verify_saved.py').data()
 A.require(b['base_library']['sha256']==json.loads(close['build/receipt.json'])['base_library']['sha256'],'corrected public library hash changed')
 return d

def evaluate(d):
 h=json.loads(d['host/receipt.json']);inv=h['observer_inventory'];A.require(h['observer_pairs']==675 and len(inv)==3,'observer coverage')
 for t,rows in inv.items():
  A.require(len(rows)==225,'observer variable omission')
  for n,row in rows.items():A.require(row['reference_sha256']==row['observed_sha256'],'observer changed history '+n)
 A.require(sha(d['host/real-budget.txt'])==h['trace']['sha256'],'trace runtime receipt')
 sd=json.loads(d['surface_domains.json'])
 for row in sd:
  A.require(inv[row['output_time']]['QFX']['observed_sha256']==row['QFX_field_sha256'],'surface QFX field binding')
 out=A.analyze(d['host/real-budget.txt'].decode(),sd);out['observer_noninterference_pairs']=675
 out['new_model_runs']=0 # Saved replay only. Actual production runs are counted separately in README.
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();r=evaluate(data())
 if args.write:(P/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 else:A.require(r==json.loads((P/'result.json').read_text()),'result detached from saved operands')
 ident=json.loads((P/'identity.json').read_text());matches=all(sha((R/n).read_bytes())==v['sha256'] for n,v in ident['current_sources'].items())
 print(json.dumps({'status':r['status'],'water_steps':len(r['water_steps']),'radiation_steps':len(r['radiation_steps']),'observer_pairs':675,'current_runtime_source_matches':matches,'source_scope':'current' if matches else 'historical_PR191_snapshot','water_conservation_approved':False,'full_energy_budget_approved':False,'new_model_runs':0}))
if __name__=='__main__':main()
