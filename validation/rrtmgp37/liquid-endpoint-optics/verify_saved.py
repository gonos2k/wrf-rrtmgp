#!/usr/bin/env python3
"""Verify the retained diagnostic, not new Mie/WRF/RTE executions."""
from functools import lru_cache
from pathlib import Path
import gzip,hashlib,importlib.util,json
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def readers():
 refs=json.loads((B/'prior-evidence.json').read_text())
 @lru_cache(None)
 def read(n):return gzip.decompress((B/'saved'/(n+'.gz')).read_bytes())
 @lru_cache(None)
 def prior(n):return gzip.decompress((ROOT/refs[n]['path']).read_bytes())
 return read,prior

def verify():
 manifest=json.loads((B/'manifest.json').read_text())['files']
 roster={str(p.relative_to(B)) for p in (B/'saved').rglob('*') if p.is_file()}
 if roster!={n for n in manifest if n.startswith('saved/')}:raise ValueError('saved roster differs')
 for n,digest in manifest.items():
  if hashlib.sha256((B/n).read_bytes()).hexdigest()!=digest:raise ValueError('sealed evidence differs '+n)
 refs=json.loads((B/'prior-evidence.json').read_text())
 for n,row in refs.items():
  p=(ROOT/row['path']).resolve()
  if not p.is_relative_to(ROOT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('prior evidence differs '+n)
 read,prior=readers()
 # Verify that the isolated adapter differs only by its module name and four
 # liquid calls before existing precipitation, sampling and delta scaling.
 expected=read('build/base_adapter.F').decode().replace('MODULE module_ra_rrtmgp','MODULE module_endpoint_adapter')
 expected=expected.replace('  USE mo_rte_kind, ONLY: wp, i8','  USE endpoint_optics, ONLY: endpoint_lw,endpoint_sw\n  USE mo_rte_kind, ONLY: wp, i8')
 for ph in ['lw','sw']:
  for path in ['lwp','uniform_lwp']:
   ice='REAL(iwp,wp)' if path=='lwp' else 'zero';label='NATIVE' if path=='lwp' else 'UNIFORM'
   old=f'      CALL require(cloud_{ph}%cloud_optics(REAL({path},wp),{ice},rl,di,clouds))'
   if expected.count(old)!=1:raise ValueError('hook insertion count')
   expected=expected.replace(old,old+f"\n      CALL endpoint_{ph}(REAL({path},wp),{ice},clouds,'{label}')")
 if read('build/module_endpoint_adapter.F').decode()!=expected:raise ValueError('diagnostic adapter modifies unrelated execution')
 for n in ('plan.json','run_mie.py','run_columns.py','build_diagnostic.py','endpoint_optics.f90'):
  if (B/n).read_bytes()!=read('executed/'+n):raise ValueError('executed source differs '+n)
 spec=importlib.util.spec_from_file_location('endpoint_analysis',B/'analyze_saved.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
 result=a.analyze(read,prior,json.loads((B/'plan.json').read_text()))
 if result!=json.loads((B/'result.json').read_text()):raise ValueError('analysis replay differs')
 ident=json.loads((B/'identity.json').read_text())
 for key,name in [('base_source','build/base_adapter.F'),('diagnostic_adapter','build/module_endpoint_adapter.F'),('caller','build/caller.f90'),('hook_source','executed/endpoint_optics.f90')]:
  if hashlib.sha256(read(name)).hexdigest()!=ident['diagnostic_build'][key]['sha256']:raise ValueError('build identity differs '+key)
 receipt=json.loads(read('rte-journal/receipt.json'))
 if len(receipt['runs'])!=15 or len(receipt['commands'])!=15:raise ValueError('qualified execution count')
 for row in receipt['runs']:
  name=row['case']+'_'+row['mode'];phase=row['case'].rsplit('_',1)[1]
  for key,file in [('input','input.dat'),('optics','optics.dat'),('result',phase+'.result')]:
   if hashlib.sha256(read(name+'/'+file)).hexdigest()!=row[key]['sha256']:raise ValueError('executed artifact differs '+name+'/'+file)

 same=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==sha for n,sha in ident['source_files'].items())
 return {'status':result['status'],'current_runtime_source_matches':same,'new_model_runs':0,'numerical':result['numerical'],'decisions':result['decisions'],'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
