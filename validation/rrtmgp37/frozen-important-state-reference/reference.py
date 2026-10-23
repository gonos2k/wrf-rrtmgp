"""One actual ice-Ih state; independent kernel and number-PSD quadrature."""
from pathlib import Path
import os,sys,json,hashlib,math,time
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-frozen-important-reference-v2'
os.environ['MIEPYTHON_USE_JIT']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['NUMBA_CACHE_DIR']=str(B/'udm37-frozen-reference-numba-cache-3.0.2')
sys.path.insert(0,str(B/'udm37-frozen-independent-deps-v1'))
import numpy as np
import miepython
from miepython.mie_nojit import _single_sphere_py
from numpy.polynomial.legendre import leggauss
from concurrent.futures import ProcessPoolExecutor,as_completed
ICE_PATH=B/'udm37-frozen-planck-coverage-v1/inputs/IOP_2008_ASCIItable.dat';ICE=np.loadtxt(ICE_PATH)
assert hashlib.sha256(ICE_PATH.read_bytes()).hexdigest()=='891d0e0690cc6c6ed2dfe81291fa20a3af177fa85ef93127c58c5f86d3c370af'
assert miepython.__version__=='3.0.2'
TARGET=json.loads((B/'udm37-frozen-selected-selection-v1/target.json').read_text());SLOPE=TARGET['lambda_m_1'];TEMP=TARGET['temperature_K'];RHO=912.
BOUNDS=[[10,250],[250,500],[500,630],[630,700],[700,820],[820,980],[980,1080],[1080,1180],[1180,1390],[1390,1480],[1480,1800],[1800,2080],[2080,2250],[2250,2390],[2390,2680],[2680,3250]]

def index(nu):
 z=np.log(1e4/np.asarray(nu));grid=np.log(ICE[:,0]);return np.interp(z,grid,ICE[:,1])-1j*np.exp(np.interp(z,grid,np.log(ICE[:,2])))

def spectral(band,degree):
 lo,hi=BOUNDS[band-1];knots=np.sort(1e4/ICE[:,0]);cuts=np.r_[lo,knots[(knots>lo)&(knots<hi)],hi]
 q,w=leggauss(degree);nu=np.concatenate([(a+b)/2+(b-a)/2*q for a,b in zip(cuts[:-1],cuts[1:])]);weights=np.concatenate([(b-a)/2*w for a,b in zip(cuts[:-1],cuts[1:])]);return nu,weights

def integrate(task):
 band,nr,nv=task;start=time.monotonic();q,w=leggauss(nr);lo,hi=math.log(1e-6),math.log(40.);y=(lo+hi)/2+(hi-lo)/2*q;u=np.exp(y);D=u/SLOPE;dD=(hi-lo)/2*w*D
 number=np.exp(-SLOPE*D);cross=math.pi*D**2/4;mass_exact=math.pi*RHO/SLOPE**4
 coefficient_weights=number*cross*dD/mass_exact
 numerical_mass=float(np.sum(number*(math.pi*RHO*D**3/6)*dD))
 nu,sw=spectral(band,nv);m=index(nu);mono=[];min_abs=math.inf
 for value,z in zip(nu,m):
  x=math.pi*D*100.*value;ext,sca,back,g=miepython.efficiencies_mx(z,x);absorb=ext-sca
  if not all(np.all(np.isfinite(v)) for v in [ext,sca,g]) or np.min(absorb)<0:raise ValueError('nonfinite or negative independent efficiencies; no clipping')
  min_abs=min(min_abs,float(np.min(absorb)))
  mono.append([float(np.sum(coefficient_weights*v)) for v in [ext,sca,absorb,sca*g]])
 mono=np.asarray(mono);c2=6.62607015e-34*299792458/1.380649e-23*100.;planck=nu**3/np.expm1(c2*nu/TEMP);weights=sw*planck;norm=float(np.sum(weights));avg=np.sum(mono*weights[:,None],axis=0)/norm
 return {'band':band,'radius_nodes':nr,'spectral_degree':nv,'spectral_nodes':len(nu),'lambda_m_1':SLOPE,'temperature_K':TEMP,'mass_quadrature_relative_difference':numerical_mass/mass_exact-1,'nu_cm_1':nu.tolist(),'spectral_weights_cm_1':sw.tolist(),'planck_shape':planck.tolist(),'monochromatic_kappa_m2_kg':mono.tolist(),'moments_m2_kg':dict(zip(['ext','sca','abs','sca_g'],map(float,avg))),'minimum_Qabs':min_abs,'elapsed_seconds':time.monotonic()-start}

