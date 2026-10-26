"""Read retained source/intermediate/NetCDFs once; leave historical packages intact."""
from common import *
import json,os,datetime as dt,tarfile,importlib.metadata
import numpy as np
from netCDF4 import Dataset,chartostring
P=Path(__file__).resolve().parent;O=B/'udm37-sterling-low-level-extract-v2'
PLAN=json.loads((P/'plan.json').read_text());J,I=118,36
def ts(hour):return (dt.datetime(2016,10,6)+dt.timedelta(hours=hour)).strftime('%Y-%m-%d_%H:%M:%S')
def fields(d,itime,j,i):
 p=np.asarray(np.float32(d['P'][itime,:,j,i]+d['PB'][itime,:,j,i]),float)
 dry=np.asarray(d['T'][itime,:,j,i],float)+300;T=dry*(p/100000)**(287/1004.5)
 z=np.asarray(np.float32(d['PH'][itime,:,j,i]+d['PHB'][itime,:,j,i]),float)/float(np.float32(9.81));hgt=float(d['HGT'][itime,j,i])
 co=float(d['COSALPHA'][itime,j,i]);si=float(d['SINALPHA'][itime,j,i]);u=(np.asarray(d['U'][itime,:,j,i],float)+np.asarray(d['U'][itime,:,j,i+1],float))/2;v=(np.asarray(d['V'][itime,:,j,i],float)+np.asarray(d['V'][itime,:,j+1,i],float))/2
 names=['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL','CLDFRA'];water={n:np.asarray(d[n][itime,:,j,i],float).tolist() for n in names}
 w=np.asarray(d['W'][itime,:,j,i],float);mu=float(d['MU'][itime,j,i]);mub=float(d['MUB'][itime,j,i]);c1=np.asarray(d['C1H'][itime,:],float);c2=np.asarray(d['C2H'][itime,:],float);dnw=np.asarray(d['DNW'][itime,:],float)
 mass=-(c1*(mu+mub)+c2)*dnw/float(np.float32(9.81))
 profiles=[]
 for k in range(len(p)):
  row={'record':k+1,'p_Pa':float(p[k]),'T_K':float(T[k]),'dry_theta_K':float(dry[k]),'qv_kg_kg':water['QVAPOR'][k],'z_msl_m':float((z[k]+z[k+1])/2),'z_agl_m':float((z[k]+z[k+1])/2-hgt),'layer_dry_mass_kg_m2':float(mass[k]),'U_grid_m_s':float(u[k]),'V_grid_m_s':float(v[k]),'wind_u_east_m_s':float(u[k]*co-v[k]*si),'wind_v_north_m_s':float(v[k]*co+u[k]*si),'W_geometric_m_s':float((w[k]+w[k+1])/2),'CLDFRA_held_diagnostic':water['CLDFRA'][k]}
  row.update({n:water[n][k] for n in names if n!='CLDFRA'});profiles.append(row)
 return {'profiles':profiles,'native':{'P':np.asarray(d['P'][itime,:,j,i],float).tolist(),'PB':np.asarray(d['PB'][itime,:,j,i],float).tolist(),'T':np.asarray(d['T'][itime,:,j,i],float).tolist(),'MU':mu,'MUB':mub,'C1H':c1.tolist(),'C2H':c2.tolist(),'DNW':dnw.tolist()},'surface':{n:float(d[n][itime,j,i]) for n in ['HGT','PBLH','PSFC','T2','Q2'] if n in d.variables},'lat_lon':[float(d['XLAT'][itime,j,i]),float(d['XLONG'][itime,j,i])]}
def recs(path):
 with path.open('rb') as f:
  while lead:=f.read(4):
   start=f.tell()-4;n=struct.unpack('>I',lead)[0];require(n<3000000,'WPS record size');v=f.read(n);require(len(v)==n and struct.unpack('>I',f.read(4))[0]==n,'WPS record markers');yield start,v
