#!/usr/bin/env python3
"""Dry-by-default, one-shot current-head UDM4 pristine serial SCM comparison."""
from __future__ import annotations
import hashlib, json, os, shutil, signal, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
OUT = ROOT / 'build/udm37-pristine-current-source-audit-v1'
BASELINE_ROOT = ROOT / 'build/pristine-udm4-runtime'
INPUTROOT = OUT / 'inputs'
SOURCE54_ROOT = ROOT / 'build/udm37-source54-pristine-serial-regression-v1/cases'
EXE = ROOT / 'build/udm37-rrtmg4-export-serial-build-v1/source/WRF/main/wrf.exe'
EXE_SHA = '5091946b34cdf9c3397f07f03133dfe2ce0c36059b1d0ec4caa90c013d5a1a57'
BUILD_RECEIPT = ROOT / 'build/udm37-rrtmg4-export-serial-build-v1/build-receipt.json'
BUILD_RECEIPT_SHA = '771bbdb333a7f24591ee52fc191ea816c6b966174c0a6f36da5f085f90df36a6'
INPUT_STAGE = OUT / 'input-stage.json'
INPUT_STAGE_SHA = '03c6954bda15d0cefbb797969095792473dc2a1da38a2b348e39bf906c8a3529'
SOURCE_MANIFEST = ROOT / 'build/udm37-rrtmg4-export-serial-build-v1/source-manifest-v1.json'
SOURCE_MANIFEST_SHA = '1d48c4fc3188577368218d19259326cf4d16436e4bc9652aef35cd4e3f5b400d'
CURRENT_SOURCE_WT = ROOT / 'build/udm37-current-rrtmg4-optics-export-work'
CURRENT_SOURCE_HEAD = '5f3034e9c43209a352977da4885a3fc15b46c532'
BUILD_SOURCE_COMMIT = 'b7b5f6f9cd657408e3bde3018d7e882ab3e4bce3'
CONFIGURE = ROOT / 'build/udm37-rrtmg4-export-serial-build-v1/source/WRF/configure.wrf'
CONFIGURE_SHA = '6a2fcd322bbff92ff61a141671d492eb8d74e3d56af28582306c024775b89c68'
PINNED = {
    'control': {
        'wrfinput_d01': '3fb1d9ae78bc0e93d072e646f052e3a39dd83d5215f864bbc89ff030f9cb6d4e',
        'wrfout_d01_1999-10-22_19:00:00': 'cc34da6667b2569063f7b302985a9e9b44dac4f4b528989255404c1a5cf9da8f',
        'source54_history': 'cc34da6667b2569063f7b302985a9e9b44dac4f4b528989255404c1a5cf9da8f',
    },
    'mixed': {
        'wrfinput_d01': '9e167c8b99d9a2cacba70c18fe111e0c6785a5cdca5a858aaf372474a5ffc36f',
        'wrfout_d01_1999-10-22_19:00:00': 'e04dd6fbd89a3df30e9d65e518d022ba2086291b6443268b7a09e293d4f4f216',
        'source54_history': 'e04dd6fbd89a3df30e9d65e518d022ba2086291b6443268b7a09e293d4f4f216',
    },
}
ASSET_EXCLUDES = {'wrf.exe', 'ideal.exe', 'wrfout_d01_1999-10-22_19:00:00', 'namelist.output', 'pristine-run.log', 'run.log'}
CASES_ROOT = OUT / 'cases'
ENV_NETCDF = ROOT / 'build/deps/netcdf'
LD_PATH = f'{ENV_NETCDF}/lib:{ROOT}/build/deps/root/usr/lib/x86_64-linux-gnu'

