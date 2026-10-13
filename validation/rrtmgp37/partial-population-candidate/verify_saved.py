"""Replay actual fixed-CF full-UDM population experiment, with final joins."""
import base64,gzip,hashlib,importlib.util,json,math,struct
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def read(name):return gzip.decompress((B/name).read_bytes())

def datasets(receipt,opt):
 test=load(ROOT/'WRF/test/rrtmgp/test_udm_partial_population.py','population');data={}
 for n,c in enumerate(receipt['processes'],1):
  if c['kind'].startswith('UDM_') and '/'+opt+'/' in c['argv'][0]:
   variant,scenario,mode,enabled=c['kind'][4:].split('_');require(c['status']=='TERMINAL' and c['actual_returncode']==0 and not c['timed_out'],'model process incomplete')
   key=scenario,mode,enabled;require(key not in data,'duplicate model execution');data[key]=test.parse(read(f'saved/command-{n:02d}.stdout.gz').decode())
 require(len(data)==10,'exact actual UDM process roster');return data

def final_joins(data):
 test=load(ROOT/'WRF/test/rrtmgp/test_udm_partial_population.py','population_final');d=data['warm','candidate','on'];joins=0;max_relative=0.
 for base in (1,4):
  for c in (base+1,base+2):
   f=(1.,.5,.25)[(c-1)%3]
   for slot in [*range(8,12),*range(16,20),*range(36,44)]:
    x=struct.unpack('!f',bytes.fromhex(d['outputs'][base][slot]))[0];y=struct.unpack('!f',bytes.fromhex(d['outputs'][c][slot]))[0]
    require(y==test.f32(f*x),'final QC/QR/host NC/NR area scaling');joins+=1
   for k in range(1,5):
    require(d['obs']['HELPER_OUT',c,1,k,0][6]==d['obs']['HELPER_OUT',base,1,k,0][6],'final native radius depends on CF');joins+=1
 for c in range(1,7):
  for k in range(1,5):
   n,q,rho=d['obs']['HELPER_IN',c,1,k,0][:3];eta=struct.unpack('!f',bytes.fromhex(d['outputs'][c][36+k-1]))[0]
   require(eta==test.f32(n/rho),'final host eta does not use same native number/density')
   observed=d['obs']['HELPER_OUT',c,1,k,0][6];expected=(3.*q*rho/(4.*math.pi*1000.*n))**(1./3.)
   rel=abs(observed-expected)/expected;require(rel<1.e-6,'actual native radius is not final mean-volume radius');max_relative=max(max_relative,rel)
 return {'final_scaled_state_and_radius_exact_comparisons':joins,'final_same_density_eta_and_radius_layers':24,'active_layers':18,'padding_layers':6,'mean_volume_radius_max_relative_difference':max_relative}

def verify():
 manifest=json.loads((B/'manifest.json').read_text());require(manifest['production_accepted'] is False,'false physical approval')
 actual={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts};require(actual==set(manifest['files']),'sealed file roster differs')
 for name,row in manifest['files'].items():
  p=B/name;require(not p.is_symlink() and len(p.read_bytes())==row['bytes'] and sha(p.read_bytes())==row['sha256'],'sealed file changed '+name)
 test=load(ROOT/'WRF/test/rrtmgp/test_udm_partial_population.py','population_verify');identity=json.loads((B/'identity.json').read_text())
 for name,digest in identity['source_files'].items():require(sha((ROOT/name).read_bytes())==digest,'current source/fixture differs '+name)
 receipt=json.loads((B/'saved/receipt.json').read_text());raw=(ROOT/'WRF/phys/module_mp_udm.F').read_bytes();require(sha(raw)==receipt['production_source_sha256'],'production binding')
 research,patches=test.snapshot(raw);require(research==read('saved/research.F.gz') and raw==read('saved/production.F.gz') and patches==receipt['patches'],'research transformation is not exact current source')
 require(read('saved/fixture.f90.gz')==test.fixture((ROOT/'WRF/test/rrtmgp/test_udm_partial_activation.f90').read_bytes()),'actual input generator differs')
 require(sha(read('saved/runner_script.py.gz'))==receipt['runner_script_sha256']==sha((ROOT/'WRF/test/rrtmgp/test_udm_partial_population.py').read_bytes()),'actual runner binding')
 result={}
 for opt in ('O0','O2'):
  data=datasets(receipt,opt);computed=test.analyze(data);require(computed==receipt['results'][opt],'declared process decisions differ');result[opt]=final_joins(data)
 require(result['O0']==result['O2'] and receipt['results']['O0']==receipt['results']['O2'],'optimization result differs')
 decision=json.loads((B/'decision.json').read_text());require(decision['candidate_adoption']=='ADOPT_SCOPED_RESEARCH_FORMULATION' and decision['production_integration']=='NOT_PERFORMED' and decision['production_accepted'] is False,'candidate silently promoted')
 publisher=json.loads((B/'publisher/binding.json').read_text())
 for row in publisher['files']:
  filename=Path(row['file']).name;band='lw' if '-lw-' in filename else 'sw';j=json.loads((B/f'publisher/udm37-population-{band}-publisher.json').read_text());data=base64.b64decode(j['content']);current=(ROOT/row['file']).read_bytes()
  require(data==current and sha(data)==row['sha256'],'fixed LUT differs from actual publisher bytes');require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==j['sha']==row['blob'],'publisher blob differs')
 require(json.loads((B/'closure-conditions.json').read_text())==json.loads((ROOT/'validation/rrtmgp37/dry-number-grid-v1/closure-conditions.json').read_text()),'seven original closure conditions changed')
 return {'status':'PASS_SCOPED_ACTUAL_PARTIAL_POPULATION_CANDIDATE','actual_UDM_calls':120,'manufactured_initial_states':12,'CF':[1.,.5,.25],'dry_densities':[.7,1.1],'CF1_original_native_bitwise':True,'local_warm_rates_invariant':True,'grid_warm_rates_and_melt_increment_area_scaled':True,'final_joins':result['O0'],'publisher_LUT_bytes_equal':True,'production_source_changed':False,'production_accepted':False,'physical_gate_closed':False,'CI_new_solver_runs_in_this_replay':0}
if __name__=='__main__':print(json.dumps(verify()))
