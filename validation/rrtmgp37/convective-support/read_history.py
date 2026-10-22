#!/usr/bin/env python3
"""Decode final hourly states and available original overlap; never rerun a model."""
from pathlib import Path
import hashlib,json
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;H=B/'udm37-convective-support-host-v1';O=B/'udm37-convective-support-analysis-v1'
def pin(p):return {'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def times(d):return [b''.join(t).decode() for t in d['Times'][:]]
def arr(v,i):return np.asarray(v[i] if v.dimensions and v.dimensions[0]=='Time' else v[:])
p=next((H/'host').glob('wrfout*'));prior=next((B/'udm37-restart-first-fix-run-v2/continuous').glob('wrfout*'));states=[];inventory={};overlap=[]
with Dataset(p) as d,Dataset(prior) as ref:
 d.set_auto_mask(False);ref.set_auto_mask(False);ts=times(d);rs=times(ref);FIELDS=['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL']
 for i,t in enumerate(ts):
  inventory[t]={}
  for n,v in d.variables.items():
   x=arr(v,i);inventory[t][n]={'shape':list(x.shape),'dtype':x.dtype.str,'sha256':hashlib.sha256(x.tobytes()).hexdigest(),'nonfinite_numeric_elements':int(np.sum(~np.isfinite(x))) if x.dtype.kind in 'fc' else 0}
  a=float(d.DX)*float(d.DY)/(d['MAPFAC_MX'][i].astype('f8')*d['MAPFAC_MY'][i].astype('f8'));A=a.sum()
  md=-(d['C1H'][i].astype('f8')[:,None,None]*(d['MU'][i]+d['MUB'][i]).astype('f8')+d['C2H'][i].astype('f8')[:,None,None])*d['DNW'][i].astype('f8')[:,None,None]/float(np.float32(9.81))
  species={n:float(np.sum(a*md*d[n][i].astype('f8'))/A) for n in FIELDS};quality={}
  for n in FIELDS+['QNCLOUD','QNRAIN','QNCCN']:
   x=d[n][i];quality[n]={'min':float(x.min()),'max':float(x.max()),'negative_elements':int(np.sum(x<0)),'nonfinite_elements':int(np.sum(~np.isfinite(x)))}
  temp=(d['T'][i].astype('f8')+300)*((d['P'][i].astype('f8')+d['PB'][i].astype('f8'))/100000)**(287/1004.5)
  counters={}
  for n in ['RAINC','RAINNC','RAINSH']:
   x=a*d[n][i].astype('f8');counters[n]={'all':float(x.sum()/A),'interior':float(x[1:-1,1:-1].sum()/A),'outer':float((x.sum()-x[1:-1,1:-1].sum())/A)}
  qv=d['QVAPOR'][i];neg=qv<0;negative_vapor=None
  if np.any(neg):
   inside=int(np.sum(neg[:,1:-1,1:-1]));loc=np.unravel_index(np.argmin(qv),qv.shape)
   negative_vapor={'elements':int(np.sum(neg)),'interior_elements':inside,'outer_elements':int(np.sum(neg))-inside,'negative_water_magnitude_kg_m2':float(np.sum(a*md*np.maximum(-qv.astype('f8'),0))/A),'minimum_kg_kg':float(qv[loc]),'minimum_fortran_k_j_i_1based':[int(x)+1 for x in loc]}
  states.append({'time':t,'water_species_kg_m2':species,'W_kg_m2':sum(species.values()),'quality':quality,'negative_vapor':negative_vapor,'temperature_from_history_K_min_max':[float(temp.min()),float(temp.max())],'counters':counters})
 for i,t in enumerate(ts):
  if t not in rs:continue
  j=rs.index(t);diffs=[];count=0
  for n,v in ref.variables.items():
   count+=1;x=arr(v,j);y=arr(d[n],i)
   if x.tobytes()!=y.tobytes():diffs.append({'field':n,'original_sha256':hashlib.sha256(x.tobytes()).hexdigest(),'new_sha256':hashlib.sha256(y.tobytes()).hexdigest(),'max_abs_difference':float(np.max(np.abs(x.astype('f8')-y.astype('f8')))) if x.dtype.kind in 'fiu' else None})
  overlap.append({'time':t,'compared_arrays':count,'differences':diffs,'all_byte_equal':not diffs})
r={'history':pin(p),'original_corrected_history':pin(prior),'records':len(states),'states':states,'array_inventory':inventory,'original_overlap':overlap,'temperature_contract':'(T+300)*((double(P)+double(PB))/100000)**(Rd/Cp); T is perturbation dry potential temperature, not air temperature','observations_available':False,'forecast_skill_approved':False}
(O/'history.json').write_text(json.dumps(r,indent=2)+'\n');print('HOURLY_HISTORY_DECODED',len(states),'overlap',[(x['time'],x['compared_arrays'],x['all_byte_equal']) for x in overlap])
