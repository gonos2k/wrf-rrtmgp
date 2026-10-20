#!/usr/bin/env python3
"""Replay retained evidence; this does not rerun Mie, RTE or WRF."""
from pathlib import Path
import gzip,json,hashlib,importlib.util
from functools import lru_cache
P=Path(__file__).resolve().parent;ROOT=P.parents[2]
def readers():
 refs=json.loads((P/'prior-evidence.json').read_text())
 @lru_cache(None)
 def read(n):return gzip.decompress((P/'saved'/(n+'.gz')).read_bytes())
 @lru_cache(None)
 def prior(n):return gzip.decompress((ROOT/refs[n]['path']).read_bytes())
 return read,prior

def verify():
 sealed=json.loads((P/'manifest.json').read_text())['files']
 roster={str(p.relative_to(P)) for p in (P/'saved').rglob('*') if p.is_file()}
 if roster!={n for n in sealed if n.startswith('saved/')}:raise ValueError('retained artifact roster differs')
 for n,v in sealed.items():
  if hashlib.sha256((P/n).read_bytes()).hexdigest()!=v:raise ValueError('sealed evidence changed '+n)
 refs=json.loads((P/'prior-evidence.json').read_text())
 for n,v in refs.items():
  path=(ROOT/v['path']).resolve()
  if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=v['sha256']:raise ValueError('prior evidence changed '+n)
 read,prior=readers()
 for n in ['plan.json','run_reference.py','check_definitions.py','cross_quadratures.py','propagate_reference.py']:
  if (P/n).read_bytes()!=read('executed/'+n):raise ValueError('executed source differs '+n)
 source_sha=hashlib.sha256(read('executed/run_reference.py')).hexdigest()
 if json.loads(read('mie/process-observation.json'))['source_sha256']!=source_sha or json.loads(read('mie/definition-controls.json'))['source_sha256']!=source_sha:raise ValueError('observed execution/control source differs')
 ident=json.loads((P/'identity.json').read_text());ref=json.loads(read('mie/result.json'))
 if ident['external_unmodified_source_sha256']!=ref['source_pin'] or ident['external_executed_source_sha256']!=ref['compiled_external_sha256']:raise ValueError('external source binding')
 expected={'optics.py':'9ca85be38321228ee36a50d726015b3e4145af86a68c069a5376d1bb754c02ea','spec_util.py':'199e2b703ee9ea147d71e7e1b40cb3e04025299b2f7272930e7cf2135f3c9aa1'}
 if ref['source_pin']!=expected or ref['source_pin']['optics.py']!=ref['compiled_external_sha256']['optics.py']:raise ValueError('pinned unchanged companion integration source')
 old=json.loads(prior('old_mie'))
 for r in ref['records']:
  original=next(x for x in old['records'] if (x['phase'],x['band'],x['reff_um'])==(r['phase'],r['band'],r['reff_um']))
  if r['original_PR183']!=original['grids'][-1]:raise ValueError('old failure/result retagged')
 receipt=json.loads(read('rte-journal/receipt.json'))
 if receipt['executable']!=ident['reused_executable']:raise ValueError('executed binary differs')
 for row in receipt['runs']:
  name=row['case']+'_'+row['mode']+'_'+row['grid'];ph=row['case'].rsplit('_',1)[1]
  for field,n in [('input','input.dat'),('optics','optics.dat'),('result',ph+'.result')]:
   if hashlib.sha256(read(name+'/'+n)).hexdigest()!=row[field]['sha256']:raise ValueError('execution receipt artifact differs '+name+'/'+n)
 s=importlib.util.spec_from_file_location('matched_analysis',P/'analyze_saved.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
 result=a.analyze(read,prior,json.loads((P/'plan.json').read_text()))
 if result!=json.loads((P/'result.json').read_text()):raise ValueError('reference analysis replay differs')
 same=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==sha for n,sha in {**ident['runtime_source_files'],**ident['coefficient_files']}.items())
 return {'status':result['status'],'qualified_radius_band_entries':result['coefficient_scope']['qualified_total'],'primary_radius_band_entries':result['coefficient_scope']['qualified_primary'],'transport_axis_screen_passed':result['transport']['axis_numerical_screen_passed'],'current_runtime_source_matches':same,'retained_new_RTE_processes':18,'new_model_runs':0,'physical_approval':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
