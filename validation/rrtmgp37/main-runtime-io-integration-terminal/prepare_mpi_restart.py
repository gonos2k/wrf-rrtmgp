#!/usr/bin/env python3
"""Prepare same-arm 12:00->13:00 restart copies; never launches WRF."""
import argparse, datetime as dt, hashlib, json, os, pathlib, re, shutil, subprocess
import numpy as np
from netCDF4 import Dataset

BASE=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
SOURCE=BASE/'build/udm37-main-runtime-io-mpi-source-v1'
BUILD=BASE/'build/udm37-main-runtime-io-mpi-build-v1'
CONTROL_RUNNER=BASE/'build/udm37-main-runtime-io-integration-preparation-v1/mpi_control_once.py'
RUNNER=BASE/'build/udm37-main-runtime-io-integration-preparation-v1/mpi_restart_once.py'
SCANNER=BASE/'build/udm37-matthew-dt60-paired-48h-v1/validate_all_numeric.py'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def pin(path):
    return {'path':str(path.resolve()),'sha256':sha(path),'size_bytes':path.stat().st_size,
            'link':os.readlink(path) if path.is_symlink() else None}
def atomic(path,value):
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);fd=os.open(path.parent,os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
def set_scalar(text,name,value):
    rx=re.compile(r'(?mi)^(\s*'+re.escape(name)+r'\s*=\s*)[^,\n]+')
    changed,count=rx.subn(lambda m:m.group(1)+value,text)
    if count!=1: raise ValueError(f'{name}: expected one assignment, got {count}')
    return changed
def attr_value(v,k):
    x=v.getncattr(k)
    if isinstance(x,np.ndarray): return {'dtype':str(x.dtype),'shape':list(x.shape),'bytes':x.tobytes().hex()}
    if isinstance(x,np.generic): return {'dtype':str(x.dtype),'bytes':np.asarray(x).tobytes().hex()}
    return repr(x)
def variable_record(v):
    v.set_auto_maskandscale(False);v.set_auto_chartostring(False)
    a=np.asarray(v[:])
    return {'dimensions':list(v.dimensions),'dtype':str(a.dtype),'shape':list(a.shape),
            'data_sha256':hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest(),
            'attributes':{k:attr_value(v,k) for k in sorted(v.ncattrs())}}
def file_schema(path):
    with Dataset(path,'r') as d:
        d.set_auto_maskandscale(False); d.set_auto_chartostring(False)
        return {'dimensions':{k:{'size':len(v),'isunlimited':bool(v.isunlimited())} for k,v in d.dimensions.items()},
                'global_attributes':{k:attr_value(d,k) for k in sorted(d.ncattrs())},
                'variables':{k:variable_record(v) for k,v in d.variables.items()}}
def scalar_namelist(text,key):
    got=re.findall(r'(?mi)^\s*'+re.escape(key)+r'\s*=\s*([^,\n]+)',text)
    if len(got)!=1: raise ValueError(f'{key}: expected one value, got {got}')
    return got[0].strip()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--control-root',type=pathlib.Path,required=True)
    ap.add_argument('--stage-root',type=pathlib.Path,required=True)
    ap.add_argument('--seed-sentinel',action='store_true',
        help='replace only ISEEDARR_MULT3D in restart-copy with signed nonzero sentinel; inactive I/O test only')
    args=ap.parse_args(); control=args.control_root.resolve(); root=args.stage_root.resolve()
    if root.exists(): raise FileExistsError(root)
    control_plan=json.loads((control/'stage-plan.json').read_text())
    control_run=json.loads((control/'execution.json').read_text())
    build=json.loads((BUILD/'result.json').read_text())
    if control_run.get('status')!='PASS_PAIRED_RUNTIME_SCOPED' or control_run.get('model_calls')!=2:
        raise ValueError('13-hour continuous parent pair is not terminal PASS')
    for arm in ('ra4','ra37'):
        result=control_run.get('results',{}).get(arm,{})
        if result.get('actual_rc')!=0 or result.get('reaped') is not True or result.get('timed_out'):
            raise ValueError(f'{arm} control did not complete RC0/reaped')
        if result.get('status') not in ('PASS_RUNTIME_SCOPED','PASS'):
            raise ValueError(f'{arm} control status is not a pass: {result.get("status")}')
        if len(result.get('validation',{}).get('times',[]))!=14:
            raise ValueError(f'{arm} control lacks 14 hourly records')
    if build.get('status')!='PASS_BUILD_INSTALL_SCOPED' or build.get('models')!=0:
        raise ValueError('fresh build receipt is invalid')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    if head!='dd7eb1da3a23ca8f21bd4d5bf82f7feecf813fc5' or head!=build['source_head']:
        raise ValueError('source/build identity mismatch')
    tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=SOURCE,text=True).strip()
    if tree!=build['source_tree']: raise ValueError('source/build tree mismatch')
    if subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip():
        raise ValueError('source worktree is dirty')
    source_files=control_plan.get('source',{}).get('selected_files',{})
    if 'WRF/Registry/registry.stoch' not in source_files:
        raise ValueError('parent stage does not pin stochastic Registry default')
    regtext=(SOURCE/'WRF/Registry/registry.stoch').read_text()
    if not re.search(r'(?mi)^rconfig\s+integer\s+multi_perturb\s+.*?\s+0\s+-\s+"stochastic forcing option',regtext):
        raise ValueError('source Registry no longer declares multi_perturb default 0')
    complete_source_pins={}
    for rel,record in source_files.items():
        current=pin(SOURCE/rel)
        if current['sha256']!=record['sha256'] or current['size_bytes']!=record['size_bytes']: raise ValueError(f'source pin changed: {rel}')
        if 'path' in record and current['path']!=record['path']: raise ValueError(f'source path changed: {rel}')
        complete_source_pins[rel]=current
    source_files=complete_source_pins
    control_pin=pin(control/'execution.json')
    if not RUNNER.is_file(): raise FileNotFoundError(RUNNER)

    root.mkdir(parents=True)
    cases={}
    for arm in ('ra4','ra37'):
        source_case=pathlib.Path(control_plan['cases'][arm]['directory'])
        case=root/arm;case.mkdir()
        checkpoint_name='wrfrst_d01_2016-10-06_12:00:00'
        original_checkpoint=source_case/checkpoint_name
        if not original_checkpoint.is_file(): raise FileNotFoundError(original_checkpoint)
        cp_before=pin(original_checkpoint)
        shutil.copy2(original_checkpoint,case/checkpoint_name)
        copied=case/checkpoint_name
        schema_before=file_schema(copied)
        seed_meta={'enabled':bool(args.seed_sentinel),'scope':'inactive multi_perturb=0 read/write I/O sentinel only',
                   'original_checkpoint':cp_before,'copy_before':pin(copied),'schema_before':schema_before,
                   'variable':'ISEEDARR_MULT3D'}
        if 'ISEEDARR_MULT3D' not in schema_before['variables']:
            raise ValueError(f'{arm}: 12-hour checkpoint lacks ISEEDARR_MULT3D')
        seed_before=schema_before['variables']['ISEEDARR_MULT3D']
        if seed_before['dtype']!='int32' or seed_before['dimensions']!=['Time','num_pert_3d','bottom_top']:
            raise ValueError(f'{arm}: unexpected seed schema {seed_before}')
        if args.seed_sentinel:
            with Dataset(copied,'r+') as d:
                v=d['ISEEDARR_MULT3D'];v.set_auto_maskandscale(False)
                old=np.asarray(v[:]).copy()
                if old.dtype!=np.dtype('int32') or old.size==0: raise ValueError('seed type/size')
                sentinel=-np.arange(1,old.size+1,dtype=np.int32).reshape(old.shape)
                if np.array_equal(old,sentinel): raise ValueError('sentinel did not change source seed')
                v[:]=sentinel
            schema_after=file_schema(copied)
            for name,record in schema_before['variables'].items():
                if name!='ISEEDARR_MULT3D' and schema_after['variables'][name]!=record:
                    raise ValueError(f'{arm}: sentinel edit changed non-seed variable {name}')
            if schema_after['dimensions']!=schema_before['dimensions'] or schema_after['global_attributes']!=schema_before['global_attributes']:
                raise ValueError(f'{arm}: sentinel edit changed dimensions/global attrs')
            after_seed=schema_after['variables']['ISEEDARR_MULT3D']
            if after_seed['dimensions']!=seed_before['dimensions'] or after_seed['dtype']!=seed_before['dtype'] or after_seed['attributes']!=seed_before['attributes']:
                raise ValueError(f'{arm}: sentinel edit changed seed schema/attributes')
            seed_meta.update(schema_after=schema_after,copy_after=pin(copied),
                seed_expected={'dimensions':list(seed_before['dimensions']),'shape':list(sentinel.shape),'dtype':str(sentinel.dtype),
                               'data_sha256':hashlib.sha256(sentinel.tobytes()).hexdigest(),
                               'min':int(sentinel.min()),'max':int(sentinel.max()),
                               'pattern':'negative signed int32 sequence -1..-N in C order'})
        else:
            seed_meta.update(copy_after=pin(copied),seed_expected={'dimensions':seed_before['dimensions'],'shape':seed_before['shape'],
                'dtype':seed_before['dtype'],'data_sha256':seed_before['data_sha256'],'pattern':'unchanged copy'})
        if pin(original_checkpoint)!=cp_before: raise ValueError('original checkpoint changed during preparation')

        # Copy only the parent's declared static roster; no 13-hour outputs or logs.
        for name,record in control_plan['cases'][arm]['files'].items():
            src=source_case/name; dst=case/name
            if pin(src)!=record: raise ValueError(f'continuous static input drift: {arm}/{name}')
            if name in ('wrf.stdout.log','namelist.output') or name.startswith(('rsl.','wrfout','wrfrst')):
                raise ValueError(f'control static roster contains runtime output {name}')
            if src.is_symlink(): dst.symlink_to(os.readlink(src))
            else: shutil.copy2(src,dst)
            if name=='wrf.exe':
                if dst.is_symlink() or dst.exists(): dst.unlink()
                shutil.copy2(BUILD/'install/bin/wrf',dst)
        nml_path=case/'namelist.input';nml=nml_path.read_text()
        changes={'run_days':'0','run_hours':'1','run_minutes':'0','run_seconds':'0',
          'start_year':'2016','start_month':'10','start_day':'06','start_hour':'12','start_minute':'00','start_second':'00',
          'end_year':'2016','end_month':'10','end_day':'06','end_hour':'13','end_minute':'00','end_second':'00',
          'history_interval':'60','restart':'.true.','restart_interval':'60','io_form_restart':'2','time_step':'60'}
        for k,v in changes.items():
            if k in ('start_minute','start_second','end_second') and not re.search(r'(?mi)^\s*'+k+r'\s*=',nml):
                nml,count=re.subn(r'(?mi)(^\s*&time_control\s*\n)', lambda m:m[1]+f' {k} = {v},\n',nml,count=1)
                if count!=1: raise ValueError('time_control group missing')
            else: nml=set_scalar(nml,k,v)
        if re.search(r'(?mi)^\s*write_hist_at_0h_rst\s*=',nml): nml=set_scalar(nml,'write_hist_at_0h_rst','.false.')
        else:
            nml,count=re.subn(r'(?mi)(^\s*&time_control\s*\n)',r'\1 write_hist_at_0h_rst = .false.,\n',nml,count=1)
            if count!=1: raise ValueError('could not insert write_hist_at_0h_rst')
        if re.search(r'(?mi)^\s*multi_perturb\s*=',nml):
            if scalar_namelist(nml,'multi_perturb')!='0': raise ValueError('multi_perturb must stay disabled')
            mp='explicit 0'
        else: mp='omitted; pinned Registry default 0'
        nml_path.write_text(nml)
        expected={p.name:pin(p) for p in sorted(case.iterdir())}
        cases[arm]={'directory':str(case),'files':expected,'source_checkpoint':cp_before,
          'restart_input':pin(copied),'continuous_reference':pin(source_case/'wrfout_d01_2016-10-06_00:00:00'),
          'seed_control':seed_meta,'multi_perturb_policy':mp,'namelist_changes':changes|{'write_hist_at_0h_rst':'.false.'},
          'status':'STAGED_UNRUN'}

    plan={'schema':'UDM_NETCDF_ZZ_RESTART_READ_STAGE_V1','status':'STAGED_UNRUN',
      'source':{'path':str(SOURCE),'head':head,'tree':tree,'selected_files':source_files},
      'build_result':pin(BUILD/'result.json'),'continuous_control_execution':control_pin,
      'control_stage_plan':pin(control/'stage-plan.json'),'runner':pin(RUNNER),'numeric_scanner':pin(SCANNER),
      'library_pins':{name:{key:value for key,value in (dict(record, size_bytes=record.get('size_bytes',record.get('size')))).items() if key!='size'} for name,record in control_run['library_pins'].items()},
      'MPI':pin(BASE/'build/deps/mpich-sock/bin/mpiexec.hydra'),
      'runtime':{'MPI':4,'OMP':2,'duration_minutes':60,'history_interval_minutes':60,
                 'start':'2016-10-06_12:00:00','end':'2016-10-06_13:00:00'},
      'limits':{'max_models':2,'per_arm_timeout_seconds':300,'first_failure_stops':True},
      'multi_perturb':0,'seed_sentinel_requested':bool(args.seed_sentinel),
      'seed_state_scope':'inactive I/O persistence control only; no active stochastic acceptance',
      'strict_comparison':{'all_variables':True,'ordered_schema_dimensions_dtype_shape':True,
          'array_bytes_exact':True,'variable_attributes_exact':True,'global_attribute_differences_recorded':True,
          'metadata_accepted':False,'physical_accepted':False},
      'models_launched':0,'cases':cases,'physical_accepted':False,
      'scope':'Same-arm 12:00 restart read to 13:00 compared with continuous 13-hour history; no physical or active stochastic approval.'}
    atomic(root/'stage-plan.json',plan)
    verifier='''#!/usr/bin/env python3
import hashlib,json,pathlib,re,sys
root=pathlib.Path(__file__).resolve().parent; p=json.loads((root/"stage-plan.json").read_text()); errors=[]
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()
for arm,c in p["cases"].items():
 d=pathlib.Path(c["directory"]); expected=set(c["files"]); actual={x.name for x in d.iterdir()}
 if actual!=expected: errors.append(f"{arm}: roster mismatch extra={sorted(actual-expected)} missing={sorted(expected-actual)}")
 for name,r in c["files"].items():
  q=d/name
  if not q.is_file(): errors.append(f"{arm}/{name}: missing"); continue
  if q.stat().st_size!=r["size_bytes"] or digest(q)!=r["sha256"]: errors.append(f"{arm}/{name}: changed")
 n=(d/"namelist.input").read_text()
 want={"run_days":"0","run_hours":"1","run_minutes":"0","run_seconds":"0","start_year":"2016","start_month":"10","start_day":"06","start_hour":"12","start_minute":"00","start_second":"00","end_year":"2016","end_month":"10","end_day":"06","end_hour":"13","end_minute":"00","end_second":"00","history_interval":"60","restart":".true.","restart_interval":"60","io_form_restart":"2","time_step":"60"}
 for k,v in want.items():
  got=re.findall(r"(?mi)^\\s*"+k+r"\\s*=\\s*([^,\\n]+)",n)
  if got!=[v]: errors.append(f"{arm}: {k} {got} != {[v]}")
 if re.search(r"(?mi)^\\s*multi_perturb\\s*=\\s*([^,\\n]+)",n) and re.findall(r"(?mi)^\\s*multi_perturb\\s*=\\s*([^,\\n]+)",n)!=["0"]: errors.append(f"{arm}: multi_perturb not zero")
 if list(d.glob("rsl.*")) or list(d.glob("wrfout*")) or (d/"namelist.output").exists(): errors.append(f"{arm}: outputs already exist")
 if {x.name for x in d.glob("wrfrst_d01_*")}!={"wrfrst_d01_2016-10-06_12:00:00"}: errors.append(f"{arm}: restart roster is not input-only")
print(json.dumps({"status":"FAIL" if errors else "PASS_STAGED_UNRUN","errors":errors,"models_launched":0,"seed_sentinel":p["seed_sentinel_requested"]}))
sys.exit(bool(errors))
'''
    (root/'verify_stage.py').write_text(verifier);os.chmod(root/'verify_stage.py',0o755)
    atomic(root/'PENDING_ROOT_AUTHORIZATION.json',{'status':'PENDING_ROOT_REVIEW',
      'plan_sha256':sha(root/'stage-plan.json'),'runner_sha256':sha(RUNNER),
      'max_models':2,'per_arm_timeout_seconds':300,'seed_sentinel':bool(args.seed_sentinel),
      'physical_accepted':False,'active_stochastic_accepted':False})
    print(json.dumps({'status':'STAGED_UNRUN','models_launched':0,'seed_sentinel':bool(args.seed_sentinel),
                      'files_per_arm':len(cases['ra4']['files']),'stage_plan_sha256':sha(root/'stage-plan.json')}))

if __name__=='__main__': main()
