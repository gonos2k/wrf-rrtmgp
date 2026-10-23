"""Reuse native history and forcing; no model or interpolation."""
from pathlib import Path
import json,hashlib,datetime as dt
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-existing-v1';O.mkdir(exist_ok=False)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 from netCDF4 import Dataset,chartostring
 import numpy as np
 prior=B/'udm37-vapor-corrected-day-v2/host';file=prior/'wrfout_d01_2016-10-06_00:00:00';require=sha(file)=='3da760fb50fa18b5ead1248ca684f72e22625524896d37a1bc2aa432c01fd72c';assert require
 names=['CLDFRA','UDM_CLDFRA','QVAPOR','QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL','P','PB','T']
 snapshots=[]
 with Dataset(file) as d:
  d.set_auto_maskandscale(False);times=chartostring(d['Times'][:]).astype(str).tolist()
  for hour in range(15,20):
   for j in range(89,100):
    row={'hour_UTC':hour,'i':37,'j':j,'lat':float(d['XLAT'][0,j-1,36]),'lon':float(d['XLONG'][0,j-1,36]),'height_m':float(d['HGT'][0,j-1,36]),'profiles':{n:np.asarray(d[n][hour,:,j-1,36],float).tolist() for n in names},'instantaneous_not_hourly':{n:float(d[n][hour,j-1,36]) for n in ['SWDNB','SWDNBC','SWDDIR','SWDDIF','COSZEN']},'ACSWDNB_J_m2':float(d['ACSWDNB'][hour,j-1,36]),'ACSWDNBC_J_m2':float(d['ACSWDNBC'][hour,j-1,36])};snapshots.append(row)
  metadata={n:{'units':getattr(d[n],'units',''),'description':getattr(d[n],'description','')} for n in names};metadata['T']['interpretation']='native history perturbation potential-temperature field, not labelled actual Kelvin temperature here'
 forcing=prior/'wrfbdy_d01';boundary=[]
 with Dataset(forcing) as d:
  d.set_auto_maskandscale(False);btimes=chartostring(d['Times'][:]).astype(str).tolist()
  for idx in [2,3]:
   row={'time':btimes[idx],'i':37,'north_width_index_order':[1,2,3,4,5],'raw_stored_values_not_decoupled':{}}
   for q in ['QVAPOR','QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL']:
    for suffix in ['BYE','BTYE']:
     n=q+'_'+suffix;v=d[n];row['raw_stored_values_not_decoupled'][n]={'dimensions':list(v.dimensions),'units_metadata':getattr(v,'units',''),'values_width_layer':np.asarray(v[idx,:,:,36],float).tolist()}
   boundary.append(row)
 r={'history_sha256':sha(file),'forcing_sha256':sha(forcing),'actual_history_times':times,'profiles_metadata':metadata,'snapshots':snapshots,'boundary_records':boundary,'scope':'fixed transect and original12/18UTC boundary records; raw forcing values not reinterpreted by units label or decoupled with an assumed mass','new_model_processes':0}
 (O/'existing.json').write_text(json.dumps(r,indent=2)+'\n');print('EXISTING_NATIVE_AND_BOUNDARY_EXTRACTED',len(snapshots))
if __name__=='__main__':main()
