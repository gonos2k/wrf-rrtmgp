from pathlib import Path
import hashlib,json
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-kfeta-expiry-host-v1'
files=[next((O/n).glob('wrfout*')) for n in ['public','observed']];inventory={};differences=[]
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
with Dataset(files[0]) as a,Dataset(files[1]) as b:
 a.set_auto_mask(False);b.set_auto_mask(False);times=lambda d:[b''.join(t).decode() for t in d['Times'][:]]
 assert times(a)==times(b)
 for i,t in enumerate(times(a)):
  inventory[t]={}
  for n,v in a.variables.items():
   x=np.asarray(v[i] if v.dimensions[0]=='Time' else v[:]);y=np.asarray(b[n][i] if b[n].dimensions[0]=='Time' else b[n][:])
   equal=x.tobytes()==y.tobytes();inventory[t][n]={'public_sha256':hashlib.sha256(x.tobytes()).hexdigest(),'observed_sha256':hashlib.sha256(y.tobytes()).hexdigest(),'equal':equal}
   if not equal:differences.append((t,n))
r={'files':list(map(pin,files)),'inventory':inventory,'pairs':sum(map(len,inventory.values())),'differences':differences,'scope':'same candidate executable, observer OFF/ON; not cold-vs-restart'}
(O/'history-comparison.json').write_text(json.dumps(r,indent=2)+'\n');print('CANDIDATE_OBSERVER_PAIRS',r['pairs'],'differences',len(differences))
