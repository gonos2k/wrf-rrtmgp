#!/usr/bin/env python3
"""Execute pinned companion integrations with a definition matched to PR183."""
from pathlib import Path
import os,sys,json,math,hashlib,importlib.util,types,functools,concurrent.futures,time
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
os.environ['MIEPYTHON_USE_JIT']='1'
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;OUT=B/'udm37-matched-reference-v1'
sys.path.insert(0,str(B/'deps/miepython-3.2.0'))
import miepython as mie,numpy as np,scipy.special as sp,scipy.stats as stats,netCDF4
SRC={'optics.py':Path('/tmp/firstapp_gfdl_optics.py'),'spec_util.py':Path('/tmp/firstapp_gfdl_spec_util.py')}
EXPECTED={'optics.py':'9ca85be38321228ee36a50d726015b3e4145af86a68c069a5376d1bb754c02ea','spec_util.py':'199e2b703ee9ea147d71e7e1b40cb3e04025299b2f7272930e7cf2135f3c9aa1'}
WATER=B/'udm37-matched-optics-inputs/Segelstein.yml'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load_external():
 spec=importlib.util.spec_from_file_location('matched_companion.optics',OUT/'external/matched_companion/optics.py');mod=importlib.util.module_from_spec(spec);sys.path.insert(0,str(OUT/'external'));spec.loader.exec_module(mod)
 # Original constructor projects invalid optics. Require that it is a no-op.
 original=mod.optics_var.__init__
 def checked(self,r,s,v,ext,sca,ssa,asy,rau,**kw):
  if np.any(ext<0) or np.any(sca<0) or np.any(sca>ext) or np.any(ssa<0) or np.any(ssa>1) or np.any(asy<0) or np.any(asy>1):raise ValueError('companion would project optical moments')
  before=[a.copy() for a in [ext,sca,ssa,asy]];original(self,r,s,v,ext,sca,ssa,asy,rau,**kw)
  if not all(np.array_equal(x,y) for x,y in zip(before,[ext,sca,ssa,asy])):raise ValueError('unexpected constructor mutation')
 mod.optics_var.__init__=checked
 from matched_companion.spec_util import mie_coefficients,convert_lblOD_to_band
 return mod.optics_var,mie_coefficients,convert_lblOD_to_band
@functools.lru_cache(None)
def roots(n):return sp.roots_legendre(n)
def data():
 a=[]
 for line in WATER.read_text().splitlines():
  try:
   x=list(map(float,line.split()))
   if len(x)==3:a.append(x)
  except ValueError:pass
 return np.array(a)
DATA=data()
def spectral(ph,band,ns):
 with netCDF4.Dataset(R/f'WRF/run/rrtmgp-clouds-{ph}-bnd.nc') as d:lo,hi=map(float,d['bnd_limits_wavenumber'][band-1])
 knots=1e4/DATA[:,0];nu=np.unique(np.r_[np.linspace(lo,hi,ns+1),knots[(knots>lo)&(knots<hi)]])
 lam=1e4/nu;m=np.interp(lam,DATA[:,0],DATA[:,1])-1j*np.exp(np.interp(lam,DATA[:,0],np.log(DATA[:,2])))
 w=np.empty(len(nu));w[0]=(nu[1]-nu[0])/2;w[-1]=(nu[-1]-nu[-2])/2;w[1:-1]=(nu[2:]-nu[:-2])/2
 T=5780 if ph=='sw' else 298.15;source=nu**3/np.expm1(1.438776877*nu/T)
 return nu,m,w*source

def calc(task):
 ph,band,reff,nr,ns=task;optics,mie_coeff,average=load_external();nu,m,ws=spectral(ph,band,ns)
 x,w=roots(nr);x=(x+1)*40;wx=w*40;r=x*reff/10;d=2*r;dw=2*reff/10*wx;area=np.pi*r*r;vol=4*np.pi*r**3/3
 E=[];S=[];G=[]
 for v,idx in zip(nu,m):
  e,s,g=mie_coeff(np.full(nr,v),r,area,np.full(nr,idx));E.append(e);S.append(s);G.append(g)
 E=np.array(E);S=np.array(S);G=np.array(G)
 z=optics.gamma_int(nu,np.array([8.]),d,vol,area,np.array([1.6*reff]),dw,E,S,G,1e6)
 if abs(float(z.r[0])/reff-1)>1e-10:raise ValueError('effective radius mismatch')
 pdf=stats.gamma.pdf(d,8,scale=reff/5);den=np.sum(pdf*vol*dw)
 # Absorption before PSD/band cancellation; kernel Qext-Qsca remains shared.
 absorb=np.sum(pdf[None,:]*(E-S)*dw[None,:],axis=1)/den
 sg=z.sca[0]*z.asy[0]
 native=np.stack([z.ext[0],z.sca[0],absorb,sg])
 f=3/(4*1000*reff*1e-6)/1000
 q=[E/area,S/area,(E-S)/area,(S*G)/area]
 direct=np.stack([f*np.sum((x**9*np.exp(-x)/math.gamma(10)*wx)[None,:]*a,axis=1) for a in q])
 algebra=float(np.max(np.abs(native-direct)/np.maximum(np.abs(native),1e-12)))
 if algebra>1e-10:raise ValueError('number/area-Gamma formulation mismatch')
 moments={name:float(average(ws,native[i:i+1],(np.arange(len(nu)),))[0]) for i,name in enumerate(['ext','sca','abs','sca_g'])}
 return {'phase':ph,'band':band,'reff_um':reff,'nr':nr,'ns':ns,'spectral_points_with_RI_knots':len(nu),**moments,'g':moments['sca_g']/moments['sca'],'integrated_reff_um':float(z.r[0]),'same_node_relative_residual':algebra,'abs_ext_minus_sca_residual':moments['abs']-(moments['ext']-moments['sca'])}
