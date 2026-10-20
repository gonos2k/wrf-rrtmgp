#!/usr/bin/env python3
from pathlib import Path
import gzip,hashlib,json,argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze_saved import analyze,require
P=Path(__file__).resolve().parent;R=P.parents[2]
def verify(check=True):
 identity=json.loads((P/'identity.json').read_text());plan=json.loads((P/'plan.json').read_text());saved={}
 for key,v in identity['saved'].items():
  b=gzip.decompress((P/v['gzip']).read_bytes());require(len(b)==v['size_bytes'] and hashlib.sha256(b).hexdigest()==v['sha256'],'saved evidence hash '+key);saved[key]=b
 for key,v in identity['runtime_sources'].items():require(hashlib.sha256((R/key).read_bytes()).hexdigest()==v['sha256'],'runtime source changed '+key)
 result=analyze(saved.__getitem__,plan)
 if check:require(result==json.loads((P/'result.json').read_text()),'summary differs from saved evidence')
 return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--write',action='store_true');q=a.parse_args();r=verify(not q.write)
 if q.write:(P/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'status':r['status'],'new_model_runs':0,'production_accepted':False}))
