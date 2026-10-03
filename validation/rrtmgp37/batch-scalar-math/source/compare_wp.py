#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,math,struct
P=Path(__file__).resolve().parent
def parse(p):
 lines=Path(p).read_text().splitlines();o={};i=0
 while i<len(lines):
  h=lines[i].split();i+=1
  n=h[0];shape=tuple(map(int,h[1:]));count=math.prod(shape)
  vals=lines[i:i+count];i+=count
  if len(vals)!=count or n in o or any(len(v)!=16 for v in vals):raise ValueError(f'malformed {n}')
  o[n]=(shape,vals)
 if i!=len(lines):raise ValueError('extra records')
 return o
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('batch');ap.add_argument('scalar');ap.add_argument('--output',required=True);a=ap.parse_args()
 b=parse(a.batch);s=parse(a.scalar)
 if b.keys()!=s.keys():raise SystemExit('WP section labels differ')
 diffs={}
 for k in b:
  if b[k][0]!=s[k][0]:raise SystemExit(f'{k} dimensions differ')
  bf=[struct.unpack('>d',int(x,16).to_bytes(8,'big'))[0] for x in b[k][1]]
  sf=[struct.unpack('>d',int(x,16).to_bytes(8,'big'))[0] for x in s[k][1]]
  if not all(math.isfinite(x) for x in bf+sf):raise SystemExit(f'nonfinite WP value in {k}')
  ids=[i for i,(x,y) in enumerate(zip(b[k][1],s[k][1])) if x!=y]
  n=len(ids); first=ids[0] if ids else None
  diffs[k]={'shape':b[k][0],'differing_values':n,'total_values':len(b[k][1]),'first_differing_flat_index':first,'first_batch_hex':b[k][1][first] if first is not None else None,'first_scalar_hex':s[k][1][first] if first is not None else None,'first_batch_value':bf[first] if first is not None else None,'first_scalar_value':sf[first] if first is not None else None,'batch_sha256_hexrecords':hashlib.sha256(('\n'.join(b[k][1])+'\n').encode()).hexdigest(),'scalar_sha256_hexrecords':hashlib.sha256(('\n'.join(s[k][1])+'\n').encode()).hexdigest()}
 out={'batch_sha256':sha(a.batch),'scalar_sha256':sha(a.scalar),'sections':diffs,'first_differing_stage':next((k for k,v in diffs.items() if v['differing_values']),None)}
 Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(a.output)
if __name__=='__main__':main()