def passes(grids):
 f=grids['fine'];return all(all(abs(f[k]-grids[axis][k])<=.01*max(abs(f[k]),1e-8) for k in ['ext','sca','abs','sca_g']) and abs(f['g']-grids[axis]['g'])<=.002 for axis in ['radius_half','spectral_half'])
if __name__=='__main__':
 OUT.mkdir(exist_ok=False);ext=OUT/'external/matched_companion';ext.mkdir(parents=True);(ext/'__init__.py').write_text('')
 for n,path in SRC.items():
  if digest(path)!=EXPECTED[n]:raise ValueError('pinned external source differs '+n)
  text=path.read_text()
  if n=='spec_util.py':
   assert text.count('nmed = 1.0003')==1 and text.count('miepython.mie(m, x)')==1
   text=text.replace('nmed = 1.0003','nmed = 1.0').replace('miepython.mie(m, x)','miepython.efficiencies_mx(m, x)')
  (ext/n).write_text(text)
 (OUT/'plan.json').write_bytes((P/'plan.json').read_bytes());metadata={'plan_sha256':digest(P/'plan.json'),'source_pin':EXPECTED,'compiled_external_sha256':{n:digest(ext/n) for n in SRC},'water_sha256':digest(WATER),'kernel':mie.__version__,'production_accepted':False,'records':[]}
 assert np.allclose(mie.efficiencies_mx(1.5-.1j,2),[1.9414784337094506,1.286167973654895,.12792139607594125,.6570830247066466],rtol=1e-10)
 # A non-vacuum convention control checks both relative index and size parameter.
 controls=[]
 for env in [1.,1.0003,1.1]:
  m=1.33-.01j;r=12.;L=1.3;a=mie.efficiencies(m,2*r,L,n_env=env);b=mie.efficiencies_mx(m/env,2*np.pi*r*env/L);assert np.allclose(a,b,rtol=1e-13,atol=1e-13);controls.append({'n_env':env,'high_level':list(map(float,a)),'relative_m_and_x':list(map(float,b))})
 metadata['medium_controls']=controls
 old=json.loads(__import__('gzip').decompress((R/'validation/rrtmgp37/liquid-endpoint-optics/saved/mie/result.json.gz').read_bytes()))
 targets=[r for r in old['records'] if (r['phase']=='lw' and r['band']==6) or (r['phase']=='sw' and r['band'] in [6,8]) or (r['phase']=='sw' and r['band']==11 and r['reff_um']==22.12519645690918) or (r['phase']=='sw' and r['band']==12 and r['reff_um']==21.5)]
 assert len(targets)==16
 records=[{'phase':r['phase'],'band':r['band'],'reff_um':r['reff_um'],'original_PR183':r['grids'][-1],'role':'weak' if r['band'] in [11,12] and r['phase']=='sw' else 'primary','levels':[]} for r in targets];metadata['records']=records
 with concurrent.futures.ProcessPoolExecutor(max_workers=6) as pool:
  pending=records
  for stage in range(2):
   tasks=[];mapping=[]
   for row in pending:
    nr,ns=(1024,256) if row['role']=='primary' else (2048,512);nr*=2**stage;ns*=2**stage
    row['levels'].append({})
    for axis,rr,ss in [('radius_half',nr//2,ns),('spectral_half',nr,ns//2),('fine',nr,ns)]:tasks.append((row['phase'],row['band'],row['reff_um'],rr,ss));mapping.append((row,axis))
   for (row,axis),v in zip(mapping,pool.map(calc,tasks)):
    row['levels'][-1][axis]=v;print(row['phase'],row['band'],row['reff_um'],axis,v['nr'],v['ns'],flush=True)
   for row in pending:row['qualified_numerical_axes']=passes(row['levels'][-1])
   (OUT/'result.json').write_text(json.dumps(metadata,indent=2)+'\n')
   pending=[r for r in pending if not r['qualified_numerical_axes']]
   print('STAGE',stage,'unqualified',len(pending),flush=True)
   if not pending:break
 metadata['completed']=True;(OUT/'result.json').write_text(json.dumps(metadata,indent=2)+'\n');print('MATCHED_REFERENCE_COMPLETE',sum(r['qualified_numerical_axes'] for r in records),len(records),flush=True)
