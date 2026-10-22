from pathlib import Path
import hashlib,json,argparse
import numpy as np
from netCDF4 import Dataset
ap=argparse.ArgumentParser();ap.add_argument('left');ap.add_argument('right');ap.add_argument('output');a=ap.parse_args();files=[Path(a.left),Path(a.right)];inventory={};diff=[]
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def times(d):return [b''.join(t).decode() for t in d['Times'][:]]
def arr(v,i):return np.asarray(v[i] if v.dimensions and v.dimensions[0]=='Time' else v[:])
with Dataset(files[0]) as x,Dataset(files[1]) as y:
 x.set_auto_mask(False);y.set_auto_mask(False);tx=times(x);ty=times(y)
 for t in tx:
  if t not in ty:continue
  i=tx.index(t);j=ty.index(t);inventory[t]={}
  assert set(x.variables)==set(y.variables)
  for n,v in x.variables.items():
   l=arr(v,i);r=arr(y[n],j);equal=l.tobytes()==r.tobytes();inventory[t][n]={'left_sha256':hashlib.sha256(l.tobytes()).hexdigest(),'right_sha256':hashlib.sha256(r.tobytes()).hexdigest(),'equal':equal}
   if not equal:diff.append([t,n])
z={'files':list(map(pin,files)),'inventory':inventory,'pairs':sum(map(len,inventory.values())),'differences':diff};Path(a.output).write_text(json.dumps(z,indent=2)+'\n');print(z['pairs'],len(diff))
