"""Verify retained actual runs and replay; never launch a scientific executable."""
import gzip,hashlib,importlib.util,json,re
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(x):return hashlib.sha256(x).hexdigest()
def read(n):
 if n.startswith('prior-PSD/'):p=B.parent/'host-source-fixed-psd/saved/psd'/(n[len('prior-PSD/'):]+'.gz')
 else:p=B/'saved'/(n+'.gz')
 return gzip.decompress(p.read_bytes())
def load(p,name):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def verify():
 seal=json.loads((B/'manifest.json').read_text());require(not seal['production_accepted'],'false approval')
 files={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts};require(files==set(seal['files']),'sealed roster differs')
 for n,z in seal['files'].items():
  p=B/n;require(not p.is_symlink() and p.stat().st_size==z['bytes'] and sha(p.read_bytes())==z['sha256'],'sealed bytes changed '+n)
 ident=json.loads((B/'identity.json').read_text());require(ident['base_main']=='c7443e7b0bf602cb76e70779629f320bd8fec182' and not ident['production_source_changed'] and not ident['physics_gates_closed'] and not ident['production_accepted'],'scope retagging')
 for n,h in ident['source_files'].items():require(sha(read('source/'+n))==h,'studied source differs '+n)
 obs=json.loads(read('observer/receipt.json'));host=json.loads(read('host/receipt.json'))
 require(host['executable']==obs['executable'] and ident['actual_input_sha256']==host['initial_input']['sha256'],'actual binary/input chain')
 for name,z in obs['sources'].items():
  source=read('source/WRF/'+name);diagnostic=read('observer/'+name)
  require(sha(source)==z['original']['sha256'] and sha(diagnostic)==z['observer']['sha256'],'compiled observer source pin')
  restored=re.sub(rb'! ENERGY_OBSERVER_BEGIN\n.*?! ENERGY_OBSERVER_END\n',b'',diagnostic,flags=re.S)
  require([x for x in restored.splitlines() if x.strip()]==[x for x in source.splitlines() if x.strip()],'observer changes original statements')
 ar=json.loads(read('observer/archive.json'));require(len(ar['original'])==len(ar['diagnostic']),'archive roster changed')
 changed=[x['name'] for x,z in zip(ar['original'],ar['diagnostic']) if x!=z]
 require(changed==ar['changed_members'] and set(changed)=={'/','/2024','/2276','solve_em.F.o/','/6732','bl_ysu.F90.o/'},'unrelated archive object changed')
 table=ar['GNU_long_name_table'].encode()
 require(sha(table)==next(z['sha256'] for z in ar['original'] if z['name']=='//'),'GNU member-name table differs')
 resolved=[]
 for name in changed:
  if name.startswith('/') and name[1:].isdigit():name=table[int(name[1:]):].split(b'/\n')[0].decode()
  elif name!='/':name=name.rstrip('/')
  resolved.append(name)
 require(resolved==ar['changed_resolved_members'] and set(resolved)=={'/','module_small_step_em.F.o','module_first_rk_step_part2.F.o','solve_em.F.o','module_ra_rrtmgp.F.o','bl_ysu.F90.o'},'member-name mapping differs')
 require(len(obs['commands'])==7 and len(host['commands'])==3,'actual process counts changed')
 for rec in obs['commands']+host['commands']:require(rec['status']=='TERMINAL' and rec['actual_returncode']==0 and not rec['timed_out'],'failed or unreaped qualified command')
 for i in [1,2,3]:require(b'SUCCESS COMPLETE WRF' in read(f'host/command-{i:02d}.stdout'),'host success absent')
 for name in ['off','on','held30s']:
  idx=json.loads(read('host/'+name+'.json'));data=read('host/'+name+'.bin');require(len(idx['records'])==211 and idx['payload_sha256']==sha(data),'history packet differs')
  for z in idx['records']:require(sha(data[z['offset']:z['offset']+z['bytes']])==z['sha256'],'history variable bytes differ')
  require(idx['attrs']['UDM_NUMBER_POLICY']==1 and idx['attrs']['UDM_POPULATION_POLICY']==2,'runtime policy differs')
 prior=ROOT/'validation/rrtmgp37/consistent-warm-input/saved/host'
 require(read('host/off.bin')==read('host/on.bin')==gzip.decompress((prior/'final-on_dt10.bin.gz').read_bytes()),'diagnostics perturb retained host arrays')
 require(ident['actual_input_sha256']==json.loads(gzip.decompress((prior/'final-input.json.gz').read_bytes()))['source_NetCDF_sha256'],'consistent initial input changed')
 # The four historical arrays remain bound to PR177 bytes, not a new solver run.
 for n,h in ident['prior_PSD_sha256'].items():require(sha(read('prior-PSD/'+n))==h,'historical PSD output changed')
 a=load(B/'analyze_saved.py','energy_replay');result=a.analyze(read);require(result==json.loads((B/'result.json').read_text()),'raw energy/matrix/PSD replay differs')
 require(not result['production_accepted'] and result['decisions']['YSU_host_dry_water_physical_approval'] is False and result['decisions']['dry_mass_temperature_equivalent_energy'].startswith('NOT_CLOSED'),'physical approval silently promoted')
 require((B/'closure-conditions.json').read_bytes()==(B.parent/'host-source-fixed-psd/closure-conditions.json').read_bytes(),'existing seven conditions changed')
 return {'status':'PASS_SCOPED_RADIATION_APPLICATION_AND_FROZEN_YSU_REPLAY','WRF_processes':3,'retained_PSD_solver_outputs':4,'new_solver_runs_in_replay':0,'dry_energy_closed':False,'YSU_host_water_approved':False,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
