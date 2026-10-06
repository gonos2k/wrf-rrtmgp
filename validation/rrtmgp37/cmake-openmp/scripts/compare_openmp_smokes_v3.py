"""Strict raw-byte and metadata comparison for the OpenMP smoke arms."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
from netCDF4 import Dataset
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP'); DEFAULT=ROOT/'build/udm-cmake-openmp-full/runtime-preflight-v3'
def raw(v):
 a=np.asarray(v)
 if a.dtype.kind=='O':return (str(a.dtype),a.shape,repr(v).encode())
 return (str(a.dtype),a.shape,a.tobytes())
def check_var(v,a,label):
 if a.dtype.kind=='f' and not np.isfinite(a).all():raise RuntimeError(f'{label}: nonfinite value')
 if a.dtype.kind in 'fiu':
  for at in ('_FillValue','missing_value'):
   if at not in v.ncattrs():continue
   for fv in np.asarray(v.getncattr(at)).reshape(-1):
    mask=np.isnan(a) if a.dtype.kind=='f' and np.isnan(fv) else a==fv
    if np.any(mask):raise RuntimeError(f'{label}: raw fill/missing value')
  v.set_auto_maskandscale(True)
  decoded=np.ma.asarray(v[:])
  if np.ma.getmaskarray(decoded).any():raise RuntimeError(f'{label}: decoded netCDF mask')
  if a.dtype.kind=='f' and not np.isfinite(np.ma.getdata(decoded)).all():raise RuntimeError(f'{label}: decoded nonfinite value')
  v.set_auto_maskandscale(False)
def compare(xp,yp):
 dif=[];cnt={'variables':0,'numeric_values':0,'attributes':0}
 with Dataset(xp) as x,Dataset(yp) as y:
  x.set_auto_maskandscale(False);y.set_auto_maskandscale(False)
  if set(x.dimensions)!=set(y.dimensions):dif.append('dimension names')
  for n in sorted(set(x.dimensions)&set(y.dimensions)):
   if (len(x.dimensions[n]),x.dimensions[n].isunlimited())!=(len(y.dimensions[n]),y.dimensions[n].isunlimited()):dif.append('dimension:'+n)
  if set(x.variables)!=set(y.variables):dif.append('variable names')
  if set(x.ncattrs())!=set(y.ncattrs()):dif.append('global attribute names')
  for n in sorted(set(x.ncattrs())&set(y.ncattrs())):
   cnt['attributes']+=1
   if raw(x.getncattr(n))!=raw(y.getncattr(n)):dif.append('global attribute:'+n)
  for n in sorted(set(x.variables)&set(y.variables)):
   a,b=x[n],y[n];cnt['variables']+=1
   if a.dtype!=b.dtype or a.dimensions!=b.dimensions or a.shape!=b.shape:dif.append('layout:'+n);continue
   if set(a.ncattrs())!=set(b.ncattrs()):dif.append('attribute names:'+n)
   for attr in sorted(set(a.ncattrs())&set(b.ncattrs())):
    cnt['attributes']+=1
    if raw(a.getncattr(attr))!=raw(b.getncattr(attr)):dif.append('attribute:'+n+':'+attr)
   av,bv=np.asarray(a[:]),np.asarray(b[:]);check_var(a,av,n);check_var(b,bv,n)
   if av.dtype.kind in 'fiu':cnt['numeric_values']+=av.size
   if av.tobytes()!=bv.tobytes():dif.append('array bytes:'+n)
 return {'left':str(xp),'right':str(yp),'status':'BITWISE_EQUAL' if not dif else 'DIFFERENT','counts':cnt,'differences':dif}
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=DEFAULT);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 pairs=[('ra37-omp1-tiles2','ra37-omp2-tiles2'),('ra37-omp2-tiles2','ra37-omp2-probe-tiles2')]
 result={'schema':'WRF_GNU_CMAKE_OPENMP_SMOKE_COMPARE_V3','executed_comparator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'pairs':[]}
 for left,right in pairs:
  paths=[]
  for arm in (left,right):
   c=a.root/arm;rr=c/'runtime-result.json'
   if not rr.is_file() or json.loads(rr.read_text()).get('status')!='PASS':raise SystemExit(f'run receipt not PASS: {rr}')
   h=sorted((c/'run').glob('wrfout_d01_*'))
   if len(h)!=1:raise SystemExit(f'expect one history: {c}')
   paths.append(h[0])
  result['pairs'].append(compare(*paths))
 result['status']='PASS' if all(x['status']=='BITWISE_EQUAL' for x in result['pairs']) else 'DIFFERENCES'
 if a.output.exists():raise SystemExit('refusing to overwrite comparison output')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print(result['status'],a.output)
 if result['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
