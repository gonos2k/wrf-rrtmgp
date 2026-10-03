#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,struct,math
import numpy as np
P=Path(__file__).resolve().parent
SIZES=[32*48,32*48,32*47,32*48,32*48,32*47]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['batch32','scalar32']);ap.add_argument('actual');ap.add_argument('wp');a=ap.parse_args()
 actual=Path(a.actual);expected=P/'fixtures-v2'/f'expected-{a.mode}.bin'
 if not actual.exists() or not expected.exists():raise SystemExit('missing actual or pinned expected')
 if actual.stat().st_size!=sum(SIZES)*4:raise SystemExit(f'wrong output bytes {actual.stat().st_size}')
 raw=actual.read_bytes();exp=expected.read_bytes();
 if not np.isfinite(np.frombuffer(raw,dtype='>f4')).all():raise SystemExit('nonfinite float32 output')
 if raw!=exp:raise SystemExit('f32 adapter outputs differ from corresponding original WRF rows')
 labels={};lines=Path(a.wp).read_text().splitlines();i=0
 while i<len(lines):
  h=lines[i].split();i+=1
  if len(h) not in (3,4):raise SystemExit(f'bad WP section header: {h}')
  name=h[0];shape=tuple(map(int,h[1:]));n=np.prod(shape,dtype=int)
  if name in labels:raise SystemExit(f'duplicate section {name}')
  vals=lines[i:i+n];i+=n
  if len(vals)!=n or any(len(x)!=16 for x in vals):raise SystemExit(f'bad values in {name}')
  labels[name]={'shape':shape,'count':int(n),'sha256_hex_records':hashlib.sha256(('\n'.join(vals)+'\n').encode()).hexdigest()}
 required={'GAS_COL_DRY','GAS_TAU','SOURCE_LAY','SOURCE_LEV','SOURCE_SFC','CLEAR_FU','CLEAR_FD','CLEAR_HEAT','TOTAL_TAU','ALL_FU','ALL_FD','ALL_HEAT'}
 if set(labels)!=required:raise SystemExit(f'WP sections mismatch {set(labels)^required}')
 expected_shapes={'GAS_COL_DRY':(32,47),'GAS_TAU':(32,47,128),'SOURCE_LAY':(32,47,128),'SOURCE_LEV':(32,48,128),'SOURCE_SFC':(32,128),'CLEAR_FU':(32,48),'CLEAR_FD':(32,48),'CLEAR_HEAT':(32,47),'TOTAL_TAU':(32,47,128),'ALL_FU':(32,48),'ALL_FD':(32,48),'ALL_HEAT':(32,47)}
 for n,s in expected_shapes.items():
  if labels[n]['shape']!=s:raise SystemExit(f'{n} shape {labels[n]["shape"]}, expected {s}')
 result={'status':'PASS','mode':a.mode,'f32_exact_match':True,'actual_sha256':sha(actual),'expected_sha256':sha(expected),'wp_sha256':sha(Path(a.wp)),'wp_sections':labels}
 out=Path(a.actual).parent/'validation.json';out.write_text(json.dumps(result,indent=2)+'\n');print(out)
if __name__=='__main__':main()
