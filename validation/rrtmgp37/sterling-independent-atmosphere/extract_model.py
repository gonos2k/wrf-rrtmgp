"""Read the existing qualified PR202 cold output, not a new forecast."""
from pathlib import Path
import numpy as np,json,hashlib,datetime as dt,os,tarfile,gzip,io
from netCDF4 import Dataset,chartostring
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-independent-atmosphere-analysis-v1'
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return {'path':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()}
def main():
 O.mkdir(exist_ok=False);file=B/'udm37-sterling-interior-day-v1/host/wrfout_d01_2016-10-06_00:00:00';pinned=pin(file)
 with tarfile.open(P.parent/'sterling-interior-day-evaluation/saved/evidence.tar.gz','r:gz') as t:prior=json.loads(t.extractfile('extract/extracted.json').read())
 assert pinned['sha256']==prior['model']['history']['sha256'];rows=[]
 with Dataset(file) as d:
  d.set_auto_maskandscale(False);times=chartostring(d['Times'][:]).astype(str).tolist();j,i=118,36;lat,lon=float(d['XLAT'][0,j,i]),float(d['XLONG'][0,j,i]);assert d['XLAT'].shape[1:]==(143,90) and [lat,lon]==[prior['grid']['latitude'][j][i],prior['grid']['longitude'][j][i]]
  for hour in [0,12,17,18,19,20,24]:
   pres=np.asarray(np.float32(d['P'][hour,:,j,i]+d['PB'][hour,:,j,i]),float);theta=np.asarray(d['T'][hour,:,j,i],float)+300;temp=theta*(pres/100000)**(287/1004.5)
   z=np.asarray(np.float32(d['PH'][hour,:,j,i]+d['PHB'][hour,:,j,i]),float)/float(np.float32(9.81));hgt=float(d['HGT'][hour,j,i]);co=float(d['COSALPHA'][hour,j,i]);si=float(d['SINALPHA'][hour,j,i])
   u=(np.asarray(d['U'][hour,:,j,i],float)+np.asarray(d['U'][hour,:,j,i+1],float))/2;v=(np.asarray(d['V'][hour,:,j,i],float)+np.asarray(d['V'][hour,:,j+1,i],float))/2
   raw={n:np.asarray(d[n][hour,:,j,i],float).tolist() for n in ['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL','CLDFRA']}
   profiles=[{'record':k+1,'p_Pa':float(pres[k]),'T_K':float(temp[k]),'dry_theta_K':float(theta[k]),'qv_kg_kg':raw['QVAPOR'][k],'z_msl_m':float((z[k]+z[k+1])/2),'z_agl_m':float((z[k]+z[k+1])/2-hgt),'layer_interfaces_agl_m':[float(z[k]-hgt),float(z[k+1]-hgt)],'wind_u_east_m_s':float(u[k]*co-v[k]*si),'wind_v_north_m_s':float(v[k]*co+u[k]*si),'QCLOUD':raw['QCLOUD'][k],'QRAIN':raw['QRAIN'][k],'CLDFRA_held_diagnostic':raw['CLDFRA'][k]} for k in range(44)]
   surface={n:float(d[n][hour,j,i]) for n in ['T2','Q2','PSFC','PBLH','U10','V10','HGT']};surface['U10_east']=surface['U10']*co-surface['V10']*si;surface['V10_north']=surface['V10']*co+surface['U10']*si
   rows.append({'hour_UTC':hour,'time_UTC':times[hour].replace('_','T')+'+00:00','surface':surface,'profiles':profiles,'original_native_water_CF_profiles':raw})
 result={'history':pinned,'source':pin(Path(__file__)),'native_read':True,'pid':os.getpid(),'selected_i_j_one_based':[37,119],'shape_j_i':[143,90],'selected_lat_lon':[lat,lon],'profiles':rows,'conversion':'P+PB added in nativefloat32; diagnostic T=(dry perturbed theta+300)*(p/100000)^(287/1004.5) inREAL64 then native saturation helper readsREAL32; geometric interfaces from nativefloat32PH+PHB/nativeg. No assertion of bit-identical earlier radiation-call T or MUT. U/V destaggered and rotated toEarth components with nativeCOS/SIN alpha','new_model_runs':0}
 (O/'model-profiles.json').write_text(json.dumps(result,indent=2)+'\n');print('EXISTING_COLD_NATIVE_PROFILES_EXTRACTED',len(rows))
if __name__=='__main__':main()
