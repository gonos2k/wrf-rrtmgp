"""One generation + one stock official-example solve; save RC before inventory."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PREP = Path(__file__).resolve().parent

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def save(p, x):
    with p.open('x') as f:
        json.dump(x, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())

def verify(spec):
    p = ROOT / spec['path']
    assert p.is_file() and p.stat().st_size == spec['bytes'], str(p)
    assert digest(p) == spec['sha256'], str(p)
    return p

def run(exe, cwd, env, label):
    start = time.time()
    child = None
    rc = None
    timed_out = False
    exception = None
    with (cwd / 'stdout.log').open('xb') as so, (cwd / 'stderr.log').open('xb') as se:
        try:
            child = subprocess.Popen([str(exe)], cwd=cwd, env=env,
                                     stdout=so, stderr=se, start_new_session=True)
            save(cwd / 'launch.json', {'pid':child.pid, 'start_unix':start,
                 'executable':str(exe), 'cwd':str(cwd), 'timeout_seconds':1200})
            rc = child.wait(timeout=1200)
        except BaseException as e:
            timed_out = isinstance(e, subprocess.TimeoutExpired)
            exception = {'type':type(e).__name__, 'message':str(e)}
            if child is not None:
                rc = child.poll()
                for sig in [signal.SIGTERM, signal.SIGKILL]:
                    if rc is not None:
                        break
                    try:
                        os.killpg(child.pid, sig)
                    except ProcessLookupError:
                        pass
                    try:
                        rc = child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        rc = child.poll()
        so.flush(); se.flush(); os.fsync(so.fileno()); os.fsync(se.fileno())
    receipt = {'label':label, 'actual_child_RC':rc, 'timeout':timed_out,
               'pid':child.pid if child else None, 'start_unix':start,
               'end_unix':time.time(), 'exception':exception,
               'status':'SPAWN_FAILED' if child is None else
                        'REAP_PENDING' if rc is None else 'TERMINAL'}
    # No output inventory or next process until an actual terminal RC is saved.
    save(cwd / 'execution.json', receipt)
    if rc is None or exception is not None:
        return receipt
    inventory = {}
    for p in sorted(cwd.iterdir()):
        if p.is_file() and not p.is_symlink():
            inventory[p.name] = {'bytes':p.stat().st_size, 'sha256':digest(p)}
    save(cwd / 'output-inventory.json', inventory)
    return receipt

def main():
    plan = json.loads((PREP / 'plan-v3.json').read_text())
    auth = json.loads((PREP / 'authorization-v3.json').read_text())
    assert auth['plan_sha256'] == digest(PREP / 'plan-v3.json')
    assert auth['runner_sha256'] == digest(Path(__file__))
    assert auth['max_LNFL_invocations'] == 1 and auth['max_LBLRTM_invocations'] == 1
    # Existing directory is a used-run marker: no retries or overwrite.
    out = ROOT / plan['output_directory']
    out.mkdir(exist_ok=False)
    save(out / 'authorization-v3.json', auth)
    paths = {k: verify(v) for k,v in plan['inputs'].items()}
    before = {k: {'size':p.stat().st_size, 'mtime_ns':p.stat().st_mtime_ns}
              for k,p in paths.items()}
    save(out / 'preflight.json', {'status':'PINNED_INPUTS_VERIFIED',
          'inputs':plan['inputs'], 'stats':before, 'plan_sha256':digest(PREP/'plan-v3.json')})
    env = os.environ.copy()
    env.update(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C',
               LD_LIBRARY_PATH=str(ROOT/'build/deps/netcdf/lib'))
    lnfl = out / 'lnfl'; lnfl.mkdir()
    shutil.copyfile(paths['lnfl_TAPE5'], lnfl/'TAPE5')
    (lnfl/'TAPE1').symlink_to(paths['aer_lines'])
    for name in plan['broadening_inputs']:
        shutil.copyfile(paths[name], lnfl/name)
    r1 = run(paths['lnfl_executable'], lnfl, env, 'LNFL_OFFICIAL_IR_DECK')
    if r1['actual_child_RC'] != 0 or r1['timeout'] or r1['exception'] is not None:
        save(out/'terminal.json', {'status':'GENERATION_FAILED','LNFL':r1,
             'LBLRTM_invocations':0})
        return 1
    tape3 = lnfl/'TAPE3'
    assert tape3.is_file() and tape3.stat().st_size > 0
    tape3_before = {'bytes':tape3.stat().st_size,'sha256':digest(tape3)}
    case = out / 'lblrtm'; case.mkdir()
    shutil.copyfile(paths['lblrtm_TAPE5'], case/'TAPE5')
    shutil.copyfile(paths['continuum'], case/'absco-ref_wv-mt-ckd.nc')
    (case/'TAPE3').symlink_to(tape3)
    r2 = run(paths['lblrtm_executable'], case, env, 'STOCK_OFFICIAL_BUILT_IN_ATMOSPHERE')
    if r2['actual_child_RC'] != 0 or r2['timeout'] or r2['exception'] is not None:
        save(out/'terminal.json', {'status':'SOLVER_FAILED_OR_REAP_PENDING',
             'LNFL':r1,'LBLRTM':r2,'new_WRF_runs':0,'new_compiles':0})
        return 1
    assert tape3_before == {'bytes':tape3.stat().st_size,'sha256':digest(tape3)}
    after = {k: {'size':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}
             for k,p in paths.items()}
    assert before == after, 'Original asset stats changed'
    save(out/'terminal.json', {'status':'TERMINAL_RC0_COMPARISON_PENDING'
         if r2['actual_child_RC']==0 and not r2['timeout'] and r2['exception'] is None else 'SOLVER_FAILED',
         'LNFL':r1,'LBLRTM':r2,'generated_TAPE3':tape3_before,
         'original_asset_stats_unchanged':True,'new_WRF_runs':0,'new_compiles':0})
    return 0 if r2['actual_child_RC']==0 and not r2['timeout'] and r2['exception'] is None else 1

if __name__ == '__main__':
    sys.exit(main())
