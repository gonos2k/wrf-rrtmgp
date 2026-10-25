"""Actual one-step support check; not a new skill forecast or replacement score."""
from pathlib import Path
import os,json,importlib.util,re,shutil,math
import numpy as np
from netCDF4 import Dataset,chartostring
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;I=B/'udm37-sterling-interior-real-v1';O=B/'udm37-sterling-interior-preflight-v1';O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
assert json.loads((I/'receipt.json').read_text())['status']=='SUCCESS'
prior=B/'udm37-vapor-corrected-day-v2/host'
for p in prior.iterdir():
 if p.is_symlink() and not p.name.startswith(('wrfinput','wrfbdy','wrfrst')):(D/p.name).symlink_to(p.resolve())
for n in ['wrfinput_d01','wrfbdy_d01']:(D/n).symlink_to(I/'encoded'/n)
shutil.copyfile(prior/'radiation_iofields.txt',D/'radiation_iofields.txt')
nml=(I/'forecast.namelist.input').read_text()
for key,val in {'run_seconds':'60','end_day':'06','end_hour':'0','end_minute':'1','history_interval_s':'60','restart_interval_s':'1000000'}.items():
 nml,n=re.subn(r'(?m)^(\s*'+key+r'\s*=\s*)[^,\n]+',lambda m:m[1]+val,nml);assert n==1,key
(D/'namelist.input').write_text(nml);env={k:v for k,v in os.environ.items() if not k.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_RESEARCH_','WRF_RADIATION_ENERGY'))};env.update(LD_LIBRARY_PATH=str(B/'deps/netcdf/lib'),OMP_NUM_THREADS='1')
exe=B/'udm37-vapor-corrected-public-v2/wrf';runner=h.Runner(O,180,env,1);runner.run(['bash','-c','ulimit -s unlimited; exec "$@"','preflight',exe],D,'unchanged_public_WRF_one_step_interior_input_support')
assert 'SUCCESS COMPLETE WRF' in (O/'command-01.stdout').read_text()
station=json.loads((P.parent/'real-output-independent-comparison/result.json').read_text())['site']['station_lat_lon_height']
with Dataset(I/'encoded/wrfinput_d01') as d:
 lat=np.asarray(d['XLAT'][0],float);lon=np.asarray(d['XLONG'][0],float);dlat=np.radians(lat-station[0]);dlon=np.radians(lon-station[1]);a=np.sin(dlat/2)**2+np.cos(np.radians(lat))*math.cos(math.radians(station[0]))*np.sin(dlon/2)**2;distance=6371000*2*np.arcsin(np.sqrt(a));j,i=np.unravel_index(np.argmin(distance),distance.shape)
 margin=min(i,j,lat.shape[1]-1-i,lat.shape[0]-1-j);site={'station_lat_lon_height':station,'model_i_j_1based':[int(i+1),int(j+1)],'model_lat_lon':[float(lat[j,i]),float(lon[j,i])],'distance_m':float(distance[j,i]),'cells_to_nearest_physical_edge':int(margin),'north_edge_cells':int(lat.shape[0]-1-j),'spec_bdy_width':5,'outside_relaxation_zone':bool(margin>=5),'original_station_preserved':True};assert margin>=20
 contracts={n:int(getattr(d,n)) for n in ['UDM_NUMBER_POLICY','UDM_POPULATION_POLICY','UDM_SPECIFIED_NUMBER_CONTRACT']};assert contracts==dict(UDM_NUMBER_POLICY=1,UDM_POPULATION_POLICY=0,UDM_SPECIFIED_NUMBER_CONTRACT=1)
with Dataset(next(D.glob('wrfout*'))) as d:
 d.set_auto_maskandscale(False);times=chartostring(d['Times'][:]).astype(str).tolist();assert times==['2016-10-06_00:00:00','2016-10-06_00:01:00']
 checks={n:{'min':float(np.min(d[n][:])),'finite':bool(np.isfinite(d[n][:]).all())} for n in ['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL','QNCLOUD','QNRAIN','QNCCN']};assert all(c['finite'] and c['min']>=0 for c in checks.values())
receipt={'status':'INTERIOR_INPUT_PREPARED_AND_ONE_STEP_SUPPORTED','site':site,'contracts':contracts,'commands':runner.commands,'executable':h.pin(exe),'namelist':h.pin(D/'namelist.input'),'output':h.pin(next(D.glob('wrfout*'))),'actual_times':times,'water_number_checks':checks,'new_forecast_evaluation':False,'original_24h_scores_changed':False,'original_QC_UTC_station_retained':True,'unprovided_condensate_remains_limitation':True,'static_lowres_geography_also_changes':True,'optical_code_improvement_claimed':False,'physical_accuracy_approved':False,'production_changes':False};h.write_json(O/'receipt.json',receipt);print(receipt['status'],site)
