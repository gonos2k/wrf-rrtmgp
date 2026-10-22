#!/usr/bin/env python3
"""Pinned saved replay of this small closeout; runs no compiler or model."""
from pathlib import Path
import argparse,gzip,hashlib,importlib.util,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2]
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('boundary_closeout_analysis',P/'analyze_saved.py')
H=load('closeout_historical_sources',P.parent/'historical-source/binding.py')
def sha(b):return hashlib.sha256(b).hexdigest()
def data():
 identity=json.loads((P/'identity.json').read_text());compressed=(P/'saved/evidence.tar.gz').read_bytes();A.require(sha(compressed)==identity['archive']['sha256'],'evidence archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(compressed)),mode='r:') as tar:
  A.require(set(tar.getnames())==set(identity['files']),'unindexed evidence');saved={n:tar.extractfile(n).read() for n in identity['files']}
 for n,row in identity['files'].items():A.require(len(saved[n])==row['bytes'] and sha(saved[n])==row['sha256'],'evidence payload '+n)
 root=H.HistoricalRoot(R,identity['current_sources'])
 for n,row in identity['current_sources'].items():A.require(sha((root/n).read_bytes())==row['sha256'],'historical source '+n)
 instrument=load('boundary_closeout_instrument',P/'instrument.py');bc,solve=instrument.instrument((root/'WRF/share/module_bc.F').read_text(),(root/'WRF/dyn_em/solve_em.F').read_text())
 A.require(saved['build/module_bc_probe.F']==bc.encode() and saved['build/solve_em_probe.F']==solve.encode(),'private diagnostic changes exceed exact IO-only transformation')
 for n in ['probe.f90','common_halo.f90']:A.require(saved[('build/' if n=='probe.f90' else 'halo/')+n]==(P/n).read_bytes(),'compiled diagnostic source differs '+n)
 build=json.loads(saved['build/receipt.json']);host=json.loads(saved['host/receipt.json']);halo=json.loads(saved['halo/receipt.json'])
 A.require(host['executable']['sha256']==build['executable']['sha256'],'host executable receipt')
 A.require(build['base_library']['sha256']==halo['library']['sha256'],'native fixture uses another public library')
 old=load('retained_PR189',P.parent/'restart-first-step/verify_saved.py').data();baseline=json.loads(old['build/receipt.json']);branch=json.loads(old['nonzero/receipt.json'])
 # PR189's fixed archive is the actual base. Its executable pins the original
 # nonzero branch which is reused as the observer-off reference here.
 A.require(branch['executable']['sha256']==baseline['executable']['sha256'],'original nonzero branch executable binding')
 A.require(build['base_library']['path'] in baseline['commands'][-1]['argv'],'base library is not the retained fixed link input')
 for name in ['checkpoint','forcing','namelist']:A.require(host[name]['sha256']==branch[name]['sha256'],'bounded host changed original '+name)
 for path,pin in build['public_sources'].items():A.require(sha((root/path).read_bytes())==pin['sha256'],'observed public source differs')
 return saved

def main():
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();result=A.analyze(data().__getitem__,json.loads((P/'plan.json').read_text()))
 if args.write:(P/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 else:A.require(result==json.loads((P/'result.json').read_text()),'result detached from saved operands')
 print(json.dumps({'status':result['status'],'positive_actual_host_relaxation_calls':len(result['actual_positive_host_relaxation_calls']),'native_final_value_checks':len(result['actual_native_final_values']),'observer_pairs':result['observer_noninterference_array_pairs'],'common_halo_cases':result['common_native_halo_policy_tile_cases'],'current_runtime_source_matches':all(sha((R/n).read_bytes())==p['sha256'] for n,p in json.loads((P/'identity.json').read_text())['current_sources'].items()),'source_scope':'historical_PR190_snapshot','production_accepted':False,'new_model_runs':0}))
if __name__=='__main__':main()
