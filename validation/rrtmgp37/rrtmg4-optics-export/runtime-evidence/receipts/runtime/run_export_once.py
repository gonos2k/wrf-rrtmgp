#!/usr/bin/env python3
"""One-use, fail-closed runner for the staged RRTMG4 observer comparison.

No model runs occur unless --execute is given and root-authorization.json binds
this exact runner, plan, staged inputs, postbuild identity, and arm order.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
PLAN = HERE / 'plan.json'
AUTH = HERE / 'root-authorization.json'
LOCK = HERE / '.one-use.lock'
RECEIPT = HERE / 'execution.json'
COMPARISON = HERE / 'comparison.json'
ARMS = ('OLD_OFF', 'NEW_OFF', 'NEW_ON')
TIMES = ('2016-10-07_12:00:00', '2016-10-07_12:01:00')
RESTART = 'wrfrst_d01_2016-10-07_12:01:00'
INPUT_RESTART = 'wrfrst_d01_2016-10-07_12:00:00'
FATAL_MARKERS = ('FATAL CALLED FROM FILE', 'APPLICATION CALLED MPI_ABORT',
                 'ERROR: FATAL', 'RRTMGP_FATAL', 'RRtmgp_fatal')


def sha(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def pin(path: Path | str) -> dict:
    p = Path(path)
    return {'path': str(p.resolve()), 'size_bytes': p.stat().st_size, 'sha256': sha(p)}


def atomic(path: Path, obj: dict) -> None:
    tmp = path.with_name(path.name + f'.tmp.{os.getpid()}')
    with tmp.open('x', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def require_pin(rec: dict, label: str) -> None:
    p = Path(rec['path'])
    if not p.is_file() or p.stat().st_size != rec['size_bytes'] or sha(p) != rec['sha256']:
        raise RuntimeError(f'{label} pin mismatch: {p}')


def attr(v):
    if isinstance(v, np.ndarray):
        return {'dtype': str(v.dtype), 'shape': list(v.shape), 'value': v.tolist()}
    if isinstance(v, bytes): return {'type':'bytes','value':v.decode('utf-8',errors='replace')}
    if isinstance(v, np.generic): return {'dtype':str(v.dtype),'value':attr(v.item())}
    return {'type':type(v).__name__,'value':v}


def ldd_map(exe: Path, ld: str) -> dict:
    env = {'PATH':'/usr/bin:/bin','LD_LIBRARY_PATH':ld,'LC_ALL':'C','LANG':'C'}
    p = subprocess.run(['/usr/bin/ldd',str(exe)],env=env,text=True,stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,check=False)
    if p.returncode: raise RuntimeError(f'ldd failed: {p.stdout[-2000:]}')
    out = {}
    for line in p.stdout.splitlines():
        parts=line.strip().split(); path=None
        if '=>' in parts:
            i=parts.index('=>')
            if i+1<len(parts) and parts[i+1].startswith('/'): path=parts[i+1]
        elif parts and parts[0].startswith('/'): path=parts[0]
        if path:
            resolved=str(Path(path).resolve(strict=True)); name=Path(resolved).name
            if name in out and out[name]!=resolved: raise RuntimeError(f'duplicate ldd basename {name}')
            out[name]=resolved
    return out


def read_plan() -> dict:
    p=json.loads(PLAN.read_text())
    if p.get('schema')!='udm37-rrtmg4-export-runtime-v4': raise RuntimeError('plan schema mismatch')
    runpin=p.get('execution_runner',{})
    if runpin.get('path')!=str(Path(__file__).resolve()) or runpin.get('sha256')!=sha(Path(__file__)) or runpin.get('size_bytes')!=Path(__file__).stat().st_size:
        raise RuntimeError('plan does not bind these runner bytes')
    return p


def verify_stage(plan: dict, empty_arms: tuple[str, ...] = ()) -> dict:
    paths={k:Path(plan[k]['path']) for k in ('stage_plan','stage_manifest','stage_readback','namelist_delta')}
    for k,p in paths.items(): require_pin(plan[k],k)
    stage=Path(plan['stage_root'])
    stage_plan=json.loads(paths['stage_plan'].read_text())
    manifest=json.loads(paths['stage_manifest'].read_text())
    rb=json.loads(paths['stage_readback'].read_text())
    if stage_plan.get('status')!='STAGED_WAITING_FOR_NEW_OBSERVER_BUILD_AND_ROOT_AUTHORIZATION':
        raise RuntimeError('stage plan status changed')
    if rb.get('status')!='PASS_STAGE_ONLY_WAITING_NEW_OBSERVER_BUILD':
        raise RuntimeError('stage readback status changed')
    if manifest.get('stage_plan_sha256')!=sha(paths['stage_plan']): raise RuntimeError('manifest does not bind stage plan')
    if rb.get('stage_plan_sha256')!=sha(paths['stage_plan']) or rb.get('stage_manifest_sha256')!=sha(paths['stage_manifest']):
        raise RuntimeError('stage readback does not bind plan/manifest')
    arm_reports={}
    for arm in ARMS:
        case=stage/arm; rec=manifest['arms'][arm];
        if len(rec['files'])!=104+(1 if arm=='OLD_OFF' else 0): raise RuntimeError(f'{arm} roster count mismatch')
        seen=set()
        for row in rec['files']:
            name=row['name']; seen.add(name); p=case/name
            if row['kind']=='symlink':
                if not p.is_symlink() or os.readlink(p)!=row['link_text']: raise RuntimeError(f'{arm}/{name}: link mismatch')
                target=p.resolve(strict=True)
                if str(target)!=row['target_path']: raise RuntimeError(f'{arm}/{name}: target mismatch')
                actual=pin(target)
            else:
                if p.is_symlink() or not p.is_file(): raise RuntimeError(f'{arm}/{name}: expected file')
                actual=pin(p)
            if actual['sha256']!=row['sha256'] or actual['size_bytes']!=row['size_bytes']:
                raise RuntimeError(f'{arm}/{name}: staged bytes mismatch')
        if sha(case/'namelist.input')!=rec['namelist_sha256']: raise RuntimeError(f'{arm}: namelist changed')
        if rec['namelist_sha256']!='55cee6702fb1a38ea2a6c33fbcc03d722a81afc5efeb74dbac5efb03407056b6':
            raise RuntimeError(f'{arm}: reviewed nml digest unexpected')
        nml_text=(case/'namelist.input').read_text()
        for field in ('rrtmgp_data_path','rrtmgp_udm_frozen_table'):
            if plan['loader_namelist_paths'][field] not in nml_text:
                raise RuntimeError(f'{arm}: namelist loader path mismatch for {field}')
        if arm=='OLD_OFF':
            if 'wrf.exe' not in seen or not (case/'wrf.exe').is_symlink(): raise RuntimeError('old arm lacks pinned executable link')
            if sha(case/'wrf.exe')!='d2c4c772ff8b3b3900b91de385a9bf9a0ab3ea5739d8deff89ec5efdc97555e6':
                raise RuntimeError('old baseline executable differs from staged PR70 binary')
        elif 'wrf.exe' in seen: raise RuntimeError(f'{arm}: staged new executable should not be embedded')
        if arm in empty_arms:
            for pattern in ('rsl.*','wrf.stdout.log','wrfout_d01_*','wrfrst_d01_*'):
                found=[p.name for p in case.glob(pattern) if p.name!=INPUT_RESTART and p.is_file()]
                if found: raise RuntimeError(f'{arm}: preexisting model outputs: {found[:5]}')
            for sub in ('trace','audit','export'):
                folder=case/sub
                if folder.exists() and any(folder.iterdir()): raise RuntimeError(f'{arm}/{sub} is not empty')
        arm_reports[arm]={'case':str(case),'file_count':len(seen),'namelist_sha256':rec['namelist_sha256'],
                          'inputs_sha256':{n:sha(case/n) for n in ('wrfinput_d01','wrfbdy_d01',INPUT_RESTART,'radiation_iofields.txt')}}
    if len({x['namelist_sha256'] for x in arm_reports.values()})!=1: raise RuntimeError('arm namelists differ')
    return {'arms':arm_reports,'stage_plan_sha256':sha(paths['stage_plan']),
            'stage_manifest_sha256':sha(paths['stage_manifest']),'stage_readback_sha256':sha(paths['stage_readback']),
            'namelist_delta_sha256':sha(paths['namelist_delta'])}


def verify_reference_capture(plan: dict) -> dict:
    """Verify the retained first-call source files without modifying them."""
    folder=Path(plan['reference_capture_root'])
    actual=[]
    for raw in sorted(folder.glob('*.raw')):
        stem=raw.with_suffix('')
        for suffix in ('raw','input','result'):
            p=stem.with_suffix('.'+suffix)
            if not p.is_file(): raise RuntimeError(f'missing retained reference capture {p}')
            actual.append(pin(p))
    expected=plan.get('reference_capture_files',[])
    if actual!=expected: raise RuntimeError('retained reference capture roster/hash changed')
    groups=capture_groups_from_folder(folder)
    records=capture_groups_json_records(groups)
    # Exercise strict JSON serialization on the actual retained capture metadata.
    json.dumps(records,sort_keys=True,allow_nan=False)
    return {'files':actual,'count':len(actual),'json_serializable_groups':len(records)}


def verify_loader_inputs(plan: dict) -> dict:
    checked=[]
    for item in plan['actual_loader_files']:
        p=Path(item['path'])
        if not p.is_file(): raise RuntimeError(f"missing actual loader input: {p}")
        got=pin(p)
        if got != item: raise RuntimeError(f"actual loader input changed: {p}")
        checked.append(got)
    return {'files':checked,'count':len(checked)}


def ensure_master_stack() -> dict:
    target=512*1024*1024
    soft,hard=resource.getrlimit(resource.RLIMIT_STACK)
    if hard != resource.RLIM_INFINITY and hard < target:
        raise RuntimeError(f'main-process hard stack limit {hard} is below required {target}')
    resource.setrlimit(resource.RLIMIT_STACK,(target,hard))
    actual_soft,actual_hard=resource.getrlimit(resource.RLIMIT_STACK)
    if actual_soft != target: raise RuntimeError(f'main-process stack limit did not reach {target}: {actual_soft}')
    return {'soft_bytes':actual_soft,'hard_bytes':actual_hard,'requested_soft_bytes':target}


def verify_runtime(plan: dict) -> dict:
    idrec=plan['runtime_identity']; identity_path=Path(idrec['path'])
    if not identity_path.is_file(): raise RuntimeError(f'new observer build identity pending: {identity_path}')
    if not {'sha256','size_bytes'} <= set(idrec):
        raise RuntimeError('fresh observer readback exists but final plan pin has not been refreshed')
    require_pin(idrec,'fresh observer postbuild readback')
    receipt=json.loads(identity_path.read_text())
    if receipt.get('schema')!=idrec['expected_schema'] or receipt.get('status')!='BUILD_PASS' or receipt.get('returncode')!=0:
        raise RuntimeError('fresh serial build receipt is not BUILD_PASS')
    if receipt.get('build_invocations')!=1 or receipt.get('real_invocations')!=0 or receipt.get('forecast_invocations')!=0 or receipt.get('model_invocations')!=0:
        raise RuntimeError('build receipt has unexpected invocation counts')
    post=receipt.get('postbuild',{})
    if post.get('status')!='BUILD_PASS' or post.get('returncode')!=0 or not post.get('success_footer_present'):
        raise RuntimeError('postbuild acceptance is not BUILD_PASS')
    if not post.get('tracked_source_unchanged') or post.get('compile_error_markers') or not post.get('serial_compile_log_controls'):
        raise RuntimeError('postbuild source/compiler controls failed')
    if post.get('build_invocations')!=1 or post.get('real_invocations')!=0 or post.get('forecast_invocations')!=0 or post.get('model_invocations')!=0:
        raise RuntimeError('postbuild invocation counts are unexpected')
    if not all(x.get('matches_reference_48') and x.get('count')==48 for x in post.get('runtime_closure_checks',{}).values()):
        raise RuntimeError('postbuild runtime closure check did not pass')
    if receipt.get('manifest_sha256')!=plan['source_manifest']['sha256'] or receipt.get('dependency_inventory_sha256')!=plan['dependency_inventory']['sha256']:
        raise RuntimeError('build receipt manifest/dependency pins differ from runtime plan')
    if receipt.get('preflight',{}).get('configure_sha256')!=plan['configure']['sha256']:
        raise RuntimeError('build receipt configure pin differs from runtime plan')
    for name in ('source_manifest','dependency_inventory','configure'):
        require_pin(plan[name],name)
    manifest=json.loads(Path(plan['source_manifest']['path']).read_text())
    if manifest.get('commit')!=plan['build_provenance']['commit'] or len(manifest.get('tracked_files',[]))!=manifest.get('tracked_file_count'):
        raise RuntimeError('fresh source manifest identity/count mismatch')
    source_root=Path(plan['fresh_source_root'])
    bad=[]
    for item in manifest['tracked_files']:
        p=source_root/item['path']
        if item['git_mode']=='120000': raw=os.readlink(p).encode() if p.is_symlink() else b''
        else: raw=p.read_bytes() if p.is_file() and not p.is_symlink() else b''
        if len(raw)!=item['size_bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            bad.append(item['path'])
            if len(bad)>=5: break
    if bad: raise RuntimeError(f'fresh tracked source drift: {bad}')
    c=post
    e=post['executables']['wrf.exe']; exe=Path(e['path'])
    if not exe.is_file() or sha(exe)!=e['sha256'] or exe.stat().st_size!=e['size_bytes']:
        raise RuntimeError('fresh observer executable does not match postbuild readback')
    if receipt.get('build_log_sha256')!=post.get('build_log_sha256'):
        raise RuntimeError('outer/postbuild build log digests disagree')
    blog=Path(post['build_log'])
    if not blog.is_file() or sha(blog)!=post['build_log_sha256']:
        raise RuntimeError('fresh compile log differs from build receipt')
    old=Path(plan['stage_root'])/'OLD_OFF'/'wrf.exe'
    if sha(old)==sha(exe): raise RuntimeError('observer binary unexpectedly equals old binary')
    libs=e['runtime_libraries']
    for lib in libs: require_pin(lib,'runtime library')
    if len(libs)!=48: raise RuntimeError('unexpected runtime library closure count')
    ld=plan.get('ld_library_path')
    if not ld: raise RuntimeError('plan lacks approved LD_LIBRARY_PATH')
    dep=json.loads(Path(plan['dependency_inventory']['path']).read_text())
    if dep.get('runtime_environment',{}).get('LD_LIBRARY_PATH')!=ld or dep.get('runtime_environment',{}).get('NETCDF')!=plan['netcdf_prefix']:
        raise RuntimeError('runtime environment differs from pinned build inventory')
    resolved=ldd_map(exe,ld)
    expected={Path(x['path']).name:str(Path(x['path']).resolve()) for x in libs}
    if resolved!=expected: raise RuntimeError('fresh executable ldd map differs from approved 48-library closure')
    if any(('mpi' in n.lower() or 'mpich' in n.lower()) for n in resolved): raise RuntimeError('serial executable unexpectedly links MPI')
    return {'readback':pin(identity_path),'executable':pin(exe),'runtime_libraries':libs,'ldd_map':resolved,
            'build_log_sha256':post.get('build_log_sha256'),'configure_sha256':plan['configure']['sha256'],
            'source_manifest_sha256':plan['source_manifest']['sha256'],'tracked_source_files_checked':len(manifest['tracked_files'])}


def read_auth(plan:dict,runtime:dict)->dict:
    if not AUTH.is_file(): raise RuntimeError('root-authorization.json missing; execution is not authorized')
    a=json.loads(AUTH.read_text())
    if a.get('schema')!='UDM37_RRTMG4_EXPORT_RUNTIME_AUTH_V1' or a.get('status')!='AUTHORIZED_ONCE': raise RuntimeError('invalid root authorization')
    expected={'runner_sha256':sha(Path(__file__)),'plan_sha256':sha(PLAN),'stage_manifest_sha256':plan['stage_manifest']['sha256'],
              'runtime_identity_sha256':runtime['readback']['sha256'],'new_executable_sha256':runtime['executable']['sha256'],
              'old_executable_sha256':'d2c4c772ff8b3b3900b91de385a9bf9a0ab3ea5739d8deff89ec5efdc97555e6',
              'reader_sha256':plan['reader']['sha256']}
    for k,v in expected.items():
        if a.get(k)!=v: raise RuntimeError(f'authorization does not bind {k}')
    if a.get('expected_arm_order')!=list(ARMS) or a.get('max_forecasts')!=3 or a.get('model_invocation_budget')!=3 or a.get('per_arm_timeout_seconds')!=120:
        raise RuntimeError('authorization does not bind exactly three arms/120s')
    t=dt.datetime.now(dt.timezone.utc); start=dt.datetime.fromisoformat(a['issued_utc'].replace('Z','+00:00')); end=dt.datetime.fromisoformat(a['expires_utc'].replace('Z','+00:00'))
    if start>t or end<=t or (end-start).total_seconds()>3600: raise RuntimeError('authorization expired or time window invalid')
    return a


def env_for(plan:dict,arm:str)->dict[str,str]:
    # Keep the process environment minimal and remove all inherited WRF/audit/export knobs.
    ld=plan['ld_library_path']
    env={'PATH':'/usr/bin:/bin','HOME':os.environ.get('HOME','/tmp'),'LANG':'C','LC_ALL':'C',
         'LD_LIBRARY_PATH':ld,'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1',
         'OMP_NESTED':'FALSE','OPENBLAS_NUM_THREADS':'1','NETCDF':plan['netcdf_prefix'],
         'WRF_RRTMGP_BATCH_SIZE':'1','WRF_RRTMGP_COLUMN_I':'24','WRF_RRTMGP_COLUMN_J':'55',
         'WRF_RRTMGP_CAPTURE_DIR':str(Path(plan['stage_root'])/arm/'trace'),
         'WRF_RRTMGP_CAPTURE_ALL':'1'}
    if arm=='NEW_ON':
        case=Path(plan['stage_root'])/arm
        env.update({'WRF_RRTMGP_AUDIT_DIR':str(case/'audit'),'WRF_RRTMGP_AUDIT_SEEDS':'128',
                    'WRF_RRTMGP_AUDIT_NATIVE4':'1','WRF_RRTMGP_RRTMG4_EXPORT_DIR':str(case/'export')})
    return env


def scan_logs(case:Path)->dict:
    success=[]; fatal=[]; logs=[]
    for pat in ('rsl.out.*','rsl.error.*','wrf.stdout.log'):
        for p in sorted(case.glob(pat)):
            if not p.is_file(): continue
            logs.append(pin(p)); text=p.read_text(errors='replace')
            if 'wrf: success complete wrf' in text.lower():
                m=re.search(r'\.(\d+)$',p.name); success.append(int(m.group(1)) if m else 0)
            for n,line in enumerate(text.splitlines(),1):
                if any(m.lower() in line.lower() for m in FATAL_MARKERS): fatal.append({'file':p.name,'line':n,'text':line[:1000]})
    return {'success_ranks':sorted(set(success)),'fatal_markers':fatal,'logs':logs}


def capture_groups(case:Path)->dict:
    folder=case/'trace'; out={}
    for raw in sorted(folder.glob('*.raw')):
        lines=raw.read_text(encoding='ascii').splitlines()
        if len(lines)<2 or lines[0].strip()!='RRTMGP_RAW_V1': raise RuntimeError(f'{raw}: invalid raw schema')
        h=lines[1].split()
        if len(h)!=4 or h[0].upper() not in ('LW','SW') or int(h[1])!=24 or int(h[2])!=55: raise RuntimeError(f'{raw}: invalid trace context')
        records={}; i=2
        while i<len(lines):
            words=lines[i].split(); i+=1
            if not words: continue
            if len(words)!=2: raise RuntimeError(f'{raw}: malformed field header')
            name,n=words[0].upper(),int(words[1]); vals=[]
            while len(vals)<n and i<len(lines):
                vals.extend(float(v.replace('D','E').replace('d','e')) for v in lines[i].split()); i+=1
            if name in records or len(vals)!=n or not np.isfinite(vals).all(): raise RuntimeError(f'{raw}: invalid field {name}')
            records[name]=vals
        if 'RADIATION_STEP' not in records or 'SOURCE_TIME_SECONDS' not in records: raise RuntimeError(f'{raw}: missing identity')
        step=int(records['RADIATION_STEP'][0]); secs=float(records['SOURCE_TIME_SECONDS'][0]); key=(h[0].upper(),step,secs)
        if key in out: raise RuntimeError(f'{case}: duplicate raw key {key}')
        stem=raw.with_suffix(''); files={s:stem.with_suffix('.'+s) for s in ('raw','input','result')}
        if any(not p.is_file() or p.stat().st_size==0 for p in files.values()): raise RuntimeError(f'{case}: incomplete capture group {stem}')
        out[key]={s:pin(p) for s,p in files.items()}
    if not out: raise RuntimeError(f'{case}: no 37-wrapper captures')
    return out


def audit_csv(case:Path)->dict:
    p=case/'audit'/'same_state.csv'
    if not p.is_file(): raise RuntimeError('NEW_ON same_state.csv missing')
    with p.open(newline='') as f:
        rd=csv.DictReader(f)
        required={'phase','domain','step','source_seconds','i','j','metric','sample_count','radius_mode','scope'}
        if not rd.fieldnames or not required<=set(rd.fieldnames): raise RuntimeError('audit CSV header incomplete')
        rows=list(rd)
    if not rows: raise RuntimeError('audit CSV empty')
    for r in rows:
        if int(r['sample_count'])!=128 or float(r['sample_count'])!=128.0: raise RuntimeError('audit seed roster is not 128')
        if r['scope']!='selected_column' or int(r['radius_mode'])!=1: raise RuntimeError('audit row context/radius mode mismatch')
        for k,v in r.items():
            if k not in ('phase','metric','scope') and v!='' and not np.isfinite(float(v)): raise RuntimeError(f'audit nonfinite {k}')
    return {'path':pin(p),'rows':rows,'row_count':len(rows)}


def baseline_audit_rows(path:Path)->list[dict]:
    with path.open(newline='') as f: rows=list(csv.DictReader(f))
    chosen=[]
    for r in rows:
        if r['step'].strip()=='2161' and float(r['source_seconds'])==129600.0 and r['domain'].strip()=='1':
            # Include selected i/j and the expected aggregate rows; reject unrelated scopes.
            if (r['i'].strip(),r['j'].strip()) in {('24','55'),('0','0')}:
                chosen.append(r)
    if not chosen: raise RuntimeError('retained audit has no step-2161 first-call rows')
    return chosen


def compare_audit_to_baseline(actual:dict, baseline_path:Path)->dict:
    expected=baseline_audit_rows(baseline_path)
    rows=actual['rows']
    got=[r for r in rows if r['step'].strip()=='2161' and float(r['source_seconds'])==129600.0 and r['domain'].strip()=='1' and (r['i'].strip(),r['j'].strip()) in {('24','55'),('0','0')}]
    key=lambda r:(r['phase'].lower(),int(r['step']),float(r['source_seconds']),int(r['i']),int(r['j']),r['metric'])
    expmap={key(r):r for r in expected}; gotmap={key(r):r for r in got}
    if len(expmap)!=len(expected) or len(gotmap)!=len(got): raise RuntimeError('duplicate first-call audit metric/context')
    if set(expmap)!=set(gotmap): raise RuntimeError(f'first-call audit row roster differs: expected {len(expmap)}, got {len(gotmap)}')
    mismatches=[]
    for k,e in expmap.items():
        g=gotmap[k]
        for col in e:
            if col in ('value37','value4','mean37','sd37','mean4','sd4','sd_delta','source_seconds'):
                if float(e[col])!=float(g[col]): mismatches.append((k,col,e[col],g[col]))
            elif e[col].strip()!=g[col].strip(): mismatches.append((k,col,e[col],g[col]))
    if mismatches: raise RuntimeError(f'NEW_ON audit first-call differs from retained native4 baseline: {mismatches[:3]}')
    return {'status':'PASS_EXACT_FIRST_CALL','rows_compared':len(expected),'selected_and_aggregate':True,
            'baseline_sha256':sha(baseline_path),'call_context':{'step':2161,'source_seconds':129600.0,'phases':['lw','sw']}}


def validate_netcdf(path:Path, expected_time:str)->dict:
    rec={'file':pin(path),'times':[],'variable_count':0,'numeric_values':0}
    with Dataset(path,'r') as ds:
        if 'Times' not in ds.variables: raise RuntimeError(f'{path}: missing Times')
        rec['times']=[''.join(x.decode() if isinstance(x,bytes) else str(x) for x in row).strip() for row in ds['Times'][:]]
        if rec['times']!=[expected_time]: raise RuntimeError(f'{path}: Times mismatch {rec["times"]}')
        rec['data_model']=ds.data_model
        rec['dimensions']={n:{'size':len(d),'unlimited':bool(d.isunlimited())} for n,d in ds.dimensions.items()}
        rec['global_attributes']={n:attr(ds.getncattr(n)) for n in ds.ncattrs()}
        for name,var in ds.variables.items():
            rec['variable_count']+=1; var.set_auto_maskandscale(False); raw=np.asarray(var[:])
            if raw.dtype.kind in 'fci':
                if not np.isfinite(raw).all(): raise RuntimeError(f'{path}:{name} raw nonfinite')
                for att in ('_FillValue','missing_value'):
                    if att in var.ncattrs() and np.any(raw==np.asarray(var.getncattr(att))): raise RuntimeError(f'{path}:{name} raw {att}')
                rec['numeric_values']+=raw.size
            var.set_auto_maskandscale(True); dec=var[:]
            if np.ma.isMaskedArray(dec) and np.ma.getmaskarray(dec).any(): raise RuntimeError(f'{path}:{name} decoded mask')
            dat=np.asarray(dec.data if np.ma.isMaskedArray(dec) else dec)
            if dat.dtype.kind in 'fci' and not np.isfinite(dat).all(): raise RuntimeError(f'{path}:{name} decoded nonfinite')
    return rec


def compare_nc(a_path:Path,b_path:Path)->dict:
    mism=[]
    a_pin=pin(a_path); b_pin=pin(b_path)
    if a_pin['sha256']!=b_pin['sha256']: mism.append('whole_file_sha256')
    with Dataset(a_path) as a,Dataset(b_path) as b:
        if a.data_model!=b.data_model: mism.append('data_model')
        da={k:(len(v),bool(v.isunlimited())) for k,v in a.dimensions.items()}; db={k:(len(v),bool(v.isunlimited())) for k,v in b.dimensions.items()}
        if da!=db: mism.append('dimensions')
        if set(a.variables)!=set(b.variables): mism.append('variable_set')
        for n in sorted(set(a.variables)&set(b.variables)):
            x,y=a[n],b[n]
            if (x.dimensions,x.shape,str(x.dtype))!=(y.dimensions,y.shape,str(y.dtype)): mism.append(f'{n}:schema'); continue
            x.set_auto_maskandscale(False);y.set_auto_maskandscale(False)
            if np.asarray(x[:]).tobytes(order='C')!=np.asarray(y[:]).tobytes(order='C'): mism.append(f'{n}:raw_bytes')
            if {k:attr(x.getncattr(k)) for k in x.ncattrs()}!={k:attr(y.getncattr(k)) for k in y.ncattrs()}: mism.append(f'{n}:attributes')
        if {k:attr(a.getncattr(k)) for k in a.ncattrs()}!={k:attr(b.getncattr(k)) for k in b.ncattrs()}: mism.append('global_attributes')
    return {'status':'PASS_EXACT' if not mism else 'FAIL_DIFFERENCE','mismatches':mism,'left':a_pin,'right':b_pin}


def validate_case(arm:str,case:Path,exe:Path,plan:dict,receipt:dict,auth:dict,pending_arms:tuple[str,...])->None:
    # This function only begins after root authorization has been checked.
    runtime=verify_runtime(plan); stage=verify_stage(plan,empty_arms=pending_arms)
    reference_capture=verify_reference_capture(plan)
    loader_pre=verify_loader_inputs(plan)
    stack_record=ensure_master_stack()
    stdout=case/'wrf.stdout.log'
    if stdout.exists() or stdout.is_symlink(): raise RuntimeError(f'{arm}: stdout already exists')
    rec={'status':'PREPARED','cwd':str(case),'executable':pin(exe),'command':[str(exe)],'started_utc':now(),
         'runtime_prelaunch':runtime,'stage_prelaunch':stage,'reference_capture_prelaunch':reference_capture,
         'actual_loader_inputs_prelaunch':loader_pre,'main_stack_limit':stack_record,
         'process_id':None,'returncode':None,'invocations':0}
    receipt['arms'][arm]=rec; atomic(RECEIPT,receipt)
    proc=None; rc=None; timed=False
    env=env_for(plan,arm)
    try:
        if sha(PLAN)!=auth['plan_sha256'] or sha(Path(__file__))!=auth['runner_sha256'] or sha(AUTH)!=receipt['authorization_sha256']:
            raise RuntimeError('authorized plan/runner/auth bytes changed before launch')
        if sha(exe)!=auth['old_executable_sha256' if arm=='OLD_OFF' else 'new_executable_sha256']:
            raise RuntimeError('arm executable changed before launch')
        with stdout.open('xb') as log:
            proc=subprocess.Popen([str(exe)],cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            rec.update({'process_id':proc.pid,'invocations':1,'status':'RUNNING'})
            receipt['model_invocations']+=1; atomic(RECEIPT,receipt)
            try: rc=proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                timed=True
                try: os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError: pass
                try: rc=proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    rc=proc.wait()
    except BaseException as e:
        rec['launch_error']=repr(e)
        if proc is not None and proc.poll() is None:
            try: os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: rc=proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                rc=proc.wait()
    rec.update({'returncode':rc,'timed_out':timed,'ended_utc':now(),'process_status':'PROCESS_COMPLETE' if proc else 'NOT_LAUNCHED'})
    atomic(RECEIPT,receipt)  # durable process result before any log/output read
    # Recheck loader bytes even when the child failed; preserve this evidence
    # before classifying its model result.
    rec['actual_loader_inputs_postprocess']=verify_loader_inputs(plan)
    atomic(RECEIPT,receipt)
    if proc is None or rc is None or rc!=0 or timed:
        rec.update({'status':'FAIL_PRESERVED','reason':'process missing, nonzero return, or timeout'}); atomic(RECEIPT,receipt)
        raise RuntimeError(f'{arm}: model process did not complete successfully')
    rec['runtime_postprocess']=verify_runtime(plan)
    rec['stage_postprocess']=verify_stage(plan)
    rec['reference_capture_postprocess']=verify_reference_capture(plan)
    atomic(RECEIPT,receipt)
    logscan=scan_logs(case); rec['log_scan']=logscan
    if logscan['fatal_markers'] or logscan['success_ranks']!=[0]:
        rec.update({'status':'FAIL_PRESERVED','reason':'fatal marker or missing unique serial success'}); atomic(RECEIPT,receipt)
        raise RuntimeError(f'{arm}: WRF success marker gate failed')
    rec['histories']=[]
    for stamp in TIMES:
        f=case/f'wrfout_d01_{stamp}'
        if not f.is_file(): raise RuntimeError(f'{arm}: missing history {f.name}')
        rec['histories'].append(validate_netcdf(f,stamp))
    extra_hist=[p.name for p in case.glob('wrfout_d01_*') if p.is_file() and p.name not in {f'wrfout_d01_{t}' for t in TIMES}]
    if extra_hist: raise RuntimeError(f'{arm}: unexpected history files {extra_hist}')
    cp=case/RESTART
    if not cp.is_file(): raise RuntimeError(f'{arm}: missing final restart')
    rec['restart']=validate_netcdf(cp,'2016-10-07_12:01:00')
    extra_cp=[p.name for p in case.glob('wrfrst_d01_*') if p.is_file() and p.name!=INPUT_RESTART and p.name!=RESTART]
    if extra_cp: raise RuntimeError(f'{arm}: unexpected restart files {extra_cp}')
    rec['capture_groups']=capture_groups_json_records(capture_groups(case))
    if arm=='NEW_ON':
        aud=audit_csv(case); rec['audit']=aud
        baseline=Path(plan['reference_audit']['path']); require_pin(plan['reference_audit'],'retained audit reference')
        rec['audit_first_call_comparison']=compare_audit_to_baseline(aud,baseline)
        expected={'rrtmg4_d01_i24_j55_step2161_lw.txt','rrtmg4_d01_i24_j55_step2161_sw.txt'}
        exp=case/'export'; files={p.name for p in exp.iterdir() if p.is_file()}
        if files!=expected: raise RuntimeError(f'NEW_ON export files {sorted(files)} != {sorted(expected)}')
        spec=importlib.util.spec_from_file_location('rrtmg4_read_export',plan['reader']['path'])
        mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
        require_pin(plan['reader'],'export reader')
        inv=[]
        for name,phase in [('rrtmg4_d01_i24_j55_step2161_lw.txt','LW'),('rrtmg4_d01_i24_j55_step2161_sw.txt','SW')]:
            parsed=mod.read_export(exp/name,expected_phase=phase); inv.append(mod.inventory(parsed))
        rec['exports']=inv
    else:
        for sub in ('audit','export'):
            p=case/sub
            if p.exists() and any(p.iterdir()): raise RuntimeError(f'{arm}: unexpected {sub} product')
    rec['runtime_final']=verify_runtime(plan); rec['status']='PASS_ARM'; atomic(RECEIPT,receipt)


def compare_campaign(plan:dict,receipt:dict)->dict:
    root=Path(plan['stage_root']); comparisons=[]
    files=[f'wrfout_d01_{t}' for t in TIMES]+[RESTART]
    for filename in files:
        for left,right in [('OLD_OFF','NEW_OFF'),('NEW_OFF','NEW_ON')]:
            c=compare_nc(root/left/filename,root/right/filename)
            if c['status']!='PASS_EXACT': raise RuntimeError(f'{filename} differs: {left} vs {right}: {c["mismatches"][:5]}')
            comparisons.append({'left_arm':left,'right_arm':right,'file':filename,**c})
    groups={a:capture_groups(root/a) for a in ARMS}
    keys=[set(g) for g in groups.values()]
    if keys[0]!=keys[1] or keys[1]!=keys[2]: raise RuntimeError('actual 37 wrapper phase/step/time roster differs across arms')
    capture_checks=[]
    for key in sorted(keys[0]):
        for suffix in ('raw','input','result'):
            vals=[groups[a][key][suffix]['sha256'] for a in ARMS]
            if len(set(vals))!=1: raise RuntimeError(f'37 raw capture changed across arms at {key}/{suffix}')
            capture_checks.append({'key':key,'suffix':suffix,'sha256':vals[0]})
    if len(keys[0])!=2 or {(k[0],k[1],k[2]) for k in keys[0]}!={('LW',2161,129600.0),('SW',2161,129600.0)}:
        raise RuntimeError(f'expected one LW/SW selected capture at step2161/time129600, got {sorted(keys[0])}')
    # Verify first-call captured legacy wrapper against retained original one-hour baseline.
    oldroot=Path(plan['reference_capture_root']); refgroups=capture_groups_from_folder(oldroot)
    for key in keys[0]:
        if key not in refgroups: raise RuntimeError(f'retained baseline capture lacks first-call key {key}')
        for suffix in ('raw','input','result'):
            if groups['NEW_ON'][key][suffix]['sha256']!=refgroups[key][suffix]['sha256']:
                raise RuntimeError(f'NEW_ON selected wrapper capture differs from retained original {key}/{suffix}')
    return {'netcdf_comparisons':comparisons,'production_capture_comparisons':capture_checks,
            'actual_roster':[{'phase':k[0],'step':k[1],'source_seconds':k[2]} for k in sorted(keys[0])],
            'first_call_vs_retained_capture':'PASS_EXACT'}


def capture_groups_json_records(groups:dict)->list[dict]:
    records=[]
    for (phase,step,secs),files in sorted(groups.items()):
        records.append({'phase':phase,'step':step,'source_seconds':secs,'files':files})
    return records


def capture_groups_from_folder(folder:Path)->dict:
    out={}
    for raw in sorted(folder.glob('*.raw')):
        lines=raw.read_text(encoding='ascii').splitlines(); h=lines[1].split()
        vals={}; i=2
        while i<len(lines):
            w=lines[i].split(); i+=1
            if not w: continue
            n=int(w[1]); a=[]
            while len(a)<n and i<len(lines): a.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split()); i+=1
            if len(a)!=n: raise RuntimeError(f'{raw}: malformed')
            vals[w[0].upper()]=a
        key=(h[0].upper(),int(vals['RADIATION_STEP'][0]),float(vals['SOURCE_TIME_SECONDS'][0]))
        stem=raw.with_suffix(''); rec={s:pin(stem.with_suffix('.'+s)) for s in ('raw','input','result')}
        if key in out: raise RuntimeError(f'duplicate retained capture {key}')
        out[key]=rec
    return out


def main()->int:
    owns_lock=False
    if len(sys.argv)!=2 or sys.argv[1] not in ('--check','--execute'):
        print('usage: run_export_once.py --check|--execute',file=sys.stderr); return 2
    try:
        plan=read_plan(); stage=verify_stage(plan,empty_arms=ARMS)
        loader_preflight=verify_loader_inputs(plan)
        # Always prove the retained scientific comparison source before readiness.
        require_pin(plan['reference_audit'],'retained native4 audit CSV')
        require_pin(plan['reader'],'strict export reader')
        retained_files=verify_reference_capture(plan)
        refcapture=capture_groups_from_folder(Path(plan['reference_capture_root']))
        if ('LW',2161,129600.0) not in refcapture or ('SW',2161,129600.0) not in refcapture:
            raise RuntimeError('retained reference capture lacks expected first LW/SW call')
        old_case=Path(plan['reference_audit']['path']).parent.parent
        ref_audit=audit_csv(old_case)
        audit_selfcheck=compare_audit_to_baseline(ref_audit,Path(plan['reference_audit']['path']))
        result={'status':'STAGE_PASS_WAITING_FOR_BUILD' if not Path(plan['runtime_identity']['path']).is_file() else 'PREPARED',
                'stage_preflight':stage,'retained_reference_capture_keys':[list(k) for k in sorted(refcapture)],
                'retained_reference_capture_files':retained_files,'actual_loader_inputs_preflight':loader_preflight,
                'reference_audit':plan['reference_audit'],'reader':plan['reader'],
                'retained_audit_selfcheck':audit_selfcheck,
                'runner':pin(Path(__file__)),'plan_sha256':sha(PLAN),
                'retained_first_call_audit_rows':len(baseline_audit_rows(Path(plan['reference_audit']['path'])))}
        if sys.argv[1]=='--check':
            if Path(plan['runtime_identity']['path']).is_file(): result['runtime_preflight']=verify_runtime(plan)
            print(json.dumps(result,indent=2,sort_keys=True)); return 0
        # Collision refusal occurs before receipt/lock mutation.
        if LOCK.exists() or RECEIPT.exists() or COMPARISON.exists(): raise RuntimeError('one-use lock/receipt/comparison already exists')
        runtime=verify_runtime(plan); auth=read_auth(plan,runtime)
        result['authorization_sha256']=sha(AUTH); result['runtime_preflight']=runtime
        fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f: f.write(json.dumps({'pid':os.getpid(),'created_utc':now(),'auth_sha256':sha(AUTH)})+'\n'); f.flush(); os.fsync(f.fileno())
        owns_lock=True
        result.update({'schema':'udm37-rrtmg4-export-execution-v4','status':'RUNNING','started_utc':now(),
                       'model_invocations':0,'arms':{},'counts':{'build':0,'real':0,'model':0}})
        atomic(RECEIPT,result)
        for idx,arm in enumerate(ARMS):
            exe=(Path(plan['stage_root'])/arm/'wrf.exe') if arm=='OLD_OFF' else Path(runtime['executable']['path'])
            validate_case(arm,Path(plan['stage_root'])/arm,exe,plan,result,auth,tuple(ARMS[idx:]))
        comparison=compare_campaign(plan,result)
        result['comparison']=comparison
        result['status']='PASS_EXACT_OUTPUTS_CAPTURE_AUDIT_EXPORT'
        result['counts']['model']=result['model_invocations']
        result['ended_utc']=now(); atomic(COMPARISON,comparison); atomic(RECEIPT,result)
        return 0
    except BaseException as e:
        # Never overwrite a pre-existing receipt after collision; only update our locked execution.
        if owns_lock and LOCK.exists() and RECEIPT.exists():
            try:
                r=json.loads(RECEIPT.read_text()); r['status']='FAIL_PRESERVED'; r['error']=repr(e); r['ended_utc']=now()
                for armrec in r.get('arms',{}).values():
                    if armrec.get('status') in ('PREPARED','RUNNING'): armrec['status']='FAIL_PRESERVED'
                r['counts']['model']=r.get('model_invocations',0); atomic(RECEIPT,r)
            except BaseException as write_error: print(f'receipt preservation error: {write_error!r}',file=sys.stderr)
        print(f'FAIL_PRESERVED_OR_PREFLIGHT: {e}',file=sys.stderr); return 1

if __name__=='__main__': raise SystemExit(main())
