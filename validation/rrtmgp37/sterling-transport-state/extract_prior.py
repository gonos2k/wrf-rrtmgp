"""Read existing state/coordinates before adding the missing native face capture."""
from pathlib import Path
import json,hashlib,tarfile,os,struct
import numpy as np
from netCDF4 import Dataset,chartostring
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-transport-prior-v1'
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
RATIO=f32(f32(461.6)/287.)
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return {'path':str(p),'sha256':h.hexdigest(),'bytes':p.stat().st_size}
def main():
 O.mkdir(exist_ok=False);old=P.parent/'sterling-thermodynamic-tendencies';ident=json.loads((old/'identity.json').read_text());arc=old/'saved/evidence.tar.gz';assert pin(arc)['sha256']==ident['archive']['sha256']
 with tarfile.open(arc) as t:
  raw=t.extractfile('native/thermodynamic_operations.txt').read();previous=json.loads(t.extractfile('extract/extracted.json').read())
 neighbors=[]
 for line in raw.splitlines():
  x=line.split()
  if x[1]==b'neighbor_start':neighbors.append({'source_seconds':int(float(x[0])),'k':int(x[4]),'i':int(float(x[5])),'j':int(float(x[6])),'values':list(map(float,x[7:]))})
 assert len(neighbors)==2450
 file=Path(previous['cold_history']['path']);fp=pin(file);assert fp['sha256']==previous['cold_history']['sha256'];states=[];context=[]
 with Dataset(file) as d:
  d.set_auto_maskandscale(False);times=chartostring(d['Times'][:]).astype(str).tolist();assert d['XLAT'].shape[1:]==(143,90)
  for hour in range(12,18):
   assert times[hour]==f'2016-10-06_{hour:02d}:00:00';pressure=np.asarray(np.float32(d['P'][hour,3:13,115:122,33:40]+d['PB'][hour,3:13,115:122,33:40]),float);dry=np.asarray(d['T'][hour,3:13,115:122,33:40],float)+300;q=np.asarray(d['QVAPOR'][hour,3:13,115:122,33:40],float);qc=np.asarray(d['QCLOUD'][hour,3:13,115:122,33:40],float);eta=np.asarray(d['ZNU'][hour,3:13],float);etaw=np.asarray(d['ZNW'][hour,3:14],float);ph=np.asarray(np.float32(d['PH'][hour,3:14,115:122,33:40]+d['PHB'][hour,3:14,115:122,33:40]),float);z=ph/float(np.float32(9.81));w=np.asarray(d['W'][hour,3:14,115:122,33:40],float);hgt=np.asarray(d['HGT'][hour,115:122,33:40],float)
   for jj in range(7):
    for ii in range(7):
     rows=[]
     for kk in range(10):rows.append({'record':kk+4,'p_Pa':float(pressure[kk,jj,ii]),'dry_theta_K':float(dry[kk,jj,ii]),'qv_kg_kg':float(q[kk,jj,ii]),'QCLOUD':float(qc[kk,jj,ii]),'eta_mass':float(eta[kk]),'z_msl_m':float((z[kk,jj,ii]+z[kk+1,jj,ii])/2),'z_agl_m':float((z[kk,jj,ii]+z[kk+1,jj,ii])/2-hgt[jj,ii]),'W_lower_interface_m_s':float(w[kk,jj,ii]),'W_upper_interface_m_s':float(w[kk+1,jj,ii])})
     item={'hour_UTC':hour,'i_j_one_based':[ii+34,jj+116],'profiles':rows}
     if (ii,jj)==(3,3):states.append(item)
     context.append(item)
  variables=list(d.variables)
 result={'native_read':True,'pid':os.getpid(),'history':fp,'original_neighbor_records':neighbors,'hourly_central_states':states,'fixed_neighborhood_states':context,'history_velocity_roster':{n:n in variables for n in ['W','WW','WWM','OMEGA','U','V']},'coordinate_scope':'historydrytheta is already rounded dry T+300; source-hour PR206 neighbors contain moisttheta perturbation and staggered geometricW. No WW is invented from W','new_model_runs':0}
 (O/'prior-state-and-coordinate.json').write_text(json.dumps(result,indent=2)+'\n');print('PRIOR_STATE_COORDINATES_READ',len(neighbors),len(context))
 for h in states:
  a,b=[next(x for x in h['profiles'] if x['record']==k) for k in [7,8]];print(h['hour_UTC'],'theta8-7',b['dry_theta_K']-a['dry_theta_K'],'q8-7_gkg',1000*(b['qv_kg_kg']-a['qv_kg_kg']),'W8',a['W_upper_interface_m_s'])
if __name__=='__main__':main()
