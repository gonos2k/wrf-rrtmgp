"""Preflight or execute one approved bounded GNU CMake CPU OpenMP WRF smoke."""
from pathlib import Path
import argparse,hashlib,json,os,re,resource,signal,subprocess,sys,time
import numpy as np
from netCDF4 import Dataset
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP'); OUT=ROOT/'build/udm-cmake-openmp-full'
SRC=ROOT/'build/pr-wrf-rrtmgp/build/udm-cmake-openmp-proposal/source'; PREF=OUT/'runtime-preflight-v3'
BASE_COMMIT='bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291'; EXPECTED_DIFF='a5c48e831c166d35346053d74859438867612de4284f83751345fa789872b2dc'
MUTABLE=re.compile(r'^(wrfout_|wrfrst_|rsl\.|namelist\.output$|.*\.log$)'); H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def githead():return subprocess.check_output(['git','-C',str(SRC),'rev-parse','HEAD'],text=True).strip()
def sourcestate():
 diff=hashlib.sha256(subprocess.check_output(['git','-C',str(SRC),'diff','--binary',BASE_COMMIT])).hexdigest()
 st=subprocess.check_output(['git','-C',str(SRC),'status','--porcelain'],text=True).splitlines()
 exp=[' M WRF/CMakeLists.txt',' M WRF/external/rte_rrtmgp/CMakeLists.txt',' M WRF/phys/module_microphysics_driver.F',' M WRF/phys/module_physics_init.F',' M config/registration37.json']
 names=[x[3:] for x in exp]
 return {'head':githead(),'diff_sha256':diff,'git_status_porcelain':sorted(st),'changed_files':{f:H(SRC/f) for f in names}}
def filehashes(p):return {x.name:H(x) for x in sorted(p.iterdir()) if x.is_file() and not MUTABLE.match(x.name) and x.name not in {'wrf.exe','real.exe','namelist.input'}}
def filetime():
 return {'executable':OUT/'install/bin/wrf','table_key_suffix':'frozen-ice-psd-moments.nc'}
def hash_external(rec):return {p:H(p) for p in rec['external_assets_sha256']}
def validate_pins(arm,rec,prepath):
 if sourcestate()!=rec['source']:raise RuntimeError('source HEAD/diff/status/file hashes changed')
 if rec['source']['head']!=BASE_COMMIT or rec['source']['diff_sha256']!=EXPECTED_DIFF:raise RuntimeError('source pin differs')
 exe=Path(rec['executable_path']);run=Path(rec['run_directory']);base=Path(rec['baseline_directory'])
 if H(exe)!=rec['executable_sha256'] or H(run/'wrf.exe')!=rec['staged_executable_sha256']:raise RuntimeError('executable bytes changed')
 if filehashes(run)!=rec['staged_input_files_sha256'] or filehashes(base)!=rec['baseline_input_files_sha256']:raise RuntimeError('immutable input files changed')
 if H(run/rec['checkpoint'])!=rec['checkpoint_sha256']:raise RuntimeError('checkpoint bytes changed')
 if H(run/'namelist.input')!=rec['staged_namelist_sha256'] or H(base/'namelist.input')!=rec['baseline_namelist_sha256']:raise RuntimeError('namelist bytes changed')
 if hash_external(rec)!=rec['external_assets_sha256']:raise RuntimeError('external coefficient/table hashes changed')
 if H(prepath)!=rec['_preflight_self_sha256']:raise RuntimeError('preflight receipt bytes changed')
 if rec['executed_runner_sha256']!=H(__file__) or rec['comparator_sha256']!=H(OUT/'compare_openmp_smokes_v3.py'):raise RuntimeError('runner/comparator bytes differ from preflight')
 if rec['probe'] is not None:
  q=OUT/'runtime-preflight-v3'
  if H(q/'gomp_probe.c')!=rec['probe']['source_sha256'] or H(q/'analyse.py')!=rec['probe']['analyzer_sha256'] or H(q/'libgomp_probe.so')!=rec['probe']['library_sha256']:raise RuntimeError('GOMP probe artifacts changed')
 return {'source':sourcestate(),'executable_sha256':H(exe),'staged_executable_sha256':H(run/'wrf.exe'),'input_files_sha256':filehashes(run),'checkpoint_sha256':H(run/rec['checkpoint']),'namelist_sha256':H(run/'namelist.input'),'external_assets_sha256':hash_external(rec)}
def attr_value(v):
 a=np.asarray(v); raw=repr(v).encode() if a.dtype.kind=='O' else a.tobytes()
 return {'dtype':str(a.dtype),'shape':list(a.shape),'sha256':hashlib.sha256(raw).hexdigest(),'repr':repr(v) if a.dtype.kind=='O' else None}
