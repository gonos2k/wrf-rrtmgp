#!/usr/bin/env python3
"""Exercise all six durable counter transitions with a fake child only."""
import importlib.util, json, tempfile
from pathlib import Path
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
RUNNER=ROOT/'build/udm37-cf0-material-anchor-continuation-v3/continue_six.py'
spec=importlib.util.spec_from_file_location('continuation_under_test',RUNNER)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
core=mod.load_base()
class FakeChild:
    pid=987654321
    returncode=0
    def wait(self,timeout=None): return 0
    def poll(self): return 0
original=core.subprocess.Popen
with tempfile.TemporaryDirectory(prefix='cf0-counter-') as td:
    tmp=Path(td); core.RUN=tmp; core.OUT=tmp/'outputs'; core.LOG=tmp/'logs'
    state={'solver_invocations':0,'new_solver_invocations':0,
           'reused_solver_invocations':2,'total_completed_or_reused_calls':2,
           'calls':[{'call_id':f'mock-{i}','status':'NOT_STARTED'} for i in range(6)]}
    core.atomic(tmp/'execution.json',state)
    core.subprocess.Popen=lambda *a,**k: FakeChild()
    try:
        for i in range(6):
            case={'call_id':f'mock-{i}','log':str(core.LOG/f'{i}.log'),
                  'output':str(core.OUT/f'{i}.result')}
            rc,timed=core.launch(case,['mock-executable'],state,i)
            assert (rc,timed)==(0,False)
            during=json.loads((tmp/'execution.json').read_text())
            assert during['solver_invocations']==i+1
            assert during['new_solver_invocations']==i+1
            assert during['total_completed_or_reused_calls']==2+i
            state['calls'][i]['status']='CALL_VALIDATED'
            # This models the continuation's post-validation atomic write.
            core.atomic(tmp/'execution.json',state)
            after=json.loads((tmp/'execution.json').read_text())
            assert after['new_solver_invocations']==i+1
            assert after['total_completed_or_reused_calls']==3+i
    finally:
        core.subprocess.Popen=original
    final=json.loads((tmp/'execution.json').read_text())
    assert final['solver_invocations']==6
    assert final['new_solver_invocations']==6
    assert final['reused_solver_invocations']==2
    assert final['total_completed_or_reused_calls']==8
print('PASS six mocked launch/validation transitions persist counters through terminal 6 new + 2 reused; no solver process started')
