"""Replay raw actual UDM and decoded NetCDF terminal arrays; no fresh solver."""
import gzip,hashlib,importlib.util,json,math,struct
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def sha(x):return hashlib.sha256(x).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def read(n):return gzip.decompress((B/n).read_bytes())
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def exchange(data,test):
 checks=0
 for key,v in data.items():
  if key[0]!='EXCHANGE':continue
  _,c,i,k,loop=key;local=data['WARM_LOCAL',c,i,k,loop];f=v[2]
  transfer=test.f32(local[2]*f);expected=test.f32(min(test.f32(local[0]+transfer),test.f32(2.e10)))
  require(v[0]==expected and v[1]==0.,'rain return is not grid mean before CCN cap')
  require(test.near(v[3]+v[4],transfer),'returned/clipped accounting differs')
  checks+=1
 return checks

def verify():
 manifest=json.loads((B/'manifest.json').read_text());require(manifest['production_accepted'] is False,'false physical approval')
 actual={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts};require(actual==set(manifest['files']),'sealed roster differs')
 for n,row in manifest['files'].items():
  p=B/n;require(not p.is_symlink() and sha(p.read_bytes())==row['sha256'] and len(p.read_bytes())==row['bytes'],'sealed file changed '+n)
 identity=json.loads((B/'identity.json').read_text());require(identity['population_policy']==identity['number_policy']==1 and identity['physical_approval'] is False,'wrong/approved policy')
 history=load(ROOT/'validation/rrtmgp37/historical-source/binding.py','history_warm173')
 for n,digest in identity['source_files'].items():require(sha(history.historical_bytes(ROOT,n,digest))==digest,'retained integrated source differs '+n)
 test=load(ROOT/'WRF/test/rrtmgp/test_udm_population_integration.py','integrated_test');r=json.loads((B/'saved/module/receipt.json').read_text())
 raw=history.historical_bytes(ROOT,'WRF/phys/module_mp_udm.F',r['source_sha256']);require(raw==read('saved/module/production.F.gz') and sha(raw)==r['source_sha256'],'compiled source differs')
 require(test.observed(raw)==read('saved/module/observed.F.gz'),'observer cannot reproduce compiled source')
 require(test.fixture(ROOT/'WRF')==read('saved/module/fixture.f90.gz'),'actual manufactured input generator differs')
 require(sha(read('saved/module/runner.py.gz'))==r['script_sha256']==identity['source_files']['WRF/test/rrtmgp/test_udm_population_integration.py'],'actual script differs')
 results={};exchange_checks=0;scope_rejections=0
 for opt in ('O0','O2'):
  data={};production=None
  for n,p in enumerate(r['processes'],1):
   require(p['status']=='TERMINAL' and not p['timed_out'],'incomplete model process')
   if not p['kind'].startswith('UDM_') or '/'+opt+'/' not in p['argv'][0]:continue
   text=read(f'saved/module/command-{n:02d}.stdout.gz').decode()
   if p['kind'].startswith('UDM_expected_reject_'):
    msg='CF0 condensate unsupported' if p['kind'].endswith('cfzero') else 'warm-only column required'
    require(p['actual_returncode']!=0 and msg in text and 'RETURN ' not in text,'scope refusal differs');scope_rejections+=1;continue
   require(p['actual_returncode']==0 and text.count('EXCHANGE_PROBE')==8 and 'REPRESENTATION_PROBE_PASS' in text,'actual successful process/probes missing')
   parsed=test.parse(text)
   for line in text.splitlines():
    if not line.startswith('EXCHANGE_PROBE'):continue
    w=line.split();a,b=int(w[1]),int(w[2]);f,ccn,nr,returned,clipped=map(float,w[3:]);old=test.f32(2.e8 if b==1 else test.f32(2.e10)-4096.)
    expected=test.f32(min(test.f32(old+test.f32(test.f32(f)*10000.)),test.f32(2.e10)))
    require(ccn==expected and nr==0. and test.near(returned+clipped,test.f32(test.f32(f)*10000.)),'actual cap/exchange probe differs')
   if p['kind'].startswith('UDM_production_'):production=parsed;continue
   _,_,scenario,mode,enabled=p['kind'].split('_');data[scenario,mode,enabled]=parsed
  require(len(data)==9 and production is not None,'actual successful execution roster differs')
  results[opt]=test.analyze(data);require(results[opt]==r['results'][opt],'raw UDM replay differs')
  for c in (1,4):require(production[1][c]==data['warm','candidate','off'][1][c],'CF1 actual diagnostic reduction differs')
  for key,value in data.items():
   if key[1:] == ('candidate','on'):exchange_checks+=exchange(value[0],test)
 require(results['O0']==results['O2'] and scope_rejections==4 and r['actual_UDM_calls']==120,'scope/optimization count differs')
 host=json.loads((B/'saved/host/receipt.json').read_text());require(host['executable']==identity['WRF_executable'] and host['status']=='PASS_SCOPED_ACTUAL_WARM_HOST_INTEGRATION','host identity differs')
 for n,digest in host['source_files'].items():require(identity['source_files']['WRF/'+n]==digest,'host/module source differs')
 for n,p in enumerate(host['processes'],1):
  require(p['status']=='TERMINAL' and not p['timed_out'],'host not reaped')
  text=read(f'saved/host/command-{n:02d}.stdout.gz').decode()
  if 'reject' in p['kind']:
   msg='UDM population differs' if p['kind'].endswith('population') else 'warm-only column required'
   require(msg in text and 'SUCCESS COMPLETE WRF' not in text,'host refusal missing')
  else:require(p['actual_returncode']==0 and 'SUCCESS COMPLETE WRF' in text and 'FATAL CALLED' not in text,'host success missing')
 packets={}
 for case in ('full20','restart'):
  index=json.loads((B/f'saved/host/{case}.terminal.json').read_text());raw=read(f'saved/host/{case}.terminal.bin.gz');require(index['population_policy']==1 and sha(raw)==index['payload_sha256'],'wrong terminal representation')
  packet={};offset=0
  for row in index['records']:
   n=row['variable'];require(n not in packet and row['offset']==offset,'terminal roster/offset');part=raw[offset:offset+row['bytes']];require(len(part)==row['bytes'] and sha(part)==row['sha256'],'terminal array differs');packet[n]=part;offset+=row['bytes']
  require(offset==len(raw),'terminal payload extent');packets[case]=packet
 require(packets['full20']==packets['restart'] and len(packets['full20'])==host['terminal_variable_comparisons']==211,'same-policy restart differs')
 require(json.loads((B/'closure-conditions.json').read_text())==json.loads((ROOT/'validation/rrtmgp37/dry-number-grid-v1/closure-conditions.json').read_text()),'seven closure conditions changed')
 psd=json.loads((B/'final-liquid-moments.json').read_text());require(psd['PHY_SIZE']=='OPEN' and psd['fixed_LUT_generation_PSD_certified'] is False and psd['production_radius_changed'] is False,'false optical approval')
 for row in psd['records']:
  require(math.isclose(row['M3_grid']/row['M2_monodisperse'],row['reff_monodisperse_m'],rel_tol=1.e-15) and row['reff_two_radius_m']>row['reff_monodisperse_m'],'PSD hypotheses do not separate M2')
 return {'status':'PASS_SCOPED_ACTUAL_WARM_POPULATION_INTEGRATION','actual_UDM_calls':120,'expected_module_scope_refusals':scope_rejections,'grid_CCN_exchange_records':exchange_checks,'actual_WRF_processes':5,'continuous_seconds':20,'checkpoint_resume_seconds':10,'terminal_arrays_bitwise_equal':211,'fresh_model_runs_in_replay':0,'final_M2_identified':False,'physical_gate_closed':False,'source_scope':'historical_PR173_snapshot','current_policy2_certified':False,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
