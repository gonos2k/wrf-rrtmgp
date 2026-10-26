"""Explicit diagnostic conventions; no forecast, tuning or process-source inference."""
from pathlib import Path
import sys,math,struct,hashlib
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
sys.path.append(str(P.parent/'sterling-independent-atmosphere'))
from parse import interpolate,require
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
PRESSURES=[97500,95000,92500,90000,87500,85000,82500,80000]
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return {'path':str(p),'bytes':p.stat().st_size,'sha256':h.hexdigest()}
def theta(T,p):return T*(100000/p)**(287/1004.5)
def real_qv(T,p,rh):
 """REAL rh_to_mxrat1 liquid formula, REAL64 diagnostic, not native REAL replay.

 RH scales vapor pressure, not the already converted saturated mixing ratio.
 """
 require(T>0 and p>0 and math.isfinite(rh),'invalid source humidity')
 e=.01*min(100,max(0,rh))*611.2*math.exp(17.67*(T-273.15)/(T-29.65))
 return max(.622*e/(p-e),1e-6) if e<p else 1e-6
def bilinear(corners,lat,lon):
 lon=lon%360;la=sorted({x['lat'] for x in corners});lo=sorted({x['lon']%360 for x in corners})
 require(len(corners)==4 and len(la)==len(lo)==2 and la[0]<=lat<=la[1] and lo[0]<=lon<=lo[1],'not a surrounding rectilinear stencil')
 value=0.
 for x in corners:
  w=(lat-la[0])/(la[1]-la[0]) if x['lat']==la[1] else (la[1]-lat)/(la[1]-la[0])
  w*= (lon-lo[0])/(lo[1]-lo[0]) if x['lon']%360==lo[1] else (lo[1]-lon)/(lo[1]-lo[0])
  value+=w*x['value']
 return value
def decode_boundary(raw,mub,c1h,c2h):
 """Inverse the actual REAL scalar coupling; THM differs from dry theta."""
 require(len(raw['QVAPOR'])==len(raw['T'])==len(c1h)==len(c2h),'boundary dimensions')
 rows=[]
 for k,(q,t) in enumerate(zip(raw['QVAPOR'],raw['T'])):
  a=c1h[k]*raw['MU']+(c1h[k]*mub+c2h[k]);require(a>0,'nonpositive pressure coupling')
  qv=q/a;thm=t/a+300;dry=thm/(1+(461.6/287)*qv)
  rows.append({'record':k+1,'pressure_coupling_Pa':a,'qv_kg_kg':qv,'moist_theta_K':thm,'dry_theta_K':dry})
 return rows
