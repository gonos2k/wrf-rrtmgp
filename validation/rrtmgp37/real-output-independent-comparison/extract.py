"""Read the retained corrected cold history once; never launch a model."""
from pathlib import Path
import json,hashlib,tarfile,datetime as dt,os,time
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-real-output-independent-v1'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return h.hexdigest()
def main():
 import numpy as np
 from netCDF4 import Dataset,chartostring
 start=dt.datetime.now(dt.timezone.utc).isoformat();O.mkdir(exist_ok=False)
 day=B/'udm37-vapor-corrected-day-v2';file=day/'host/wrfout_d01_2016-10-06_00:00:00';prior=R/'validation/rrtmgp37/vapor-first-operation'
 with tarfile.open(prior/'saved/evidence.tar.gz') as tar:
  old=json.load(tar.extractfile('history.json'));saved_receipt=tar.extractfile('day/receipt.json').read()
 assert saved_receipt==(day/'receipt.json').read_bytes()
 assert sha(file)==old['history']['sha256'] and file.stat().st_size==old['history']['bytes']
 (O/'baseline-day-receipt.json').write_bytes(saved_receipt);(O/'namelist.input').write_bytes((day/'host/namelist.input').read_bytes())
 with Dataset(file) as d:
  d.set_auto_maskandscale(False)
  times=chartostring(d['Times'][:]).astype(str).tolist();expected=[(dt.datetime(2016,10,6)+dt.timedelta(hours=k)).strftime('%Y-%m-%d_%H:%M:%S') for k in range(25)];assert times==expected
  lat,lon=np.asarray(d['XLAT'][0],float),np.asarray(d['XLONG'][0],float);assert d.MAP_PROJ==3 and lat.shape==(99,90)
  assert np.all(lat==lat[:,:1]) and np.all(lon==lon[:1,:]) and np.all(np.diff(lat[:,0])>0) and np.all(np.diff(lon[0])>0)
  assert np.array_equal(d['XLAT'][0],d['XLAT'][-1]) and np.array_equal(d['XLONG'][0],d['XLONG'][-1])
  site=(38.97203,-77.48690);assert lat.min()<site[0]<lat.max() and lon.min()<site[1]<lon.max()
  a=np.sin((np.deg2rad(lat)-np.deg2rad(site[0]))/2)**2+np.cos(np.deg2rad(lat))*np.cos(np.deg2rad(site[0]))*np.sin(np.deg2rad(lon-site[1])/2)**2
  distance=2*6371000*np.arcsin(np.sqrt(a));j,i=map(int,np.unravel_index(np.argmin(distance),lat.shape));assert (j,i)==(96,36)
  grid={'shape_j_i':list(lat.shape),'latitude':lat.tolist(),'longitude':lon.tolist(),'MAP_PROJ':int(d.MAP_PROJ),'DX_m':float(d.DX),'DY_m':float(d.DY),'selected_j_i_zero_based':[j,i],'selected_height_m':float(d['HGT'][0,j,i]),'selected_landmask':float(d['LANDMASK'][0,j,i]),'distance_m':float(distance[j,i]),'spec_bdy_width':5,'coordinate_static_endpoints_equal':True}
  v=d['ACSWDNB'];assert str(v.dtype)=='float32' and v.units=='J m-2'
  ac=np.asarray(v[:,j,i],dtype=float);assert np.isfinite(ac).all() and np.all(np.diff(ac)>=0)
  attrs={k:int(d.getncattr(k)) for k in ['MP_PHYSICS','RA_LW_PHYSICS','RA_SW_PHYSICS','UDM_NUMBER_POLICY','UDM_POPULATION_POLICY','UDM_SPECIFIED_NUMBER_CONTRACT']}
  assert attrs==dict(MP_PHYSICS=27,RA_LW_PHYSICS=37,RA_SW_PHYSICS=37,UDM_NUMBER_POLICY=1,UDM_POPULATION_POLICY=0,UDM_SPECIFIED_NUMBER_CONTRACT=1)
  model={'history':old['history'],'source_path':str(file.resolve()),'times_utc':times,'ACSWDNB_J_m2':ac.tolist(),'ACSWDNB_storage_dtype':str(v.dtype),'ACSWDNB_units':v.units,'SWDOWN_instantaneous_W_m2_not_scored':np.asarray(d['SWDOWN'][:,j,i],float).tolist(),'attributes':attrs,'DT_s':float(d.DT),'namelist_sha256':sha(day/'host/namelist.input'),'executable':json.loads(saved_receipt)['executable'],'selected_j_i_zero_based':[j,i]}
 for n,x in [('grid.json',grid),('model-extract.json',model)]: (O/n).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
 (O/'extraction-receipt.json').write_text(json.dumps({'status':'SUCCESS','pid':os.getpid(),'started_utc':start,'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source_sha256':sha(Path(__file__)),'native_history_read':True,'records':25,'new_WRF_Mie_RTE_processes':0,'historical_day_receipt_sha256':sha(day/'receipt.json'),'history_sha256':sha(file),'physical_accuracy_approved':False},indent=2)+'\n');print('ACTUAL_CORRECTED_HISTORY_EXTRACTED',j+1,i+1,len(times))
if __name__=='__main__':main()