def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def atomic_json(path: Path, value: dict) -> None:
    tmp=path.with_name(path.name+'.tmp')
    data=json.dumps(value,indent=2,sort_keys=True)+'\n'
    with tmp.open('x',encoding='utf-8') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def static_pin_snapshot() -> dict:
    head=subprocess.check_output(['git','-C',str(CURRENT_SOURCE_WT),'rev-parse','HEAD'],text=True).strip()
    if head!=CURRENT_SOURCE_HEAD: raise RuntimeError(f'current source head changed: {head}')
    wrf_diff=subprocess.check_output(['git','-C',str(CURRENT_SOURCE_WT),'diff','--name-only',BUILD_SOURCE_COMMIT,CURRENT_SOURCE_HEAD,'--','WRF'],text=True).splitlines()
    wrf_worktree=subprocess.check_output(['git','-C',str(CURRENT_SOURCE_WT),'status','--porcelain','--','WRF'],text=True).splitlines()
    if wrf_diff or wrf_worktree: raise RuntimeError(f'WRF source tree differs from compiled commit: commit_diff={wrf_diff}; worktree={wrf_worktree}')
    return {'source_head':head,'build_commit':BUILD_SOURCE_COMMIT,'wrf_tree_commit_diff':wrf_diff,'wrf_tree_worktree_status':wrf_worktree,
            'executable_sha256':sha_file(EXE),'configure_sha256':sha_file(CONFIGURE),
            'build_receipt_sha256':sha_file(BUILD_RECEIPT),'source_manifest_sha256':sha_file(SOURCE_MANIFEST),
            'input_stage_sha256':sha_file(INPUT_STAGE)}

def tree_fingerprint(path: Path) -> dict:
    if path.is_file():
        return {'kind': 'file', 'sha256': sha_file(path), 'bytes': path.stat().st_size}
    if path.is_dir():
        rows=[]
        for item in sorted(path.rglob('*')):
            rel=item.relative_to(path).as_posix()
            if item.is_symlink(): rows.append((rel,'link',os.readlink(item)))
            elif item.is_file(): rows.append((rel,'file',item.stat().st_size,sha_file(item)))
            elif item.is_dir(): rows.append((rel,'dir'))
        encoded=json.dumps(rows,separators=(',',':')).encode()
        return {'kind':'dir','entries':len(rows),'sha256':hashlib.sha256(encoded).hexdigest()}
    return {'kind':'other'}

def asset_inventory(case: Path) -> dict:
    inv={}
    for src in sorted(case.iterdir(), key=lambda p:p.name):
        if src.name in ASSET_EXCLUDES or src.name.startswith(('wrfout_d01_', 'wrfrst_d01_', 'rsl.')): continue
        if src.name.startswith('namelist.input.backup.'):
            # Keep the exact legacy backup link target, but it is not a runtime input.
            inv[src.name]={'kind':'link','target':os.readlink(src)} if src.is_symlink() else tree_fingerprint(src)
            continue
        if src.is_symlink():
            target=Path(os.readlink(src))
            if not target.is_absolute(): target=(src.parent/target).resolve()
            inv[src.name]={'kind':'link','target':os.readlink(src),'resolved':str(target),'target_fingerprint':tree_fingerprint(target)}
        elif src.is_file(): inv[src.name]=tree_fingerprint(src)
        else: inv[src.name]=tree_fingerprint(src)
    return inv

def variable_attr(variable, name):
    value=variable.getncattr(name)
    if isinstance(value, np.ndarray): return {'dtype':str(value.dtype),'shape':list(value.shape),'bytes':value.tobytes().hex()}
    if isinstance(value, np.generic): return {'dtype':str(value.dtype),'bytes':np.asarray(value).tobytes().hex()}
    if isinstance(value, bytes): return {'type':'bytes','hex':value.hex()}
    if isinstance(value, str): return {'type':'str','value':value}
    return {'type':type(value).__name__,'value':value}

