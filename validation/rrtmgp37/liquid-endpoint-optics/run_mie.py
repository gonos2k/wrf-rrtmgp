#!/usr/bin/env python3
"""Actual independent calculation; not run by the stdlib saved-evidence CI."""
from pathlib import Path
import os,sys,json,math,hashlib,time,importlib.util,concurrent.futures
os.environ['MIEPYTHON_USE_JIT']='1'
for n in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[n]='1'
ROOT=Path(__file__).resolve().parents[3];BUILD=ROOT.parent
sys.path.insert(0,str(BUILD/'deps/miepython-3.2.0'))
import miepython as mie,numpy as np,scipy.integrate as it,netCDF4
from numpy.polynomial.legendre import leggauss
PACKAGE=Path(__file__).resolve().parent
WATER=BUILD/'udm37-matched-optics-inputs/Segelstein.yml'
OUT=BUILD/'udm37-endpoint-mie-v1'
def load_data():
 a=[]
 for l in WATER.read_text().splitlines():
  try:
   v=list(map(float,l.split()))
   if len(v)==3:a.append(v)
  except ValueError:pass
 return np.array(a)
DATA=load_data()
def calc(task):
 ph,band,reff,nr,ns=task
 with netCDF4.Dataset(ROOT/f'WRF/run/rrtmgp-clouds-{ph}-bnd.nc') as d:lo,hi=map(float,d['bnd_limits_wavenumber'][band-1])
 x,w=leggauss(ns);nu=(lo+hi)/2+(hi-lo)/2*x;wav=1e4/nu
 if min(wav)<DATA[0,0] or max(wav)>DATA[-1,0]:raise ValueError('RI extrapolation')
 m=np.interp(wav,DATA[:,0],DATA[:,1])-1j*np.exp(np.interp(wav,DATA[:,0],np.log(DATA[:,2])))
 gx=np.linspace(0,80,nr+1);area=gx**9*np.exp(-gx)/math.gamma(10);radius=gx*reff/10
 f=3/(4*1000*reff*1e-6)/1000;mom=[]
 for L,M in zip(wav,m):
  qe,qs,_,g=mie.efficiencies_mx(M,2*np.pi*radius[1:]/L)
  z=[it.simpson(area*np.r_[0,qe],x=gx),it.simpson(area*np.r_[0,qs],x=gx),it.simpson(area*np.r_[0,qe-qs],x=gx),it.simpson(area*np.r_[0,qs*g],x=gx)]
  mom.append(z)
 T=5780 if ph=='sw' else 298.15;weights=w*nu**3/np.expm1(1.438776877*nu/T);z=f*np.average(mom,weights=weights,axis=0)
 return {'phase':ph,'band':band,'reff_um':reff,'nr':nr,'ns':ns,**dict(zip(['ext','sca','abs','sca_g'],map(float,z))),'g':float(z[3]/z[1]),'wavenumber_cm_1':[lo,hi]}
def converged(a,b):
 return all(abs(a[k]-b[k])<=.01*max(abs(b[k]),1e-8) for k in ['ext','sca','abs','sca_g']) and abs(a['g']-b['g'])<=.002
if __name__=='__main__':
 OUT.mkdir(exist_ok=False)
 plan=json.loads((PACKAGE/'plan.json').read_text());(OUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 assert np.allclose(mie.efficiencies_mx(1.5-.1j,2.),[1.9414784337094506,1.286167973654895,.12792139607594125,.6570830247066466],rtol=1e-10)
 sp=importlib.util.spec_from_file_location('trace_parser',ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py');p=importlib.util.module_from_spec(sp);sp.loader.exec_module(p)
 radii={'lw':{21.5},'sw':{21.5}};selected={}
 for case,ph in [('night_peak','lw'),('day_peak','lw'),('day_peak','sw')]:
  cap=BUILD/'udm37-lut-exposure-captures-v1'/case/'capture';_,i=p.trace((cap/(ph+'.input')).read_bytes(),'input')
  rows=[{'native_level':k+1,'radius_um':rr} for k,rr in enumerate(i['REL']['values']) if rr>21.5 and i['LWP']['values'][k]>0]
  selected[case+'_'+ph]=rows;radii[ph].update(row['radius_um'] for row in rows)
 records=[];metadata={'plan_sha256':hashlib.sha256((PACKAGE/'plan.json').read_bytes()).hexdigest(),'water_sha256':hashlib.sha256(WATER.read_bytes()).hexdigest(),'miepython_version':mie.__version__,'selected':selected,'records':records,'production_accepted':False}
 tasks=[(ph,b,r,512,48) for ph in radii for b in range(1,17 if ph=='lw' else 15) for r in sorted(radii[ph])]
 with concurrent.futures.ProcessPoolExecutor(max_workers=6) as pool:
  for row in pool.map(calc,tasks):
   records.append({'phase':row['phase'],'band':row['band'],'reff_um':row['reff_um'],'grids':[row]})
  (OUT/'result.json').write_text(json.dumps(metadata,indent=2)+'\n');print('coarse complete',len(records),flush=True)
  pending=records
  for nr,ns in [(1024,96),(2048,192),(4096,384)]:
   new=[]
   tasks=[(r['phase'],r['band'],r['reff_um'],nr,ns) for r in pending]
   for rec,row in zip(pending,pool.map(calc,tasks)):
    rec['grids'].append(row);rec['converged']=converged(rec['grids'][-2],row)
    if not rec['converged']:new.append(rec)
   print(nr,ns,'remaining',len(new),flush=True);(OUT/'result.json').write_text(json.dumps(metadata,indent=2)+'\n');pending=new
   if not pending:break
 metadata['all_coefficients_converged']=all(r['converged'] for r in records)
 (OUT/'result.json').write_text(json.dumps(metadata,indent=2)+'\n');print('MIE_COMPLETE',metadata['all_coefficients_converged'],flush=True)
