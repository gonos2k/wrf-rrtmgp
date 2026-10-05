#!/usr/bin/env python3
"""Six immutable BON LW columns; direct library, no WRF or adapter invocation."""
import hashlib, importlib.util, json, os, re, resource, subprocess, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent

def pin(p):
    p = Path(p)
    return dict(path=str(p.absolute()), sha256=hashlib.sha256(p.read_bytes()).hexdigest(), size_bytes=p.stat().st_size)

def check(p):
    q = pin(p['path'])
    assert q['sha256'] == p['sha256'] and q['size_bytes'] == p['size_bytes'], p['path']
    return q

def write(p, data):
    tmp = p.with_suffix('.temporary')
    with tmp.open('w') as f:
        json.dump(data, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, p)

def snapshot(inv, env):
    roster = [inv[n] for n in ['executable','build_receipt','compiled_source_file','current_source_file','comparison_helper','runtime_table']]
    roster += inv['receipt_source_pin_manifest'] + inv['receipt_runtime_libraries'] + inv['coefficient_files']
    for c in inv['cases']: roster += [c[n] for n in ['input','raw','result']]
    closure = subprocess.run(['/usr/bin/ldd',inv['executable']['path']], env=env, text=True, capture_output=True, check=True)
    assert 'not found' not in closure.stdout
    paths = {str(Path(x).resolve()) for x in re.findall(r'(?:=>\s*)?(/[^\s()]+)',closure.stdout)}
    expected = {str(Path(x['path']).resolve()) for x in inv['receipt_runtime_libraries']}
    # The historical roster excludes the ELF interpreter, unlike the full ldd readback.
    loader = str(Path('/lib64/ld-linux-x86-64.so.2').resolve())
    assert paths == expected | {loader}, {'extra':sorted(paths-expected),'missing':sorted(expected-paths)}
    return {'files':[check(p) for p in roster], 'ldd_resolved_paths':sorted(paths),
            'ELF_interpreter_additional_current_pin':pin(loader)}

def main():
    inv=json.loads((HERE/'inventory.json').read_text()); plan=json.loads((HERE/'plan.json').read_text())
    auth=json.loads((HERE/'root-execution-authorization.json').read_text())
    assert auth['inventory_sha256']==pin(HERE/'inventory.json')['sha256']
    assert auth['plan_sha256']==pin(HERE/'plan.json')['sha256']
    assert auth['runner_sha256']==pin(__file__)['sha256'] and auth['maximum_solver_calls']==6
    assert len(inv['cases'])==len(plan['proposed_invocations'])==6
    receipt=json.loads(Path(inv['build_receipt']['path']).read_text())
    assert receipt['status']=='BUILD_PASS' and receipt['build_returncode']==0 and receipt['executable']==inv['executable']
    for phase in ['preflight_pins','postflight_pins']:
        actual=next(p for p in receipt[phase]['source_files'] if p['path'].endswith('/reference_column.f90'))
        assert actual==inv['compiled_source_file']
    assert inv['compiled_source_file']['sha256']==inv['current_source_file']['sha256']
    assert inv['runtime_table']['sha256']=='8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583'
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','LD_LIBRARY_PATH':receipt['environment']['LD_LIBRARY_PATH'],
         'LANG':'C','LC_ALL':'C','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
         'WRF_RRTMGP_FROZEN_TABLE':inv['runtime_table']['path']}
    before=snapshot(inv,env)
    out=HERE/'run-v1'; out.mkdir()
    lock=os.open(str(out/'ONE_USE'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(lock)
    spec=importlib.util.spec_from_file_location('bon_replay_compare',inv['comparison_helper']['path'])
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    rec={'schema':'bon-night-independent-direct-replay-v1','status':'RUNNING','actual_solver_invocations':0,
         'WRF_REAL_build_invocations':0,'authorization':pin(HERE/'root-execution-authorization.json'),
         'inventory':pin(HERE/'inventory.json'),'plan':pin(HERE/'plan.json'),'runner':pin(__file__),
         'before':before,'environment':env,'calls':[],'started_unix':time.time()}
    dest=out/'execution.json';write(dest,rec)
    soft,hard=resource.getrlimit(resource.RLIMIT_STACK)
    assert hard==resource.RLIM_INFINITY or hard>=512*1024**2
    def stack():resource.setrlimit(resource.RLIMIT_STACK,(512*1024**2,hard))
    try:
        for c,planned in zip(inv['cases'],plan['proposed_invocations']):
            assert c['case_id']==planned['case_id'] and planned['timeout_seconds']==180
            result=out/(c['case_id']+'.result'); log=out/(c['case_id']+'.log')
            argv=[inv['executable']['path'],inv['data_dir'],c['input']['path'],str(result),'1','']
            assert argv[:3]==planned['argv'][:3] and planned['argv'][4:]==argv[4:]
            a={'case_id':c['case_id'],'argv':argv,'started_unix':time.time(),'input':c['input'],'production':c['result']}
            rec['calls'].append(a)
            with log.open('xb') as f:
                p=subprocess.Popen(argv,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,preexec_fn=stack)
                rec['actual_solver_invocations']+=1;a['pid']=p.pid;write(dest,rec)
                try:a['returncode']=p.wait(timeout=180);a['timed_out']=False
                except subprocess.TimeoutExpired:p.kill();a['returncode']=p.wait();a['timed_out']=True
            a['ended_unix']=time.time();a['log']=pin(log);write(dest,rec)
            assert a['returncode']==0 and not a['timed_out'],a
            a['result']=pin(result)
            actual=helper.read_result(Path(c['result']['path'])); reference=helper.read_result(result)
            comp=helper.compare(actual,reference); comp['production_only_sections']=sorted(set(actual['sections'])-set(reference['sections']))
            comp['reference_only_sections']=sorted(set(reference['sections'])-set(actual['sections']))
            write(out/(c['case_id']+'-comparison.json'),comp);a['comparison']=pin(out/(c['case_id']+'-comparison.json'))
            a['passed']=comp['passed'];write(dest,rec)
            assert comp['passed'],comp['failed_sections']
        rec['after']=snapshot(inv,env);assert rec['before']==rec['after']
        rec['status']='PASS_SIX_DIRECT_LIBRARY_REPLAYS'
    except Exception as exc:
        rec['status']='FAIL_STOPPED_NO_RETRY';rec['error']=str(exc);raise
    finally:
        rec['ended_unix']=time.time();write(dest,rec)
        print(json.dumps({'status':rec['status'],'actual_solver_invocations':rec['actual_solver_invocations'],'receipt':pin(dest)}))

if __name__=='__main__':main()
