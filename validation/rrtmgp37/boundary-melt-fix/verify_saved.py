"""Reconstruct saved real UDM diagnostics and WRF scope outcomes; no solver."""
import copy,gzip,hashlib,importlib.util,json,struct
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def read(name):return gzip.decompress((B/name).read_bytes())
def datasets(receipt,opt):
 partial=load(ROOT/'WRF/test/rrtmgp/test_udm_partial_activation.py','partial');partial.STAGES=('MELT_PRE','MELT_POST');data={}
 for variant in ('fixed','observed','old_order'):
  for policy in (0,1):
   kind='UDM_'+variant+'_policy'+str(policy)
   hits=[(n,c) for n,c in enumerate(receipt['processes'],1) if c['kind']==kind and '/'+opt+'/' in c['argv'][0]]
   require(len(hits)==1,'actual UDM command roster');n,c=hits[0]
   require(c['actual_returncode']==0 and not c['timed_out'] and c['status']=='TERMINAL','UDM execution incomplete')
   data[variant,policy]=partial.parse(read(f'saved/module/command-{n:02d}.stdout.gz').decode())
 return data

def verify():
 m=json.loads((B/'manifest.json').read_text());require(m['production_accepted'] is False,'false physical approval')
 actual={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
 require(actual==set(m['files']),'saved file roster differs')
 for name,r in m['files'].items():
  p=B/name;require(not p.is_symlink() and len(p.read_bytes())==r['bytes'] and sha(p.read_bytes())==r['sha256'],'sealed file changed '+name)
 identity=json.loads((B/'identity.json').read_text())
 history=load(ROOT/'validation/rrtmgp37/historical-source/binding.py','historical_boundary_melt')
 for name,r in identity['source_files'].items():
  require(sha(history.historical_bytes(ROOT,name,r))==r,'retained fix source differs '+name)
 require(identity['production_accepted'] is False,'identity physical approval')
 module=json.loads((B/'saved/module/receipt.json').read_text());melt=load(ROOT/'WRF/test/rrtmgp/test_udm_ice_melt_number.py','melt')
 raw=history.historical_bytes(ROOT,'WRF/phys/module_mp_udm.F',module['source_sha256']);require(sha(raw)==module['source_sha256'],'module source binding')
 require(read('saved/module/fixed.F.gz')==raw,'compiled fixed source differs')
 require(read('saved/module/observed.F.gz')==melt.observe(raw,True),'compiled observer source differs')
 old=read('saved/module/old_order.F.gz');old=old.decode();import re
 old=re.sub(r'! MELT_TEST_BEGIN\n.*?! MELT_TEST_END\n','',old,flags=re.S).encode()
 history=load(ROOT/'validation/rrtmgp37/historical-source/binding.py','history')
 require(old==history.historical_bytes(ROOT,'WRF/phys/module_mp_udm.F',identity['pre_fix_mp_sha256']),'old-order control differs from PR170')
 for opt in ('O0','O2'):
  rows=melt.analyze(datasets(module,opt));require(rows==module['results'][opt]['rows'],'stored melting rows differ')
 require(module['results']['O0']==module['results']['O2'] and module['UDM_calls']==48,'optimization or execution count')
 boundary=json.loads((B/'saved/boundary/receipt.json').read_text());require(boundary['input_source_sha256']==sha(history.historical_bytes(ROOT,'WRF/share/input_wrf.F',boundary['input_source_sha256'])),'boundary/current source mismatch')
 source=history.historical_bytes(ROOT,'WRF/share/input_wrf.F',boundary['input_source_sha256']).decode();start=source.index('        IF (config_flags%udm_number_policy == 1) THEN');end=source.index('        ENDIF',start)+len('        ENDIF');guard=source[start:end]
 require(sha(guard.encode())==boundary['guard_block_sha256'] and guard in read('saved/boundary/input_guard.f90.gz').decode(),'compiled guard is not exact current input block')
 require(boundary['executable']['sha256']==identity['wrf_executable']['sha256'],'WRF executable binding')
 require(len(boundary['probe'])==16 and len(boundary['WRF_runs'])==3,'scope execution count')
 for n,c in enumerate(boundary['processes'],1):
  require(c['status']=='TERMINAL' and c['actual_returncode']==0 and not c['timed_out'],'scope process incomplete')
  s=read(f'saved/boundary/command-{n:02d}.stdout.gz').decode(errors='replace')
  if c['kind'].startswith('guard_'):
   rejected=1<=int(c['kind'].split('_')[-1])<=6
   require(('FATAL CALLED' in s and 'GUARD_ACCEPTED' not in s) if rejected else ('GUARD_ACCEPTED' in s and 'FATAL CALLED' not in s),'guard outcomes differ')
  if c['kind'].startswith('WRF_'):
   if c['kind']=='WRF_specified_policy1':require('specified/nested boundaries unsupported' in s and 'FATAL CALLED' in s and 'SUCCESS COMPLETE WRF' not in s,'specified boundary not refused')
   else:require('SUCCESS COMPLETE WRF' in s and 'FATAL CALLED' not in s,'periodic runtime failed')
 closure=json.loads((B/'closure-conditions.json').read_text());require(closure==json.loads((ROOT/'validation/rrtmgp37/dry-number-grid-v1/closure-conditions.json').read_text()),'seven original conditions changed')
 return {'status':'PASS_SCOPED_BOUNDARY_AND_MELT_FIX','actual_full_UDM_calls':48,'actual_WRF_periodic_successes':2,'actual_WRF_specified_refusals':1,'exact_guard_probe_executions':16,'mass_and_latent_heat_block_preserved':True,'source_scope':'historical_PR171_snapshot','current_fix_certified':False,'retained_test_configuration':'PR171_snapshot','CI_fresh_model_runs':0,'physical_gate_closed':False,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
