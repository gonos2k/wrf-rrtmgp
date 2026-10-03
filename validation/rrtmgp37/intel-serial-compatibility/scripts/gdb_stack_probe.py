#!/usr/bin/env python3
"""Stop the exact failed binary before integration; read stack/frame, then kill."""
import hashlib,json,os,pathlib,resource,shutil,signal,subprocess,time
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
CASE=ROOT/'build/udm-workspace-intel-runtime/gdb-solve-entry'
RUN=CASE/'run'
PREVIOUS=ROOT/'build/udm-workspace-intel-runtime/ra37-stack512-v2'
assert not CASE.exists(),'fresh case required'
RUN.mkdir(parents=True)
prior=json.loads((PREVIOUS/'receipt.json').read_text())
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
for name,h in prior['inputs_before'].items():
 shutil.copy2(PREVIOUS/'run'/name,RUN/name);assert sha(RUN/name)==h
inv=json.loads((ROOT/'build/udm-intel-feasibility/inventory-probe-receipt.json').read_text());env=os.environ.copy();env.update(inv['controlled_environment']);env['OPENBLAS_NUM_THREADS']='1'
for key in list(env):
 if key.startswith('WRF_RRTMGP_') or key=='WRF_UDM_BOUNDARY_CAPTURE':env.pop(key)
resource.setrlimit(resource.RLIMIT_STACK,(512*1024*1024,resource.getrlimit(resource.RLIMIT_STACK)[1]))
cmd='''set pagination off
set confirm off
set language c
set startup-with-shell off
set disable-randomization off
break *0xf2d090
run
python
import gdb, json, pathlib
result={}
inferior=gdb.selected_inferior()
result['pid']=inferior.pid
result['actual_inferior_proc_limits']=pathlib.Path('/proc/'+str(inferior.pid)+'/limits').read_text()
result['actual_inferior_proc_status']=pathlib.Path('/proc/'+str(inferior.pid)+'/status').read_text()
result['actual_executable']=str(pathlib.Path('/proc/'+str(inferior.pid)+'/exe').resolve())
result['entry_rsp']=int(gdb.parse_and_eval('$rsp'))
result['entry_rip']=int(gdb.parse_and_eval('$rip'))
grid=int(gdb.parse_and_eval('$rdi'))
result['grid_pointer']=grid
bounds={}
for name,offset in [('sm31',0x51348),('em31',0x5134c),('sm32',0x51350),('em32',0x51354),('sm33',0x51358),('em33',0x5135c)]:
 bounds[name]=int(gdb.parse_and_eval('*(int*)'+hex(grid+offset)))
result['grid_bounds_from_actual_pointer']=bounds
result['memory_extents']=[bounds['em31']-bounds['sm31']+1,bounds['em32']-bounds['sm32']+1,bounds['em33']-bounds['sm33']+1]
counts={}
for name in ['num_moist','num_dfi_moist','num_scalar','num_dfi_scalar','num_tracer','num_chem']:
 counts[name]=int(gdb.parse_and_eval('*(int*)&module_state_description_mp_'+name+'_'))
result['actual_global_counts']=counts
gdb.execute('set $entry_rsp=$rsp')
print('ENTRY_EVIDENCE '+json.dumps(result,sort_keys=True))
end
break *0xf2d65b
continue
python
result['before_fault_rsp']=int(gdb.parse_and_eval('$rsp'))
result['before_fault_rip']=int(gdb.parse_and_eval('$rip'))
result['frame_delta_bytes']=result['entry_rsp']-result['before_fault_rsp']
result['frame_delta_mib']=result['frame_delta_bytes']/1024/1024
result['before_fault_proc_maps']=pathlib.Path('/proc/'+str(gdb.selected_inferior().pid)+'/maps').read_text()
pathlib.Path('../actual-inferior-evidence.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\\n')
print('FRAME_EVIDENCE '+json.dumps({k:result[k] for k in ['before_fault_rip','before_fault_rsp','frame_delta_bytes','frame_delta_mib']},sort_keys=True))
end
x/i $rip
info registers rsp rbp rdi
kill
quit
'''
(CASE/'commands.gdb').write_text(cmd)
argv=['gdb','--batch','-x',str(CASE/'commands.gdb'),'--args','./wrf.exe']
started=time.monotonic();timed_out=False
with (CASE/'gdb.log').open('wb') as f:
 proc=subprocess.Popen(argv,cwd=RUN,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 try:proc.wait(timeout=120)
 except subprocess.TimeoutExpired:
  timed_out=True;os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
after={n:sha(RUN/n) for n in prior['inputs_before']}
receipt=dict(status='ENTRY_ONLY_PROBE_PASS' if proc.returncode==0 and not timed_out and (CASE/'actual-inferior-evidence.json').is_file() else 'FAIL',argv=argv,returncode=proc.returncode,timed_out=timed_out,elapsed_s=time.monotonic()-started,launcher_sha256=sha(__file__),gdb_commands_sha256=sha(CASE/'commands.gdb'),gdb_log_sha256=sha(CASE/'gdb.log'),controlled_environment=inv['controlled_environment'],parent_stack_limit_bytes=resource.getrlimit(resource.RLIMIT_STACK),inputs_before=prior['inputs_before'],inputs_after=after,inputs_unchanged=after==prior['inputs_before'],exact_failed_binary_sha256=sha(RUN/'wrf.exe'),integration_executed=False,inferior_terminated_by_debugger=True)
if (CASE/'actual-inferior-evidence.json').is_file():receipt['actual_inferior_evidence_sha256']=sha(CASE/'actual-inferior-evidence.json')
(CASE/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(receipt['status'],CASE/'receipt.json')