def inspect_history(run,structural):
 hs=sorted(run.glob('wrfout_d01_*'))
 if len(hs)!=1 or hs[0].name!='wrfout_d01_2010-06-11_12:01:00':raise RuntimeError('history time/file schedule mismatch')
 path=hs[0]; out={'path':str(path),'sha256':H(path),'dimensions':{},'global_attributes':{},'variables':{},'numeric_values':0,'decoded_masks':0}
 with Dataset(path) as ds:
  ds.set_auto_maskandscale(False)
  out['dimensions']={n:{'size':len(d),'unlimited':d.isunlimited()} for n,d in ds.dimensions.items()}
  for dim,size in [('Time',1),('west_east',289),('south_north',189),('bottom_top',39)]:
   if dim not in ds.dimensions or len(ds.dimensions[dim])!=size:raise RuntimeError(f'dimension {dim} is not expected size {size}')
  if set(ds.variables)!=set(structural['variables']):raise RuntimeError('history variable-name set differs from CMake structural reference')
  if sorted(ds.ncattrs())!=structural['global_attribute_names']:raise RuntimeError('global attribute names differ from structural reference')
  for n,val in [('MP_PHYSICS',27),('RA_LW_PHYSICS',37),('RA_SW_PHYSICS',37)]:
   if n not in ds.ncattrs() or int(ds.getncattr(n))!=val:raise RuntimeError(f'output attr {n} mismatch')
  tv=np.asarray(ds.variables['Times'][:]);stamp=b''.join(tv.reshape(-1).tolist()).decode('ascii').strip().replace('\x00','')
  if stamp!='2010-06-11_12:01:00':raise RuntimeError('Times is not exact expected timestamp: '+repr(stamp))
  for k in ds.ncattrs():out['global_attributes'][k]=attr_value(ds.getncattr(k))
  for n,v in ds.variables.items():
   s=structural['variables'][n];a=np.asarray(v[:])
   if str(v.dtype)!=s['dtype'] or list(v.dimensions)!=s['dimensions'] or list(v.shape)!=s['shape'] or sorted(v.ncattrs())!=s['attributes']:
    raise RuntimeError(f'output variable schema differs from reference: {n}')
   if a.dtype.kind in 'fiu':
    out['numeric_values']+=a.size
    if a.dtype.kind=='f' and not np.isfinite(a).all():raise RuntimeError(f'nonfinite output in {n}')
    for at in ('_FillValue','missing_value'):
     if at in v.ncattrs():
      for fv in np.asarray(v.getncattr(at)).reshape(-1):
       bad=np.isnan(a) if a.dtype.kind=='f' and np.isnan(fv) else a==fv
       if np.any(bad):raise RuntimeError(f'raw fill/missing marker found in {n}')
    v.set_auto_maskandscale(True);masked=np.ma.asarray(v[:]); mask=np.ma.getmaskarray(masked)
    if np.any(mask):raise RuntimeError(f'decoded netCDF mask found in {n}')
    if a.dtype.kind=='f' and not np.isfinite(np.ma.getdata(masked)).all():raise RuntimeError(f'decoded nonfinite output in {n}')
    out['decoded_masks']+=int(mask.sum());v.set_auto_maskandscale(False)
   out['variables'][n]={'dtype':str(a.dtype),'dimensions':list(v.dimensions),'shape':list(a.shape),'array_sha256':hashlib.sha256(a.tobytes()).hexdigest(),'attributes':{k:attr_value(v.getncattr(k)) for k in v.ncattrs()}}
 if len(out['variables'])!=211:raise RuntimeError(f'expected 211 variables, got {len(out["variables"])}')
 return out
AP=argparse.ArgumentParser();AP.add_argument('--case',choices=['ra37-omp1-tiles2','ra37-omp2-tiles2','ra37-omp2-probe-tiles2'],required=True);AP.add_argument('--execute',action='store_true');AP.add_argument('--timeout',type=int,default=600);args=AP.parse_args()
if not 1<=args.timeout<=600:raise SystemExit('timeout must be 1..600 seconds')
case=PREF/args.case;prepath=case/'preflight.json';run=case/'run';receipt_path=case/'runtime-result.json'
if not prepath.is_file():raise SystemExit('missing preflight receipt')
rec=json.loads(prepath.read_text());side=case/'preflight.sha256'
if not side.is_file() or side.read_text().split()[0]!=H(prepath):raise SystemExit('preflight sidecar hash mismatch')
if rec.get('status')!='PREPARED_NOT_RUN_PENDING_ROOT_REVIEW':raise SystemExit('invalid preflight status')
rec['_preflight_self_sha256']=H(prepath)
try:pre=validate_pins(args.case,rec,prepath)
except Exception as e:raise SystemExit('preflight pin check failed: '+repr(e))
if not args.execute:
 print('PREFLIGHT_ONLY_NOT_RUN',args.case,rec['_preflight_self_sha256']);raise SystemExit(0)
