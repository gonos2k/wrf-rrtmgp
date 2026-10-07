#!/usr/bin/env python3
"""One-use same-arm restart-read check; all variables and arrays are strict."""
import argparse, datetime as dt, hashlib, importlib.util, json, os, pathlib, re, resource
import signal, subprocess, sys, time
import numpy as np
from netCDF4 import Dataset

BASE=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
SOURCE=BASE/'build/udm37-main-runtime-io-mpi-source-v1'
BUILD=BASE/'build/udm37-main-runtime-io-mpi-build-v1'
MPI=BASE/'build/deps/mpich-sock/bin/mpiexec.hydra'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def pin(p):
    return {'path':str(p.resolve()),'sha256':sha(p),'size_bytes':p.stat().st_size,
            'link':os.readlink(p) if p.is_symlink() else None}
def atomic(path,value):
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);fd=os.open(path.parent,os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
def stop_group(proc):
    errors=[]
    for sig in (signal.SIGTERM,signal.SIGKILL):
        try: os.killpg(proc.pid,sig)
        except ProcessLookupError: pass
        except BaseException as e: errors.append(repr(e))
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if sig==signal.SIGKILL: errors.append('child group leader not reaped after SIGKILL')
        except BaseException as e: errors.append(repr(e))
    return proc.poll(),proc.returncode is not None,errors
def raw(v):
    v.set_auto_maskandscale(False);v.set_auto_chartostring(False)
    if v.ndim==0: return np.asarray(v[...])
    return np.asarray(v[:])
def times(ds):
    v=ds['Times'];v.set_auto_maskandscale(False);v.set_auto_chartostring(False)
    return [b''.join(row).decode('ascii') for row in np.asarray(v[:])]
def val_attr(v,name):
    x=v.getncattr(name)
    if isinstance(x,np.ndarray): return {'dtype':str(x.dtype),'shape':list(x.shape),'bytes':x.tobytes().hex()}
    if isinstance(x,np.generic): return {'dtype':str(x.dtype),'bytes':np.asarray(x).tobytes().hex()}
    return repr(x)
def attrs(obj): return {k:val_attr(obj,k) for k in sorted(obj.ncattrs())}
def snapshot(root,cases):
    return {arm:{name:pin(root/arm/name) for name in cases[arm]['files']} for arm in ('ra4','ra37')}
def scalar(text,key):
    v=re.findall(r'(?mi)^\s*'+re.escape(key)+r'\s*=\s*([^,\n]+)',text)
    if len(v)!=1: raise ValueError(f'{key}: expected one assignment, got {v}')
    return v[0].strip()
def validate_seed(case,plan,arm):
    seed_plan=plan['cases'][arm]['seed_control']; expected=seed_plan['seed_expected']
    cp=case/'wrfrst_d01_2016-10-06_13:00:00'
    if not cp.is_file(): raise ValueError(f'{arm}: missing 13:00 restart checkpoint')
    with Dataset(cp) as d:
        if times(d)!=['2016-10-06_13:00:00']:
            raise ValueError(f'{arm}: output restart checkpoint time is not 13:00')
        if 'ISEEDARR_MULT3D' not in d.variables: raise ValueError(f'{arm}: seed absent from 13:00 checkpoint')
        v=d['ISEEDARR_MULT3D'];a=raw(v)
        if list(v.dimensions)!=expected['dimensions'] or list(a.shape)!=expected['shape'] or str(a.dtype)!=expected['dtype']:
            raise ValueError(f'{arm}: output seed schema differs from restart input')
        got=hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
        if got!=expected['data_sha256']: raise ValueError(f'{arm}: output seed values did not persist')
        expected_attrs=seed_plan['schema_before']['variables']['ISEEDARR_MULT3D']['attributes']
        if attrs(v)!=expected_attrs: raise ValueError(f'{arm}: output seed attributes changed')
        if expected['pattern'].startswith('negative signed int32 sequence'):
            want=-np.arange(1,a.size+1,dtype=np.int32).reshape(a.shape)
            if not np.array_equal(a,want): raise ValueError(f'{arm}: sentinel ordering changed')
        return {'checkpoint':pin(cp),'seed_dimensions':list(v.dimensions),'seed_shape':list(a.shape),
                'seed_dtype':str(a.dtype),'seed_sha256':got,'pattern':expected['pattern']}
def compare_all(resumed,continuous,when):
    report={'resumed':pin(resumed),'continuous_reference':pin(continuous),'target_time':when,
      'checked':[],'mismatches':[],'variable_attribute_differences':[],'global_attribute_differences':[],
      'metadata_accepted':False,'physical_accepted':False}
    with Dataset(resumed) as a,Dataset(continuous) as b:
        ta,tb=times(a),times(b)
        if ta!=[when]: raise ValueError(f'resumed history times {ta}')
        if tb!=[(dt.datetime(2016,10,6)+dt.timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(14)]: raise ValueError(f'continuous history must have 14 hourly records ending {when}, got {len(tb)} {tb[-1:]}')
        ib=tb.index(when)
        if a.data_model!=b.data_model: raise ValueError('NetCDF data model mismatch')
        da={n:{'size':len(v),'unlimited':v.isunlimited()} for n,v in a.dimensions.items()}
        db={n:{'size':len(v),'unlimited':v.isunlimited()} for n,v in b.dimensions.items()}
        report['dimensions_resumed']=da;report['dimensions_continuous']=db;report['data_model']=a.data_model
        if set(da)!=set(db): raise ValueError('complete dimension roster differs')
        for n in da:
            if da[n]['unlimited']!=db[n]['unlimited'] or (n!='Time' and da[n]['size']!=db[n]['size']): raise ValueError(f'dimension schema mismatch: {n}')
        if da['Time']['size']!=1 or db['Time']['size']!=14: raise ValueError('unexpected Time extents')
        if list(a.variables)!=list(b.variables): raise ValueError('ordered variable roster differs')
        for name in a.variables:
            va,vb=a[name],b[name]
            if va.dimensions!=vb.dimensions or va.dtype!=vb.dtype: raise ValueError(f'{name}: dimensions/dtype mismatch')
            xa,xb=raw(va),raw(vb)
            if 'Time' in va.dimensions:
                axis=va.dimensions.index('Time')
                xa=np.take(xa,0,axis=axis);xb=np.take(xb,ib,axis=axis)
            if xa.shape!=xb.shape: raise ValueError(f'{name}: array extent mismatch {xa.shape} != {xb.shape}')
            same=xa.tobytes()==xb.tobytes()
            rec={'name':name,'dimensions':list(va.dimensions),'dtype':str(xa.dtype),'shape_at_time':list(xa.shape),
                 'exact':same,'sha256_resumed':hashlib.sha256(np.ascontiguousarray(xa).tobytes()).hexdigest(),
                 'sha256_continuous':hashlib.sha256(np.ascontiguousarray(xb).tobytes()).hexdigest()}
            if not same:
                rec['differing_elements']=int(np.count_nonzero(xa!=xb))
                if xa.dtype.kind in 'fiu' and xa.size:
                    rec['max_abs']=float(np.max(np.abs(xa.astype('f8')-xb.astype('f8'))))
                report['mismatches'].append(rec)
            report['checked'].append(rec)
            aa,ab=attrs(va),attrs(vb)
            if aa!=ab: report['variable_attribute_differences'].append({'name':name,'resumed':aa,'continuous':ab})
        ga,gb=attrs(a),attrs(b)
        for name in sorted(set(ga)|set(gb)):
            if ga.get(name)!=gb.get(name): report['global_attribute_differences'].append({'name':name,'resumed':ga.get(name),'continuous':gb.get(name)})
    report['status']='PASS_ALL_COMMON_ARRAYS_EXACT' if not report['mismatches'] and not report['variable_attribute_differences'] else 'FAIL_ARRAY_MISMATCH_PRESERVED'
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stage-root',type=pathlib.Path,required=True)
    ap.add_argument('--max-seconds',type=int,default=300)
    args=ap.parse_args();root=args.stage_root.resolve()
    if args.max_seconds<=0 or args.max_seconds>300: raise ValueError('timeout must be 1..300 seconds')
    for p in (root/'execution.json',root/'.one-use.lock'):
        if p.exists(): raise FileExistsError(p)
    plan_path=root/'stage-plan.json';auth_path=root/'root-authorization.json'
    plan=json.loads(plan_path.read_text());auth=json.loads(auth_path.read_text())
    if auth.get('status')!='AUTHORIZED_BOUNDED_ROOT_EXECUTION' or auth.get('physical_accepted') is not False or auth.get('active_stochastic_accepted') is not False:
        raise ValueError('root authorization is pending or has invalid acceptance scope')
    if auth.get('stage_plan_sha256')!=sha(plan_path) or auth.get('runner_sha256')!=sha(pathlib.Path(__file__).resolve()):
        raise ValueError('root authorization does not match frozen plan/runner')
    if auth.get('max_models')!=2 or auth.get('per_arm_timeout_seconds')!=300 or auth.get('seed_sentinel')!=plan['seed_sentinel_requested']:
        raise ValueError('root authorization limits/sentinel mode mismatch')
    if plan.get('multi_perturb')!=0 or plan.get('physical_accepted') is not False:
        raise ValueError('scope metadata invalid')
    for n in ('build_result','numeric_scanner','runner','control_stage_plan','MPI'):
        if n not in plan or pin(pathlib.Path(plan[n]['path']))!=plan[n]: raise ValueError(f'planned dependency changed: {n}')
    if pin(MPI)!=plan['MPI']: raise ValueError('MPI launcher mismatch')
    build_pin=pin(BUILD/'result.json'); runner_pin=pin(pathlib.Path(__file__).resolve())
    if build_pin!=plan['build_result'] or runner_pin!=plan['runner']: raise ValueError('build/runner declared join mismatch')
    build=json.loads((BUILD/'result.json').read_text())
    if build.get('status')!='PASS_BUILD_INSTALL_SCOPED' or build.get('source_head')!=plan['source']['head']:
        raise ValueError('build/source receipt mismatch')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=SOURCE,text=True).strip()
    if head!=plan['source']['head'] or tree!=plan['source']['tree'] or subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip():
        raise ValueError('source is not frozen clean')
    source_pins={rel:pin(SOURCE/rel) for rel in plan['source']['selected_files']}
    if source_pins!=plan['source']['selected_files']:
        raise ValueError('selected source pins changed')
    control_ref=pathlib.Path(plan['continuous_control_execution']['path'])
    if pin(control_ref)!=plan['continuous_control_execution']:
        raise ValueError('continuous control execution pin changed')
    control_exec=json.loads(control_ref.read_text())
    if control_exec.get('status')!='PASS_PAIRED_RUNTIME_SCOPED' or control_exec.get('model_calls')!=2:
        raise ValueError('continuous control pair not PASS')
    for arm in ('ra4','ra37'):
        cr=control_exec['results'][arm]
        if cr.get('status')!='PASS_RUNTIME_SCOPED' or cr.get('validation',{}).get('status')!='PASS_RUNTIME_SCOPED':
            raise ValueError(f'{arm}: continuous parent status gate failed')
        if cr.get('actual_rc')!=0 or cr.get('reaped') is not True or cr.get('timed_out'):
            raise ValueError(f'{arm}: continuous parent not RC0/reaped')
        if cr.get('validation',{}).get('times',[])!=[(dt.datetime(2016,10,6)+dt.timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(14)]:
            raise ValueError(f'{arm}: continuous parent not 14-hour validated')
        c=plan['cases'][arm];case=root/arm
        binary=pin(case/'wrf.exe');built=build['executables']['wrf']
        if binary['sha256']!=built['sha256'] or binary['size_bytes']!=built['size_bytes']: raise ValueError(f'{arm}: staged executable differs from build')
        scans=cr['validation']['numeric_scan'];origin=c['source_checkpoint']
        matches=[v for v in scans if pathlib.Path(v['path']).resolve()==pathlib.Path(origin['path']).resolve()]
        if len(matches)!=1 or matches[0]['status']!='PASS' or matches[0]['sha256']!=origin['sha256'] or matches[0]['size_bytes']!=origin['size_bytes']: raise ValueError(f'{arm}: source checkpoint differs from saved control scan pin')
        if pin(pathlib.Path(origin['path']))!=origin: raise ValueError(f'{arm}: source checkpoint mutated')
        with Dataset(origin['path']) as d:
            if times(d)!=['2016-10-06_12:00:00']: raise ValueError(f'{arm}: source checkpoint wrong time')
        if pin(case/'wrfrst_d01_2016-10-06_12:00:00')!=c['restart_input']:
            raise ValueError(f'{arm}: restart input pin changed')
        history_origin=c['continuous_reference']
        history_matches=[v for v in scans if pathlib.Path(v['path']).resolve()==pathlib.Path(history_origin['path']).resolve()]
        if len(history_matches)!=1 or history_matches[0]['status']!='PASS' or history_matches[0]['sha256']!=history_origin['sha256'] or history_matches[0]['size_bytes']!=history_origin['size_bytes']:
            raise ValueError(f'{arm}: continuous history differs from saved control scan pin')
        if pin(pathlib.Path(c['continuous_reference']['path']))!=c['continuous_reference']:
            raise ValueError(f'{arm}: continuous reference pin changed')
        expected_start='2016-10-06_12:00:00';expected_end='2016-10-06_13:00:00'
        nml=(case/'namelist.input').read_text()
        if scalar(nml,'run_days')!='0' or scalar(nml,'run_hours')!='1' or scalar(nml,'run_minutes')!='0' or scalar(nml,'run_seconds')!='0':
            raise ValueError(f'{arm}: duration namelist mismatch')
        def date(prefix):
            vals=[scalar(nml,prefix+'_'+x) for x in ('year','month','day','hour','minute','second')]
            return f'{int(vals[0]):04d}-{int(vals[1]):02d}-{int(vals[2]):02d}_{int(vals[3]):02d}:{int(vals[4]):02d}:{int(vals[5]):02d}'
        if date('start')!=expected_start or date('end')!=expected_end: raise ValueError(f'{arm}: date namelist mismatch')
        if scalar(nml,'restart').lower()!='.true.' or scalar(nml,'restart_interval')!='60' or scalar(nml,'history_interval')!='60' or scalar(nml,'io_form_restart')!='2' or scalar(nml,'time_step')!='60' or scalar(nml,'history_interval_s')!='0':
            raise ValueError(f'{arm}: restart/time namelist mismatch')
        if re.search(r'(?mi)^\s*multi_perturb\s*=\s*([^,\n]+)',nml) and scalar(nml,'multi_perturb')!='0':
            raise ValueError(f'{arm}: stochastic mode is not disabled')
        with Dataset(case/'wrfrst_d01_2016-10-06_12:00:00') as d:
            if times(d)!=[expected_start]: raise ValueError(f'{arm}: checkpoint time mismatch')
            if 'ISEEDARR_MULT3D' not in d.variables: raise ValueError(f'{arm}: input seed missing')
            v=d['ISEEDARR_MULT3D'];a=raw(v); seed=c['seed_control']['seed_expected']
            if list(v.dimensions)!=seed['dimensions'] or str(a.dtype)!=seed['dtype'] or hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()!=seed['data_sha256']:
                raise ValueError(f'{arm}: staged seed differs from expected checkpoint/sentinel')
    # Import the scanner and validate staged files before writing STARTING.
    scanner_pin=plan['numeric_scanner'];scanner=pathlib.Path(scanner_pin['path'])
    if pin(scanner)!=scanner_pin: raise ValueError('numeric scanner pin changed')
    spec=importlib.util.spec_from_file_location('zz_numeric_scan',scanner)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    stage_pins={n:pin(root/n) for n in ('stage-plan.json','verify_stage.py','root-authorization.json')}
    before=snapshot(root,plan['cases'])
    planned_files={arm:plan['cases'][arm]['files'] for arm in ('ra4','ra37')}
    if before!=planned_files:
        raise ValueError('staged inputs, including symlink targets/text, differ from the frozen case roster')
    subprocess.run([sys.executable,str(root/'verify_stage.py')],cwd=root,check=True,capture_output=True,text=True)
    env=os.environ.copy()
    for key in list(env):
        if key.startswith(('OMP_','GOMP_','KMP_','WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE')) or key in ('LD_PRELOAD','LD_AUDIT'): env.pop(key,None)
    env.update(LD_LIBRARY_PATH=':'.join(str(BASE/p) for p in ('build/deps/netcdf/lib','build/deps/root/usr/lib/x86_64-linux-gnu','build/deps/mpich-sock/lib')),
        MPICH_INTERFACE_HOSTNAME='127.0.0.1',OMP_NUM_THREADS='2',OMP_STACKSIZE='512M',OMP_DYNAMIC='FALSE',OMP_MAX_ACTIVE_LEVELS='1',OPENBLAS_NUM_THREADS='1')
    ldd=subprocess.check_output(['ldd',str(BUILD/'install/bin/wrf')],env=env,text=True)
    if 'not found' in ldd: raise ValueError('unresolved linked library')
    libfiles=[pathlib.Path(line.split('=>')[1].split()[0]) for line in ldd.splitlines() if '=>' in line and line.split('=>')[1].split()[0].startswith('/')]
    libraries={str(p):pin(p) for p in libfiles}
    if not plan.get('library_pins') or libraries!=plan['library_pins']: raise ValueError('runtime library closure differs from staged plan')
    hard=resource.getrlimit(resource.RLIMIT_STACK)[1]
    if hard!=resource.RLIM_INFINITY and hard<512*1024**2: raise ValueError('stack hard limit too small')
    resource.setrlimit(resource.RLIMIT_STACK,(512*1024**2,hard))
    lock=root/'.one-use.lock'
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try: os.write(fd,(str(os.getpid())+'\n').encode());os.fsync(fd)
    finally: os.close(fd)
    dfd=os.open(root,os.O_DIRECTORY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    rec={'schema':'UDM_NETCDF_ZZ_RESTART_READ_EXECUTION_V1','status':'STARTING','models':0,
      'source':{'head':head,'tree':plan['source']['tree']},'build_result':pin(BUILD/'result.json'),
      'selected_source_pins':source_pins,
      'continuous_control_execution':pin(control_ref),'runner':pin(pathlib.Path(__file__).resolve()),
      'stage_pins':stage_pins,'inputs_before':before,'library_pins':libraries,'MPI':pin(MPI),
      'runtime':plan['runtime'],'results':{},'physical_accepted':False,'active_stochastic_accepted':False,
      'metadata_accepted':False,'scope':plan['seed_state_scope']}
    atomic(root/'execution.json',rec)
    for arm in ('ra4','ra37'):
        case=root/arm; env_arm=env.copy()
        if arm=='ra37': env_arm['WRF_RRTMGP_BATCH_SIZE']='32'
        cmd=[str(MPI),'-launcher','fork','-iface','lo','-n','4',str(case/'wrf.exe')]
        row={'argv':cmd,'cwd':str(case),'status':'STARTING','actual_rc':None,'started_unix':time.time(),'models':0}
        rec['results'][arm]=row;atomic(root/'execution.json',rec);proc=None
        try:
            with (case/'wrf.stdout.log').open('xb') as log:
                proc=subprocess.Popen(cmd,cwd=case,env=env_arm,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                row.update(status='RUNNING',pid=proc.pid,models=1);rec['models']+=1;atomic(root/'execution.json',rec)
                try: rc=proc.wait(timeout=args.max_seconds)
                except subprocess.TimeoutExpired:
                    row['timed_out']=True;rc,_,cleanup=stop_group(proc)
                    if cleanup:row['cleanup_errors']=cleanup
                row.update(actual_rc=rc,reaped=proc.returncode is not None,status='REAPED' if proc.returncode is not None else 'REAP_PENDING',ended_unix=time.time());atomic(root/'execution.json',rec)
            # Durable actual return code precedes logs/output/scanner reads.
            row.update(actual_rc=rc,reaped=proc.returncode is not None,status='REAPED',ended_unix=time.time())
            atomic(root/'execution.json',rec)
            if rc!=0 or row.get('timed_out') or not row['reaped']: raise RuntimeError(f'{arm}: child rc/reap gate failed')
            texts=[]
            for rank in range(4):
                for pref in ('rsl.out','rsl.error'):
                    texts.append((case/f'{pref}.{rank:04d}').read_text(errors='replace'))
            if not all('SUCCESS COMPLETE WRF' in x for x in texts[::2]): raise RuntimeError(f'{arm}: rank success missing')
            if any(x in '\n'.join(texts) for x in ('FATAL CALLED','MPI_ABORT','ERROR: FATAL','VARIABLE NOT FOUND')):
                raise RuntimeError(f'{arm}: fatal/backend error marker')
            if re.search(r'BAD MEMORY ORDER\s*\|\s*ZZ\s*\|','\n'.join(texts),re.I): raise RuntimeError(f'{arm}: padded ZZ backend warning')
            history=case/'wrfout_d01_2016-10-06_13:00:00'
            if not history.is_file(): raise RuntimeError(f'{arm}: missing 13h history')
            with Dataset(history) as d:
                if times(d)!=['2016-10-06_13:00:00']: raise RuntimeError(f'{arm}: wrong resumed history time')
                expected_ra=37 if arm=='ra37' else 4
                if int(d.MP_PHYSICS)!=27 or not (int(d.RA_LW_PHYSICS)==int(d.RA_SW_PHYSICS)==expected_ra):
                    raise RuntimeError(f'{arm}: physics metadata mismatch')
            cp_result=validate_seed(case,plan,arm)
            scans=[mod.scan_file(p) for p in (history,case/'wrfrst_d01_2016-10-06_13:00:00')]
            if any(x.get('status')!='PASS' for x in scans): raise RuntimeError(f'{arm}: numeric scan failed')
            cmp=compare_all(history,pathlib.Path(plan['cases'][arm]['continuous_reference']['path']),'2016-10-06_13:00:00')
            atomic(root/f'{arm}-comparison.json',cmp)
            if cmp['status']!='PASS_ALL_COMMON_ARRAYS_EXACT': raise RuntimeError(f'{arm}: full-state exact comparison failed')
            if cmp['variable_attribute_differences']: raise RuntimeError(f'{arm}: variable attribute mismatch')
            row.update(status='PASS_RESTART_READ_SCOPED',validation={'seed_output':cp_result,'numeric_scans':scans,
                'comparison':pin(root/f'{arm}-comparison.json'),
                'output_pins':[pin(history),cp_result['checkpoint']]},physical_accepted=False,active_stochastic_accepted=False)
            atomic(root/'execution.json',rec)
        except BaseException as exc:
            cleanup=[]
            if proc is not None:
                rc2,reaped,cleanup=stop_group(proc)
                row.update(actual_rc=proc.poll() if proc.returncode is not None else rc2,
                           reaped=reaped,cleanup_errors=cleanup)
            row.update(status='FAIL_PRESERVED' if proc is None or proc.returncode is not None else 'FAIL_REAP_PENDING',error=repr(exc),ended_unix=time.time())
            rec['status']=row['status'];atomic(root/'execution.json',rec)
            raise
    try:
        if head!=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip() or tree!=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=SOURCE,text=True).strip() or subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip(): raise ValueError('source identity changed postflight')
        if source_pins!={rel:pin(SOURCE/rel) for rel in source_pins}: raise ValueError('selected source changed postflight')
        if build_pin!=pin(BUILD/'result.json') or runner_pin!=pin(pathlib.Path(__file__).resolve()) or plan['MPI']!=pin(MPI) or scanner_pin!=pin(scanner): raise ValueError('build/runner/MPI/scanner changed postflight')
        for c in plan['cases'].values():
            for name in ('continuous_reference','source_checkpoint'):
                if pin(pathlib.Path(c[name]['path']))!=c[name]: raise ValueError(f'original reference changed: {name}')
        if pin(control_ref)!=plan['continuous_control_execution'] or pin(pathlib.Path(plan['control_stage_plan']['path']))!=plan['control_stage_plan']: raise ValueError('control receipts changed')
    except BaseException as exc:
        rec.update(status='POSTFLIGHT_FAIL_PRESERVED',error=repr(exc));atomic(root/'execution.json',rec);raise
    try:
        after=snapshot(root,plan['cases'])
        if before!=after: raise RuntimeError('staged input files changed during restart run')
        if stage_pins!={n:pin(root/n) for n in stage_pins}: raise RuntimeError('stage/auth files changed')
        if libraries!={str(p):pin(p) for p in libfiles}: raise RuntimeError('runtime library changed')
        rec.update(status='PASS_PAIRED_RESTART_READ_SCOPED',assets_after=after,ended_unix=time.time(),
           physical_accepted=False,active_stochastic_accepted=False,metadata_accepted=False)
        atomic(root/'execution.json',rec)
    except BaseException as exc:
        rec.update(status='POSTFLIGHT_FAIL_PRESERVED',error=repr(exc));atomic(root/'execution.json',rec);raise
    print(json.dumps({'status':rec['status'],'models':rec['models'],'physical_accepted':False,
                      'active_stochastic_accepted':False}))

if __name__=='__main__': main()
