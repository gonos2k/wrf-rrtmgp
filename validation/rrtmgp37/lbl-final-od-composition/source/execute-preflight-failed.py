from pathlib import Path
import subprocess,os,json,hashlib,time,signal,shutil,datetime
BASE=Path(__file__).resolve().parent; ROOT=BASE.parents[1]
DONOR=ROOT/'build/udm37-lblrtm-negative-pocket-observer-v10-run-v1'
PLAN=json.loads((DONOR/'plan-v1.json').read_text())
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
stage=BASE/'stage'; objects=stage/'build/lblrtm_v12.17_linux_gnu_dbl.obj'
before={p.name:sha(p) for p in objects.glob('*.o')}
run('build-v1',['/usr/bin/make','-f','make_lblrtm','linuxGNUdbl'],stage/'build',ENV)
after={p.name:sha(p) for p in objects.glob('*.o')};changed=[n for n in before if before[n]!=after[n]]
write('build-object-check-v1.json',{'changed_objects':changed,'all_other_objects_identical':changed==['oprop.o'],'other_objects':len(before)-1})
assert changed==['oprop.o']
exe=stage/'lblrtm_v12.17_linux_gnu_dbl'
write('execution-identity-v1.json',{'source_sha256':sha(stage/'src/oprop.f90'),'executable_sha256':sha(exe),'compiler_version':subprocess.check_output(['/usr/bin/gfortran','--version'],text=True).splitlines()[0],'ldd':subprocess.check_output(['/usr/bin/ldd',str(exe)],env=ENV,text=True),'production_accepted':False})
inputs=PLAN['held_case']['inputs']
for arm in ('off','on'):
 case=BASE/('case-'+arm);case.mkdir();records=[]
 for r in inputs:
  name=r['path']; (case/name).parent.mkdir(parents=True,exist_ok=True);source=(DONOR/'runs/od-v10'/name).resolve();assert source.is_file()
  if r['kind']=='copied_input':
   assert sha(source)==r['sha256'];shutil.copyfile(source,case/name)
  else:(case/name).symlink_to(source)
  records.append({'path':name,'resolved_source':str(source),'sha256':sha(source),'bytes':source.stat().st_size})
 write('inputs-v1-'+arm+'.json',{'files':records,'inputs_count':len(records),'TAPE5_modified':False})
 env=ENV.copy();env['UDM37_MIN_R3_TRACE']='1' if arm=='on' else '0'
 run('solver-v1-'+arm,[str(exe)],case,env)
 assert all(sha(case/r['path'])==r['sha256'] for r in records),'input mutation'
 assert len(list(case.glob('ODdeflt_*')))==45
print('Completed one make and two solver processes')