def compare_history(actual: Path, reference: Path) -> dict:
    result={'actual':str(actual),'reference':str(reference),'status':'FAIL','issues':[],
            'whole_file_sha256_actual':sha_file(actual) if actual.is_file() else None,
            'whole_file_sha256_reference':sha_file(reference) if reference.is_file() else None,
            'whole_file_sha256_equal':actual.is_file() and reference.is_file() and sha_file(actual)==sha_file(reference),
            'variable_count_actual':0,'variable_count_reference':0,'common_variable_count':0,
            'equal_variables':[],'different_variables':[],'missing_variables':[],'extra_variables':[],
            'dimension_differences':[],'global_attribute_differences':[]}
    with Dataset(actual,'r') as a, Dataset(reference,'r') as b:
        a.set_auto_maskandscale(False); b.set_auto_maskandscale(False)
        if a.data_model != b.data_model: result['issues'].append({'kind':'data_model','actual':a.data_model,'reference':b.data_model})
        av=set(a.variables); bv=set(b.variables)
        result['variable_count_actual']=len(av); result['variable_count_reference']=len(bv)
        result['common_variable_count']=len(av&bv)
        result['missing_variables']=sorted(bv-av); result['extra_variables']=sorted(av-bv)
        ad={k:{'size':len(v),'unlimited':v.isunlimited()} for k,v in a.dimensions.items()}; bd={k:{'size':len(v),'unlimited':v.isunlimited()} for k,v in b.dimensions.items()}
        if ad!=bd: result['dimension_differences']={'actual':ad,'reference':bd}
        ag={k:variable_attr(a,k) for k in a.ncattrs()}; bg={k:variable_attr(b,k) for k in b.ncattrs()}
        if ag!=bg: result['global_attribute_differences']={'actual':ag,'reference':bg}
        for name in sorted(av&bv):
            va,vb=a.variables[name],b.variables[name]
            issue=[]
            if va.dtype!=vb.dtype: issue.append('dtype')
            if tuple(va.dimensions)!=tuple(vb.dimensions): issue.append('dimensions')
            if va.shape!=vb.shape: issue.append('shape')
            attrs_a={k:variable_attr(va,k) for k in va.ncattrs()}; attrs_b={k:variable_attr(vb,k) for k in vb.ncattrs()}
            if attrs_a!=attrs_b: issue.append('attributes')
            if not issue:
                xa=np.ma.asarray(va[:]); xb=np.ma.asarray(vb[:])
                if np.ma.getmaskarray(xa).any() or np.ma.getmaskarray(xb).any(): issue.append('masked-values')
                xa=np.asarray(xa); xb=np.asarray(xb)
                if xa.dtype.kind in 'fci' and (not np.isfinite(xa).all() or not np.isfinite(xb).all()): issue.append('nonfinite')
                if xa.shape==xb.shape and xa.dtype==xb.dtype and not xa.tobytes(order='C')==xb.tobytes(order='C'): issue.append('raw-bytes')
            if issue: result['different_variables'].append({'name':name,'reasons':issue})
            else: result['equal_variables'].append(name)
    result['status']='PASS' if result['whole_file_sha256_equal'] and not (result['issues'] or result['different_variables'] or result['missing_variables'] or result['extra_variables'] or result['dimension_differences'] or result['global_attribute_differences']) and result['common_variable_count']==208 else 'FAIL'
    return result

def utcnow(): return datetime.now(timezone.utc).isoformat()

