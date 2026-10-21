#!/usr/bin/env python3
"""Read actual original stock/surface data, retaining missing boundary terms."""
from pathlib import Path
import json,hashlib
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-real-budget-analysis-v1';O.mkdir(exist_ok=True)
FIELDS=['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL']
def pin(p):return {'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def row(d,i):
 g=float(np.float32(9.81));a=float(d.DX)*float(d.DY)/(np.asarray(d['MAPFAC_MX'][i],dtype='f8')*np.asarray(d['MAPFAC_MY'][i],dtype='f8'))
 mt=np.asarray(d['MU'][i]+d['MUB'][i],dtype='f8');c1=np.asarray(d['C1H'][i],dtype='f8');c2=np.asarray(d['C2H'][i],dtype='f8');dnw=np.asarray(d['DNW'][i],dtype='f8')
 md=-(c1[:,None,None]*mt+c2[:,None,None])*dnw[:,None,None]/g
 w={n:float(np.sum(a*md*np.asarray(d[n][i],dtype='f8'))) for n in FIELDS}
 out={'time':b''.join(d['Times'][i]).decode(),'area_m2':float(a.sum()),'species_kg':w,'W_kg':sum(w.values()),'W_domain_mean_kg_m2':sum(w.values())/a.sum()}
 for key,field,scale in [('P','RAINNC',1),('Pc','RAINC',1),('Eproxy','ACLHF',1/2501000),('QFX','QFX',1)]:
  out[key]=float(np.sum(a*np.asarray(d[field][i],dtype='f8')))*scale if field in d.variables else None
 return out
fs=[B/'udm37-restart-first-fix-run-v2/continuous/wrfinput_d01',next((B/'udm37-restart-first-fix-run-v2/continuous').glob('wrfout*'))]
rows=[];availability=[]
for f in fs:
 with Dataset(f) as d:
  d.set_auto_mask(False)
  for i in range(len(d.dimensions['Time'])):rows.append(row(d,i))
  availability.append({'file':pin(f),'times':len(d.dimensions['Time']),'fields':list(d.variables)})
late=[]
for a,b in zip(rows[1:],rows[2:]):
 dw=b['W_kg']-a['W_kg'];p=b['P']+b['Pc']-a['P']-a['Pc'];e=b['Eproxy']-a['Eproxy']
 late.append({'start':a['time'],'end':b['time'],'dW_kg':dw,'P_kg':p,'E_ACLHF_kg':e,'dW_plus_P_minus_E_before_boundary_kg':dw+p-e,'closed_water_residual_kg':None,'boundary_advection_relaxation_specified_not_available_in_history':True})
r={'definition':'all physical mass cells, seven water species, native REAL32 MU+MUB input, double coefficient and mass products; area DX*DY/(MAPFAC_MX*MAPFAC_MY); g is native REAL32 9.81','states':rows,'late_intervals':late,'availability':availability,'six_hour_closed_water_budget':None,'not_available':['six-hour lateral advection','six-hour relaxation and specified increments','initial surface cumulative counters in wrfinput','native-top flux (history top is extended TOA)','actual high-frequency thermal RHS consumption'],'physical_water_budget_approved':False}
(O/'inventory.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'states':[{k:v for k,v in x.items() if k in ['time','W_domain_mean_kg_m2']} for x in rows],'late_intervals':late},indent=2))
