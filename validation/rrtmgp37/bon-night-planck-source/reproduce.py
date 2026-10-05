#!/usr/bin/env python3
"""Verify the archived inputs; optionally rerun the pinned Python-only analysis."""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, os
from pathlib import Path
import shutil, subprocess, sys, time
sys.dont_write_bytecode=True

def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())
def write_json(path: Path, value: object) -> None:
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
def compare_tree(a, b, path=''):
    errors=[]
    if isinstance(a,dict) and isinstance(b,dict):
        if set(a)!=set(b): return [f'{path}: object keys differ']
        for k in a: errors.extend(compare_tree(a[k],b[k],f'{path}/{k}'))
    elif isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b): return [f'{path}: list length differs']
        for i,(x,y) in enumerate(zip(a,b)): errors.extend(compare_tree(x,y,f'{path}/{i}'))
    elif isinstance(a,bool) or isinstance(b,bool):
        if a!=b: errors.append(f'{path}: boolean differs')
    elif isinstance(a,(int,float)) and isinstance(b,(int,float)):
        if not (math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b))<=1e-9): errors.append(f'{path}: numeric difference exceeds absolute 1e-9')
    elif a!=b: errors.append(f'{path}: value differs')
    return errors

def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',action='store_true',help='run one isolated Python analysis (requires NumPy/SciPy/netCDF4)')
    ap.add_argument('--output-dir',type=Path,help='fresh nonexistent output directory; required with --run')
    ap.add_argument('--source-root',type=Path,help='checkout with WRF/run and WRF/external/rte_rrtmgp; defaults to repository root')
    a=ap.parse_args(); package=Path(__file__).resolve().parent
    repo=a.source_root.resolve() if a.source_root else package.parents[2]
    from verify import verify_package
    print(json.dumps({'verification':verify_package(package,repo),'analysis_run':bool(a.run)},sort_keys=True))
    if not a.run:
        if a.output_dir: ap.error('--output-dir requires --run')
        return 0
    if a.output_dir is None: ap.error('--run requires --output-dir')
    out=a.output_dir.absolute(); out.mkdir(parents=True,exist_ok=False)
    stage=out/'stage'; stage.mkdir(); analysis=stage/'analysis'; analysis.mkdir()
    plan_bytes=(package/'analysis/plan.json').read_bytes(); plan=json.loads(plan_bytes)
    data_map={'packet':'legacy-lw-packet.txt.gz','input':'matched-gp-input.txt.gz','gp_source':'gp-lw-transport.txt.gz'}
    helper_map={'angular_helper':'angular_reference.py','legacy_helper':'legacy_lw_replay.py'}
    source_base='build/udm37-bon-common-band-source-pr-work/'
    source_keys=('coefficients','gp_kernel','gp_frontend','gp_loader','legacy_source')
    before={}; proc=None; launch=None; stdout=None; stderr=None
    try:
        for key,filename in data_map.items():
            target=stage/plan['pins'][key]['path']; target.parent.mkdir(parents=True,exist_ok=True)
            raw=gzip.decompress((package/'data'/filename).read_bytes())
            pin=plan['pins'][key]
            if len(raw)!=pin['bytes'] or sha_bytes(raw)!=pin['sha256']: raise ValueError('staged data pin mismatch: '+key)
            with target.open('xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
        for key,filename in helper_map.items():
            target=stage/plan['pins'][key]['path']; target.parent.mkdir(parents=True,exist_ok=True)
            raw=(package/'analysis'/filename).read_bytes()
            if sha_bytes(raw)!=plan['pins'][key]['sha256']: raise ValueError('staged helper pin mismatch: '+key)
            with target.open('xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
        # Preserve frozen relative pin names by mirroring their source tree under
        # stage/build/... . Source/coefficient files are checked symlinks to the
        # current checkout; they are not copied into the evidence package.
        for key in source_keys:
            pin=plan['pins'][key]; text=Path(pin['path']).as_posix()
            if not text.startswith(source_base): raise ValueError('unexpected source pin path '+key)
            source=repo/Path(text[len(source_base):])
            if not source.is_file() or source.stat().st_size!=pin['bytes'] or sha_file(source)!=pin['sha256']:
                raise ValueError('tracked source/coefficient pin mismatch '+key)
            target=stage/Path(text); target.parent.mkdir(parents=True,exist_ok=True); target.symlink_to(source.resolve())
            before[key]={'path':str(source.resolve()),'sha256':sha_file(source),'size_bytes':source.stat().st_size}
        design=plan['pins']['design_v1']; target=stage/design['path']; target.parent.mkdir(parents=True,exist_ok=True)
        db=(package/'design/v1/plan.json').read_bytes()
        if sha_bytes(db)!=design['sha256']: raise ValueError('design-v1 pin mismatch')
        with target.open('xb') as f: f.write(db); f.flush(); os.fsync(f.fileno())
        for name in ('analyze.py','plan.json'):
            shutil.copyfile(package/'analysis'/name,analysis/name)
        if (analysis/'plan.json').read_bytes()!=plan_bytes: raise ValueError('staged plan was rewritten')
        expected=json.loads((package/'analysis/result.json').read_text())
        launch={'status':'LAUNCHED','started_epoch':time.time(),'pid':None,'executable':sys.executable,
                'plan_sha256':sha_bytes(plan_bytes),'script_sha256':sha_file(analysis/'analyze.py')}
        proc=subprocess.Popen([sys.executable,'-B',str(analysis/'analyze.py')],cwd=stage,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        launch['pid']=proc.pid; write_json(out/'launch.json',launch)
        try: stdout,stderr=proc.communicate(timeout=1800)
        except subprocess.TimeoutExpired:
            proc.kill(); stdout,stderr=proc.communicate()
        (out/'stdout.log').write_text(stdout,encoding='utf-8'); (out/'stderr.log').write_text(stderr,encoding='utf-8')
        result_path=analysis/'result.json'; compare={'status':'NOT_COMPARABLE'}
        if proc.returncode==0 and result_path.is_file():
            actual=json.loads(result_path.read_text()); errs=compare_tree(expected,actual)
            compare={'status':'PASS_WITHIN_ABS_1E-9' if not errs else 'FAIL_RESULT_DIFFERENCE',
                     'absolute_tolerance':1e-9,'error_count':len(errs),'first_errors':errs[:20],
                     'actual_result_sha256':sha_file(result_path)}
            shutil.copyfile(result_path,out/'result.json')
        after={}
        for key in source_keys:
            path=Path(before[key]['path']); after[key]={'path':str(path),'sha256':sha_file(path),'size_bytes':path.stat().st_size}
        unchanged=before==after
        status='PASS_REPRODUCED_ANALYSIS' if proc.returncode==0 and compare['status'].startswith('PASS') and unchanged else 'FAIL_PRESERVED'
        receipt={'status':status,'pid':proc.pid,'returncode':proc.returncode,'started_epoch':launch['started_epoch'],'ended_epoch':time.time(),
                 'plan_sha256':sha_bytes(plan_bytes),'script_sha256':sha_file(analysis/'analyze.py'),
                 'substantive_comparison':compare,'source_coefficient_pre':before,'source_coefficient_post':after,
                 'source_pins_unchanged':unchanged,'scope':'Python analysis only; no compiled RTE/WRF/forecast call.'}
        write_json(out/'execution-receipt.json',receipt); print(json.dumps(receipt,sort_keys=True))
        return 0 if status.startswith('PASS') else 1
    except Exception as exc:
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
                try: stdout,stderr=proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill(); stdout,stderr=proc.communicate()
            elif stdout is None or stderr is None:
                stdout,stderr=proc.communicate()
            for name,value in (('stdout.log',stdout),('stderr.log',stderr)):
                if value is not None and not (out/name).exists():
                    (out/name).write_text(value,encoding='utf-8')
        if not (out/'execution-receipt.json').exists():
            write_json(out/'execution-receipt.json',{'status':'FAIL_PRESERVED','error':f'{type(exc).__name__}: {exc}',
                'pid':proc.pid if proc is not None else None,'returncode':proc.poll() if proc is not None else None,
                'started_epoch':launch['started_epoch'] if launch is not None else None,
                'source_coefficient_pre':before,'scope':'No automatic retry; child process terminated/reaped if launched; output retained.'})
        raise
if __name__=='__main__': raise SystemExit(main())