def run_one(name: str, reference_assets_before: dict, official_assets_before: dict, source54_assets_before: dict) -> dict:
    ref=INPUTROOT/name
    baseline=BASELINE_ROOT/name
    source54=SOURCE54_ROOT/name
    run=CASES_ROOT/name
    if run.exists(): raise RuntimeError(f'refusing nonempty/preexisting case: {run}')
    if not ref.is_dir(): raise RuntimeError(f'missing reference case: {ref}')
    for fname in ('wrfinput_d01','namelist.input','radiation_iofields.txt','force_ideal.nc','input_soil','input_sounding'):
        if not (ref/fname).is_file(): raise RuntimeError(f'missing staged current-source input {name}/{fname}')
    for fname,expected in PINNED[name].items():
        if fname == 'source54_history': continue
        if sha_file(baseline/fname)!=expected: raise RuntimeError(f'official baseline pin mismatch {name}/{fname}')
    if sha_file(source54/'wrfout_d01_1999-10-22_19:00:00') != PINNED[name]['source54_history']:
        raise RuntimeError(f'source54 history pin mismatch {name}')
    run.mkdir(parents=True,exist_ok=False)
    copied=[]
    for src in sorted(ref.iterdir(),key=lambda p:p.name):
        if src.name in ASSET_EXCLUDES: continue
        dst=run/src.name
        if src.is_symlink(): os.symlink(os.readlink(src),dst)
        elif src.is_file(): shutil.copy2(src,dst)
        else: raise RuntimeError(f'unexpected directory asset {src}')
        copied.append(src.name)
    os.symlink(EXE,run/'wrf.exe')
    before=asset_inventory(run)
    prelaunch_pins=static_pin_snapshot()
    case_result={'case':name,'case_path':str(run),'status':'FAIL','staged_files':copied,
                 'asset_inventory_before':before,'start_utc':utcnow(),'process':{},'prelaunch_static_pins':prelaunch_pins,'runtime_checks':{},'comparison':None}
    env=os.environ.copy()
    for key in list(env):
        if key.startswith('WRF_RRTMGP_'): env.pop(key,None)
    env.update({'NETCDF':str(ENV_NETCDF),'LD_LIBRARY_PATH':LD_PATH,'OMP_NUM_THREADS':'1'})
    start=time.monotonic(); proc=None
    with (run/'run.log').open('wb') as log:
        try:
            proc=subprocess.Popen(['./wrf.exe'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            case_result['process']['pid']=proc.pid
            rc=proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            case_result['process']['timed_out']=True
            if proc is not None:
                os.killpg(proc.pid,signal.SIGTERM)
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL); proc.wait()
            rc=124
        except BaseException as e:
            case_result['process']['exception']=repr(e)
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM); proc.wait(timeout=5)
            rc=125
    case_result['process'].update({'returncode':rc,'elapsed_seconds':time.monotonic()-start,'end_utc':utcnow()})
    # Persist the terminal process result before reading logs or opening NetCDF.
    atomic_json(OUT/f'{name}-execution.json',{'schema':'current-source-pristine-case-execution-v1','case':name,**case_result['process']})
    case_result['postprocess_static_pins']=static_pin_snapshot()
    static_pins_unchanged=case_result['postprocess_static_pins']==prelaunch_pins
    logtxt=(run/'run.log').read_text(errors='replace')
    success='SUCCESS COMPLETE WRF' in logtxt
    history=run/'wrfout_d01_1999-10-22_19:00:00'
    case_result['runtime_checks']={'static_pins_unchanged':static_pins_unchanged,'success_complete_marker':success,'history_exists':history.is_file(),
       'history_bytes':history.stat().st_size if history.is_file() else None,
       'runtime_assets_unchanged':asset_inventory(run)==before,
       'staged_inputs_unchanged':asset_inventory(ref)==reference_assets_before,
       'official_baseline_assets_unchanged':asset_inventory(baseline)==official_assets_before,
       'source54_assets_unchanged':asset_inventory(source54)==source54_assets_before,
       'official_baseline_history_unchanged':sha_file(baseline/'wrfout_d01_1999-10-22_19:00:00')==PINNED[name]['wrfout_d01_1999-10-22_19:00:00']}
    if history.is_file():
        case_result['comparison']=compare_history(history,baseline/'wrfout_d01_1999-10-22_19:00:00')
        case_result['source54_comparison']=compare_history(history,source54/'wrfout_d01_1999-10-22_19:00:00')
    after=asset_inventory(run)
    case_result['asset_inventory_after']=after
    case_result['runtime_checks']['runtime_assets_unchanged']=after==before
    case_result['runtime_checks']['staged_inputs_unchanged']=asset_inventory(ref)==reference_assets_before
    case_result['runtime_checks']['official_baseline_assets_unchanged']=asset_inventory(baseline)==official_assets_before
    case_result['runtime_checks']['source54_assets_unchanged']=asset_inventory(source54)==source54_assets_before
    case_result['reference_input_unchanged']=sha_file(baseline/'wrfinput_d01')==PINNED[name]['wrfinput_d01']
    case_result['reference_assets_after']=asset_inventory(ref)
    case_result['official_baseline_assets_after']=asset_inventory(baseline)
    case_result['official_baseline_sha256_after']=sha_file(baseline/'wrfout_d01_1999-10-22_19:00:00')
    case_result['source54_history_sha256_after']=sha_file(source54/'wrfout_d01_1999-10-22_19:00:00')
    case_result['source54_assets_after']=asset_inventory(source54)
    case_result['status']='PASS' if (rc==0 and success and history.is_file() and case_result['runtime_checks']['static_pins_unchanged'] and case_result['runtime_checks']['runtime_assets_unchanged'] and case_result['runtime_checks']['staged_inputs_unchanged'] and case_result['runtime_checks']['official_baseline_assets_unchanged'] and case_result['runtime_checks']['source54_assets_unchanged'] and case_result['runtime_checks']['official_baseline_history_unchanged'] and case_result['official_baseline_assets_after']==official_assets_before and case_result['source54_assets_after']==source54_assets_before and case_result['reference_input_unchanged'] and case_result['comparison'] and case_result['comparison']['status']=='PASS' and case_result['source54_comparison'] and case_result['source54_comparison']['status']=='PASS') else 'FAIL_PRESERVED'
    (OUT/f'{name}-receipt.json').write_text(json.dumps(case_result,indent=2,sort_keys=True)+'\n')
    return case_result

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true',help='run exactly the two staged 60-second cases once; default only preflights')
    args=parser.parse_args()
    if sha_file(EXE)!=EXE_SHA: raise SystemExit('current executable SHA mismatch')
    if sha_file(CONFIGURE)!=CONFIGURE_SHA: raise SystemExit('build configure pin mismatch')
    if sha_file(SOURCE_MANIFEST)!=SOURCE_MANIFEST_SHA: raise SystemExit('source manifest pin mismatch')
    if sha_file(BUILD_RECEIPT)!=BUILD_RECEIPT_SHA: raise SystemExit('current build receipt pin mismatch')
    head=subprocess.check_output(['git','-C',str(CURRENT_SOURCE_WT),'rev-parse','HEAD'],text=True).strip()
    if head!=CURRENT_SOURCE_HEAD: raise SystemExit(f'current target source head changed: {head}')
    changed=subprocess.check_output(['git','-C',str(CURRENT_SOURCE_WT),'diff','--name-only',BUILD_SOURCE_COMMIT, CURRENT_SOURCE_HEAD],text=True).splitlines()
    wrf_source_paths=subprocess.check_output(['git','-C',str(CURRENT_SOURCE_WT),'diff','--name-only',BUILD_SOURCE_COMMIT,CURRENT_SOURCE_HEAD,'--','WRF'],text=True).splitlines()
    if wrf_source_paths: raise SystemExit(f'WRF source tree differs from compiled commit: {wrf_source_paths}')
    compiled_paths=[p for p in changed if p.startswith('WRF/') and p.endswith(('.F','.F90','.f','.f90','.c','.cc','.cpp'))]
    if compiled_paths: raise SystemExit(f'compiled source changed after build: {compiled_paths}')
    local_code=subprocess.check_output(['git','-C',str(CURRENT_SOURCE_WT),'diff','--name-only','HEAD','--','WRF/Registry','WRF/phys','WRF/dyn_em','WRF/share','WRF/frame','WRF/external'],text=True).splitlines()
    if local_code: raise SystemExit(f'compiled-source working tree is dirty: {local_code}')
    if sha_file(INPUT_STAGE)!=INPUT_STAGE_SHA: raise SystemExit('staged input manifest pin mismatch')
    if CASES_ROOT.exists(): raise SystemExit(f'refusing pre-existing output root {CASES_ROOT}')
    stage=__import__('json').loads(INPUT_STAGE.read_text())
    for name in ('control','mixed'):
        ref=INPUTROOT/name; baseline=BASELINE_ROOT/name; source54=SOURCE54_ROOT/name
        expected_assets=stage['cases'][name]['input_asset_inventory']
        if sorted(p.name for p in ref.iterdir())!=sorted(expected_assets): raise SystemExit(f'input-stage roster mismatch {name}')
        if asset_inventory(ref)!=expected_assets: raise SystemExit(f'input-stage asset fingerprint mismatch {name}')
        for fn,expected in PINNED[name].items():
            if fn=='source54_history': continue
            if sha_file(baseline/fn)!=expected: raise SystemExit(f'official baseline mismatch {name}/{fn}')
        if sha_file(source54/'wrfout_d01_1999-10-22_19:00:00')!=PINNED[name]['source54_history']:
            raise SystemExit(f'source54 baseline mismatch {name}')
        for fn in ('wrfinput_d01','namelist.input','radiation_iofields.txt','force_ideal.nc','input_soil','input_sounding'):
            if not (ref/fn).is_file(): raise SystemExit(f'missing staged input {name}/{fn}')
        if sha_file(ref/'wrfinput_d01')!=PINNED[name]['wrfinput_d01']:
            raise SystemExit(f'staged input mismatch {name}/wrfinput_d01')
        if sha_file(ref/'namelist.input')!=stage['cases'][name]['namelist_sha256'] or sha_file(ref/'radiation_iofields.txt')!=stage['cases'][name]['radiation_iofields_sha256']:
            raise SystemExit(f'namelist or IO fields mismatch {name}')
    if not args.execute:
        check={'schema':'current-source-pristine-ra4-preflight-v1','status':'READY_NOT_RUN','target_source_commit':head,'build_commit':BUILD_SOURCE_COMMIT,'runner_sha256':sha_file(Path(__file__)),'build_receipt_sha256':sha_file(BUILD_RECEIPT),'binary_sha256':sha_file(EXE),'configure_sha256':sha_file(CONFIGURE),'source_manifest_sha256':sha_file(SOURCE_MANIFEST),'models_invoked':0,'output_root_absent':not CASES_ROOT.exists(),'cases':['control','mixed']}
        (OUT/'current-preflight.json').write_text(json.dumps(check,indent=2,sort_keys=True)+'\n')
        print(json.dumps(check,sort_keys=True))
        return 0
    CASES_ROOT.mkdir()
    start=utcnow(); results=[]
    reference_assets={name:asset_inventory(INPUTROOT/name) for name in ('control','mixed')}
    official_assets={name:asset_inventory(BASELINE_ROOT/name) for name in ('control','mixed')}
    source54_assets={name:asset_inventory(SOURCE54_ROOT/name) for name in ('control','mixed')}
    # Exactly the two pre-authorized fixtures, once each. Never retry.
    for name in ('control','mixed'):
        try: results.append(run_one(name,reference_assets[name],official_assets[name],source54_assets[name]))
        except BaseException as e:
            failure={'case':name,'status':'FAIL_PRESERVED','error':repr(e),'time_utc':utcnow()}
            (OUT/f'{name}-receipt.json').write_text(json.dumps(failure,indent=2)+'\n')
            results.append(failure)
    summary={'schema':'current-source-pristine-serial-ra4-regression-v1','started_utc':start,'ended_utc':utcnow(),
       'binary':str(EXE),'binary_sha256':sha_file(EXE),'cases':results,
       'scope':'Two fresh 60-second SCM cases only; each compared exactly to the immutable official WRF4 history and source54 current-source history. No pristine rerun.'}
    (OUT/'runtime-comparison.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    return 0 if all(x['status']=='PASS' for x in results) else 1

if __name__=='__main__': raise SystemExit(main())
