#!/usr/bin/env python3
from pathlib import Path
import gzip,tarfile,io,json,hashlib,importlib.util,argparse
P=Path(__file__).resolve().parent;R=P.parents[2]
def load():
 spec=importlib.util.spec_from_file_location('specified_analysis',P/'analyze_saved.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
A=load()
def data():
 identity=json.loads((P/'identity.json').read_text());out={};archives={}
 for n,row in identity['files'].items():
  if 'gzip' in row:b=gzip.decompress((P/row['gzip']).read_bytes())
  else:
   path=row['archive']
   if path not in archives:archives[path]=tarfile.open(fileobj=io.BytesIO(gzip.decompress((P/path).read_bytes())),mode='r:')
   b=archives[path].extractfile(row['member']).read()
  A.require(len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],'evidence hash '+n);out[n]=b
 spec=importlib.util.spec_from_file_location('specified_historical_binding',P.parent/'historical-source/binding.py');history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)
 for n,row in identity['current_sources'].items():A.require(hashlib.sha256(history.historical_bytes(R,n,row['sha256'])).hexdigest()==row['sha256'],'historical source '+n)
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');a=p.parse_args();saved=data();result=A.analyze(saved.__getitem__,json.loads((P/'plan.json').read_text()))
 if a.write:(P/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 else:A.require(result==json.loads((P/'result.json').read_text()),'summary differs from actual evidence')
 print(json.dumps({'status':result['status'],'current_runtime_source_matches':all(hashlib.sha256((R/n).read_bytes()).hexdigest()==row['sha256'] for n,row in json.loads((P/'identity.json').read_text())['current_sources'].items()),'source_scope':'historical_PR188_snapshot','full_host_restart_bitwise_criterion_passed':False,'new_model_runs':0,'production_accepted':False}))