def intermediate(path,lat,lon):
 rr=iter(recs(path));rows=[]
 for start,ver in rr:
  require(struct.unpack('>i',ver)[0]==5,'WPS version');_,h=next(rr);_,pr=next(rr);_,wind=next(rr);off,data=next(rr)
  field=h[60:69].decode().strip();p,nx,ny,proj=struct.unpack('>fiii',h[140:]);require((nx,ny,proj)==(360,181,0),'WPS latlon projection');name,slat,slon,dlat,dlon,earth=struct.unpack('>8sfffff',pr)
  if field not in ['TT','RH','UU','VV','HGT'] or not 75000<=p<=100000:continue
  # Header STARTLOC applies to both axes; negative dlat means row0 is north.
  require(name==b'SWCORNER' and (slat,slon,dlat,dlon)==(90.,0.,-1.,1.),'actual WPS origin/increments')
  a=np.frombuffer(data,dtype='>f4').reshape(ny,nx);y=(lat-slat)/dlat;x=(lon%360-slon)/dlon;corners=[]
  for j in [int(np.floor(y)),int(np.floor(y))+1]:
   for i in [int(np.floor(x)),int(np.floor(x))+1]:corners.append({'lat':slat+j*dlat,'lon':slon+i*dlon,'value':float(a[j,i]),'row_col_zero_based':[j,i]})
  rows.append({'field':field,'p_Pa':p,'units':h[69:94].decode().strip(),'header_offset':start,'slab_record_offset':off,'slab_sha256':hashlib.sha256(data).hexdigest(),'corners':corners,'bilinear_value':bilinear(corners,lat,lon),'wind_is_earth_relative':struct.unpack('>i',wind)[0]==0})
 return rows
def grib(path,lat,lon):
 # The isolated decoder dependency directory does not modify the model environment.
 sys.path.insert(0,str(B/'udm37-sterling-low-level-python-deps'));import eccodes as e
 rows=[]
 with path.open('rb') as f:
  while True:
   g=e.codes_grib_new_from_file(f)
   if g is None:break
   try:
    typ=e.codes_get(g,'typeOfLevel');p=e.codes_get(g,'level');n=e.codes_get(g,'shortName')
    if typ!='isobaricInhPa' or n not in ['t','r','u','v','gh'] or not 750<=p<=1000:continue
    corners=[{k:(int(x[k]) if k=='index' else float(x[k])) for k in ['lat','lon','value','index']} for x in e.codes_grib_find_nearest(g,lat,lon,npoints=4)]
    message=e.codes_get_message(g)
    rows.append({'shortName':n,'p_Pa':p*100,'date':e.codes_get(g,'dataDate'),'time':e.codes_get(g,'dataTime'),'units':e.codes_get(g,'units'),'source_message_offset':e.codes_get_message_offset(g),'source_message_bytes':len(message),'source_message_sha256':hashlib.sha256(message).hexdigest(),'corners':corners,'bilinear_value':bilinear(corners,lat,lon),'grid':{k:e.codes_get(g,k) for k in ['Ni','Nj','latitudeOfFirstGridPointInDegrees','longitudeOfFirstGridPointInDegrees','iDirectionIncrementInDegrees','jDirectionIncrementInDegrees']}})
   finally:e.codes_release(g)
 return {'decoder':{'eccodes_python':importlib.metadata.version('eccodes'),'eccodes_library':e.codes_get_api_version()},'rows':rows}
