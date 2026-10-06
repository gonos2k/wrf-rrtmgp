#!/usr/bin/env python3
"""Prepare or execute short GNU CMake WRF radiation compatibility smokes.

Default is --prepare-only. --execute runs one-minute RA37 frozen-on, expected
RA37 frozen-off rejection, and RA4 frozen-off control in fresh private folders.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, resource, shutil, subprocess, time
import numpy as np
from netCDF4 import Dataset

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
TASK = ROOT / 'build/udm-cmake-export-fix'
INSTALL = TASK / 'install-final'
SOURCE = ROOT / 'build/pr-wrf-rrtmgp/build/udm-cmake-export-fix/source'
BASE37 = ROOT / 'build/udm-selected-real-audit/off-only-20261003-v1/audit-off/run'
BASE4 = ROOT / 'build/udm-selected-real-audit/ra4-baseline-run-20261003-v1/run'
TABLE = ROOT / 'build/pr-wrf-rrtmgp/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
NETCDF = ROOT / 'build/deps/netcdf'
OUT = TASK / 'runtime-smokes-v2'
MUTABLE = re.compile(r'^(wrfout_|wrfrst_|rsl\.|namelist\.output$|.*\.log$)')
CHECKPOINT = 'wrfrst_d01_2010-06-11_12:00:00'
HISTORY = 'wrfout_d01_2010-06-11_12:01:00'
HAIL_FATAL = 'RRTMGP_INPUT_UDM_HAIL_OPTICS_UNSUPPORTED'
PINNED_COMMIT = 'bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291'
PINNED_EXE_SHA256 = '721b112a0906a1d25d2eb26535fe50b644c4f71a38a4584128c945e4e7a4acd0'
PINNED_CHECKPOINT_SHA256 = '943a53db058f2d9560c6f0d571f3ff9bb8efb407010c5eea2026922a6eeee7b8'
PINNED_TABLE_SHA256 = '8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583'
PINNED_DIFF_SHA256 = '81b21852f8092869b8ff015029d6ac44ce152de711ede7a764ab115c7494a39b'
PINNED_CONFIG = {
    'CMakeCache.txt':'d913f3abffcf71b06e702b98236367bb9dd1dd9d40735d43ddd56bc69363236c',
    'build.ninja':'a211a5bff72c45aee4df551ac2f984da9e8f96c3ab545fe8432acef99402cba1',
    'toolchain.cmake':'8c00a7b004133cbbb1b566b6660b5fe1878ebc4aaeb18ecd0a1cd6afebdae6df',
}
CONFIG_FILES={'CMakeCache.txt':TASK/'binary-final/CMakeCache.txt',
              'build.ninja':TASK/'binary-final/build.ninja',
              'toolchain.cmake':TASK/'toolchain.cmake'}
PINNED_SOURCE_FILES = {
    'WRF/CMakeLists.txt':'f2a9fad649e0d9dfc23d0f0719252b438c928e9fa4346ad08eb9dd460331fc99',
    'WRF/external/rte_rrtmgp/CMakeLists.txt':'aa0c88f42a9a045c7098b8cc4064458208736e9ed742a0803139feade609deda',
    'WRF/phys/module_physics_init.F':'a60589e0af8d8a4bb5984652fb08bf404e5c304ec2baf4c6285b25d442b6a0af',
    'WRF/phys/module_microphysics_driver.F':'1c3b3ecd8c8f5f3fb4572f2837216faff33425b75898cfe5bcc92c06c78a8716',
}
PINNED_REGISTRATION_SHA256='2090b7ec32a3f0fc7e4c6eaa0632df4a2836665d92559285958f205cffe1d27c'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def source_provenance():
    commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    diff=hashlib.sha256(subprocess.check_output(['git','-C',str(SOURCE),'diff','--binary','HEAD'])).hexdigest()
    config={k:sha(p) for k,p in CONFIG_FILES.items()}
    reg=sha(SOURCE/'config/registration37.json')
    paths=['WRF/CMakeLists.txt','WRF/external/rte_rrtmgp/CMakeLists.txt',
           'WRF/phys/module_physics_init.F','WRF/phys/module_microphysics_driver.F']
    source_files={p:sha(SOURCE/p) for p in paths}
    return {'commit':commit,'diff_sha256':diff,'config_sha256':config,
            'registration37_sha256':reg,'source_files_sha256':source_files}


def verify_pins():
    prov=source_provenance()
    if prov['commit']!=PINNED_COMMIT: raise RuntimeError('source commit pin mismatch')
    if prov['diff_sha256']!=PINNED_DIFF_SHA256: raise RuntimeError('source diff pin mismatch')
    if prov['config_sha256']!=PINNED_CONFIG: raise RuntimeError('CMake configuration hash pin mismatch')
    if prov['registration37_sha256']!=PINNED_REGISTRATION_SHA256: raise RuntimeError('registration receipt pin mismatch')
    if prov['source_files_sha256']!=PINNED_SOURCE_FILES: raise RuntimeError('changed source file pin mismatch')
    if sha(INSTALL/'bin/wrf')!=PINNED_EXE_SHA256: raise RuntimeError('installed executable pin mismatch')
    if sha(TABLE)!=PINNED_TABLE_SHA256: raise RuntimeError('frozen table pin mismatch')
    return prov


def files_hashes(directory):
    out={}
    for p in sorted(Path(directory).iterdir()):
        if p.is_file() and (not MUTABLE.match(p.name) or p.name==CHECKPOINT) and p.name not in {'wrf.exe','real.exe','namelist.input'}:
            out[p.name]=sha(p)
    return out


def verify_case_state(case_dir, receipt):
    run=Path(receipt['run_directory'])
    provenance=verify_pins()
    if provenance!=receipt['source_configuration_hashes']: raise RuntimeError('source/config provenance changed since preflight')
    if sha(__file__)!=receipt['runner_sha256']: raise RuntimeError('runner changed since preflight')
    if sha(INSTALL/'bin/wrf')!=PINNED_EXE_SHA256 or sha(run/'wrf.exe')!=PINNED_EXE_SHA256:
        raise RuntimeError('installed or staged executable changed')
    if sha(TABLE)!=PINNED_TABLE_SHA256: raise RuntimeError('frozen table changed')
    baseline=Path(receipt['source_baseline'])
    if sha(baseline/CHECKPOINT)!=PINNED_CHECKPOINT_SHA256 or sha(run/CHECKPOINT)!=PINNED_CHECKPOINT_SHA256:
        raise RuntimeError('baseline or staged checkpoint changed')
    if sha(baseline/'namelist.input')!=receipt['baseline_namelist_sha256']:
        raise RuntimeError('baseline namelist changed')
    if sha(run/'namelist.input')!=receipt['staged_namelist_sha256']:
        raise RuntimeError('staged namelist changed')
    if sha(baseline/HISTORY)!=receipt['baseline_history_sha256']:
        raise RuntimeError('reference history changed')
    if files_hashes(baseline)!=receipt['baseline_immutable_inputs_sha256']:
        raise RuntimeError('baseline immutable assets changed')
    if files_hashes(run)!=receipt['staged_immutable_inputs_sha256']:
        raise RuntimeError('staged immutable assets changed')
    return {'source_configuration':provenance,'installed_executable_sha256':sha(INSTALL/'bin/wrf'),
            'staged_executable_sha256':sha(run/'wrf.exe'),'checkpoint_sha256':sha(run/CHECKPOINT),
            'table_sha256':sha(TABLE),'namelist_sha256':sha(run/'namelist.input'),
            'baseline_assets_sha256':hashlib.sha256(json.dumps(files_hashes(baseline),sort_keys=True).encode()).hexdigest(),
            'staged_assets_sha256':hashlib.sha256(json.dumps(files_hashes(run),sort_keys=True).encode()).hexdigest()}


def stack_preexec(stack_record_path):
    def set_limit():
        requested=512*1024*1024
        soft,hard=resource.getrlimit(resource.RLIMIT_STACK)
        if hard!=-1 and hard<requested: raise RuntimeError('hard stack limit below requested 512 MiB')
        resource.setrlimit(resource.RLIMIT_STACK,(requested,hard))
        actual=resource.getrlimit(resource.RLIMIT_STACK)
        Path(stack_record_path).write_text(json.dumps({'soft_bytes':actual[0],'hard_bytes':actual[1]})+'\n')
    return set_limit


def namelist_fields(path):
    text=Path(path).read_text()
    result={}
    for key in ('run_minutes','ra_lw_physics','ra_sw_physics','rrtmgp_udm_frozen_optics','rrtmgp_udm_frozen_table'):
        m=re.search(r'^\s*'+re.escape(key)+r'\s*=\s*([^\n!]+)',text,re.M|re.I)
        if not m: raise ValueError(f'missing namelist key {key}: {path}')
        result[key]=m.group(1).strip().rstrip(',')
    return result


def replace_key(text,key,value):
    pat=re.compile(r'^(\s*'+re.escape(key)+r'\s*=\s*)[^\n!]*',re.M|re.I)
    text,n=pat.subn(lambda m:m.group(1)+value,text)
    if n!=1: raise ValueError(f'expected exactly one {key}, found {n}')
    return text


def namelist_without_smoke_fields(path):
    text=Path(path).read_text()
    for key in ('run_minutes','rrtmgp_udm_frozen_optics','rrtmgp_udm_frozen_table'):
        text=re.sub(r'^\s*'+re.escape(key)+r'\s*=\s*[^\n!]*\n','',text,flags=re.M|re.I)
    return text


def mask_for(var, array):
    mask=np.zeros(array.shape,dtype=bool)
    for attr in ('_FillValue','missing_value'):
        if attr not in var.ncattrs(): continue
        val=np.asarray(var.getncattr(attr))
        if array.dtype.kind in 'fc' and np.any(np.isnan(val)):
            mask |= np.isnan(array)
        else:
            for v in val.reshape(-1): mask |= (array==v)
    return mask


def history_check(candidate, baseline):
    result={'history_file':HISTORY,'status':'PASS','variables':0,'numeric_values':0,'times_string':None,'times_bytes_equal':False,'numeric_fill_masks':[],'nonfinite':[],'layout_mismatches':[]}
    cp=Path(candidate)/HISTORY; bp=Path(baseline)/HISTORY
    if not cp.is_file() or not bp.is_file(): raise ValueError('expected 12:01 history is missing')
    candidate_histories=sorted(p.name for p in Path(candidate).glob('wrfout_d01_*'))
    if candidate_histories != [HISTORY]: raise ValueError(f'unexpected history schedule: {candidate_histories}')
    with Dataset(bp) as b, Dataset(cp) as c:
        b.set_auto_maskandscale(False); c.set_auto_maskandscale(False)
        for label,d in (('baseline',b),('candidate',c)):
            dims={name:len(d.dimensions[name]) for name in ('Time','west_east','south_north','bottom_top') if name in d.dimensions}
            if dims!={'Time':1,'west_east':289,'south_north':189,'bottom_top':39}:
                raise ValueError(f'{label} domain dimensions are not expected MP27/RA4 fixture: {dims}')
        if set(b.variables)!=set(c.variables): raise ValueError('history variable names differ')
        if 'Times' not in b.variables or 'Times' not in c.variables: raise ValueError('Times variable missing')
        result['times_bytes_equal']=np.asarray(b['Times'][:]).tobytes()==np.asarray(c['Times'][:]).tobytes()
        if not result['times_bytes_equal']: raise ValueError('12:01 Times bytes differ')
        times=np.asarray(c['Times'][:])
        if times.dtype.kind=='S':
            text=b''.join(times.reshape(-1).tolist()).decode('ascii').rstrip('\x00 ')
        else:
            text=str(times.reshape(-1)[0]).strip()
        result['times_string']=text
        if text!='2010-06-11_12:01:00': raise ValueError(f'unexpected exact Times value: {text!r}')
        for name in sorted(b.variables):
            x,y=b[name],c[name]
            if x.dimensions!=y.dimensions or x.shape!=y.shape or x.dtype!=y.dtype:
                result['layout_mismatches'].append(name); continue
            result['variables']+=1
            if y.dtype.kind not in 'biufc': continue
            xa=np.asarray(x[:]); ya=np.asarray(y[:])
            xm=mask_for(x,xa); ym=mask_for(y,ya)
            if np.any(xm) or np.any(ym): result['numeric_fill_masks'].append(name)
            valid=~ym
            if ya.dtype.kind in 'fc' and np.any(~np.isfinite(ya[valid])):
                result['nonfinite'].append(name)
            result['numeric_values']+=int(np.count_nonzero(valid))
    if result['layout_mismatches'] or result['numeric_fill_masks'] or result['nonfinite']:
        result['status']='FAIL'
        raise ValueError('history validation failed: '+json.dumps(result,sort_keys=True))
    return result


def setup_case(name, baseline, physics, mode, outcome):
    pinned_source=verify_pins()
    if sha(Path(baseline)/CHECKPOINT)!=PINNED_CHECKPOINT_SHA256: raise RuntimeError('baseline restart pin mismatch')
    if CHECKPOINT not in files_hashes(baseline): raise RuntimeError('baseline restart absent from immutable input set')
    dst=OUT/name
    if dst.exists(): raise RuntimeError('refusing to overwrite '+str(dst))
    run=dst/'run'; run.mkdir(parents=True)
    for p in sorted(Path(baseline).iterdir()):
        if p.is_file() and (not MUTABLE.match(p.name) or p.name==CHECKPOINT) and p.name not in {'wrf.exe','real.exe'}:
            shutil.copy2(p,run/p.name)
    src_nml=Path(baseline)/'namelist.input'
    text=src_nml.read_text()
    text=replace_key(text,'run_minutes','1')
    if physics==37:
        text=replace_key(text,'ra_lw_physics','37')
        text=replace_key(text,'ra_sw_physics','37')
    else:
        text=replace_key(text,'ra_lw_physics','4')
        text=replace_key(text,'ra_sw_physics','4')
    text=replace_key(text,'rrtmgp_udm_frozen_optics',str(mode))
    text=replace_key(text,'rrtmgp_udm_frozen_table',("'"+str(TABLE)+"'") if mode==1 else "''")
    (run/'namelist.input').write_text(text)
    if namelist_without_smoke_fields(src_nml)!=namelist_without_smoke_fields(run/'namelist.input'):
        raise ValueError(f'unexpected namelist change outside bounded smoke keys for {name}')
    shutil.copy2(INSTALL/'bin/wrf',run/'wrf.exe')
    baseline_hashes=files_hashes(baseline)
    copied_hashes=files_hashes(run)
    if baseline_hashes!=copied_hashes: raise RuntimeError(f'immutable staged inputs differ for {name}')
    common={
       'case':name,'expected_outcome':outcome,'source_baseline':str(baseline),
       'run_directory':str(run),'source_commit':pinned_source['commit'],
       'source_worktree_diff_sha256':pinned_source['diff_sha256'],
       'source_configuration_hashes':pinned_source,
       'registered_source_checks':['python3 tools/register37.py --check','python3 tools/compare_registry.py'],
       'runner_sha256':sha(__file__),
       'installed_wrf_sha256':sha(INSTALL/'bin/wrf'),'staged_wrf_sha256':sha(run/'wrf.exe'),
       'baseline_immutable_inputs_sha256':baseline_hashes,'staged_immutable_inputs_sha256':copied_hashes,
       'checkpoint_name':CHECKPOINT,'checkpoint_sha256':sha(run/CHECKPOINT),
       'baseline_checkpoint_sha256':sha(Path(baseline)/CHECKPOINT),
       'baseline_namelist_sha256':sha(src_nml),'staged_namelist_sha256':sha(run/'namelist.input'),
       'baseline_history_sha256':sha(Path(baseline)/HISTORY),
       'namelist_changes_limited_to':['run_minutes','rrtmgp_udm_frozen_optics','rrtmgp_udm_frozen_table'],
       'baseline_namelist_fields':namelist_fields(src_nml),'staged_namelist_fields':namelist_fields(run/'namelist.input'),
       'runtime_controls':{'timeout_seconds':600,'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OMP_STACKSIZE':'512M','OPENBLAS_NUM_THREADS':'1','diagnostic_prefixes_removed':['WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE'],'rlimit_stack_bytes':resource.getrlimit(resource.RLIMIT_STACK)},
       'expected_history':HISTORY if outcome=='success' else None,
       'history_validation':'exact expected Times string and bytes, one output file/time, expected dimensions, identical variable names/layout/dtypes vs matching baseline, reject any numeric fill mask, require finite numeric values; no bytewise-value assertion',
    }
    if physics==37 and mode==0:
        common['expected_rejection_marker']=HAIL_FATAL
    common['frozen_table_sha256']=sha(TABLE)
    write(dst/'preflight.json',common)
    return common


def execute(case):
    d=OUT/case; run=d/'run'; receipt=json.loads((d/'preflight.json').read_text())
    preflight_state=verify_case_state(d,receipt)
    log=run/'wrf.stdout.log'
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','LD_LIBRARY_PATH':str(NETCDF/'lib'),
         'NETCDF':str(NETCDF),'NETCDF_C':str(NETCDF),'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE',
         'OMP_STACKSIZE':'512M','OPENBLAS_NUM_THREADS':'1'}
    stack_file=d/'child_stack_limit.json'
    if stack_file.exists(): raise RuntimeError('refusing to overwrite child stack record')
    started=time.monotonic()
    try:
        with log.open('wb') as f:
            p=subprocess.run([str(run/'wrf.exe')],cwd=run,env=env,stdout=f,stderr=subprocess.STDOUT,
                             timeout=600,preexec_fn=stack_preexec(stack_file))
        code=p.returncode; timeout=False
    except subprocess.TimeoutExpired:
        code=None; timeout=True
    logtext=log.read_text(errors='replace') if log.exists() else ''
    rsltexts=[x.read_text(errors='replace') for x in run.glob('rsl.error.*')]
    all_logs='\n'.join([logtext]+rsltexts)
    success=(code==0 and 'SUCCESS COMPLETE WRF' in all_logs)
    failures=[]
    if receipt['expected_outcome']=='success':
        if timeout or not success:
            failures.append(f'expected success but runtime failed or timed out: rc={code}, timeout={timeout}')
        else:
            try: receipt['history_validation_result']=history_check(run,receipt['source_baseline'])
            except Exception as exc: failures.append(str(exc))
    else:
        if timeout or code==0 or HAIL_FATAL not in all_logs:
            failures.append(f'expected fail-closed hail rejection; rc={code}, timeout={timeout}, marker={HAIL_FATAL in all_logs}')
        if (run/HISTORY).exists() or 'SUCCESS COMPLETE WRF' in all_logs:
            failures.append('expected rejection occurred after forecast history/success')
        if not failures: receipt['rejection_result']='PASS_EXPECTED_HAIL_FAIL_CLOSED'
    receipt.update(runtime_returncode=code,runtime_timeout=timeout,runtime_elapsed_seconds=time.monotonic()-started,
                   runtime_log_sha256=sha(log),prelaunch_state=preflight_state,
                   child_stack_limit=json.loads(stack_file.read_text()) if stack_file.exists() else None,
                   immutable_inputs_unchanged=(files_hashes(run)==receipt['staged_immutable_inputs_sha256']))
    if not receipt['immutable_inputs_unchanged']: failures.append('immutable run inputs changed')
    try: receipt['postrun_state']=verify_case_state(d,receipt)
    except Exception as exc: failures.append('postrun immutability check: '+str(exc))
    if receipt.get('child_stack_limit',{}).get('soft_bytes')!=512*1024*1024:
        failures.append('WRF child did not receive 512 MiB RLIMIT_STACK')
    receipt['runtime_environment_actual']=env
    receipt['status']='PASS' if not failures else 'FAIL'
    receipt['failures']=failures
    write(d/'result.json',receipt)
    if failures: raise RuntimeError('; '.join(failures))
    return receipt


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--execute',action='store_true',help='execute prepared cases; do not use until approved')
    a=p.parse_args()
    if a.execute:
        results=[]
        for name in ('ra37-frozen1','ra37-frozen0-expected-rejection','ra4-frozen0'):
            results.append(execute(name))
        write(OUT/'suite-result.json',{'cases':results})
        print('SMOKE_SUITE_FINISHED',OUT/'suite-result.json')
    else:
        if OUT.exists(): raise RuntimeError('refusing to overwrite '+str(OUT))
        OUT.mkdir(parents=True)
        cases=[
           setup_case('ra37-frozen1',BASE37,37,1,'success'),
           setup_case('ra37-frozen0-expected-rejection',BASE37,37,0,'expected-rejection'),
           setup_case('ra4-frozen0',BASE4,4,0,'success'),
        ]
        hashes={str(p):sha(p) for p in (BASE37/CHECKPOINT,BASE4/CHECKPOINT,INSTALL/'bin/wrf',TABLE)}
        write(OUT/'suite-preflight.json',{'status':'PREPARED_NOT_RUN','cases':[c['case'] for c in cases],
             'runner_sha256':sha(__file__),
             'common_checkpoint_sha256':hashes[str(BASE37/CHECKPOINT)],'ra4_checkpoint_sha256':hashes[str(BASE4/CHECKPOINT)],
             'checkpoint_identical':hashes[str(BASE37/CHECKPOINT)]==hashes[str(BASE4/CHECKPOINT)],
             'installed_wrf_sha256':hashes[str(INSTALL/'bin/wrf')],'frozen_table_sha256':hashes[str(TABLE)],
             'checkpoint_hail_positive':{'QHAIL_positive_cells':554915,'QHAIL_max_kgkg':0.0025105075910687447,'QGRAUP_positive_cells':537276,'QGRAUP_max_kgkg':0.0016134108882397413},
             'meaning':'mode 0 is an expected fail-closed probe only on this hail-positive checkpoint, not a normal successful forecast case',
             'source_commit':cases[0]['source_commit']})
        print('SMOKE_SUITE_PREPARED_NOT_RUN',OUT/'suite-preflight.json')

if __name__=='__main__': main()
