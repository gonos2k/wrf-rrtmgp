#!/usr/bin/env python3
"""Only already saved history fields; match QFX to the native add_a2a support."""
from pathlib import Path
import json,hashlib
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-real-budget-analysis-v1'
p=next((B/'udm37-real-budget-host-v2/host').glob('wrfout*'));rows=[]
with Dataset(p) as d:
 d.set_auto_mask(False)
 for i in range(3):
  a=float(d.DX)*float(d.DY)/(d['MAPFAC_MX'][i].astype('f8')*d['MAPFAC_MY'][i].astype('f8'));q=d['QFX'][i].astype('f8');lh=d['LH'][i].astype('f8')
  rows.append({'source_time_s':21540+60*i,'output_time':b''.join(d['Times'][i]).decode(),'QFX_full_kg_s':float(np.sum(a*q)),'QFX_interior_kg_s':float(np.sum((a*q)[1:-1,1:-1])),'LH_minus_2500000_QFX_max_W_m2':float(np.max(np.abs(lh-2500000*q))),'QFX_field_sha256':hashlib.sha256(np.asarray(d['QFX'][i]).tobytes()).hexdigest(),'all_history_QFX_finite':bool(np.isfinite(q).all())})
(O/'surface_domains.json').write_text(json.dumps(rows,indent=2)+'\n');print('SURFACE_SUPPORT_EXTRACTED',len(rows))
