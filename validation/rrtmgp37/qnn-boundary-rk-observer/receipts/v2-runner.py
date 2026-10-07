#!/usr/bin/env python3
"""One-use OFF/ON QNN-boundary observer control; no physical approval."""
import argparse, datetime as dt, hashlib, importlib.util, json, os, pathlib, re, resource, signal, subprocess, sys, time
import numpy as np
from netCDF4 import Dataset

BASE=pathlib.Path(__file__).resolve().parent.parent
SOURCE=BASE/'build/udm37-qnn-boundary-observer-source-v1'
BUILD=BASE/'build/udm37-qnn-boundary-observer-build-v1'
MPI=BASE/'build/deps/mpich-sock/bin/mpiexec.hydra'
SCHEMA_PATH=BASE/'build/udm37-qnn-boundary-observer-implementation-v1/schema.json'
STOCH=SOURCE/'WRF/Registry/registry.stoch'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def pin(p):return {'path':str(p.resolve()),'sha256':sha(p),'size_bytes':p.stat().st_size,'link':os.readlink(p) if p.is_symlink() else None}
def atomic(p,v):
    t=p.with_name(p.name+'.tmp')
    with t.open('x') as f:json.dump(v,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(t,p);fd=os.open(p.parent,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def stop_group(p):
    errors=[]
    for sig in (signal.SIGTERM,signal.SIGKILL):
        try:os.killpg(p.pid,sig)
        except ProcessLookupError:pass
        except BaseException as e:errors.append(repr(e))
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if sig==signal.SIGKILL:errors.append('leader not reaped after SIGKILL')
        except BaseException as e:errors.append(repr(e))
    return p.poll(),p.returncode is not None,errors
def raw(v):
    v.set_auto_maskandscale(False);v.set_auto_chartostring(False)
    return np.asarray(v[...] if v.ndim==0 else v[:])
def times(ds):
    v=ds['Times'];v.set_auto_maskandscale(False);v.set_auto_chartostring(False)
    return [b''.join(x).decode('ascii') for x in np.asarray(v[:])]
def attr(obj,k):
    x=obj.getncattr(k)
    if isinstance(x,np.ndarray):return {'dtype':str(x.dtype),'shape':list(x.shape),'bytes':x.tobytes().hex()}
    if isinstance(x,np.generic):return {'dtype':str(x.dtype),'bytes':np.asarray(x).tobytes().hex()}
    return repr(x)
def attrs(obj):return {k:attr(obj,k) for k in sorted(obj.ncattrs())}
def snapshot(root,cases):return {arm:{n:pin(root/arm/n) for n in c['files']} for arm,c in cases.items()}
def fscalar(text,k):
    x=re.findall(r'(?mi)^\s*'+re.escape(k)+r'\s*=\s*([^,\n]+)',text)
    if len(x)!=1:raise ValueError(f'{k}: expected one assignment, found {x}')
    return x[0].strip()
def check_multi_perturb(text,stoch_pin):
    x=re.findall(r'(?mi)^\s*multi_perturb\s*=\s*([^,\n]+)',text)
    if x:
        if len(x)!=1 or x[0].strip()!='0':raise ValueError(f'multi_perturb override is not zero: {x}')
        return 'explicit_zero'
    q=pathlib.Path(stoch_pin['path'])
    if pin(q)!=stoch_pin:raise ValueError('registry.stoch pin changed')
    line=next((s for s in q.read_text().splitlines() if re.search(r'\brconfig\s+integer\s+multi_perturb\b',s)),None)
    if line is None or not re.search(r'\bmax_domains\s+0\s+-',line):raise ValueError('registry multi_perturb default is not pinned zero')
    return 'registry_default_zero'

def compare_nc(left,right):
    out={'left':pin(left),'right':pin(right),'whole_file_exact':sha(left)==sha(right),'variables':[],
         'dimension_differences':[],'global_attribute_differences':[],'variable_attribute_differences':[],'array_mismatches':[]}
    with Dataset(left) as a,Dataset(right) as b:
        da={k:(len(v),bool(v.isunlimited())) for k,v in a.dimensions.items()};db={k:(len(v),bool(v.isunlimited())) for k,v in b.dimensions.items()}
        if da!=db:out['dimension_differences']={'left':da,'right':db}
        if list(a.variables)!=list(b.variables):raise ValueError(f'ordered NetCDF variable roster differs: {left.name}')
        ga,gb=attrs(a),attrs(b)
        for k in sorted(set(ga)|set(gb)):
            if ga.get(k)!=gb.get(k):out['global_attribute_differences'].append({'name':k,'left':ga.get(k),'right':gb.get(k)})
        for n in a.variables:
            x,y=a[n],b[n]
            if x.dimensions!=y.dimensions or x.dtype!=y.dtype:raise ValueError(f'{left.name}/{n}: schema mismatch')
            vx,vy=raw(x),raw(y)
            exact=vx.shape==vy.shape and vx.tobytes()==vy.tobytes()
            entry={'name':n,'dimensions':list(x.dimensions),'dtype':str(vx.dtype),'shape':list(vx.shape),'arrays_exact':exact}
            if not exact:
                if vx.shape==vy.shape:entry['different_elements']=int(np.count_nonzero(vx!=vy))
                out['array_mismatches'].append(entry)
            out['variables'].append(entry)
            ax,ay=attrs(x),attrs(y)
            if ax!=ay:out['variable_attribute_differences'].append({'name':n,'left':ax,'right':ay})
    out['pass_exact']=bool(out['whole_file_exact'] and not out['dimension_differences'] and not out['global_attribute_differences'] and not out['variable_attribute_differences'] and not out['array_mismatches'])
    return out

EXPECTED_COLUMNS={
 (0,1):(0,1,23,1,'Y-start',(1,45,1,25),(23,6)),
 (1,4):(1,4,90,26,'X-end',(46,90,26,50),(85,26)),
 (2,3):(2,3,1,74,'X-start',(1,45,51,75),(6,74)),
 (3,2):(3,2,68,99,'Y-end',(46,90,76,99),(68,94)),
}
NAME=re.compile(r'^qnn_d(?P<d>\d+)_rank(?P<rank>\d+)_tile(?P<tile>\d+)_step(?P<step>\d+)_rk(?P<rk>\d+)_side(?P<side>\d+)\.raw$')
def read_capture(directory,schema):
    files=sorted(directory.glob('*.raw'))
    if len(files)!=schema['expected_packets']:raise ValueError(f'expected {schema["expected_packets"]} packets, found {len(files)}')
    seen=set();tile_by_column={};records=[];inflows=0;outflows=0;maxrows=0
    for p in files:
        m=NAME.fullmatch(p.name)
        if not m:raise ValueError(f'unrecognized capture filename {p.name}')
        ident={k:int(v) for k,v in m.groupdict().items()};key=(ident['rank'],ident['side'])
        if key not in EXPECTED_COLUMNS:raise ValueError(f'unexpected rank/side {key}')
        rank,side,i,j,label,bounds,source=EXPECTED_COLUMNS[key]
        if ident['d']!=1 or ident['rank']!=rank or ident['side']!=side or ident['step'] not in schema['model_steps'] or ident['rk'] not in schema['RK_steps']:
            raise ValueError(f'packet identity mismatch {ident}')
        unique=(ident['d'],ident['rank'],ident['tile'],ident['step'],ident['rk'],ident['side'])
        if unique in seen:raise ValueError(f'duplicate packet key {unique}')
        seen.add(unique);tile_by_column.setdefault(key,set()).add(ident['tile'])
        lines=p.read_text().splitlines()
        if len(lines)!=schema['rows_each_packet']+2 or lines[0]!='UDM37QNNB1':raise ValueError(f'{p.name}: packet row count/magic')
        hdr=[int(x) for x in lines[1].split()]
        if len(hdr)!=15:raise ValueError(f'{p.name}: header count {len(hdr)}')
        domain,step,rk,hrank,tile,hside,hi,hj,kts,ktf,bits,its,itf,jts,jtf=hdr
        if (domain,step,rk,hrank,tile,hside,hi,hj)!=(ident['d'],ident['step'],ident['rk'],rank,ident['tile'],side,i,j):raise ValueError(f'{p.name}: filename/header mismatch')
        if (kts,ktf,bits,its,itf,jts,jtf)!=(1,44,32,*bounds):raise ValueError(f'{p.name}: bounds/kind mismatch {hdr}')
        rows=[]
        for line in lines[2:]:
            f=line.split()
            if len(f)!=18:raise ValueError(f'{p.name}: row token count {len(f)}')
            ints=[int(x) for x in f[:5]];vals=[float(x) for x in f[5:]]
            if not all(np.isfinite(vals)):raise ValueError(f'{p.name}: nonfinite row')
            k,branch,si,sj,valid=ints
            if k!=kts+len(rows) or branch not in (0,1) or valid!=1:raise ValueError(f'{p.name}: invalid row key/status {ints}')
            vel,ccn,q0,q1,nc0,nc1,nr0,nr1,al,alb,native_sum,rho,source_qnn=vals
            s32=np.float32(np.float32(al)+np.float32(alb));r32=np.float32(np.float32(1.0)/s32)
            if native_sum!=float(s32) or rho!=float(r32) or not (s32>0 and r32>0):raise ValueError(f'{p.name}: REAL32 density replay mismatch at k={k}')
            inflow=(vel>=0.0 if side in (1,3) else vel<=0.0)
            if branch!=(1 if inflow else 0):raise ValueError(f'{p.name}: branch disagrees with tested velocity at k={k}')
            if nc0!=nc1 or nr0!=nr1:raise ValueError(f'{p.name}: observer changed read-only QNC/QNR context')
            if branch==1:
                inflows+=1
                if (si,sj,source_qnn)!=(0,0,0.0) or q1!=ccn or ccn!=1.0e8:raise ValueError(f'{p.name}: inflow must assign the pinned CCN=1e8 source')
            else:
                outflows+=1
                if (si,sj)!=source or q1!=source_qnn:raise ValueError(f'{p.name}: outflow source/copy contract')
            rows.append({'k':k,'branch':branch,'velocity_test_operand':vel,'ccn':ccn,'qnn_before':q0,'qnn_after':q1,
                         'qnc_before':nc0,'qnc_after':nc1,'qnr_before':nr0,'qnr_after':nr1,'rho_dry':rho})
        if len(rows)!=44 or rows[-1]['k']!=44:raise ValueError(f'{p.name}: incomplete 44-level column')
        maxrows=max(maxrows,len(rows));records.append({'path':p.name,'identity':ident,'sha256':sha(p),'bytes':p.stat().st_size,'rows':rows})
    expected={(r,s,t,step,rk) for r,s in ((0,1),(1,4),(2,3),(3,2)) for t in tile_by_column.get((r,s),set()) for step in schema['model_steps'] for rk in schema['RK_steps']}
    if len(seen)!=24:raise ValueError(f'packet identity coverage {len(seen)} != 24')
    if any(len(x)!=1 for x in tile_by_column.values()):raise ValueError('tile identity varied across captured step/RK packets')
    if inflows==0:raise ValueError('no nonzero inflow observed in the four selected columns')
    return {'status':'PASS_PACKET_STRUCTURE_AND_SOURCE_RELATIONS',
       'packet_count':len(records),'rows':sum(len(r['rows']) for r in records),'inflow_rows':inflows,'outflow_rows':outflows,
       'unique_packet_keys':len(seen),'tile_by_column':{str(k):sorted(v) for k,v in tile_by_column.items()},
       'packets':[{k:v for k,v in row.items() if k!='rows'} for row in records],
       'row_summary':[{k:v for k,v in row.items() if k!='identity'} for row in records],
       'scope':'Four selected boundary columns only; no all-domain event coverage or unit authority.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stage-root',type=pathlib.Path,required=True);ap.add_argument('--timeout',type=int,default=300)
    args=ap.parse_args();root=args.stage_root.resolve()
    if not 1<=args.timeout<=300:raise ValueError('timeout must be 1..300 seconds')
    if (root/'execution.json').exists() or (root/'.one-use.lock').exists():raise FileExistsError('one-use root already started')
    planpath=root/'stage-plan.json';authpath=root/'root-authorization.json';plan=json.loads(planpath.read_text());auth=json.loads(authpath.read_text())
    if auth.get('stage_plan_sha256')!=sha(planpath) or auth.get('runner_sha256')!=sha(pathlib.Path(__file__).resolve()):raise ValueError('root authorization hash mismatch')
    if auth.get('max_models')!=2 or auth.get('timeout_seconds_each')!=300:raise ValueError('authorization limits mismatch')
    br=json.loads((BUILD/'result.json').read_text())
    if br.get('status')!='PASS_BUILD_INSTALL_SCOPED' or br.get('source_head')!=plan['source']['head'] or br.get('source_tree')!=plan['source']['tree']:
        raise ValueError('observer build/source mismatch at launch')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip();tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=SOURCE,text=True).strip()
    if head!=plan['source']['head'] or tree!=plan['source']['tree'] or subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip():raise ValueError('observer source is not clean/frozen')
    sourcepins={n:pin(SOURCE/n) for n in plan['source']['selected_files']}
    if sourcepins!=plan['source']['selected_files']:raise ValueError('observer selected source files changed')
    if pin(STOCH)!=plan['source']['registry_stoch']:raise ValueError('registry.stoch pin changed')
    control_exec=pathlib.Path(plan['control_execution']['path'])
    if pin(control_exec)!=plan['control_execution']:raise ValueError('13h control execution pin changed')
    if pin(BUILD/'result.json')!=plan['build_result'] or pin(BUILD/'plan.json')!=plan['build_plan']:raise ValueError('observer build receipts changed')
    if pin(SCHEMA_PATH)!=plan['observer_schema']:raise ValueError('capture schema changed')
    validator=pathlib.Path(plan['stage_validator']['path'])
    if pin(validator)!=plan['stage_validator']:raise ValueError('stage validator pin changed')
    schema=json.loads(SCHEMA_PATH.read_text())
    scanner_pin=plan['numeric_scanner'];scanner=pathlib.Path(scanner_pin['path'])
    if pin(scanner)!=scanner_pin:raise ValueError('numeric scanner changed')
    spec=importlib.util.spec_from_file_location('qnn_numeric_scan',scanner);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    subprocess.run([sys.executable,str(validator)],cwd=root,check=True,capture_output=True,text=True)
    before=snapshot(root,plan['cases'])
    for arm in ('off','on'):
        if before[arm]!=plan['cases'][arm]['files']:raise ValueError(f'{arm}: staged roster/input pin mismatch')
        nml=(root/arm/'namelist.input').read_text()
        want={'run_days':'0','run_hours':'0','run_minutes':'2','run_seconds':'0','history_interval':'1','restart_interval':'2','time_step':'60','frames_per_outfile':'1000','mp_physics':'27','use_mp_re':'1','ra_lw_physics':'37','ra_sw_physics':'37','rrtmgp_udm_frozen_optics':'1'}
        for k,v in want.items():
            if fscalar(nml,k)!=v:raise ValueError(f'{arm}: {k}={fscalar(nml,k)} expected {v}')
        check_multi_perturb(nml,plan['source']['registry_stoch'])
        if arm=='off' and plan['cases'][arm]['capture_gate']!='unset':raise ValueError('OFF capture gate must be unset')
        if arm=='on' and plan['cases'][arm]['capture_gate']!='1':raise ValueError('ON capture gate must be exactly 1')
        for p in (root/arm).glob('wrfout*'):
            raise ValueError(f'{arm}: preexisting history {p.name}')
        if any((root/arm).glob('rsl.*')) or any((root/arm).glob('wrfrst*')) or (root/arm/'namelist.output').exists():raise ValueError(f'{arm}: preexisting output')
    env=os.environ.copy();home=os.environ.get('HOME')
    for k in list(env):
        if k.startswith(('OMP_','GOMP_','KMP_','WRF_RRTMGP_','WRF_UDM_')) or k in ('LD_PRELOAD','LD_AUDIT'):env.pop(k,None)
    env.update(LD_LIBRARY_PATH=':'.join(str(BASE/p) for p in ('build/deps/netcdf/lib','build/deps/root/usr/lib/x86_64-linux-gnu','build/deps/mpich-sock/lib')),
      MPICH_INTERFACE_HOSTNAME='127.0.0.1',OMP_NUM_THREADS='2',OMP_STACKSIZE='512M',OMP_DYNAMIC='FALSE',OMP_MAX_ACTIVE_LEVELS='1',OPENBLAS_NUM_THREADS='1',WRF_RRTMGP_BATCH_SIZE='32')
    if env.get('HOME')!=home:raise ValueError('HOME changed unexpectedly')
    ldd=subprocess.check_output(['ldd',str(BUILD/'install/bin/wrf')],env=env,text=True)
    if 'not found' in ldd:raise ValueError('unresolved executable dependency')
    libs=[pathlib.Path(x.split('=>')[1].split()[0]) for x in ldd.splitlines() if '=>' in x and x.split('=>')[1].split()[0].startswith('/')]
    librarypins={str(p):pin(p) for p in libs}
    lock=root/'.one-use.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:os.write(fd,(str(os.getpid())+'\n').encode());os.fsync(fd)
    finally:os.close(fd)
    dfd=os.open(root,os.O_DIRECTORY)
    try:os.fsync(dfd)
    finally:os.close(dfd)
    rec={'schema':'UDM37_QNN_BOUNDARY_RUNTIME_EXECUTION_V2','status':'STARTING','model_calls':0,
       'source':{'head':head,'tree':tree},'build_result':pin(BUILD/'result.json'),'runner':pin(pathlib.Path(__file__).resolve()),
       'stage_pins':{x:pin(root/x) for x in ('stage-plan.json','verify_stage.py','root-authorization.json')},
       'selected_source_pins':sourcepins,'inputs_before':before,'library_pins':librarypins,'MPI':pin(MPI),
       'runtime':plan['runtime'],'HOME_preserved':home,'arms':{},'scientific_accepted':False,
       'scope':'Observer OFF/ON passivity only; no unmodified-source equivalence or physics approval.'}
    atomic(root/'execution.json',rec)
    for arm in ('off','on'):
        d=root/arm;armenv=env.copy()
        if arm=='on':
            cap=pathlib.Path(plan['cases'][arm]['capture_directory'])
            if not cap.is_dir() or any(cap.iterdir()):raise ValueError('ON capture directory is not fresh')
            armenv['WRF_UDM_QNN_BOUNDARY_CAPTURE']='1';armenv['WRF_UDM_QNN_BOUNDARY_DIR']=str(cap)
        else:
            armenv.pop('WRF_UDM_QNN_BOUNDARY_CAPTURE',None);armenv.pop('WRF_UDM_QNN_BOUNDARY_DIR',None)
        cmd=[str(MPI),'-launcher','fork','-iface','lo','-n','4',str(d/'wrf.exe')]
        row={'status':'STARTING','models':0,'actual_rc':None,'argv':cmd,'cwd':str(d),'started_unix':time.time()};rec['arms'][arm]=row;atomic(root/'execution.json',rec);proc=None
        try:
            with (d/'wrf.stdout.log').open('xb') as log:
                proc=subprocess.Popen(cmd,cwd=d,env=armenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                row.update(status='RUNNING',pid=proc.pid,models=1);rec['model_calls']+=1;atomic(root/'execution.json',rec)
                try:rc=proc.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    row['timed_out']=True;rc,_,errs=stop_group(proc)
                    if errs:row['cleanup_errors']=errs
                row.update(actual_rc=rc,reaped=proc.returncode is not None,status='REAPED',ended_unix=time.time())
                # Persist terminal child status before closing its log or inspecting outputs.
                atomic(root/'execution.json',rec)
            row.update(actual_rc=rc,reaped=proc.returncode is not None,status='REAPED',ended_unix=time.time())
            atomic(root/'execution.json',rec)
            if rc!=0 or row.get('timed_out') or not row['reaped']:raise RuntimeError(f'{arm}: child did not complete RC0/reaped')
            logs=[]
            for rank in range(4):
                out=(d/f'rsl.out.{rank:04d}').read_text(errors='replace');err=(d/f'rsl.error.{rank:04d}').read_text(errors='replace');logs.extend((out,err))
                if 'SUCCESS COMPLETE WRF' not in out:raise RuntimeError(f'{arm}: rank {rank} lacks success marker')
            if any(x in '\n'.join(logs) for x in ('FATAL CALLED','MPI_ABORT','ERROR: FATAL','QNN_BOUNDARY_CAPTURE:')):raise RuntimeError(f'{arm}: fatal observer/model marker')
            histories=sorted(d.glob('wrfout_d01_*'))
            expected_names=[plan['cases'][arm]['expected_history_file']]
            if [p.name for p in histories]!=expected_names:raise RuntimeError(f'{arm}: history roster differs')
            restart=d/plan['cases'][arm]['expected_restart']
            if not restart.is_file() or len(list(d.glob('wrfrst_d01_*')))!=1:raise RuntimeError(f'{arm}: restart roster differs')
            scans=[mod.scan_file(p) for p in histories+[restart]]
            if any(x.get('status')!='PASS' for x in scans):raise RuntimeError(f'{arm}: numeric scan failed')
            with Dataset(histories[-1]) as nc:
                if times(nc)!=plan['cases'][arm]['expected_history_times']:raise RuntimeError(f'{arm}: history Times are not 00:00/00:01/00:02')
                if int(nc.MP_PHYSICS)!=27 or int(nc.RA_LW_PHYSICS)!=37 or int(nc.RA_SW_PHYSICS)!=37:raise RuntimeError(f'{arm}: physics metadata')
            row['numeric_scans']=scans;row['outputs']=[pin(p) for p in histories+[restart]]
            if arm=='off':
                if any((d/'capture').glob('*.raw')):raise RuntimeError('OFF arm unexpectedly wrote observer packets')
                row['capture_status']='OFF_NO_CAPTURE_EXPECTED'
            else:
                if pin(SCHEMA_PATH)!=plan['observer_schema']:raise RuntimeError('observer schema changed')
                capture=read_capture(pathlib.Path(plan['cases'][arm]['capture_directory']),schema)
                atomic(root/'capture-validation.json',capture);row['capture_validation']=pin(root/'capture-validation.json')
                row['capture_status']=capture['status']
            row['status']='PASS_RUNTIME_SCOPED';atomic(root/'execution.json',rec)
        except BaseException as e:
            if proc is not None:
                rc2,reaped,errs=stop_group(proc);row.update(actual_rc=proc.poll() if proc.returncode is not None else rc2,reaped=reaped)
                if errs:row['cleanup_errors']=errs
            row.update(status='FAIL_PRESERVED',error=repr(e),ended_unix=time.time());rec['status']='FAIL_PRESERVED';atomic(root/'execution.json',rec);raise
    try:
        output_comparisons=[]
        names=[plan['cases']['off']['expected_history_file']]
        names.append(plan['cases']['off']['expected_restart'])
        if len(names)!=2 or len(set(names))!=2:raise RuntimeError('expected exactly one multi-time history and one restart')
        for kind in names:
            result=compare_nc(root/'off'/kind,root/'on'/kind);output_comparisons.append(result)
            rec['off_on_comparisons']=output_comparisons
            atomic(root/'execution.json',rec)
            if not result['pass_exact']:raise RuntimeError(f'OFF/ON complete output differs: {kind}')
        if rec['arms']['on']['capture_status']=='NONZERO_INFLOW_NOT_OBSERVED':
            rec['observer_scope_result']='NONZERO_INFLOW_NOT_OBSERVED'
        else:rec['observer_scope_result']='INFLOW_OBSERVED_IN_SELECTED_COLUMNS'
        after=snapshot(root,plan['cases'])
        if before!=after:raise RuntimeError('staged inputs changed during model calls')
        rec['inputs_after']=after
        if sourcepins!={n:pin(SOURCE/n) for n in sourcepins}:raise RuntimeError('source changed during execution')
        if pin(STOCH)!=plan['source']['registry_stoch']:raise RuntimeError('registry changed during execution')
        if librarypins!={str(p):pin(p) for p in libs}:raise RuntimeError('library closure changed')
        if rec['stage_pins']!={x:pin(root/x) for x in rec['stage_pins']}:raise RuntimeError('stage/authorization changed')
        rec.update(status='PASS_PAIRED_OBSERVER_OFF_ON_RUNTIME_SCOPED',ended_unix=time.time(),scientific_accepted=False)
        atomic(root/'execution.json',rec)
    except BaseException as e:
        rec.update(status='FAIL_PRESERVED',error=repr(e),ended_unix=time.time(),scientific_accepted=False)
        atomic(root/'execution.json',rec)
        raise
    print(json.dumps({'status':rec['status'],'models':rec['model_calls'],'observer_scope_result':rec['observer_scope_result'],'scientific_accepted':False}))

if __name__=='__main__':main()