def main():
 O.mkdir(exist_ok=False);(O/'tasks').mkdir();parity=[]
 for nu in [30.,1100.,3100.]:
  z=complex(index(nu))
  for u in [1.,4.,20.]:
   x=math.pi*u/SLOPE*100*nu;got=np.asarray(miepython.efficiencies_mx(z,x));ref=np.asarray(_single_sphere_py(z,x,0));delta=float(np.max(np.abs(got-ref)))
   if not np.allclose(got,ref,rtol=2e-9,atol=2e-9):raise ValueError('actual-state JIT/non-JIT parity')
   parity.append({'nu_cm_1':nu,'u':u,'x':x,'n':z.real,'k_positive':-z.imag,'JIT':got.tolist(),'non_JIT':ref.tolist(),'max_absolute_difference':delta})
 result={'state':TARGET,'definition':'same ice-Ih homogeneous sphere, exponential diameter PSD; n_env1, density912; Planck thin moments','miepython_version':miepython.__version__,'actual_state_JIT_nonJIT_parity':parity,'u_range':[1e-6,40.],'geometric_area_upper_tail_fraction':math.exp(-40)*(40**2+2*40+2)/2,'geometric_mass_upper_tail_fraction':math.exp(-40)*(40**3+3*40**2+6*40+6)/6,'tail_is_certified_optical_error_bound':False,'coefficient_numerical_screen':.01,'physical_tolerance':None,'records':[],'completed':False,'physical_accuracy_approved':False}
 cache={};pending=list(range(1,17))
 for nr,nv in [(512,8),(1024,16),(2048,32)]:
  todo=[(b,r,v) for b in pending for r,v in [(nr,nv),(nr//2,nv),(nr,nv//2)] if (b,r,v) not in cache]
  with ProcessPoolExecutor(max_workers=4) as pool:
   futures={pool.submit(integrate,t):t for t in todo}
   for fut in as_completed(futures):
    key=futures[fut];row=fut.result();cache[key]=row;(O/'tasks'/('%02d-r%d-v%d.json'%key)).write_text(json.dumps(row,indent=2)+'\n');print('COMPLETED',key,'s',round(row['elapsed_seconds'],2),flush=True)
  remaining=[]
  for b in pending:
   fine=cache[b,nr,nv];rh=cache[b,nr//2,nv];vh=cache[b,nr,nv//2];a=fine['moments_m2_kg']['abs'];dr=abs(a-rh['moments_m2_kg']['abs'])/abs(a);dv=abs(a-vh['moments_m2_kg']['abs'])/abs(a)
   record=next((r for r in result['records'] if r['band']==b),None)
   if record is None:record={'band':b,'levels':[]};result['records'].append(record)
   record['levels'].append({'radius_nodes':nr,'spectral_degree':nv,'fine':fine,'radius_half':rh,'spectral_half':vh,'absorption_radius_relative_change':dr,'absorption_spectral_relative_change':dv,'qualified_numerical_axes':dr<=.01 and dv<=.01})
   record['qualified_numerical_axes']=dr<=.01 and dv<=.01
   if not record['qualified_numerical_axes']:remaining.append(b)
  pending=remaining;result['records'].sort(key=lambda r:r['band']);(O/'result.json').write_text(json.dumps(result,indent=2)+'\n')
  if not pending:break
 result['completed']=True;result['all_numerical_axes_qualified']=not pending;result['remaining_unqualified_bands']=pending
 result['source_pins']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ICE_PATH,B/'udm37-frozen-independent-deps-v1/miepython/core.py',B/'udm37-frozen-independent-deps-v1/miepython/mie_jit.py',B/'udm37-frozen-independent-deps-v1/miepython/mie_nojit.py']}
 (O/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('REFERENCE_COMPLETE',not pending,flush=True)
if __name__=='__main__':main()
