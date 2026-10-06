#!/usr/bin/env python3
"""Single-use direct midpoint generator; root approval required before execution."""
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
PLAN_SHA='03fa89ff0f8d1ac041c855629a68a97e8a15f1918bf5869b849428c31c7c35e5'
PYTHON=Path('/usr/bin/python3.12')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tree_hashes(d): return {str(p.relative_to(d)):sha(p) for p in sorted(d.rglob('*')) if p.is_file()}
def verify_files(items):
    actual={}
    for x in items:
        p=Path(x['path']); h=sha(p)
        if h!=x['sha256']: raise RuntimeError(f"pinned file changed: {p}: {h} != {x['sha256']}")
        actual[str(p)]=h
    return actual

def main():
    lock=HERE/'run.lock'; receipt=HERE/'execution.json'
    if receipt.exists(): raise RuntimeError('Midpoint generation already has a receipt; do not rerun')
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f: f.write(json.dumps({'pid':os.getpid(),'created_utc':dt.datetime.now(dt.timezone.utc).isoformat()})+'\n');f.flush();os.fsync(f.fileno())
    rec={'status':'PREFLIGHT_FAILED','started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'runs':[],
         'scope':'Direct numerical interpolation sample only; not physical accuracy or model validation.'}
    plan=None
    try:
        pp=HERE/'plan.json'; ph=sha(pp);rec['plan_sha256']=ph
        if ph!=PLAN_SHA: raise RuntimeError(f'plan pin mismatch: {ph}')
        plan=json.loads(pp.read_text())
        if plan['status']!='PLAN_ONLY_NOT_EXECUTED':raise RuntimeError('Plan status changed')
        if not PYTHON.is_file() or not os.access(PYTHON,os.X_OK):raise RuntimeError(f'interpreter missing: {PYTHON}')
        rec['python']=str(PYTHON)
        rec['source_pins_before']=verify_files([{'path':v['path'],'sha256':v['sha256']} for v in plan['source_pins'].values()])
        rec['fixed_inputs_before']=verify_files(list(plan['fixed_inputs'].values()))
        priorplan=Path(plan['planck_coverage_plan']['path'])
        if sha(priorplan)!=plan['planck_coverage_plan']['sha256']:raise RuntimeError('Parent coverage plan changed')
        expanded=Path(plan['expanded_reference']['generation_dir'])
        result=expanded/'result.json';table=expanded/'frozen-ice-psd-moments.nc'
        if not result.is_file() or not table.is_file():raise RuntimeError('Expanded reference generation has not completed')
        # Reuse the pinned generation artifact validator; no new coefficient calculation occurs here.
        tool=Path(plan['source_checkout'])/'tools/udm_frozen_optics'
        import sys
        sys.path.insert(0,str(tool))
        import compare
        axes,arrays,receipt_data,rhash=compare.load(expanded)
        expected_axis=plan['expanded_reference']['expected_temperatures_K']
        expected_lam=plan['expanded_reference']['expected_lambda_m_inv']
        if receipt_data['status']!=plan['expanded_reference']['required_generation_status']:
            raise RuntimeError('Expanded generation is incomplete or wrong status')
        if axes['temperature'].tolist()!=expected_axis or axes['lambda'].tolist()!=expected_lam:
            raise RuntimeError('Expanded generation axes do not match plan')
        controls=plan['expanded_reference']['required_controls']
        actual={'order':receipt_data['order'],'max_spectral_step_cm_inv':receipt_data['max_spectral_step_cm_inv'],
                'workers':receipt_data['workers'],'spectral_chunk_size':receipt_data['spectral_chunk_size'],'max_terms':receipt_data['max_terms']}
        if actual!=controls:raise RuntimeError(f'Expanded controls mismatch: {actual}')
        # The binary is verified against its own receipt by compare.load. Do not infer
        # numerical-source drift from path-dependent bytes in separately built output dirs.
        rec['expanded_reference_before']={'result_sha256':sha(result),'table_sha256':sha(table),'receipt_sha256':rhash,
                                          'kernel_binary_sha256':receipt_data['kernel_binary_sha256']}
        run=plan['run'];outdir=Path(run['output_dir']);idir=Path(run['input_dir'])
        if outdir.exists() or idir.exists() or (HERE/'logs').exists():raise RuntimeError('Midpoint input/output/log path exists; preserve it')
        idir.mkdir(parents=True)
        staged=[]
        for name,source in [('IOP_2008_ASCIItable.dat',plan['fixed_inputs']['ice_index']['path']),
                            ('tsi-ssi_v03r00_reference-spectra_c20240830.txt',plan['fixed_inputs']['solar_spectrum']['path'])]:
            dst=idir/name;dst.symlink_to(source); staged.append({'path':str(dst),'sha256':sha(dst)})
        if any(x['sha256']!=plan['fixed_inputs']['ice_index' if Path(x['path']).name.startswith('IOP') else 'solar_spectrum']['sha256'] for x in staged):
            raise RuntimeError('Staged material/solar input hash mismatch')
        rec['staged_inputs']=staged
        argv=[str(PYTHON),str(Path(plan['generator']['path'])),'--input-dir',str(idir),'--data-dir',run['data_dir'],
              '--output-dir',str(outdir),'--lambda-grid',*[str(x) for x in run['parameters']['lambda_grid_m_inv']],
              '--temperatures',*[str(x) for x in run['parameters']['temperatures_K']],
              '--order','128','--spectral-step','50','--workers','12','--spectral-chunk-size','32','--max-terms','32000000']
        env=os.environ.copy();env.update({'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
        log=HERE/'logs'/'direct-midpoints.log';log.parent.mkdir()
        item={'name':'direct_interknots','argv':argv,'cwd':plan['source_checkout'],'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'output_dir':str(outdir),'log_path':str(log)};rec['runs'].append(item)
        t0=time.monotonic();rc=None;timeout=False
        try:
            with log.open('xb') as f:
                proc=subprocess.Popen(argv,cwd=plan['source_checkout'],env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
                try:rc=proc.wait(timeout=run['timeout_seconds'])
                except subprocess.TimeoutExpired:
                    timeout=True
                    try:os.killpg(proc.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(proc.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        proc.wait()
                    rc=proc.returncode
        except BaseException as exc:item['launch_exception']=repr(exc);item['traceback']=traceback.format_exc()
        item.update({'finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-t0,'returncode':rc,'timed_out':timeout})
        if log.is_file():item['log_sha256']=sha(log)
        item['outputs']=tree_hashes(outdir) if outdir.is_dir() else None
        if rc!=0 or timeout or not (outdir/'result.json').is_file() or not (outdir/'frozen-ice-psd-moments.nc').is_file():raise RuntimeError('Direct midpoint generation failed; outputs preserved')
        d_axes,d_arrays,direct,dhash=compare.load(outdir)
        if direct['status']!='COMPLETE_NUMERICAL_GENERATION_NOT_MODEL_VALIDATION':raise RuntimeError('Direct generation incomplete')
        if direct['temperatures_K']!=run['parameters']['temperatures_K'] or direct['lambda_grid_m_inv']!=expected_lam:raise RuntimeError('Direct output axes mismatch')
        for key in ('input_sources','gas_data_sha256','generator_sha256','kernel_source_sha256','kernel_source_adaptation','numerical_packages','compiler','kernel_flags','quadrature_algorithm','quadrature_nodes_weights_sha256','order','max_spectral_step_cm_inv','workers','spectral_chunk_size','max_terms','quadrature_area_weight_pruning_threshold'):
            if direct[key]!=receipt_data[key]:raise RuntimeError(f'Direct provenance/numerics differ from expanded generation: {key}')
        item['result_sha256']=sha(outdir/'result.json');item['result_receipt_sha256']=dhash;item['table_sha256']=sha(outdir/'frozen-ice-psd-moments.nc')
        item['kernel_binary_sha256']=direct['kernel_binary_sha256']
        item['expanded_kernel_binary_sha256']=receipt_data['kernel_binary_sha256']
        item['kernel_binary_bytes_identical']=direct['kernel_binary_sha256']==receipt_data['kernel_binary_sha256']
        item['kernel_binary_policy']='Each binary is verified against its own artifact receipt; cross-output-directory byte identity is reported only.'
        rec['expanded_reference_after']={'result_sha256':sha(result),'table_sha256':sha(table)}
        if rec['expanded_reference_after']['result_sha256']!=rec['expanded_reference_before']['result_sha256'] or rec['expanded_reference_after']['table_sha256']!=rec['expanded_reference_before']['table_sha256']:
            raise RuntimeError('Expanded reference changed during midpoint generation')
        rec['source_pins_after']=verify_files([{'path':v['path'],'sha256':v['sha256']} for v in plan['source_pins'].values()])
        rec['fixed_inputs_after']=verify_files(list(plan['fixed_inputs'].values()))
        if rec['source_pins_after']!=rec['source_pins_before'] or rec['fixed_inputs_after']!=rec['fixed_inputs_before']:
            raise RuntimeError('Pinned sources/inputs changed during generation')
        rec['status']='DIRECT_MIDPOINT_GENERATION_COMPLETE_DIAGNOSTICS_PENDING'
    except BaseException as exc:
        rec['status']='FAILED_PRESERVED';rec['exception']=repr(exc);rec['traceback']=traceback.format_exc()
        if plan is not None:
            try:rec['source_pins_after']=verify_files([{'path':v['path'],'sha256':v['sha256']} for v in plan['source_pins'].values()])
            except Exception as pinexc:rec['source_pin_error']=repr(pinexc)
            try:rec['fixed_inputs_after']=verify_files(list(plan['fixed_inputs'].values()))
            except Exception as pinexc:rec['fixed_input_error']=repr(pinexc)
    rec['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    tmp=HERE/'execution.json.tmp'
    with tmp.open('x') as f:json.dump(rec,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,receipt)
    print(json.dumps({'status':rec['status'],'receipt':str(receipt)}))
    return 0 if rec['status']=='DIRECT_MIDPOINT_GENERATION_COMPLETE_DIAGNOSTICS_PENDING' else 1
if __name__=='__main__':raise SystemExit(main())
