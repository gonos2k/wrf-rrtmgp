"""Run one separately frozen saved-data reader; never launch a model/build."""
from pathlib import Path
import argparse, hashlib, json, os, signal, subprocess, sys, time

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for data in iter(lambda: f.read(1048576), b''):
            h.update(data)
    return h.hexdigest()

def write(p, obj, mode='x'):
    with p.open(mode) as f:
        json.dump(obj, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--authorization', required=True, type=Path)
    a = ap.parse_args()
    auth = json.loads(a.authorization.read_text())
    assert auth['scope'] == 'ONE_SAVED_DATA_COUPLING_RECORD_AUDIT_NO_MODELS'
    assert auth['max_invocations'] == 1
    for field in ['plan', 'reader', 'review', 'runner']:
        item = auth[field]
        assert sha(ROOT/item['path']) == item['sha256'], field
    assert (ROOT/auth['runner']['path']).resolve() == Path(__file__).resolve()
    # The author-reviewed command explicitly includes the output arguments.
    argv = auth['argv']
    assert argv[:3] == ['/usr/bin/python3', '-I', '-S']
    assert Path(argv[3]).resolve() == (ROOT/auth['reader']['path']).resolve()
    out = ROOT/auth['output_dir']
    out.mkdir(exist_ok=False)
    write(out/'authorization.json',auth)
    write(out/'launch.json',dict(argv=argv,cwd=str(ROOT),started_epoch=time.time(),
          parent_PID=os.getpid(),timeout_seconds=auth['timeout_seconds']))
    start=time.time(); timed_out=False; wait_exception=None
    def terminate_and_reap(child):
        for sig in [signal.SIGTERM, signal.SIGKILL]:
            try:os.killpg(child.pid,sig)
            except ProcessLookupError:pass
            try:
                child.wait(timeout=5)
                return True
            except subprocess.TimeoutExpired:pass
        return child.poll() is not None
    with (out/'stdout.log').open('wb') as stdout, (out/'stderr.log').open('wb') as stderr:
        try:
            child=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr,start_new_session=True)
        except BaseException as exc:
            write(out/'execution.json',dict(schema='UDM37_SAVED_COUPLING_READER_EXECUTION_V1',
                status='SPAWN_FAILED_NO_CONFIRMED_CHILD',actual_child_RC=None,
                confirmed_child_invocations=0,spawn_exception=repr(exc),argv=argv,cwd=str(ROOT),
                start_epoch=start,end_epoch=time.time(),WRF_REAL_RTE_LNFL_LBLRTM_builds_or_models=0))
            print(json.dumps(dict(status='SPAWN_FAILED_NO_CONFIRMED_CHILD',exception=repr(exc))))
            return 1
        try:
            child.wait(timeout=auth['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timed_out=True;terminate_and_reap(child)
        except BaseException as exc:
            wait_exception=repr(exc);terminate_and_reap(child)
    # Actual terminal RC is durable BEFORE any numerical report is opened.
    execution=dict(schema='UDM37_SAVED_COUPLING_READER_EXECUTION_V1',
         status='TERMINAL' if child.poll() is not None else 'TERMINATION_PENDING_REQUIRES_LIVE_HANDLE_CHECK',
         actual_child_RC=child.returncode,timed_out=timed_out,child_PID=child.pid,
         wait_exception=wait_exception,confirmed_child_invocations=1,
         argv=argv,cwd=str(ROOT),start_epoch=start,end_epoch=time.time(),
         WRF_REAL_RTE_LNFL_LBLRTM_builds_or_models=0)
    write(out/'execution.json',execution)
    if child.returncode != 0 or timed_out or wait_exception is not None:
        print(json.dumps(execution));return 1
    outputs=[]
    for p in out.iterdir():
        if p.is_file():outputs.append(dict(name=p.name,sha256=sha(p),size_bytes=p.stat().st_size))
    write(out/'postflight.json',dict(status='READER_RC0_OUTPUTS_INVENTORIED',
          execution_sha256=sha(out/'execution.json'),outputs=outputs))
    print(json.dumps(dict(actual_child_RC=child.returncode,output_dir=str(out))))
    return 0

if __name__=='__main__':
    sys.exit(main())
