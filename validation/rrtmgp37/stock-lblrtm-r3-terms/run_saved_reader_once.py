import hashlib,json,os,subprocess,time
from pathlib import Path
D=Path(__file__).resolve().parent
run=D.parent/'udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1'
assert json.loads((run/'execution.json').read_text())['actual_child_returncode']==0
assert (run/'postflight.json').is_file()
assert not (D/'reader-execution.json').exists()
cmd=['/usr/bin/python3','-I','-S',str(D/'analyze_r3_terms.py')]
start=time.time()
with (D/'reader-stdout.log').open('xb') as a,(D/'reader-stderr.log').open('xb') as b:
 c=subprocess.Popen(cmd,stdout=a,stderr=b)
 rc=c.wait()
with (D/'reader-execution.json').open('x') as f:
 json.dump({'actual_child_returncode':rc,'command':cmd,'started_epoch':start,'ended_epoch':time.time(),'reader_source_sha256':hashlib.sha256((D/'analyze_r3_terms.py').read_bytes()).hexdigest(),'model_build_or_solver_invocations':0},f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
print('actual reader RC',rc)
raise SystemExit(rc)