if receipt_path.exists() or (run/'wrf.stdout.log').exists() or list(run.glob('wrfout_d01_*')):raise SystemExit('refusing to overwrite previous runtime evidence')
result={'schema':'WRF_GNU_CMAKE_OPENMP_SMOKE_RESULT_V3','status':'RUNNING','case':args.case,'preflight_sha256':rec['_preflight_self_sha256'],'executed_runner_sha256':H(__file__),'comparator_sha256':H(OUT/'compare_openmp_smokes_v3.py'),'preflight_state':pre,'timeout_seconds':args.timeout,'started_epoch':time.time()}
(case/'runtime-result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
failed=None
try:
 env={k:v for k,v in os.environ.items() if not k.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_OMP_PROBE_'))};env.pop('LD_PRELOAD',None)
 threads=rec['runtime']['threads'];env.update(OMP_NUM_THREADS=str(threads),OMP_DYNAMIC='FALSE',OMP_STACKSIZE='512M',OPENBLAS_NUM_THREADS='1')
 env['LD_LIBRARY_PATH']=str(ROOT/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu'
 if rec['runtime']['probe']:
  log=case/'gomp-workers.log';env['LD_PRELOAD']=str(PREF/'libgomp_probe.so');env['WRF_OMP_PROBE_LOG']=str(log)
 result['runtime_environment']={k:env[k] for k in ('OMP_NUM_THREADS','OMP_DYNAMIC','OMP_STACKSIZE','OPENBLAS_NUM_THREADS','LD_LIBRARY_PATH')}
 result['probe_enabled']=bool(rec['runtime']['probe']);result['command']=['./wrf.exe'];result['child_RLIMIT_STACK_bytes']=536870912
 def set_child_stack():resource.setrlimit(resource.RLIMIT_STACK,(536870912,536870912))
 start=time.monotonic()
 with (case/'wrf.stdout.log').open('wb') as logf:
  p=subprocess.Popen(['./wrf.exe'],cwd=run,env=env,stdout=logf,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=set_child_stack)
  try:rc=p.wait(timeout=args.timeout);to=False
  except subprocess.TimeoutExpired:
   to=True
   try:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   rc=p.returncode
 result.update(returncode=rc,timed_out=to,elapsed_seconds=time.monotonic()-start,stdout_sha256=H(case/'wrf.stdout.log'))
 if to or rc!=0:raise RuntimeError(f'WRF failed/timed out (timeout={to}, rc={rc})')
 txt=(case/'wrf.stdout.log').read_text(errors='replace')
 if 'SUCCESS COMPLETE WRF' not in txt and not any('SUCCESS COMPLETE WRF' in p.read_text(errors='replace') for p in run.glob('rsl.error.*')):raise RuntimeError('SUCCESS COMPLETE WRF marker absent')
 result['history']=inspect_history(run,rec['structural_reference'])
 if rec['runtime']['probe']:
  proof=case/'worker-proof.json';an=PREF/'analyse.py'; log=case/'gomp-workers.log'
  if H(PREF/'gomp_probe.c')!=rec['probe']['source_sha256'] or H(PREF/'libgomp_probe.so')!=rec['probe']['library_sha256'] or H(an)!=rec['probe']['analyzer_sha256']:raise RuntimeError('probe source/library/analyzer hash mismatch')
  subprocess.run([sys.executable,str(an),'--exe',str(run/'wrf.exe'),'--log',str(log),'--output',str(proof)],check=True)
  details=json.loads(proof.read_text())
  if not details.get('verified_two_radiation_workers'):raise RuntimeError('two-worker radiation callback proof failed')
  result['worker_proof']={'sha256':H(proof),'log_sha256':H(log),'source_sha256':H(PREF/'gomp_probe.c'),'library_sha256':H(PREF/'libgomp_probe.so'),'analyzer_sha256':H(an),'details':details}
except Exception as e:failed=repr(e)
finally:
 try:post=validate_pins(args.case,rec,prepath)
 except Exception as e:post={'postflight_error':repr(e)};failed=failed or repr(e)
 result['postflight_state']=post
 result['status']='PASS' if failed is None else 'FAIL'
 if failed:result['error']=failed
 result['completed_epoch']=time.time()
 receipt_path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(result['status'],receipt_path)
if result['status']!='PASS':raise SystemExit(1)
