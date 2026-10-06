import hashlib,json,os,subprocess,time
from pathlib import Path
D=Path(__file__).resolve().parent
plan=json.loads((D/'build-plan.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
review=D.parent/'udm37-lblrtm-panel-trace-preflight-review-v1/review.json'
assert sha(review)=='f6c0a4b9d65b67a49094d2a29cdbc853617d68087f206b6b9507c415a2c3126b'
assert sha(Path(plan['source_original_path']))==plan['source_original_sha256']
assert sha(Path(plan['source_trace_path']))==plan['source_trace_sha256']
assert not (D/'build-launch.json').exists()
exe=D/'source/LBLRTM/lblrtm_v12.17_linux_gnu_dbl';exe.unlink()
obj=D/'source/LBLRTM/build/lblrtm_v12.17_linux_gnu_dbl.obj'
for x in plan['copied_objects_before']:assert sha(obj/x['file'])==x['sha256']
env={'HOME':os.environ['HOME'],'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','LD_LIBRARY_PATH':str(D.parent/'deps/netcdf/lib')}
def save(p,d):
 with p.open('x') as f:json.dump(d,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
start=time.time();cmd=plan['build_command']
with (D/'build-stdout.log').open('xb') as a,(D/'build-stderr.log').open('xb') as b:
 child=subprocess.Popen(cmd,cwd=plan['build_cwd'],env=env,stdout=a,stderr=b,start_new_session=True)
 save(D/'build-launch.json',{'command':cmd,'pid':child.pid,'started_epoch':start,'plan_sha256':sha(D/'build-plan.json'),'review_sha256':sha(review),'HOME_inherited':True})
 rc=child.wait()
# Write actual RC before inspecting build output, executable, or log.
save(D/'build-execution.json',{'actual_child_returncode':rc,'started_epoch':start,'ended_epoch':time.time(),'command':cmd,'compile_build_invocations':1,'solver_invocations':0})
print('actual build RC',rc)
if rc:raise SystemExit(rc)
assert exe.is_file();assert sha(exe)!='a5c363c87a44b686e8bff1cf0e60fcfb7b0e167c8ec74d0201b6cc6b2b41473b'
changed=[x['file'] for x in plan['copied_objects_before'] if sha(obj/x['file'])!=x['sha256']]
assert changed==['oprop.o'],changed
save(D/'build-postflight.json',{'status':'TRACE_BINARY_COMPILED_INCREMENTAL_OPROP_ONLY','changed_objects':changed,'executable':{'path':str(exe),'sha256':sha(exe),'size_bytes':exe.stat().st_size},'stock_source_still_exact':sha(Path(plan['source_original_path']))==plan['source_original_sha256'],'source_trace_sha256':sha(Path(plan['source_trace_path'])),'actual_child_returncode':0})
print('new trace binary SHA',sha(exe))
