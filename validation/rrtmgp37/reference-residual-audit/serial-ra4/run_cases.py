#!/usr/bin/env python3
"""One-shot isolated 60 s RA4 serial regression against pinned pristine histories."""
from __future__ import annotations
import hashlib, json, os, shutil, signal, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
OUT = ROOT / 'build/udm37-source54-pristine-serial-regression-v1'
REFROOT = ROOT / 'build/pristine-udm4-runtime'
EXE = OUT / 'WRF/main/wrf.exe'
EXE_SHA = '7d6526f4c509aa93d2b28c73db6c782d72e68ef76fc1658ceb360250adf03caa'
PINNED = {
    'control': {
        'wrfinput_d01': '3fb1d9ae78bc0e93d072e646f052e3a39dd83d5215f864bbc89ff030f9cb6d4e',
        'wrfout_d01_1999-10-22_19:00:00': 'cc34da6667b2569063f7b302985a9e9b44dac4f4b528989255404c1a5cf9da8f',
    },
    'mixed': {
        'wrfinput_d01': '9e167c8b99d9a2cacba70c18fe111e0c6785a5cdca5a858aaf372474a5ffc36f',
        'wrfout_d01_1999-10-22_19:00:00': 'e04dd6fbd89a3df30e9d65e518d022ba2086291b6443268b7a09e293d4f4f216',
    },
}
ASSET_EXCLUDES = {'wrf.exe', 'wrfout_d01_1999-10-22_19:00:00', 'namelist.output', 'pristine-run.log', 'run.log'}
CASES_ROOT = OUT / 'cases'
ENV_NETCDF = ROOT / 'build/deps/netcdf'
LD_PATH = f'{ENV_NETCDF}/lib:{ROOT}/build/deps/root/usr/lib/x86_64-linux-gnu'

def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

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
            'variable_count_actual':0,'variable_count_reference':0,'common_variable_count':0,
            'equal_variables':[],'different_variables':[],'missing_variables':[],'extra_variables':[],
            'dimension_differences':[],'global_attribute_differences':[]}
    with Dataset(actual,'r') as a, Dataset(reference,'r') as b:
        a.set_auto_maskandscale(False); b.set_auto_maskandscale(False)
        av=set(a.variables); bv=set(b.variables)
        result['variable_count_actual']=len(av); result['variable_count_reference']=len(bv)
        result['common_variable_count']=len(av&bv)
        result['missing_variables']=sorted(bv-av); result['extra_variables']=sorted(av-bv)
        ad={k:len(v) for k,v in a.dimensions.items()}; bd={k:len(v) for k,v in b.dimensions.items()}
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
    result['status']='PASS' if not (result['different_variables'] or result['missing_variables'] or result['extra_variables'] or result['dimension_differences'] or result['global_attribute_differences']) and result['common_variable_count']==208 else 'FAIL'
    return result

def utcnow(): return datetime.now(timezone.utc).isoformat()

def run_one(name: str, reference_assets_before: dict) -> dict:
    ref=REFROOT/name
    run=CASES_ROOT/name
    if run.exists(): raise RuntimeError(f'refusing nonempty/preexisting case: {run}')
    if not ref.is_dir(): raise RuntimeError(f'missing reference case: {ref}')
    for fname,expected in PINNED[name].items():
        if sha_file(ref/fname)!=expected: raise RuntimeError(f'reference pin mismatch {name}/{fname}')
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
    case_result={'case':name,'case_path':str(run),'status':'FAIL','staged_files':copied,
                 'asset_inventory_before':before,'start_utc':utcnow(),'process':{},'runtime_checks':{},'comparison':None}
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
    logtxt=(run/'run.log').read_text(errors='replace')
    success='SUCCESS COMPLETE WRF' in logtxt
    history=run/'wrfout_d01_1999-10-22_19:00:00'
    case_result['runtime_checks']={'success_complete_marker':success,'history_exists':history.is_file(),
       'history_bytes':history.stat().st_size if history.is_file() else None,
       'runtime_assets_unchanged':asset_inventory(run)==before,
       'official_reference_assets_unchanged':asset_inventory(ref)==reference_assets_before}
    if history.is_file(): case_result['comparison']=compare_history(history,ref/'wrfout_d01_1999-10-22_19:00:00')
    after=asset_inventory(run)
    case_result['asset_inventory_after']=after
    case_result['runtime_checks']['runtime_assets_unchanged']=after==before
    case_result['reference_input_unchanged']=sha_file(ref/'wrfinput_d01')==PINNED[name]['wrfinput_d01']
    case_result['reference_assets_after']=asset_inventory(ref)
    case_result['status']='PASS' if (rc==0 and success and history.is_file() and case_result['runtime_checks']['runtime_assets_unchanged'] and case_result['reference_input_unchanged'] and case_result['comparison'] and case_result['comparison']['status']=='PASS') else 'FAIL_PRESERVED'
    (OUT/f'{name}-receipt.json').write_text(json.dumps(case_result,indent=2,sort_keys=True)+'\n')
    return case_result

def main():
    if sha_file(EXE)!=EXE_SHA: raise SystemExit('current executable SHA mismatch')
    if CASES_ROOT.exists(): raise SystemExit(f'refusing pre-existing output root {CASES_ROOT}')
    CASES_ROOT.mkdir()
    start=utcnow(); results=[]
    reference_assets={name:asset_inventory(REFROOT/name) for name in ('control','mixed')}
    # Exactly the two pre-authorized fixtures, once each. Never retry.
    for name in ('control','mixed'):
        try: results.append(run_one(name,reference_assets[name]))
        except BaseException as e:
            failure={'case':name,'status':'FAIL_PRESERVED','error':repr(e),'time_utc':utcnow()}
            (OUT/f'{name}-receipt.json').write_text(json.dumps(failure,indent=2)+'\n')
            results.append(failure)
    summary={'schema':'source54-pristine-serial-ra4-regression-v1','started_utc':start,'ended_utc':utcnow(),
       'binary':str(EXE),'binary_sha256':sha_file(EXE),'cases':results,
       'scope':'Two fresh 60-second SCM cases only; all exact common raw NetCDF variables/schema/attributes required. No pristine rerun.'}
    (OUT/'runtime-comparison.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    return 0 if all(x['status']=='PASS' for x in results) else 1

if __name__=='__main__': raise SystemExit(main())
