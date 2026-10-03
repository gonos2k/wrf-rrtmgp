set pagination off
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
pathlib.Path('../actual-inferior-evidence.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print('FRAME_EVIDENCE '+json.dumps({k:result[k] for k in ['before_fault_rip','before_fault_rsp','frame_delta_bytes','frame_delta_mib']},sort_keys=True))
end
x/i $rip
info registers rsp rbp rdi
kill
quit
