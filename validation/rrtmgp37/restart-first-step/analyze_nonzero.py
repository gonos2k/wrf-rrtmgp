#!/usr/bin/env python3
"""Read the one actual nonzero host branch without another model run."""
from pathlib import Path
from datetime import datetime
import json
import numpy as np
from netCDF4 import Dataset
def analyze(O):
 d=O/'host';forcing=d/'wrfbdy_d01';receipt=json.loads((O/'receipt.json').read_text())
 observed=[]
 with Dataset(next(d.glob('wrfout*'))) as out,Dataset(forcing) as b:
  ts=[b''.join(x).decode() for x in out['Times'][:]]
  for it,t in enumerate(ts):
   sec=(datetime.strptime(t,'%Y-%m-%d_%H:%M:%S')-datetime(2016,10,6)).total_seconds();record=int(sec//21600);elapsed=sec-record*21600
   a=(np.asarray(out['C1H'][it,:])[:,None]*(out['MU'][it,0,:]+out['MUB'][it,0,:])[None,:]+np.asarray(out['C2H'][it,:])[:,None]).astype('f4')
   row={'time':t,'record':record,'record_elapsed_s':elapsed,'numbers':{}}
   for field in ['QNCLOUD','QNRAIN']:
    s=(b[field+'_BYS'][record,0,:,:]+np.float32(elapsed)*b[field+'_BTYS'][record,0,:,:]).astype('f4');expected=(s/a).astype('f4');actual=np.asarray(out[field][it,:,0,:])
    # Boundary arithmetic is native REAL32; preserve raw bits and report deviation.
    patch=actual[:2,22:25];target=expected[:2,22:25]
    assert np.isfinite(patch).all() and (patch>0).all() if elapsed>0 else not np.any(patch)
    # Report native evaluation differences; do not invent a fitted tolerance.
    if elapsed==0:assert np.array_equal(patch,target)
    full=np.asarray(out[field][it]);assert np.isfinite(full).all() and np.all(full>=0)
    row['numbers'][field]={'actual':patch.astype(float).tolist(),'expected':target.astype(float).tolist(),'max_abs_uncoupling_evaluation_difference':float(np.max(abs(patch-target))),'actual_bits':patch.view('u4').tolist(),'expected_bits':target.view('u4').tolist(),'coupled':s[:2,22:25].astype(float).tolist(),'mass_factor_Pa':a[:2,22:25].astype(float).tolist(),'relaxation_strip':full[:2,1:5,22:25].astype(float).tolist(),'interior_max':float(full[:,5:-5,5:-5].max())}
   observed.append(row)
 receipt.update(status='SUCCESS',observed=observed);(O/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('NONZERO_HOST_RECORD_TRANSITION_COMPLETE',[(r['time'],{n:v['actual'][0][1] for n,v in r['numbers'].items()}) for r in observed])
if __name__=='__main__':
 analyze(Path(__file__).resolve().parents[4]/'udm37-restart-first-nonzero-host-v1')
