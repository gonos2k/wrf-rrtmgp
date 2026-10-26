"""Compare actual prepared initial fields on shared geographic cells; no model launch."""
from pathlib import Path
import hashlib,json,importlib.util
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-interior-input-contrast-v2';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
old=B/'udm37-specified-number-run-v2/encoded/wrfinput_d01';new=B/'udm37-sterling-interior-real-v1/encoded/wrfinput_d01';rows=[]
with Dataset(old) as x,Dataset(new) as y:
 x.set_auto_maskandscale(False);y.set_auto_maskandscale(False)
 lat=np.asarray(x['XLAT'][0]);lon=np.asarray(x['XLONG'][0]);nlat=np.asarray(y['XLAT'][0,22:121,:]);nlon=np.asarray(y['XLONG'][0,22:121,:]);assert lat.shape==nlat.shape==(99,90)
 assert np.array_equal(np.argmin(abs(np.asarray(y['XLAT'][0,:,0])[:,None]-lat[:,0][None,:]),axis=0),np.arange(99)+22)
 assert np.array_equal(np.argmin(abs(np.asarray(y['XLONG'][0,0,:])[:,None]-lon[0,:][None,:]),axis=0),np.arange(90))
 coordinate_difference={n:{'different_cells':int(np.count_nonzero(a!=b)),'max_abs_degrees':float(np.max(abs(b.astype(float)-a.astype(float))))} for n,a,b in [('latitude',lat,nlat),('longitude',lon,nlon)]}
 assert np.array_equal([lat[96,36],lon[96,36]],[nlat[96,36],nlon[96,36]])
 for n in ['HGT','LANDMASK','LU_INDEX','IVGTYP','ISLTYP','TSK','TMN','SST','SMOIS','TSLB','P','PB','T','QVAPOR']:
  if n not in x.variables or n not in y.variables:continue
  a=np.asarray(x[n][0]);b=np.asarray(y[n][0,...,22:121,:]);assert a.shape==b.shape
  delta=b.astype(float)-a.astype(float);assert np.isfinite(delta).all();j=96;i=36
  rows.append({'variable':n,'units':getattr(x[n],'units',''),'description_old':getattr(x[n],'description',''),'description_new':getattr(y[n],'description',''),'shape':list(a.shape),'different_elements':int(np.count_nonzero(delta)),'elements':int(a.size),'difference_min':float(delta.min()),'difference_max':float(delta.max()),'difference_mean':float(np.mean(delta)),'difference_RMS':float(np.sqrt(np.mean(delta*delta))),'site_old':np.asarray(a[...,j,i],float).tolist(),'site_new':np.asarray(b[...,j,i],float).tolist(),'site_delta':np.asarray(delta[...,j,i],float).tolist()})
result={'status':'ACTUAL_PREPARED_INPUT_SHARED_GEOGRAPHY_CONTRAST_COMPLETE','original':h.pin(old),'interior':h.pin(new),'original_shape':[99,90],'interior_overlap_j_zero_based':[22,121],'all_overlap_coordinates_bitwise_equal':False,'nominal_overlap_nearest_rows_and_columns_confirmed':True,'coordinate_differences':coordinate_difference,'original_station_cell_coordinates_bitwise_equal':True,'station_original_i_j':[37,97],'station_new_i_j':[37,119],'variables':rows,'temperature_note':'stored initial T is compared in its on-file theta representation, not relabelled as actual air temperature; physical dry-theta conversion is separately applied to native forecast history','isolated_domain_effect_measured':False,'preprocessor_or_geography_effect_separated':False,'new_WRF_processes':0};(O/'input-contrast.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status']);print([(r['variable'],r['different_elements'],r['difference_RMS']) for r in rows])
