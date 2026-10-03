#!/usr/bin/env python3
"""Prepare/run fresh GNU Make RA37/RA4 one-minute restart parity checks.

Default --prepare-only is safe. --run requires review of generated preflight pins.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, resource, shutil, subprocess, time
import numpy as np
from netCDF4 import Dataset

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
TASK=ROOT/'build/pr-wrf-rrtmgp/build/udm-cmake-export-fix/make-parity'
SRC=TASK/'source'; WRF=SRC/'WRF'; RUNROOT=TASK/'runtime-parity-v5'
TABLE=ROOT/'build/pr-wrf-rrtmgp/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
NETCDF=ROOT/'build/deps/netcdf'
CHECKPOINT='wrfrst_d01_2010-06-11_12:00:00'; HISTORY='wrfout_d01_2010-06-11_12:01:00'
PINCOMMIT='bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291'
SOURCEFILES=['WRF/CMakeLists.txt','WRF/external/rte_rrtmgp/CMakeLists.txt','WRF/phys/module_physics_init.F','WRF/phys/module_microphysics_driver.F','config/registration37.json']
CASES={
 'ra37-frozen1': {'input':ROOT/'build/udm-selected-real-audit/off-only-20261003-v1/audit-off/run','reference':ROOT/'build/udm-workspace-real-runtime/ra37-candidate/run','physics':37,'mode':1},
 'ra4-frozen0': {'input':ROOT/'build/udm-selected-real-audit/ra4-baseline-run-20261003-v1/run','reference':ROOT/'build/udm-workspace-real-runtime/ra4-candidate/run','physics':4,'mode':0},
}
MUTABLE=re.compile(r'^(wrfout_|wrfrst_|rsl\.|namelist\.output$|.*\.log$)')
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def dump(p,x): Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def source_prov():
 commit=subprocess.check_output(['git','-C',str(SRC),'rev-parse','HEAD'],text=True).strip()
 if commit!=PINCOMMIT: raise RuntimeError('source commit pin mismatch')
 return {'commit':commit,
  'diff_sha256':sha_bytes(subprocess.check_output(['git','-C',str(SRC),'diff','--binary','HEAD'])),
  'source_files_sha256':{p:sha(SRC/p) for p in SOURCEFILES},
  'configure_wrf_sha256':sha(WRF/'configure.wrf'),
  'registration_check':'PASS','compiler':subprocess.check_output(['gfortran','--version'],text=True).splitlines()[0]}
def asset_hashes(d):
 out={}
 for p in sorted(Path(d).iterdir()):
  if p.is_file() and (not MUTABLE.match(p.name) or p.name==CHECKPOINT) and p.name not in {'wrf.exe','real.exe','namelist.input'}: out[p.name]=sha(p)
 return out
def ensure_pins(r):
 base=Path(r['input_directory']); run=Path(r['run_directory']); ref=Path(r['reference_history'])
 if source_prov()!=r['source_provenance']: raise RuntimeError('source/config changed since preflight')
 exe=WRF/'main/wrf.exe'
 if sha(exe)!=r['candidate_executable_sha256']: raise RuntimeError('candidate WRF executable changed')
 if sha(run/'wrf.exe')!=r['candidate_executable_sha256']: raise RuntimeError('staged run executable changed')
 if sha(TABLE)!=r['table_sha256']: raise RuntimeError('frozen table changed')
 if sha(base/CHECKPOINT)!=r['checkpoint_sha256'] or sha(run/CHECKPOINT)!=r['checkpoint_sha256']: raise RuntimeError('checkpoint changed')
 if sha(ref)!=r['reference_history_sha256']: raise RuntimeError('reference history changed')
 if sha(Path(r['reference_run_directory'])/'wrf.exe')!=r['reference_executable_sha256']:
  raise RuntimeError('reference executable changed')
 if sha(base/'namelist.input')!=r['source_namelist_sha256']: raise RuntimeError('source namelist changed')
 if sha(run/'namelist.input')!=r['staged_namelist_sha256']: raise RuntimeError('staged namelist changed')
 if asset_hashes(base)!=r['input_assets'] or asset_hashes(run)!=r['staged_assets']: raise RuntimeError('immutable run assets changed')

def nmlfields(path):
 t=Path(path).read_text(); out={}
 for k in ['run_minutes','ra_lw_physics','ra_sw_physics','rrtmgp_udm_frozen_optics','rrtmgp_udm_frozen_table']:
  m=re.search(r'^\s*'+k+r'\s*=\s*([^\n!]+)',t,re.M|re.I)
  if not m: raise RuntimeError(f'missing {k}')
  out[k]=m.group(1).strip().rstrip(',')
 return out
def setkey(text,key,val):
 text,n=re.subn(r'^(\s*'+key+r'\s*=\s*)[^\n!]*',lambda m:m.group(1)+val,text,count=1,flags=re.M|re.I)
 if n!=1: raise RuntimeError(f'expected one {key}, found {n}')
 return text
def nml_without(path):
 t=Path(path).read_text()
 for k in ['run_minutes','rrtmgp_udm_frozen_optics','rrtmgp_udm_frozen_table']:
  t=re.sub(r'^\s*'+k+r'\s*=\s*[^\n!]*\n','',t,flags=re.M|re.I)
 return t
def setup(name,c):
 base=c['input']; refdir=c['reference']; run=RUNROOT/name/'run'; run.mkdir(parents=True)
 if sha(base/CHECKPOINT)!=sha(refdir/CHECKPOINT): raise RuntimeError(f'{name}: input/reference checkpoint differs')
 # Stage all baseline files except previous executable/output artifacts.
 for p in sorted(base.iterdir()):
  if p.is_file() and (not MUTABLE.match(p.name) or p.name==CHECKPOINT) and p.name not in {'wrf.exe','real.exe'}:
   shutil.copy2(p,run/p.name)
 nml=(base/'namelist.input').read_text()
 nml=setkey(nml,'run_minutes','1')
 nml=setkey(nml,'ra_lw_physics',str(c['physics'])); nml=setkey(nml,'ra_sw_physics',str(c['physics']))
 nml=setkey(nml,'rrtmgp_udm_frozen_optics',str(c['mode']))
 nml=setkey(nml,'rrtmgp_udm_frozen_table',("'"+str(TABLE)+"'") if c['mode']==1 else "''")
 (run/'namelist.input').write_text(nml)
 if nml_without(base/'namelist.input')!=nml_without(run/'namelist.input'): raise RuntimeError('namelist changed outside approved fields')
 shutil.copy2(WRF/'main/wrf.exe',run/'wrf.exe')
 if asset_hashes(base)!=asset_hashes(run): raise RuntimeError('staged assets mismatch')
 prov=source_prov()
 r={'case':name,'input_directory':str(base),'reference_run_directory':str(refdir),'reference_history':str(refdir/HISTORY),'run_directory':str(run),
    'source_provenance':prov,'source_commit':prov['commit'],'source_diff_sha256':prov['diff_sha256'],
    'candidate_executable':str((WRF/'main/wrf.exe')),'candidate_executable_sha256':sha(WRF/'main/wrf.exe'),
    'reference_executable_sha256':sha(refdir/'wrf.exe'),'reference_history_sha256':sha(refdir/HISTORY),
    'checkpoint_sha256':sha(base/CHECKPOINT),'table_sha256':sha(TABLE),
    'source_namelist_sha256':sha(base/'namelist.input'),'staged_namelist_sha256':sha(run/'namelist.input'),
    'source_namelist_fields':nmlfields(base/'namelist.input'),'staged_namelist_fields':nmlfields(run/'namelist.input'),
    'namelist_changes_limited_to':['run_minutes','rrtmgp_udm_frozen_optics','rrtmgp_udm_frozen_table'],
    'input_assets':asset_hashes(base),'staged_assets':asset_hashes(run),
    'expected_history':HISTORY,'expected_times':'2010-06-11_12:01:00','expected_dimensions':{'Time':1,'west_east':289,'south_north':189,'bottom_top':39},
    'comparison_contract':'require exact metadata/attrs and all array values against matching PR30 GNU Make serial reference; reject any numeric fill mask or nonfinite output',
    'status':'PREPARED_NOT_RUN'}
 dump(RUNROOT/name/'preflight.json',r)
 return r

def mask(var,a):
 m=np.zeros(a.shape,dtype=bool)
 for attr in ('_FillValue','missing_value'):
  if attr not in var.ncattrs(): continue
  vals=np.asarray(var.getncattr(attr)).reshape(-1)
  for v in vals:
   if np.issubdtype(a.dtype,np.floating) and np.isnan(v): m|=np.isnan(a)
   else: m|=a==v
 return m
def compare(candidate,reference):
 out={'status':'PASS','variables':0,'numeric_values':0,'differences':[],'attrs_different':[],
      'layout_mismatches':[],'fill_markers':[],'nonfinite':[],'bytewise_compared_arrays':0}
 with Dataset(reference) as b,Dataset(candidate) as c:
  b.set_auto_maskandscale(False); c.set_auto_maskandscale(False)
  if set(b.variables)!=set(c.variables): out['layout_mismatches'].append({'kind':'variable_names','reference_only':sorted(set(b.variables)-set(c.variables)),'candidate_only':sorted(set(c.variables)-set(b.variables))})
  if set(b.dimensions)!=set(c.dimensions): out['layout_mismatches'].append({'kind':'dimension_names','reference_only':sorted(set(b.dimensions)-set(c.dimensions)),'candidate_only':sorted(set(c.dimensions)-set(b.dimensions))})
  for dn in b.dimensions:
   if dn not in c.dimensions or len(b.dimensions[dn])!=len(c.dimensions[dn]): out['layout_mismatches'].append({'kind':'dimension_length','name':dn,'reference':len(b.dimensions[dn]),'candidate':len(c.dimensions[dn]) if dn in c.dimensions else None})
  expected={'Time':1,'west_east':289,'south_north':189,'bottom_top':39}
  dims={dn:len(c.dimensions[dn]) for dn in expected if dn in c.dimensions}
  if dims!=expected: out['layout_mismatches'].append({'kind':'expected_domain','candidate':dims,'expected':expected})
  if 'Times' not in b.variables or 'Times' not in c.variables:
   out['layout_mismatches'].append({'kind':'Times_missing'}); times=None
  else:
   ba=np.asarray(b['Times'][:]); ca=np.asarray(c['Times'][:])
   if ba.dtype!=ca.dtype or ba.shape!=ca.shape or ba.tobytes()!=ca.tobytes(): out['differences'].append({'name':'Times','kind':'bytewise_mismatch'})
   val=ca.reshape(-1)
   times=b''.join(val.tolist()).decode('ascii').rstrip('\x00 ') if val.dtype.kind=='S' else str(val[0]).strip()
   if times!='2010-06-11_12:01:00': out['differences'].append({'name':'Times','kind':'unexpected_time','value':times})
  out['times_string']=times
  def attr_equal(x,y):
   xa,ya=np.asarray(x),np.asarray(y)
   if xa.shape!=ya.shape or xa.dtype.kind!=ya.dtype.kind: return False
   if xa.dtype.kind in 'fc': return np.array_equal(xa,ya,equal_nan=True)
   return np.array_equal(xa,ya)
  for k in set(b.ncattrs())|set(c.ncattrs()):
   if k not in b.ncattrs() or k not in c.ncattrs() or not attr_equal(b.getncattr(k),c.getncattr(k)): out['attrs_different'].append(k)
  for name in sorted(set(b.variables)&set(c.variables)):
   x,y=b[name],c[name]
   if x.dimensions!=y.dimensions or x.shape!=y.shape or x.dtype!=y.dtype:
    out['layout_mismatches'].append({'kind':'variable','name':name,'reference':{'dimensions':x.dimensions,'shape':x.shape,'dtype':str(x.dtype)},'candidate':{'dimensions':y.dimensions,'shape':y.shape,'dtype':str(y.dtype)}}); continue
   for attr in set(x.ncattrs())|set(y.ncattrs()):
    if attr not in x.ncattrs() or attr not in y.ncattrs() or not attr_equal(x.getncattr(attr),y.getncattr(attr)): out['attrs_different'].append(f'{name}:{attr}')
   xa=np.asarray(x[:]); ya=np.asarray(y[:]); xm=mask(x,xa); ym=mask(y,ya)
   if ya.dtype.kind in 'biufc' and (np.any(xm)|np.any(ym)): out['fill_markers'].append(name)
   if ya.dtype.kind in 'fc' and (np.any(~np.isfinite(xa)) or np.any(~np.isfinite(ya))): out['nonfinite'].append(name)
   out['variables']+=1
   if y.dtype.kind in 'biufc':
    out['numeric_values']+=ya.size
   out['bytewise_compared_arrays']+=1
   if xa.dtype!=ya.dtype or xa.shape!=ya.shape or xa.tobytes(order='C')!=ya.tobytes(order='C'):
    if ya.dtype.kind in 'fc' and xa.shape==ya.shape:
     diff=np.abs(xa.astype(np.float64)-ya.astype(np.float64)); mx=float(np.nanmax(diff)) if diff.size else 0.0
     count=sum(a!=b for a,b in zip(xa.tobytes(order='C'),ya.tobytes(order='C')))
    else: mx=None; count=None
    out['differences'].append({'name':name,'kind':'raw_array_bytes','max_abs':mx,'byte_diff_count':count})
 if out['differences'] or out['attrs_different'] or out['layout_mismatches'] or out['fill_markers'] or out['nonfinite']: out['status']='FAIL'
 return out
def setstack():
 n=512*1024*1024
 soft,hard=resource.getrlimit(resource.RLIMIT_STACK)
 if hard!=-1 and hard<n: raise RuntimeError('hard stack below requested 512MiB')
 resource.setrlimit(resource.RLIMIT_STACK,(n,hard))
def child_stack_failure(record):
 return 'WRF child did not receive 512 MiB RLIMIT_STACK' if (record or {}).get('soft_bytes')!=512*1024*1024 else None
def run_one(name):
 d=RUNROOT/name; r=json.loads((d/'preflight.json').read_text())
 run=Path(r['run_directory']); log=run/'wrf.stdout.log'; started=time.monotonic()
 env={'PATH':'/home/korea_keun/.local/bin:/usr/bin:/bin','NETCDF':str(NETCDF),'NETCDF_C':str(NETCDF),'LD_LIBRARY_PATH':str(NETCDF/'lib'),'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OMP_STACKSIZE':'512M','OPENBLAS_NUM_THREADS':'1'}
 childrec=d/'child-stack.json'; failures=[]; timed_out=False; code=None; p=None; comparison=None
 try:
  ensure_pins(r)
  if childrec.exists(): raise RuntimeError('child stack receipt already exists')
  def preexec():
   setstack(); soft,hard=resource.getrlimit(resource.RLIMIT_STACK); childrec.write_text(json.dumps({'soft_bytes':soft,'hard_bytes':hard})+'\n')
  with log.open('wb') as f:
   try: p=subprocess.run([str(run/'wrf.exe')],cwd=run,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=600,preexec_fn=preexec)
   except subprocess.TimeoutExpired as exc: timed_out=True; code=None
  if p is not None: code=p.returncode
  logs=log.read_text(errors='replace')+'\n'+'\n'.join(q.read_text(errors='replace') for q in run.glob('rsl.error.*'))
  if timed_out: failures.append('runtime timeout after 600s; subprocess.run terminated and reaped child')
  elif code!=0 or 'SUCCESS COMPLETE WRF' not in logs: failures.append(f'WRF did not complete successfully rc={code}')
  cp=run/HISTORY
  if not cp.is_file(): failures.append('missing expected history')
  else:
   if sorted(q.name for q in run.glob('wrfout_d01_*'))!=[HISTORY]: failures.append('unexpected history output schedule')
   comparison=compare(cp,r['reference_history'])
   if comparison['status']!='PASS': failures.append('strict bytewise parity comparison failed')
 except Exception as exc:
  failures.append(f'{type(exc).__name__}: {exc}')
 cp=run/HISTORY
 if cp.is_file():
  try: r['candidate_history_sha256']=sha(cp)
  except Exception as exc: failures.append(f'history hashing failed: {exc}')
 r.update(status='PASS' if not failures else 'FAIL_PRESERVED',failures=failures,
  runtime_returncode=code,runtime_timeout=timed_out,runtime_seconds=time.monotonic()-started,
  runtime_log_sha256=sha(log) if log.is_file() else None,runtime_environment=env,
  child_stack=json.loads(childrec.read_text()) if childrec.is_file() else None,comparison=comparison)
 try: ensure_pins(r); r['postrun_pin_check']='PASS'
 except Exception as exc: r['postrun_pin_check']=f'FAIL: {type(exc).__name__}: {exc}'; failures.append(r['postrun_pin_check']); r['status']='FAIL_PRESERVED'
 stack_error=child_stack_failure(r.get('child_stack'))
 if stack_error:
  failures.append(stack_error); r['status']='FAIL_PRESERVED'
 r['failures']=failures
 dump(d/'result.json',r); return r

def main():
 p=argparse.ArgumentParser(); p.add_argument('--run',action='store_true'); p.add_argument('--case',choices=list(CASES)); a=p.parse_args()
 if a.run:
  names=[a.case] if a.case else list(CASES)
  results=[run_one(n) for n in names]
  dump(RUNROOT/'suite-result.json',{'status':'PASS','results':results}); print('PARITY_PASS',','.join(names))
 else:
  if RUNROOT.exists(): raise RuntimeError(f'refusing overwrite {RUNROOT}')
  RUNROOT.mkdir(parents=True)
  reg=subprocess.run(['python3',str(SRC/'tools/register37.py'),'--check'],check=True,text=True,capture_output=True).stdout.strip()
  subprocess.run(['python3',str(SRC/'tools/compare_registry.py')],check=True)
  results=[setup(n,c) for n,c in CASES.items()]
  dump(RUNROOT/'suite-preflight.json',{'status':'PREPARED_NOT_RUN','base':PINCOMMIT,'registered_check':reg,'cases':results,'runner_sha256':sha(__file__)})
  print('PREPARED',RUNROOT/'suite-preflight.json')
if __name__=='__main__': main()
