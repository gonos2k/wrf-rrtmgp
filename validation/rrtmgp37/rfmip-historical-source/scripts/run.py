#!/usr/bin/env python3
"""One historical SW standalone invocation with immutable inputs and observers."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, time
from build import pin, closure

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main():
    if (HERE/'execution.json').exists() or (HERE/'run').exists():
        raise FileExistsError('Refusing an implicit solver repeat')
    plan=json.loads((HERE/'plan.json').read_text())
    build=json.loads((HERE/'build-receipt.json').read_text())
    review_path=HERE/'pre-run-review.json'
    review=json.loads(review_path.read_text())
    if not str(review.get('status','')).startswith('PASS_SCOPED'):
        raise ValueError('Static observer review has not passed')
    if build['status']!='PASS_BUILD_NO_SOLVER' or not build['runtime_closure_exact_to_v5']:
        raise ValueError('Historical build has not passed its runtime gate')
    for record in [*plan['source_files'],*plan['pins'].values()]:
        actual=pin(record['path'])
        if (actual['sha256'],actual['size'])!=(record['sha256'],record['bytes']):
            raise ValueError('Staged source/input changed: '+record['path'])
    executable=Path(build['executable']['path'])
    if pin(executable)!=build['executable']:
        raise ValueError('Executable changed after build')
    env=dict(os.environ);env.update(build['controlled_environment'])
    if closure(executable,env)!=build['runtime_closure']:
        raise ValueError('Linked runtime changed')
    run=HERE/'run';run.mkdir()
    for key,name in [('coefficient','coeff.nc'),('input','input.nc'),('profile_selector','profiles.txt')]:
        (run/name).symlink_to(plan['pins'][key]['path'])
    # v1.0 read_size() precedes parsing argv[2]. Both names must resolve to
    # exactly the same input without altering that historical driver ordering.
    (run/'multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc').symlink_to(plan['pins']['input']['path'])
    refs=ROOT/'build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/reference'
    for var in ('rsd','rsu'):
        filename=f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
        shutil.copy2(refs/filename,run/filename)
    extra_pins={'plan':pin(HERE/'plan.json'),'build_receipt':pin(HERE/'build-receipt.json'),
                'pre_run_review':pin(review_path),'runner':pin(HERE/'run.py'),
                'loader_equivalence':pin(ROOT/'build/udm37-rfmip-historical-source-plan-v1/loader-equivalence-v1.json')}
    command=[str(executable),'8','input.nc','coeff.nc','1','diag','profiles.txt']
    receipt={'status':'RUNNING_ONE_HISTORICAL_STANDALONE','argv':command,'cwd':str(run),
             'pins':extra_pins,'source_commit':plan['source_commit'],
             'new_SW_standalone_calls':1,'new_WRF_REAL_or_forecast_calls':0,
             'reused_current_arm':'completed-v5-old_solar; no rerun',
             'started_epoch':time.time()}
    (HERE/'launched.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    log=HERE/'driver.log'
    try:
        with log.open('x') as stream:
            result=subprocess.run(command,cwd=run,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
        receipt.update(returncode=result.returncode,ended_epoch=time.time(),log=pin(log))
        if result.returncode:
            raise RuntimeError('Historical standalone returned nonzero')
        text=log.read_text()
        if any(marker in text for marker in ['stopping','unblock_and_write:','write_field:']):
            raise RuntimeError('Historical driver reported an error despite a zero return code')
        # The legacy driver STOP can return zero on error. Complete fresh
        # observer records and exact sizes are therefore required as well.
        sizes={'source_pre':135*(8+224*8),'source_post':135*(8+224*8),
               'optics':135*(8+60*224*3*8),
               'flux_solver':135*(8+61*2*8),'flux_written':135*(8+61*2*8)}
        for key,size in sizes.items():
            file=run/('diag_'+key+'.bin')
            if file.stat().st_size!=size:
                raise ValueError('Incomplete observer capture: '+key)
        receipt['captures']={key:pin(run/('diag_'+key+'.bin')) for key in sizes}
        receipt['outputs']={var:pin(run/f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc') for var in ('rsd','rsu')}
        for record in [*plan['source_files'],*plan['pins'].values()]:
            actual=pin(record['path'])
            if (actual['sha256'],actual['size'])!=(record['sha256'],record['bytes']):
                raise ValueError('Source/input changed during run')
        receipt['status']='COMPLETE_ONE_HISTORICAL_STANDALONE_NOT_ACCURACY_VERDICT'
    except Exception as exc:
        receipt.update(status='FAILED_ONE_HISTORICAL_STANDALONE',error=f'{type(exc).__name__}: {exc}',ended_epoch=time.time())
        raise
    finally:
        (HERE/'execution.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':receipt['status'],'returncode':receipt['returncode'],
                      'new_SW_standalone_calls':1,'elapsed_s':receipt['ended_epoch']-receipt['started_epoch']},sort_keys=True))

if __name__=='__main__':main()
