#!/usr/bin/env python3
"""Single-use pinned executor for plan.json. Root must authorize before use."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import traceback

HERE=Path(__file__).resolve().parent
PLAN_SHA256='e069e49ce28cca69dc0864e2fa2fa783f3a019a41f700a47234a767e2cbad856'
PYTHON=Path('/usr/bin/python3.12')
TIMEOUT_SECONDS=7200

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree_hashes(root:Path)->dict[str,str]:
    return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}

def verify_pins(plan:dict)->dict[str,str]:
    pins={}
    for item in plan['source_pins'].values():
        p=Path(item['path']); got=sha(p)
        if got!=item['sha256']: raise RuntimeError(f'source pin mismatch: {p}: {got} != {item["sha256"]}')
        pins[str(p)]=got
    for item in plan['fixed_inputs'].values():
        p=Path(item['path']); got=sha(p)
        if got!=item['sha256']: raise RuntimeError(f'fixed input pin mismatch: {p}: {got} != {item["sha256"]}')
        pins[str(p)]=got
    return pins

def main()->int:
    lock=HERE/'run.lock'; receipt=HERE/'execution.json'
    if receipt.exists(): raise RuntimeError(f'Existing execution receipt; preserving single-use state: {receipt}')
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write(json.dumps({'pid':os.getpid(),'created_utc':dt.datetime.now(dt.timezone.utc).isoformat()})+'\n')
        f.flush(); os.fsync(f.fileno())
    record={'status':'PREFLIGHT_FAILED','runner_sha256':sha(Path(__file__)),
            'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'pre_pins':{},'post_pins':{},'runs':[],
            'scope':'Numerical coefficient generation/interpolation diagnostics only; not WRF/model validation.'}
    plan=None
    try:
        pp=HERE/'plan.json'; got=sha(pp); record['plan_sha256']=got
        if got!=PLAN_SHA256: raise RuntimeError(f'plan changed: {got} != reviewed {PLAN_SHA256}')
        plan=json.loads(pp.read_text())
        if plan['status']!='PLAN_ONLY_NOT_EXECUTED': raise RuntimeError(f"unexpected plan state {plan['status']}")
        record['pre_pins']=verify_pins(plan)
        if not PYTHON.is_file() or not os.access(PYTHON,os.X_OK): raise RuntimeError(f'Required interpreter unavailable: {PYTHON}')
        record['python']=str(PYTHON)
        env=os.environ.copy(); env.update({'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
        record['environment_overrides']={'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
        record['timeout_seconds_per_generation']=TIMEOUT_SECONDS
        idir=Path(plan['input_staging']['planned_dir'])
        runs=plan['generation_runs']; outdirs=[Path(r['output_dir']) for r in runs]
        if idir.exists(): raise RuntimeError(f'Input staging exists; preserve/review: {idir}')
        if len(set(outdirs))!=len(outdirs) or any(p.exists() for p in outdirs): raise RuntimeError('An output directory exists or paths collide')
        idir.mkdir(parents=True)
        for spec in plan['input_staging']['links_or_copies']:
            src=Path(spec['source']); dst=idir/spec['basename']
            if sha(src)!=spec['sha256']: raise RuntimeError(f'Input changed before staging: {src}')
            dst.symlink_to(src)
            if not dst.is_file() or sha(dst)!=spec['sha256']: raise RuntimeError(f'Input staging mismatch: {dst}')
        record['staged_input_hashes']={str(p):sha(p) for p in sorted(idir.iterdir())}
        failed=False
        command_by_name={c['run']:c for c in plan['commands_not_run']}
        for run in runs:
            command=command_by_name.get(run['name'])
            if command is None: raise RuntimeError(f"No pinned argv for generation {run['name']}")
            argv=command['argv']
            if not argv or argv[0]!='python3': raise RuntimeError('Reviewed generator argv changed')
            argv=[str(PYTHON),*argv[1:]]; outdir=Path(run['output_dir'])
            if outdir.exists(): raise RuntimeError(f'Output unexpectedly exists: {outdir}')
            log=HERE/'logs'/f"{run['name']}.log"; log.parent.mkdir(exist_ok=True)
            item={'name':run['name'],'argv':argv,'cwd':plan['source_checkout'],'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'log_path':str(log),'output_dir':str(outdir)}
            record['runs'].append(item)
            t0=time.monotonic(); timed_out=False
            try:
                with log.open('xb') as stream:
                    proc=subprocess.Popen(argv,cwd=plan['source_checkout'],env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                    try: rc=proc.wait(timeout=TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        timed_out=True
                        try: os.killpg(proc.pid,signal.SIGTERM)
                        except ProcessLookupError: pass
                        try: proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            try: os.killpg(proc.pid,signal.SIGKILL)
                            except ProcessLookupError: pass
                            proc.wait()
                        rc=proc.returncode
                item['returncode']=rc
            except BaseException as exc:
                item['launch_exception']=repr(exc); item['traceback']=traceback.format_exc(); rc=None
            item.update({'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-t0,'timed_out':timed_out})
            if log.is_file(): item['log_sha256']=sha(log)
            item['outputs']=tree_hashes(outdir) if outdir.is_dir() else None
            try:
                nowpins=verify_pins(plan); item['pins_unchanged_after_run']=nowpins==record['pre_pins']
                if nowpins!=record['pre_pins']: item['pin_error']='Pinned source/input changed during run'; failed=True
            except Exception as exc:
                item['pins_unchanged_after_run']=False; item['pin_error']=repr(exc); failed=True
            valid=False
            if rc==0 and not timed_out and outdir.is_dir() and (outdir/'result.json').is_file() and (outdir/'frozen-ice-psd-moments.nc').is_file():
                result=json.loads((outdir/'result.json').read_text())
                item['result_sha256']=sha(outdir/'result.json'); item['table_sha256']=sha(outdir/'frozen-ice-psd-moments.nc')
                expected_status=plan['old_generation']['status']
                valid=result.get('status')==expected_status
                item['expected_generation_status']=expected_status
            item['generation_valid']=valid
            if not valid: failed=True
            if failed: break
        record['post_pins']=verify_pins(plan)
        record['staged_input_hashes_after']={str(p):sha(p) for p in sorted(idir.iterdir())}
        if record['staged_input_hashes_after']!=record.get('staged_input_hashes'): failed=True
        if record['post_pins']!=record['pre_pins']: failed=True
        record['status']='FAILED_PRESERVED' if failed or len(record['runs'])!=2 else 'GENERATIONS_COMPLETE_DIAGNOSTICS_PENDING'
    except BaseException as exc:
        record['status']='FAILED_PRESERVED'; record['exception']=repr(exc); record['traceback']=traceback.format_exc()
        if plan is not None:
            try: record['post_pins']=verify_pins(plan)
            except Exception as pexc: record['post_pin_exception']=repr(pexc)
    record['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    tmp=HERE/'execution.json.tmp'
    with tmp.open('x') as f:
        json.dump(record,f,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,receipt)
    print(json.dumps({'status':record['status'],'receipt':str(receipt),'runs':len(record['runs'])}))
    return 0 if record['status']=='GENERATIONS_COMPLETE_DIAGNOSTICS_PENDING' else 1
if __name__=='__main__': raise SystemExit(main())
