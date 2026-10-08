from pathlib import Path
import datetime,hashlib,json,os,signal,subprocess,time,shutil
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
DONOR=ROOT/'build/udm37-lblrtm-negative-pocket-observer-v10-run-v1'
PLAN=json.loads((DONOR/'plan-v2.json').read_text())
ENV=os.environ.copy();ENV.update(PATH='/usr/bin:/bin',LANG='C',LC_ALL='C',LD_LIBRARY_PATH=str(ROOT/'build/deps/netcdf/lib'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,j):
    with (BASE/name).open('x') as f:json.dump(j,f,indent=2);f.write('\n')
def run(name,command,cwd,env,timeout=600):
    t=time.time();r={'command':command,'cwd':str(cwd),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'timeout_seconds':timeout,'environment':{k:env[k] for k in ('PATH','LANG','LC_ALL','LD_LIBRARY_PATH')},
      'observer_environment':env.get('UDM37_MIN_R3_TRACE'),'process_exit':'NOT_STARTED'}
    with (BASE/(name+'.lock')).open('x'):pass
    p=None
    with (BASE/(name+'.stdout')).open('xb') as out,(BASE/(name+'.stderr')).open('xb') as err:
        try:
            p=subprocess.Popen(command,cwd=cwd,env=env,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True)
            r['pid']=p.pid;write(name+'-launch.json',r)
            while p.poll() is None:
                if time.time()-t>timeout:raise TimeoutError(name)
                if name.startswith('solver'):
                    trace=cwd/'UDM37_LAYER_USE'
                    if trace.exists() and trace.stat().st_size>32*2**20:raise RuntimeError('32MiB trace ceiling')
                    if sum(x.stat().st_size for x in cwd.iterdir() if x.is_file() and not x.is_symlink())>3*2**30:raise RuntimeError('3GiB case ceiling')
                time.sleep(.2)
            r.update(returncode=p.wait(),process_exit='REAPED',elapsed_seconds=time.time()-t);write(name+'-result.json',r)
            if r['returncode']!=0:raise RuntimeError(name+' nonzero exit')
        except BaseException:
            if p is not None:
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    p.wait()
            r.update(returncode=None if p is None else p.returncode,process_exit='REAPED_ON_EXCEPTION',elapsed_seconds=time.time()-t)
            if not (BASE/(name+'-result.json')).exists():write(name+'-exception.json',r)
            raise
def prepare_case(name,sample,dptmin):
    case=BASE/name;case.mkdir();rows=[]
    for r in PLAN['held_case']['inputs']:
        source=(DONOR/'runs/od-v10'/r['path']).resolve();target=case/r['path'];target.parent.mkdir(parents=True,exist_ok=True)
        if r['kind']=='copied_input':
            if sha(source)!=r['sha256']:raise ValueError('donor pin')
            shutil.copyfile(source,target)
        else:target.symlink_to(source)
        rows.append({'path':r['path'],'bytes':source.stat().st_size,'sha256':sha(source)})
    original=(case/'TAPE5').read_bytes();lines=original.decode().splitlines(True)
    # Official record1.2 IOD column65; record1.3 SAMPLE field3/DPTMIN field7.
    control=lines[1];lines[1]=control[:64]+'2'+control[65:]
    numeric=lines[2];lines[2]=numeric[:20]+f'{sample:10.3E}'+numeric[30:60]+f'{dptmin:10.3E}'+numeric[70:]
    (case/'TAPE5').write_text(''.join(lines))
    for r in rows:
        if r['path']=='TAPE5':r.update(bytes=(case/'TAPE5').stat().st_size,sha256=sha(case/'TAPE5'))
    write(name+'-inputs.json',{'files':rows,'IOD':2,'SAMPLE':sample,'DPTMIN_input':dptmin,
      'original_TAPE5_sha256':hashlib.sha256(original).hexdigest(),'changed_zero_based_spans':[[1,64,65],[2,20,30],[2,60,70]],
      'state_and_other_controls_preserved':True})
    return case,rows
def check_inputs(case,rows):
    if any(sha(case/r['path'])!=r['sha256'] for r in rows):raise ValueError('executed input mutation')
    if len(list(case.glob('ODexact_*')))!=45:raise ValueError('expected45 exact OD files')
