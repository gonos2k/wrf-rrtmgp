from pathlib import Path
import subprocess,os,json,hashlib,time,signal,shutil,datetime
BASE=Path(__file__).resolve().parent; ROOT=BASE.parents[1]
DONOR=ROOT/'build/udm37-lblrtm-negative-pocket-observer-v10-run-v1'
PLAN=json.loads((DONOR/'plan-v2.json').read_text())
ENV=os.environ.copy(); ENV.update(PATH='/usr/bin:/bin',LANG='C',LC_ALL='C',LD_LIBRARY_PATH=str(ROOT/'build/deps/netcdf/lib'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,record):
 with (BASE/name).open('x') as f:json.dump(record,f,indent=2);f.write('\n')
def run(name,cmd,cwd,env,limit=600):
 start=time.time(); record={'command':cmd,'cwd':str(cwd),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'timeout_seconds':limit,'environment':{k:env[k] for k in ('PATH','LANG','LC_ALL','LD_LIBRARY_PATH')},'process_exit':'NOT_STARTED'}
 with (BASE/(name+'.lock')).open('x'):pass
 child=None
 with (BASE/(name+'.stdout')).open('xb') as out,(BASE/(name+'.stderr')).open('xb') as err:
  try:
   child=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True)
   record['pid']=child.pid
   write(name+'-launch.json',record)
   while child.poll() is None:
    if time.time()-start>limit:raise TimeoutError(name)
    if name.startswith('solver'):
     trace=cwd/'UDM37_MIN_R3'
     if trace.exists() and trace.stat().st_size>32*2**20:raise RuntimeError('trace ceiling')
     size=sum(p.stat().st_size for p in cwd.iterdir() if p.is_file() and not p.is_symlink())
     if size>800*2**20:raise RuntimeError('output ceiling')
    time.sleep(.2)
   record['returncode']=child.wait();record['process_exit']='REAPED';record['elapsed_seconds']=time.time()-start
   write(name+'-result.json',record)
   if record['returncode']!=0:raise RuntimeError(f'{name} rc {record["returncode"]}')
  except BaseException:
   if child is not None:
    try:os.killpg(child.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:child.wait(timeout=3)
    except subprocess.TimeoutExpired:
     try:os.killpg(child.pid,signal.SIGKILL)
     except ProcessLookupError:pass
     child.wait()
   raise
stage=BASE/'stage-v2';exe=stage/'lblrtm_v12.17_linux_gnu_dbl'
assert sha(exe)==json.loads((BASE/'execution-identity.json').read_text())['executable_sha256']
assert json.loads((BASE/'build-object-check.json').read_text())['all_other_objects_identical']
inputs=PLAN['held_case']['inputs']
for arm in ('off','on'):
 case=BASE/('case-v3-'+arm);case.mkdir()
 records=[]
 for r in inputs:
  name=r['path']; (case/name).parent.mkdir(parents=True,exist_ok=True); source=(DONOR/'runs/od-v10'/name).resolve(); assert source.is_file(),name
  if r['kind']=='copied_input':
   assert sha(source)==r['sha256'],name
   shutil.copyfile(source,case/name)
  else:(case/name).symlink_to(source)
  records.append({'path':name,'resolved_donor':str(source),'sha256':sha(source),'bytes':source.stat().st_size})
 write('inputs-v3-'+arm+'.json',{'files':records,'TAPE5_modified':False,'inputs_count':len(records)})
 env=ENV.copy();env['UDM37_MIN_R3_TRACE']='1' if arm=='on' else '0'
 run('solver-v3-'+arm,[str(exe)],case,env)
files=sorted((BASE/'case-v3-on').glob('ODdeflt_*'));assert len(files)==45
comparison=[]
for p in files:
 other=BASE/'case-v3-off'/p.name; old=DONOR/'runs/od-v10'/p.name
 comparison.append({'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p),'OFF_ON_identical':sha(p)==sha(other),'previous_v10_identical':sha(p)==sha(old)})
write('optical-depth-comparison.json',{'files':comparison,'OD_arrays_count':len(files),'all_OFF_ON_identical':all(r['OFF_ON_identical'] for r in comparison),'all_previous_v10_identical':all(r['previous_v10_identical'] for r in comparison),'comparison_scope':'Full 45 binary OD files, not timing-text logs or all working files','physical_reference_accepted':False})
assert all(r['OFF_ON_identical'] and r['previous_v10_identical'] for r in comparison)
assert not (BASE/'case-v3-off/UDM37_MIN_R3').exists()
print(json.dumps({'status':'PASS_SCOPED_CAPTURE_AND_OD_PASSIVITY','build_children':1,'solver_children':2,'OD_files':45,'trace_bytes':(BASE/'case-v3-on/UDM37_MIN_R3').stat().st_size,'production_accepted':False}))
