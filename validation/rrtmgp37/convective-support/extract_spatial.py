#!/usr/bin/env python3
"""Extract existing precipitation grids only; no model, interpolation, or changed fields."""
from pathlib import Path
import hashlib,json,struct
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-convective-support-analysis-v1';O.mkdir(exist_ok=True)
p=next((B/'udm37-restart-first-fix-run-v2/continuous').glob('wrfout*'))
blocks=[];names=['RAINC','RAINNC','RAINSH'];pins={}
with Dataset(p) as d:
 d.set_auto_mask(False);a=float(d.DX)*float(d.DY)/(d['MAPFAC_MX'][1].astype('f8')*d['MAPFAC_MY'][1].astype('f8'));ny,nx=a.shape
 area=a.astype('<f8').tobytes();blocks.append(area)
 times=[b''.join(t).decode() for t in d['Times'][1:5]]
 for i,t in enumerate(times,1):
  pins[t]={}
  for n in names:
   raw=np.asarray(d[n][i],dtype='<f4').tobytes();blocks.append(raw);pins[t][n]=hashlib.sha256(raw).hexdigest()
raw=b''.join(blocks);(O/'rain-spatial.bin').write_bytes(raw)
meta={'source_file':{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size},'nx':nx,'ny':ny,'times':times,'fields':names,'format':'row-major little-endian area float64 then time/field float32; physical mass grid only','field_sha256':pins,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
(O/'rain-spatial.json').write_text(json.dumps(meta,indent=2)+'\n');print('EXISTING_RAIN_FIELDS_EXTRACTED',times,len(raw))
