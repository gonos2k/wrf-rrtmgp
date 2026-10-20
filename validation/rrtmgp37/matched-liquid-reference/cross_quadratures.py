#!/usr/bin/env python3
"""Separate radial and spectral method corrections on the selected 16 entries."""
import json,concurrent.futures
import run_reference as r

def old_spectral(ph,band,ns):
 with r.netCDF4.Dataset(r.R/f'WRF/run/rrtmgp-clouds-{ph}-bnd.nc') as d:lo,hi=map(float,d['bnd_limits_wavenumber'][band-1])
 x,w=r.np.polynomial.legendre.leggauss(ns);nu=(lo+hi)/2+(hi-lo)*x/2;lam=1e4/nu
 m=r.np.interp(lam,r.DATA[:,0],r.DATA[:,1])-1j*r.np.exp(r.np.interp(lam,r.DATA[:,0],r.np.log(r.DATA[:,2])))
 T=5780 if ph=='sw' else 298.15
 return nu,m,w*nu**3/r.np.expm1(1.438776877*nu/T)
def calc(task):
 r.spectral=old_spectral
 return r.calc(task)
if __name__=='__main__':
 result=json.loads((r.OUT/'result.json').read_text());assert result['completed']
 tasks=[(x['phase'],x['band'],x['reff_um'],x['levels'][-1]['fine']['nr'],x['original_PR183']['ns']) for x in result['records']]
 plan={'scope':'Selected 16 combinations only. Same final new radial quadrature with original PR183 spectral nodes; no thresholds or qualifications changed.','definition_fixed':True,'decomposition':'new - old = (new - cross) + (cross - old), for signed moments. First is spectral method correction at fixed new radial integration; second includes radial method/normalization correction at fixed original spectral nodes.','tasks':tasks,'production_accepted':False}
 (r.OUT/'cross-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 with concurrent.futures.ProcessPoolExecutor(max_workers=6) as pool:
  rows=list(pool.map(calc,tasks))
 (r.OUT/'cross-result.json').write_text(json.dumps({'completed':True,'records':rows,'new_WRF_runs':0},indent=2)+'\n')
 print('CROSS_QUADRATURE_COMPLETE',len(rows))
