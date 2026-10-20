#!/usr/bin/env python3
"""Group actual LW fluxes only on common physical wavenumber intervals."""
from pathlib import Path
import importlib.util,json,math
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-clear-reference-run-v4'
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ana=load('ana',R/'validation/rrtmgp37/same-state-engines/analyze_saved.py');ang=load('ang',R/'validation/rrtmgp37/bon-night-common-angle/analysis/angular_reference.py')
_,e=ana.parse4(next((O/'legacy_source/export4').glob('*.txt')).read_bytes())
def f(n):
 z=e['CLOUD' if n.startswith('BAND_') else 'GAS',n];return np.asarray(z['values']).reshape(z['shape'],order='F')
lo4=f('BAND_WAVENUM_LO');hi4=f('BAND_WAVENUM_HI')
with Dataset(R/'WRF/run/rrtmgp-gas-lw-g128.nc') as d:
 bounds=np.asarray(d['bnd_limits_gpt'][:]);bands=np.asarray(d['bnd_limits_wavenumber'][:])
ls=(O/'lw/source.dat').read_text().splitlines();nl,ng=map(int,ls[0].split());tau=np.fromstring(ls[1],sep=' ').reshape(nl,ng,order='F');lay=np.fromstring(ls[2],sep=' ').reshape(nl,ng,order='F');lev=np.fromstring(ls[3],sep=' ').reshape(nl+1,ng,order='F');surf=np.fromstring(ls[4],sep=' ')
em=float((O/'lw/input.dat').read_text().splitlines()[7].split()[0]);up37=[];dn37=[]
for a,b in bounds:
 sel=slice(a-1,b);u,d=ang.transfer(.6096748751,tau[:,sel],lay[:,sel],lev[:,sel],surf[sel],np.full(b-a+1,em));up37.append(u);dn37.append(d)
u4=f('RTE_BAND_UP_NATIVE')*f('RTE_DELWAVE')[:,None]*float(f('RTE_FLUXFAC')[0]);d4=f('RTE_BAND_DN_NATIVE')*f('RTE_DELWAVE')[:,None]*float(f('RTE_FLUXFAC')[0])
up37=np.asarray(up37);dn37=np.asarray(dn37)
common=sorted(set(bands.ravel()).intersection(set(lo4)|set(hi4)));assert common[0]==10 and common[-1]==3250
rows=[]
for a,b in zip(common[:-1],common[1:]):
 i=np.where((bands[:,0]>=a)&(bands[:,1]<=b))[0];j=np.where((lo4>=a)&(hi4<=b))[0]
 assert len(i) and len(j) and sum(bands[i,1]-bands[i,0])==b-a and sum(hi4[j]-lo4[j])==b-a
 rows.append({'wavenumber_cm_1':[float(a),float(b)],'bands37_one_based':(i+1).tolist(),'bands4_one_based':(j+1).tolist(),'native_top_DN37':float(dn37[i,59].sum()),'native_top_DN4':float(d4[j,59].sum()),'native_top_DN37_minus4':float(dn37[i,59].sum()-d4[j,59].sum())})
summary=json.loads((O/'analysis.json').read_text());fref=summary['conditional_reference'];f37=summary['upstream_one_angle'];f4=summary['legacy4']
def diff(a,b):
 return {k:([x-y for x,y in zip(a[k],b[k])] if isinstance(a[k],list) else a[k]-b[k]) for k in a}
summary['LW_difference_decomposition']={'one37_minus_angular_reference':diff(f37,fref),'angular_reference_minus_4':diff(fref,f4),'one37_minus4':diff(f37,f4),'physical_accuracy':'NOT_APPROVED; angular reference inherits 37 gas optical/source and layer definitions'}
summary['common_physical_band_upper_DN']=rows
summary['legacy_band_sum_residual_W_m2']=float(max(abs(d4.sum(axis=0)-np.asarray(ana.native4((O/'legacy_source/native4.txt').read_bytes())[1]['DN']))))
summary['vendor_control']={}
for ph in ['lw','sw']:
 vv=[np.fromstring(x,sep=' ') for x in (B/f'udm37-clear-reference-vendor-v3/{ph}/flux.dat').read_text().splitlines()]
 uv=[np.fromstring(x,sep=' ') for x in (O/ph/'flux.dat').read_text().splitlines()]
 summary['vendor_control'][ph]={'max_direct_upstream_vs_direct_vendor_flux_W_m2':float(max(np.max(abs(vv[0]-uv[0])),np.max(abs(vv[1]-uv[1]))))}
(O/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
(O/'band-arrays.json').write_text(json.dumps({'bands37':bands.tolist(),'gpoint_bounds37':bounds.tolist(),'bands4':list(zip(lo4.tolist(),hi4.tolist())),'up37':up37.tolist(),'dn37':dn37.tolist(),'up4':u4.tolist(),'dn4':d4.tolist()},indent=2)+'\n')
print('COMMON_PHYSICAL_BANDS',json.dumps(sorted(rows,key=lambda r:abs(r['native_top_DN37_minus4']),reverse=True)[:4],indent=2))
