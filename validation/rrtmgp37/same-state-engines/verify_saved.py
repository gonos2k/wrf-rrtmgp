#!/usr/bin/env python3
"""Replay retained paired diagnostic evidence, not new engine executions."""
from pathlib import Path
from functools import lru_cache
import gzip,json,hashlib,importlib.util
P=Path(__file__).resolve().parent;R=P.parents[2]
def load():
 s=importlib.util.spec_from_file_location('same_state_analysis',P/'analyze_saved.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
@lru_cache(None)
def read(n):return gzip.decompress((P/'saved'/(n+'.gz')).read_bytes())
def verify():
 manifest=json.loads((P/'manifest.json').read_text())['files']
 roster={str(p.relative_to(P)) for p in (P/'saved').rglob('*') if p.is_file()}
 if roster!={n for n in manifest if n.startswith('saved/')}:raise ValueError('saved roster differs')
 for n,d in manifest.items():
  if hashlib.sha256((P/n).read_bytes()).hexdigest()!=d:raise ValueError('sealed evidence differs '+n)
 for n in ['plan.json','compare.f90','build.py','run.py']:
  if (P/n).read_bytes()!=read('executed/'+n):raise ValueError('executed caller/recipe differs '+n)
 plan=json.loads((P/'plan.json').read_text());receipt=json.loads(read('runtime/receipt.json'));ident=json.loads((P/'identity.json').read_text());build=json.loads(read('build/receipt.json'))
 if receipt['plan_sha256']!=hashlib.sha256(read('runtime/plan.json')).hexdigest() or json.loads(read('runtime/plan.json'))!=plan:raise ValueError('plan not bound before execution')
 if build!=ident['build'] or build['executable']!=receipt['executable']:raise ValueError('actual linked executable differs')
 if len(build['commands'])!=2 or any(c['actual_returncode']!=0 for c in build['commands']):raise ValueError('caller compile/link failure')
 if hashlib.sha256(read('executed/compare.f90')).hexdigest()!=build['caller']['sha256']:raise ValueError('compiled source differs')
 sources={}
 for ph,row in receipt['sources'].items():
  path=(R/row['path']).resolve()
  if not path.is_relative_to(R) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('retained source input differs')
  sources[ph]=gzip.decompress(path.read_bytes()).decode().splitlines()
 for row in receipt['runs']:
  n=row['name'];ph=row['phase'];ls=read(n+'/input.dat').decode().splitlines();lw=sources['lw'];sw=sources['sw'];source=lambda a,i:list(map(float,a[i].split()))
  if ls[0]!=f'{ph.upper()} 121 59 {row["seed"]}':raise ValueError('run selection differs')
  constants=source(lw,1);constants[3]=source(sw,1)[3]
  if list(map(float,ls[1].split()))!=constants:raise ValueError('surface/engine constants differ')
  expected=[source(lw,k) for k in range(2,14)];cf=[0.]*121;lwp=[0.]*121
  if row['arm']=='liquid':cf[29]=1.;lwp[29]=10.
  expected += [cf,lwp,[21.5]*121,source(lw,26),source(lw,29)]+[source(sw,k) for k in range(30,35)]
  if [list(map(float,l.split())) for l in ls[2:]]!=expected:raise ValueError('declared common atmospheric/cloud recipe differs')
  for key,file in [('input','input.dat'),('native4','native4.txt'),('result37',ph+'.result'),('snapshot','before.bin'),('export4','export4.txt')]:
   if hashlib.sha256(read(n+'/'+file)).hexdigest()!=row[key]['sha256']:raise ValueError('process receipt artifact differs '+n+'/'+file)
 a=load();result=a.analyze(read,plan)
 if result!=json.loads((P/'result.json').read_text()):raise ValueError('paired comparison replay differs')
 same=all(hashlib.sha256((R/n).read_bytes()).hexdigest()==d for n,d in {**ident['runtime_source_files'],**ident['coefficients']}.items())
 return {'status':result['status'],'current_runtime_source_matches':same,'actual_retained_paired_processes':6,'actual_retained_engine_calls':12,'max_dry_column_relative_difference':result['max_dry_gas_column_relative_difference'],'new_model_runs':0,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
