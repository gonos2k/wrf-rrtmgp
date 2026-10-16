"""Retained candidate replay. No Fortran/WRF/RTE/Mie process is launched."""
import gzip,hashlib,importlib.util,json,re
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(x):return hashlib.sha256(x).hexdigest()
def read(n):
 p=B.parent/'applied-radiation-energy/saved'/(n[len('prior178/'):]+'.gz') if n.startswith('prior178/') else B/'saved'/(n+'.gz')
 return gzip.decompress(p.read_bytes())
def load(p,name):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def verify():
 seal=json.loads((B/'manifest.json').read_text());require(not seal['production_accepted'],'false approval')
 files={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts};require(files==set(seal['files']),'sealed roster differs')
 for n,z in seal['files'].items():
  p=B/n;require(not p.is_symlink() and p.stat().st_size==z['bytes'] and sha(p.read_bytes())==z['sha256'],'sealed bytes changed '+n)
 ident=json.loads((B/'identity.json').read_text());require(ident['base_main']=='eff9ced5798583b48b4fa651338aef596babb6b0' and not ident['production_source_changed'] and not ident['production_accepted'] and not ident['physics_gates_closed'],'source/approval retagging')
 for n,h in ident['source_files'].items():require(sha(read('source/'+n))==h,'historical source differs')
 build=json.loads(read('candidate/receipt.json'));host=json.loads(read('host/receipt.json'));prior=json.loads(read('prior178/observer/receipt.json'))
 require(build['base_archive']==prior['new_archive'] and build['executable']==host['executable'],'private base/executable chain')
 require(len(build['commands'])==5 and len(host['commands'])==5,'actual process counts differ')
 for x in build['commands']+host['commands']:require(x['status']=='TERMINAL' and x['actual_returncode']==0 and not x['timed_out'],'actual process failed/unreaped')
 for i in range(1,6):require(b'SUCCESS COMPLETE WRF' in read(f'host/command-{i:02d}.stdout'),'host incomplete')
 for n,h in build['sources'].items():
  src=read('candidate/'+n);require(sha(src)==h['sha256'],'compiled candidate source differs')
  stripped=re.sub(rb'! CAPACITY_CANDIDATE_BEGIN\n.*?! CAPACITY_CANDIDATE_END\n',b'',src,flags=re.S)
  original=read('prior178/observer/'+n) if n=='phys/module_ra_rrtmgp.F' else read('source/WRF/'+n)
  require([x for x in stripped.splitlines() if x.strip()]==[x for x in original.splitlines() if x.strip()],'unmarked science change')
 archive=json.loads(read('candidate/archive.json'));prior_ar=json.loads(read('prior178/observer/archive.json'))
 require(archive['original_PR178_observer']==prior_ar['diagnostic'],'base archive members differ')
 changed=[x['name'] for x,z in zip(archive['original_PR178_observer'],archive['candidate']) if x!=z];require(len(archive['candidate'])==len(archive['original_PR178_observer']) and changed==archive['changed_members'] and set(changed)=={'/','/6732','/6754','/6832'},'unrelated object changed')
 table=prior_ar['GNU_long_name_table'].encode();resolved=[table[int(n[1:]):].split(b'/\n')[0].decode() for n in changed if n[1:].isdigit()];require(set(resolved)=={'module_ra_rrtmgp.F.o','module_ra_rrtmg_lw.F.o','module_ra_rrtmg_sw.F.o'},'wrong candidate object scope')
 for name in ['legacy','capacity','held30s','cloud_native','cloud_gamma8']:
  idx=json.loads(read('host/'+name+'.json'));data=read('host/'+name+'.bin');require(idx['payload_sha256']==sha(data) and len(idx['records'])==211,'history packet differs')
  require(idx['attrs']['UDM_NUMBER_POLICY']==1 and idx['attrs']['UDM_POPULATION_POLICY']==2,'population changed')
  for z in idx['records']:require(sha(data[z['offset']:z['offset']+z['bytes']])==z['sha256'],'history variable changed')
  require(host['inputs'][name]['sha256']==ident['actual_input_sha256'][name],'actual input pin differs')
 require(read('host/legacy.bin')==read('prior178/host/on.bin'),'private defaults change retained production history')
 positive_sha=sha(read('input/positive.nc'));require(ident['actual_input_sha256']['cloud_native']==ident['actual_input_sha256']['cloud_gamma8']==positive_sha,'positive cloud input differs')
 for name in ['legacy','capacity','held30s']:require(ident['actual_input_sha256'][name]==json.loads(read('prior178/host/receipt.json'))['initial_input']['sha256'],'heat comparison input changed')
 require((B/'closure-conditions.json').read_bytes()==(B.parent/'applied-radiation-energy/closure-conditions.json').read_bytes(),'seven conditions changed')
 a=load(B/'analyze_saved.py','capacity_replay');result=a.analyze(read);require(result==json.loads((B/'result.json').read_text()),'raw capacity/positive cloud replay differs')
 require(not result['decision']['candidate_in_production'] and not result['decision']['unique_original_WRF_thermodynamics_proved'],'candidate silently certified as original WRF policy')
 return {'status':'PASS_SCOPED_NATIVE_CONSTANT_KAPPA_CANDIDATE_AND_LIVE_GAMMA8','actual_WRF_processes':5,'positive_cloud_source_seconds':10,'new_science_runs_in_replay':0,'production_source_changed':False,'whole_energy_approved':False,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
