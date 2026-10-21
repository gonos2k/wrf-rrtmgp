#!/usr/bin/env python3
"""Explicit coupled dry-number boundary conversion, and exact-zero real producer.

No nonzero volume number is inferred from legacy files. For nonzero data, call
coupled_volume_endpoints with independently declared endpoint n, rho_d and mass
factor arrays. Native boundary interpolation is linear in S, not n or eta.
The CLI reuses PR187's stricter exact-zero real dataset path only.
"""
from pathlib import Path
import argparse,importlib.util,json
import numpy as np

def coupled_eta_endpoints(eta0,eta1,a0,a1,seconds):
 eta0,eta1,a0,a1=np.broadcast_arrays(*[np.asarray(x,dtype=np.float64) for x in (eta0,eta1,a0,a1)])
 if not all(np.isfinite(x).all() for x in (eta0,eta1,a0,a1)) or min(float(np.min(a0)),float(np.min(a1)))<=0 or min(float(np.min(eta0)),float(np.min(eta1)))<0:
  raise ValueError('finite nonnegative eta and positive native mass factors required')
 if not np.isfinite(seconds) or seconds<=0:raise ValueError('positive time interval required')
 s0=a0*eta0;s1=a1*eta1
 if not np.isfinite(s0).all() or not np.isfinite(s1).all():raise ValueError('nonfinite coupled endpoint')
 return s0,(s1-s0)/seconds

def coupled_volume_endpoints(n0,n1,rho0,rho1,a0,a1,seconds):
 n0,n1,rho0,rho1=np.broadcast_arrays(*[np.asarray(x,dtype=np.float64) for x in (n0,n1,rho0,rho1)])
 if not all(np.isfinite(x).all() for x in (n0,n1,rho0,rho1)) or min(float(np.min(rho0)),float(np.min(rho1)))<=0:
  raise ValueError('finite volume number and positive endpoint dry densities required')
 return coupled_eta_endpoints(n0/rho0,n1/rho1,a0,a1,seconds)

def write_volume_series(boundary,field,side,n_endpoints,rho_endpoints,a_endpoints,endpoint_times):
 """Write one complete native NC/NR side series from explicit endpoint states.

 Requires N+1 states for N stored records, including the last tendency endpoint.
 Density and full native mass factor are supplied, never inferred from filenames.
 Condensate endpoints in the existing file must be positive wherever number is.
 """
 from netCDF4 import Dataset
 from datetime import datetime
 if field not in ('QNCLOUD','QNRAIN') or side not in ('XS','XE','YS','YE'):raise ValueError('cloud/rain side required')
 fmt='%Y-%m-%d_%H:%M:%S';times=[datetime.strptime(str(t),fmt) for t in endpoint_times]
 dt=np.asarray([(b-a).total_seconds() for a,b in zip(times,times[1:])])
 if not len(dt) or np.any(dt<=0):raise ValueError('strictly increasing endpoint times required')
 n,rho,a=np.broadcast_arrays(*[np.asarray(x,dtype=np.float64) for x in (n_endpoints,rho_endpoints,a_endpoints)])
 if n.shape[0]!=len(times):raise ValueError('N+1 endpoint states required')
 value=[];slope=[]
 for k,seconds in enumerate(dt):
  v,t=coupled_volume_endpoints(n[k],n[k+1],rho[k],rho[k+1],a[k],a[k+1],seconds);value.append(v);slope.append(t)
 value=np.asarray(value);slope=np.asarray(slope)
 with Dataset(boundary,'r+') as d:
  tags=[np.asarray(getattr(d,key,0)) for key in ['UDM_SPECIFIED_NUMBER_CONTRACT','UDM_NUMBER_POLICY']]
  if any(x.shape!=() or x.dtype.kind not in 'iu' or int(x)!=1 for x in tags):raise ValueError('explicit integer S_eta contract required')
  file_times=[b''.join(x).decode() for x in np.asarray(d['Times'][:])]
  if file_times!=list(endpoint_times[:-1]):raise ValueError('endpoint times differ from actual boundary records')
  vn=field+'_B'+side;tn=field+'_BT'+side
  if value.shape!=d[vn].shape or slope.shape!=d[tn].shape:raise ValueError('endpoint boundary dimensions differ')
  mass={'QNCLOUD':'QCLOUD','QNRAIN':'QRAIN'}[field]
  mv=np.asarray(d[mass+'_B'+side][:],dtype=float);mt=np.asarray(d[mass+'_BT'+side][:],dtype=float)
  q=np.concatenate([mv,(mv[-1]+mt[-1]*dt[-1])[None,...]],axis=0)
  if not np.isfinite(q).all() or np.any(q<0) or np.any((n>0)&(q<=0)):raise ValueError('positive number requires positive matching condensate endpoints')
  # Match native storage: first encode eta and a in REAL32, couple them,
  # then difference the stored S endpoints (including the final endpoint).
  # Differencing unrounded ideal S and rounding afterward is a different wire contract.
  eta32=(n/rho).astype('f4');a32=a.astype('f4');states32=a32*eta32
  vr=states32[:-1];tr=np.diff(states32,axis=0)/dt.astype('f4').reshape((len(dt),)+(1,)*(n.ndim-1))
  if not np.isfinite(eta32).all() or not np.isfinite(a32).all() or np.any(a32<=0) or not np.isfinite(states32).all() or not np.isfinite(tr).all():raise ValueError('nonfinite REAL32 boundary payload')
  d[vn][:]=vr;d[tn][:]=tr
  d[vn].units='Pa kg_dry-1';d[tn].units='Pa kg_dry-1 s-1'
 return {'values':vr.astype(float).tolist(),'tendencies':tr.astype(float).tolist(),'linear_interpolation':'stored S_eta','endpoint_times':list(endpoint_times)}

def produce_zero(initial,boundary,out):
 from netCDF4 import Dataset
 root=Path(__file__).resolve().parents[3]
 spec=importlib.util.spec_from_file_location('exact_zero',root/'validation/rrtmgp37/clear-reference/zero_number_input.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 report=m.produce(initial,boundary,out)
 for name in ['wrfinput_d01','wrfbdy_d01']:
  with Dataset(out/name,'r+') as d:
   d.setncattr('UDM_SPECIFIED_NUMBER_CONTRACT',np.int32(1))
   d.setncattr('UDM_BOUNDARY_SUPPORT','single serial domain; number1/population0; encoded S_eta-v1')
   d.setncattr('UDM_CLOUD_RAIN_BOUNDARY','S=(C1H*(MU+MUB)+C2H)*eta; dS/dt from coupled endpoints')
   d.setncattr('UDM_CCN_BOUNDARY','volume ccn_conc/current rho_d at inflow; eta zero-gradient outflow; QNCCN file unused')
  if m.inspect(out/name,name=='wrfbdy_d01')!=report['files'][name]:raise ValueError('number producer changed original arrays')
 report.update(boundary_runtime_support='REQUIRES_GENERAL_BUILD_S_ETA_V1',boundary_contract=1,CCN='separate constant-volume inflow/eta outflow contract; no file relaxation')
 (out/'producer.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('initial',type=Path);p.add_argument('boundary',type=Path);p.add_argument('out',type=Path);a=p.parse_args();produce_zero(a.initial,a.boundary,a.out)
