from pathlib import Path
import argparse,gzip,hashlib,importlib.util,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2]
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load('kfeta_analysis',P/'analyze.py');I=load('kfeta_instrument',P/'instrument.py');V=load('kfeta_readonly',P.parent/'real-case-budget/verify_saved.py')
require=A.require
def sha(b):return hashlib.sha256(b).hexdigest()
def data():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'],'archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  require(set(t.getnames())==set(ident['files']),'archive roster');d={n:t.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(d[n])==p['sha256'] and len(d[n])==p['bytes'],'payload '+n)
 for n,p in ident['current_sources'].items():require(sha((R/n).read_bytes())==p['sha256'],'current source '+n)
 require(I.transform(R).encode()==d['probe/solve_em.F'],'generated observer')
 V.readonly((R/'WRF/dyn_em/solve_em.F').read_text(),d['probe/solve_em.F'].decode())
 require(d['probe/probe.f90']==(P/'probe.f90').read_bytes(),'compiled observer helper')
 native=json.loads(d['native/receipt.json']);probe=json.loads(d['probe/receipt.json']);host=json.loads(d['host/receipt.json'])
 require(native['source']['sha256']==sha((R/'WRF/phys/module_physics_addtendc.F').read_bytes()),'compiled production source')
 require(native['fixture']['sha256']==sha((P/'native.f90').read_bytes()),'native fixture source')
 require(probe['private_source']['sha256']==sha(d['probe/solve_em.F']),'compiled diagnostic source')
 require(probe['base_library']['sha256']==native['library']['sha256'],'observer library differs')
 for arm,b in [('public',native),('observed',probe)]:
  require(host['arms'][arm]['executable']['sha256']==b['executable']['sha256'],'host executable')
 require(host['arms']['public']['namelist']['sha256']==host['arms']['observed']['namelist']['sha256'],'observer namelist changed')
 for c in native['commands']+probe['commands']+host['commands']:require(c['actual_returncode']==0 and not c['timed_out'],'qualified execution failed')
 for n in [1,2]:require('SUCCESS COMPLETE WRF' in d[f'host/command-0{n}.stdout'].decode() and 'FATAL CALLED' not in d[f'host/command-0{n}.stdout'].decode(),'host not complete')
 old=load('kfeta_checkpoint_binding',P.parent/'restart-first-step/verify_saved.py').data();oldreceipt=json.loads(old['nonzero/receipt.json'])
 for arm in ['public','observed']:
  require(host['arms'][arm]['checkpoint']['sha256']==oldreceipt['checkpoint']['sha256'],'checkpoint changed')
  require(host['arms'][arm]['forcing']['sha256']==oldreceipt['original_forcing']['sha256'],'original real forcing changed')
 return d
def main():
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();r=A.analyze(data())
 if args.write:(P/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 else:require(r==json.loads((P/'result.json').read_text()),'result differs from actual evidence')
 print(json.dumps(r));print('current_runtime_source_matches=true new_model_runs=0')
if __name__=='__main__':main()
