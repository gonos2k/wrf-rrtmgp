#!/usr/bin/env python3
import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
authpath=root/'build/udm37-lblrtm-candidate-decision-reader-authorization-v2.json'
def check(pin):
 p=Path(pin['path']);assert p.stat().st_size==pin['size_bytes'];assert hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
auth=json.loads(authpath.read_text())
for key in ('plan','reader','root_static_review','independent_static_review','build_execution','build_postflight','solver_postflight','build_plan','build_runner','source','executable','candidate_execution'): check(auth[key])
e=json.loads(Path(auth['candidate_execution']['path']).read_text());assert e['actual_child_returncode']==0 and e['reaped'] is True and e['timed_out'] is False and e['exception'] is None
receipt=root/'build/udm37-lblrtm-candidate-decision-reader-outer-execution-v2.json'
assert not receipt.exists()
cmd=[sys.executable,'-B',auth['reader']['path'],'--authorization',str(authpath)]
start=time.time();p=None;rc=None;timeout=False;error=None;out=b'';err=b''
try:
 p=subprocess.Popen(cmd,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 try:out,err=p.communicate(timeout=180)
 except subprocess.TimeoutExpired:
  timeout=True;os.killpg(p.pid,signal.SIGTERM)
  try:out,err=p.communicate(timeout=10)
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate(timeout=10)
 rc=p.returncode
except BaseException as exc:error=type(exc).__name__+': '+str(exc)
finally:
 d={'status':'TERMINAL' if rc is not None else 'NOT_REAPED','command':cmd,'cwd':str(root),'pid':p.pid if p else None,'actual_child_returncode':rc,'timed_out':timeout,'exception':error,'reaped':rc is not None,'start_epoch':start,'end_epoch':time.time(),'stdout_bytes':len(out),'stderr_bytes':len(err)}
 with receipt.open('x') as f:json.dump(d,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 (receipt.parent/'reader-stdout-v2.txt').write_bytes(out);(receipt.parent/'reader-stderr-v2.txt').write_bytes(err)
 print(json.dumps(d),flush=True)
if rc is None or timeout or error:sys.exit(2)
sys.exit(rc)