def main():
 O.mkdir(exist_ok=False);history=B/'udm37-sterling-interior-day-v1/host/wrfout_d01_2016-10-06_00:00:00';inp=B/'udm37-sterling-interior-real-v1/encoded/wrfinput_d01';bdy=inp.with_name('wrfbdy_d01');w=B/'udm37-sterling-interior-wps-v3';src=B/'udm37-sterling-interior-inputs-v1'
 with tarfile.open(P.parent/'sterling-interior-day-evaluation/saved/evidence.tar.gz','r:gz') as t:old=json.loads(t.extractfile('extract/extracted.json').read())
 hp=pin(history);require(hp['sha256']==old['model']['history']['sha256'],'not qualified PR202 cold')
 models=[];transect=[]
 with Dataset(history) as d:
  d.set_auto_maskandscale(False);times=chartostring(d['Times'][:]).tolist();require(d['XLAT'].shape[1:]==(143,90),'grid shape')
  for hour in PLAN['model_hours_UTC']:
   require(times[hour]==ts(hour),'history time index');row=fields(d,hour,J,I);row.update(hour_UTC=hour,time_UTC=ts(hour));models.append(row)
  for hour in [11,12,15,17,18]:
   for ii,jj in PLAN['transect_i_j_one_based']:
    row=fields(d,hour,jj-1,ii-1);row.update(hour_UTC=hour,i_j_one_based=[ii,jj]);transect.append(row)
  boundary_wind=[]
  sites={'XS':(0,J),'XE':(89,J),'YS':(I,0),'YE':(I,142)}
  for hour in [0,6,11,12,15,17,18]:
   for side,(i,j) in sites.items():
    face=d['U'][hour,:,j,0 if side=='XS' else 90] if side in ['XS','XE'] else d['V'][hour,:,0 if side=='YS' else 143,i]
    boundary_wind.append({'side':side,'hour_UTC':hour,'i_j_mass_projection_one_based':[i+1,j+1],'inward_normal_grid_velocity_m_s':(np.asarray(face,float)*(1 if side in ['XS','YS'] else -1)).tolist(),'scope':'actual history boundary face grid-normal velocity; positive into domain, not a measured parcel trajectory or integrated scalar flux'})
 lat,lon=models[0]['lat_lon'];forcing=[]
 for hour in PLAN['source_hours_UTC']:
  gr=src/'grib/matthew'/('fnl_'+ts(hour)[:10].replace('-','')+'_'+ts(hour)[11:13]+'_00.grib2');im=src/'intermediate'/('FILE:'+ts(hour)[:13]);met=w/('met_em.d01.'+ts(hour)+'.nc')
  gs=grib(gr,lat,lon);ints=intermediate(im,lat,lon)
  with Dataset(met) as d:
   d.set_auto_maskandscale(False);p=np.asarray(d['PRES'][0,:,J,I],float);rows=[]
   for k in range(len(p)):
    if 75000<=p[k]<=100000:
     T=float(d['TT'][0,k,J,I]);rh=float(d['RH'][0,k,J,I]);rows.append({'record':k+1,'p_Pa':float(p[k]),'T_K':T,'source_RH_percent':rh,'qv_kg_kg_REAL_method1_diagnostic':real_qv(T,float(p[k]),rh),'z_msl_m':float(d['GHT'][0,k,J,I])})
   metdata={'pin':pin(met),'profiles':rows,'selected_lat_lon':[float(d['XLAT_M'][0,J,I]),float(d['XLONG_M'][0,J,I])],'provided_flags':{n:d.getncattr(n) for n in ['FLAG_QV','FLAG_SH','FLAG_RH'] if n in d.ncattrs()}}
  forcing.append({'hour_UTC':hour,'time_UTC':ts(hour),'GRIB_pin':pin(gr),'intermediate_pin':pin(im),'GRIB':gs,'intermediate':ints,'met_em':metdata});print('RETAINED_SOURCE_READ',hour,flush=True)
 with Dataset(inp) as d,Dataset(bdy) as b:
  d.set_auto_maskandscale(False);b.set_auto_maskandscale(False);initial=fields(d,0,J,I);c1=np.asarray(d['C1H'][0,:],float).tolist();c2=np.asarray(d['C2H'][0,:],float).tolist();records=[];valid=[]
  for side,(i,j) in sites.items():
   along=j if side in ['XS','XE'] else i;mub=float(d['MUB'][0,j,i]);raw0={n:np.asarray(b[n+'_B'+side][0,0,:,along],float).tolist() for n in ['QVAPOR','T']};raw0['MU']=float(b['MU_B'+side][0,0,along]);decoded=decode_boundary(raw0,mub,c1,c2)
   q=np.asarray(d['QVAPOR'][0,:,j,i],np.float32);thm=np.asarray(d['THM'][0,:,j,i],np.float32);mu=np.float32(d['MU'][0,j,i]);mb=np.float32(mub);c=np.asarray(c1,np.float32);c22=np.asarray(c2,np.float32);a=np.float32(np.float32(c*mu)+np.float32(c*mb+c22))
   valid.append({'side':side,'q_coupled_exact_REAL32':np.float32(q*a).astype(float).tolist()==raw0['QVAPOR'],'THM_pert_coupled_exact_REAL32':np.float32(thm*a).astype(float).tolist()==raw0['T'],'input_THM_pert_K':thm.astype(float).tolist(),'input_dry_theta_K':(np.asarray(d['T'][0,:,j,i],float)+300).tolist(),'input_qv':q.astype(float).tolist(),'decoded':decoded})
   for hour in [0,6,11,12,15,17,18,24]:
    ix=hour//6;delta=(hour%6)*3600
    raw={n:np.asarray(b[n+'_B'+side][ix,0,:,along],float).tolist() for n in ['QVAPOR','T']};raw['MU']=float(b['MU_B'+side][ix,0,along]);tend={n:np.asarray(b[n+'_BT'+side][ix,0,:,along],float).tolist() for n in ['QVAPOR','T']};tend['MU']=float(b['MU_BT'+side][ix,0,along]);applied={n:([f32(x+f32(delta*y)) for x,y in zip(raw[n],tend[n])] if n!='MU' else f32(raw[n]+f32(delta*tend[n]))) for n in raw}
    records.append({'side':side,'hour_UTC':hour,'record_start_hour':ix*6,'dtbc_s':delta,'i_j_one_based':[i+1,j+1],'lat_lon':[float(d['XLAT'][0,j,i]),float(d['XLONG'][0,j,i])],'MUB_Pa':mub,'raw_coupled':raw,'coupled_tendencies_per_second':tend,'interpolated_coupled_target':applied,'decoded':decode_boundary(applied,mub,c1,c2),'scope':'outer boundary target at native eta levels; no pressure/temperature conversion using interior pressure and no station observation error computed'})
  boundary={'C1H':c1,'C2H':c2,'coupling_validation_at_initial_time':valid,'targets':records,'history_face_wind':boundary_wind,'use_theta_m':1}
 require(all(v['q_coupled_exact_REAL32'] and v['THM_pert_coupled_exact_REAL32'] for v in valid),'boundary inverse not qualified')
 result={'base_main':PLAN['base_main'],'extractor':pin(Path(__file__)),'pid':os.getpid(),'native_read':True,'history':hp,'input':pin(inp),'boundary':pin(bdy),'forecast_namelist':pin(inp.parent.parent/'forecast.namelist.input'),'real_namelist_output':pin(inp.parent.parent/'host/namelist.output'),'selected_i_j_one_based':[37,119],'shape_j_i':[143,90],'fixed_lat_lon':[lat,lon],'model':models,'initial':initial,'transect':transect,'forcing':forcing,'boundary_data':boundary,'new_model_runs':0,'diagnostic_temperature':'REAL64 dry theta from output T+300 and f32(P+PB), Rd/cp=287/1004.5; native saturation reads REAL32. Boundary T stores coupled moist perturbationtheta, not this dry output T','CF_scope':'history CLDFRA held diagnostic, not fresh wrapper sample mask or independently retrieved cloud fraction'}
 (O/'extracted.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print('EXISTING_CHAIN_EXTRACTED',len(models),len(forcing))
if __name__=='__main__':main()
