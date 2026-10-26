"""Read the completed new native history and bounded auxiliary fields; no model launch."""
from pathlib import Path
import json,hashlib,importlib.util,re,datetime as dt,os,time,math
import numpy as np
from netCDF4 import Dataset,chartostring
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-interior-day-extract-v1'
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');H=importlib.util.module_from_spec(s);s.loader.exec_module(H)
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return {'path':str(p),'sha256':h.hexdigest(),'bytes':p.stat().st_size}
def times(d):return chartostring(d['Times'][:]).astype(str).tolist()
WATER=['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL'];NUMBER=['QNCLOUD','QNRAIN','QNCCN'];COND=['QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL']
def main():
 started=dt.datetime.now(dt.timezone.utc).isoformat();run=B/'udm37-sterling-interior-day-v1';receipt=json.loads((run/'receipt.json').read_text());assert receipt['status']=='SUCCESS' and not receipt['error'];D=run/'host';O.mkdir(exist_ok=False)
 assets={n:receipt[n] for n in ['initial','forcing','executable','frozen_table','namelist','iofields','prepared_forecast_namelist']};assets.update({'coefficient/'+n:v for n,v in receipt['coefficient_files'].items()});after={n:pin(Path(v['path'])) for n,v in assets.items()};assert all(after[n]['sha256']==v['sha256'] for n,v in assets.items()),'runtime assets changed'
 files=list(D.glob('wrfout*'));assert len(files)==1;file=files[0];historypin=pin(file);models={};state=[];validity=[]
 with Dataset(file) as d:
  d.set_auto_maskandscale(False);tt=times(d);assert tt==[(dt.datetime(2016,10,6)+dt.timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(25)]
  lat,lon=np.asarray(d['XLAT'][0],float),np.asarray(d['XLONG'][0],float);assert lat.shape==(143,90) and d.MAP_PROJ==3
  site=(38.97203,-77.4869);p=np.deg2rad(lat);p0=math.radians(site[0]);a=np.sin((p-p0)/2)**2+np.cos(p)*math.cos(p0)*np.sin(np.deg2rad(lon-site[1])/2)**2;dist=2*6371000*np.arcsin(np.sqrt(a));j,i=map(int,np.unravel_index(np.argmin(dist),dist.shape));assert (j,i)==(118,36)
  assert np.array_equal(d['XLAT'][0],d['XLAT'][-1]) and np.array_equal(d['XLONG'][0],d['XLONG'][-1])
  grid=dict(shape_j_i=list(lat.shape),latitude=lat.tolist(),longitude=lon.tolist(),MAP_PROJ=int(d.MAP_PROJ),DX_m=float(d.DX),DY_m=float(d.DY),selected_j_i_zero_based=[j,i],selected_height_m=float(d['HGT'][0,j,i]),selected_landmask=float(d['LANDMASK'][0,j,i]),distance_m=float(dist[j,i]),spec_bdy_width=5)
  v=d['ACSWDNB'];models=dict(history=historypin,selected_j_i_zero_based=[j,i],times_utc=tt,ACSWDNB_J_m2=np.asarray(v[:,j,i],float).tolist(),ACSWDNBC_J_m2=np.asarray(d['ACSWDNBC'][:,j,i],float).tolist(),ACSWDNB_storage_dtype=str(v.dtype),ACSWDNB_units=v.units,DT_s=float(d.DT),attributes={k:int(getattr(d,k)) for k in ['MP_PHYSICS','RA_LW_PHYSICS','RA_SW_PHYSICS','UDM_NUMBER_POLICY','UDM_POPULATION_POLICY','UDM_SPECIFIED_NUMBER_CONTRACT']},SWDOWN_instantaneous_W_m2_not_scored=np.asarray(d['SWDOWN'][:,j,i],float).tolist())
  nonfinite=0
  for h,t in enumerate(tt):
   row={'time_utc':t,'nonfinite_elements':0,'water_number':{}}
   for n,v in d.variables.items():
    if v.dtype.kind not in 'fiu':continue
    arr=np.asarray(v[h] if v.dimensions and v.dimensions[0]=='Time' else v[:]);bad=int(np.count_nonzero(~np.isfinite(arr)));row['nonfinite_elements']+=bad
    if n in WATER+NUMBER:row['water_number'][n]={'min':float(np.min(arr)),'max':float(np.max(arr)),'negative_elements':int(np.count_nonzero(arr<0)),'nonfinite_elements':bad}
   nonfinite+=row['nonfinite_elements'];assert set(row['water_number'])==set(WATER+NUMBER);validity.append(row)
   mut=np.float32(d['MU'][h,j,i]+d['MUB'][h,j,i]);c1=np.asarray(d['C1H'][h],dtype='f4');c2=np.asarray(d['C2H'][h],dtype='f4');dnw=np.asarray(d['DNW'][h],dtype='f4');md=np.float32(np.float32(-dnw*np.float32(c1*mut+c2))/np.float32(9.81));assert md.shape==(44,) and np.all(md>0)
   profiles={n:np.asarray(d[n][h,:,j,i],float).tolist() for n in WATER+['CLDFRA','UDM_CLDFRA','P','PB','T']};cf=profiles['CLDFRA'];q=[profiles[n] for n in COND]
   cu={n:np.asarray(d[n][h,:,j,i],float).tolist() for n in ['QC_CU','QI_CU'] if n in d.variables}
   state.append(dict(hour_UTC=h,history_state_kind='end-of-step native history, not exact radiation-consumer capture',dry_layer_mass_kg_m2_history_coupling=md.astype(float).tolist(),profiles=profiles,max_CLDFRA=max(cf),max_UDM_CLDFRA_diagnostic_not_consumed_here=max(profiles['UDM_CLDFRA']),six_condensate_grid_paths_g_m2=[1000*math.fsum(float(m)*v for m,v in zip(md,a)) for a in q],six_condensate_CF0_paths_g_m2=[1000*math.fsum(float(m)*v for m,v,c in zip(md,a,cf) if c<=0) for a in q],CU_grid_paths_g_m2=([1000*math.fsum(float(m)*v for m,v in zip(md,cu[n])) for n in ['QC_CU','QI_CU']] if cu else None),CU_profiles=(cu if cu else None),mass_note='native dry hybrid formula from same history MU+MUB,C1H,C2H,DNW,g; not claimed identical to MUT at an earlier radiation call'))
  history={'history':historypin,'records':25,'variable_count':len(d.variables),'numeric_nonfinite_elements':nonfinite,'hourly_validity':validity,'negative_sample_scope':'all physical-grid hourly output elements; no claim of every internal RK stage'}
 # Main history does not always output the optional CU arrays; the bounded auxiliary stream does.
 diagnostic=B/'udm37-sterling-interior-components-v1';dr=json.loads((diagnostic/'receipt.json').read_text());assert dr['status']=='SUCCESS' and not dr['error'];comparison=json.loads((B/'udm37-sterling-interior-components-comparison.json').read_text());assert comparison['pairs']==1350 and not comparison['differences']
 E=diagnostic/'host';surfacefiles=list(E.glob('sterling_surface_*'));cloudfiles=list(E.glob('sterling_state_*'));assert len(surfacefiles)==len(cloudfiles)==1
 with Dataset(surfacefiles[0]) as d:
  d.set_auto_maskandscale(False);surface=dict(file=pin(surfacefiles[0]),times_utc=times(d),selected_j_i_zero_based=[j,i],values={n:np.asarray(d[n][:,j,i],float).tolist() for n in ['SWDNB','SWDNBC','SWDDIR','SWDDIRC','SWDDIF','SWDDNI','COSZEN','ACSWDNB','ACSWDNBC']},metadata={n:{'units':getattr(d[n],'units',''),'description':getattr(d[n],'description','')} for n in d.variables if n not in ['Times','XLAT','XLONG']})
 with Dataset(cloudfiles[0]) as d:
  d.set_auto_maskandscale(False);cloud_states={'file':pin(cloudfiles[0]),'times_utc':times(d),'selected_j_i_zero_based':[j,i],'scope':'native end-of-step snapshots every600s; CLDFRA may be a held radiation diagnostic from the preceding call, while q is current end-of-step. Distinguish these states from exact adapter mask/incloud inputs','profiles':[{n:np.asarray(d[n][h,:,j,i],float).tolist() for n in ['CLDFRA','UDM_CLDFRA',*COND,'QC_CU','QI_CU']} for h in range(len(d.dimensions['Time']))]}
  assert cloud_states['times_utc']==[(dt.datetime(2016,10,6,16)+dt.timedelta(minutes=10*n)).strftime('%Y-%m-%d_%H:%M:%S') for n in range(7)]
 # Attach CU state at matching hourly endpoints only; do not interpolate mass to manufacture600s optical paths.
 for hour,index in [(16,0),(17,6)]:
  row=state[hour];cu=cloud_states['profiles'][index];row['CU_profiles']={n:cu[n] for n in ['QC_CU','QI_CU']};row['CU_grid_paths_g_m2']=[1000*math.fsum(m*q for m,q in zip(row['dry_layer_mass_kg_m2_history_coupling'],cu[n])) for n in ['QC_CU','QI_CU']]
 log=(run/'command-01.stdout').read_text(errors='replace');steps=re.findall(r'Timing for main: time ([\d_:-]+)',log);assert steps==[(dt.datetime(2016,10,6)+dt.timedelta(minutes=m)).strftime('%Y-%m-%d_%H:%M:%S') for m in range(1,1441)]
 lw=sorted({int(float(x)) for x in re.findall(r'LW RRTMGP_UDM_PHASE_PATH[^\n]*source_time_seconds=\s*([\d.E+\-]+)',log)})
 summary={'status':receipt['status'],'steps':len(steps),'terminal_time_utc':steps[-1],'LW_source_seconds':lw,'actual_elapsed_seconds':receipt['commands'][0]['finished_at']-receipt['commands'][0]['started_at'],'executable':receipt['executable'],'input':receipt['initial'],'forcing':receipt['forcing'],'namelist':receipt['namelist'],'frozen_table':receipt['frozen_table'],'coefficient_files':receipt['coefficient_files'],'runtime_assets_unchanged_after':True,'postflight_assets':after,'cold24h_WRF_processes':1,'new_build_WPS_REAL_Mie_RTE_processes':0,'general_restart_certification':False,'bounded_diagnostic_restart_performed':True,'actual_WRF_processes_total':2,'diagnostic_receipt':dr,'diagnostic_overlap_comparison':comparison}
 data=dict(model=models,grid=grid,history=history,hourly_state=state,surface=surface,cloud_states=cloud_states,run_summary=summary)
 (O/'extracted.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');(O/'receipt.json').write_text(json.dumps({'status':'SUCCESS','pid':os.getpid(),'started_utc':started,'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source':pin(Path(__file__)),'history':historypin,'records':25,'native_read':True,'new_model_processes':0},indent=2)+'\n');print('ACTUAL_INTERIOR_DAY_EXTRACTED',len(steps),len(lw),surface['times_utc'][0],surface['times_utc'][-1])
if __name__=='__main__':main()
