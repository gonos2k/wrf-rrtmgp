#!/usr/bin/env python3
"""Run isolated 2-rank WRF startup-failure probes and record process cleanup evidence."""
from __future__ import annotations
import hashlib, json, os, pathlib, signal, subprocess, sys, time

ROOT = pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
BUNDLE = ROOT / 'build/udm-sr-row-dm-sm/validation/collective-frozen-failures-v2'
EXE = ROOT / 'build/udm-sr-row-dm-sm/source/WRF/main/wrf.exe'
LAUNCHER = ROOT / 'build/deps/mpich-sock/bin/mpiexec'
DATA = ROOT / 'build/pr-wrf-rrtmgp/WRF/run'
CHECKPOINT = ROOT / 'build/udm-frozen-restart-plan/trial-mode1-0to12/wrfrst_d01_2010-06-11_12:00:00'
TABLE = ROOT / 'build/udm-mpix-evidence-work/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
COEFFS = ['rrtmgp-gas-lw-g128.nc','rrtmgp-gas-sw-g112.nc','rrtmgp-clouds-lw-bnd.nc','rrtmgp-clouds-sw-bnd.nc']
TIMEOUT = 60

def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def local_processes(case: pathlib.Path) -> list[dict[str, object]]:
    found=[]
    for proc in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
            if str(EXE) not in cmd: continue
            cwd=os.readlink(proc/'cwd')
            if cwd==str(case): found.append({'pid':int(proc.name),'cwd':cwd,'cmdline':cmd})
        except (OSError,ValueError):
            continue
    return found

def main() -> int:
    pre=json.loads((BUNDLE/'preflight.json').read_text())
    if digest(EXE)!=pre['executable_sha256'] or digest(CHECKPOINT)!=pre['checkpoint_sha256']:
        raise RuntimeError('approved executable/checkpoint changed after preflight')
    shared_before={n:digest(DATA/n) for n in COEFFS}
    if shared_before!=pre['shared_coeff_hashes_before']:
        raise RuntimeError('shared coefficient assets differ from preflight')
    cases=[]
    for name in ('missing-frozen-table','malformed-frozen-header'):
        case=BUNDLE/name
        if not case.is_dir(): raise RuntimeError(f'missing case directory {case}')
        if local_processes(case): raise RuntimeError(f'refusing case with preexisting local WRF processes: {case}')
        env=os.environ.copy()
        env['PATH']=str(LAUNCHER.parent)+os.pathsep+env.get('PATH','')
        env['LD_LIBRARY_PATH']=str(ROOT/'build/deps/root/usr/lib/x86_64-linux-gnu')+':'+str(ROOT/'build/deps/mpich-sock/lib')+':'+env.get('LD_LIBRARY_PATH','')
        env['MPICH_INTERFACE_HOSTNAME']='127.0.0.1';env['OMP_NUM_THREADS']='1';env['OPENBLAS_NUM_THREADS']='1'
        for key in list(env):
            if key.startswith(('WRF_RRTMGP_','RRTMGP_TRACE','RRTMGP_AUDIT')): env.pop(key,None)
        cmd=[str(LAUNCHER),'-launcher','fork','-iface','lo','-n','2','./wrf.exe']
        launcher_log=case/'launcher.log'
        start=time.time();timed_out=False;cleanup=[]
        with launcher_log.open('w') as stream:
            proc=subprocess.Popen(cmd,cwd=case,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                returncode=proc.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                timed_out=True;cleanup.append('SIGTERM process group after timeout')
                try: os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError: pass
                try: returncode=proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cleanup.append('SIGKILL process group after 5-second grace')
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    returncode=proc.wait(timeout=5)
        elapsed=time.time()-start
        before_cleanup=local_processes(case)
        if before_cleanup:
            cleanup.append('targeted SIGTERM/SIGKILL of case-cwd WRF ranks after launcher return')
            for item in before_cleanup:
                try: os.kill(int(item['pid']),signal.SIGTERM)
                except ProcessLookupError: pass
            time.sleep(1)
            for item in local_processes(case):
                try: os.kill(int(item['pid']),signal.SIGKILL)
                except ProcessLookupError: pass
        remaining=local_processes(case)
        ranklogs={}
        for path in sorted(case.glob('rsl.error.*')):
            ranklogs[path.name]={'sha256':digest(path),'text':path.read_text(errors='replace')}
        expected=('table hash failed' if name=='missing-frozen-table' else 'NetCDF open:')
        rank0=ranklogs.get('rsl.error.0000',{}).get('text','')
        expected_seen=expected in rank0 and 'RRTMGP_FROZEN_TABLE:' in rank0 and 'MPI_Abort(MPI_COMM_WORLD' in rank0
        criteria={'nonzero_launcher_return':returncode!=0,'not_timed_out':not timed_out,
                  'expected_loader_error_and_abort_on_rank0':expected_seen,
                  'two_rank_error_logs_present':all(f'rsl.error.{r:04d}' in ranklogs for r in (0,1)),
                  'no_manual_cleanup_required':not before_cleanup,
                  'no_orphan_rank_after_run':not remaining}
        result={'case':name,'command':cmd,'timeout_seconds':TIMEOUT,'returncode':returncode,
                'timed_out':timed_out,'elapsed_seconds':elapsed,'remaining_before_cleanup':before_cleanup,
                'cleanup_actions':cleanup,'remaining_after_cleanup':remaining,'expected_error_substring':expected,
                'criteria':criteria,'status':'PASS' if all(criteria.values()) else 'FAIL',
                'launcher_log_sha256':digest(launcher_log),'rank_logs':{k:{'sha256':v['sha256'],'tail':v['text'][-4000:]} for k,v in ranklogs.items()},
                'private_assets':{'coefficients':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted((case/'coefficients').iterdir())},
                                  'frozen_table_path':str(case/'coefficients/frozen-ice-psd-moments.nc'),
                                  'frozen_table_exists':(case/'coefficients/frozen-ice-psd-moments.nc').exists(),
                                  'frozen_table_sha256':digest(case/'coefficients/frozen-ice-psd-moments.nc') if (case/'coefficients/frozen-ice-psd-moments.nc').exists() else None}}
        (case/'run-receipt.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        cases.append(result)
        print(json.dumps({'case':name,'status':result['status'],'returncode':returncode,'timeout':timed_out,
                          'elapsed_seconds':elapsed,'remaining_before_cleanup':before_cleanup,'cleanup_actions':cleanup},sort_keys=True),flush=True)
    shared_after={n:digest(DATA/n) for n in COEFFS}
    run={'schema':'WRF_MPI_FROZEN_TABLE_FAILURE_RUN_V1','status':'PASS' if all(c['status']=='PASS' for c in cases) else 'FAIL',
         'source_commit':pre['source_commit'],'executable_sha256_before_after':[pre['executable_sha256'],digest(EXE)],
         'checkpoint_sha256_before_after':[pre['checkpoint_sha256'],digest(CHECKPOINT)],
         'frozen_table_source_sha256_before_after':[pre['frozen_table_source_sha256'],digest(TABLE)],
         'shared_coeff_hashes_before':shared_before,'shared_coeff_hashes_after':shared_after,
         'shared_assets_unchanged':shared_before==shared_after,'cases':cases}
    (BUNDLE/'run-results.json').write_text(json.dumps(run,indent=2,sort_keys=True)+'\n')
    return 0 if run['status']=='PASS' and run['shared_assets_unchanged'] else 1

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(f'collective probe runner failed: {exc}',file=sys.stderr);raise
