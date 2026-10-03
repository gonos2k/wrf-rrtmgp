from pathlib import Path
import argparse,json,re,subprocess
ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,required=True);ap.add_argument('--log',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
elf=subprocess.check_output(['readelf','-h',str(a.exe)],text=True)
pie=bool(re.search(r'Type:\s+DYN',elf))
symbols={}
for line in subprocess.check_output(['nm','-an',str(a.exe)],text=True).splitlines():
 fields=line.split()
 if len(fields)==3 and '._omp_fn.' in fields[2]:symbols[int(fields[0],16)]=fields[2]
rows=[];groups={};starts={}
for line in a.log.read_text().splitlines():
 fields=line.split();row={'event':fields[0]}
 row.update({k:int(v,16) if v.startswith('0x') else int(v) for k,v in [s.split('=',1) for s in fields[1:]]})
 address=row['callback']-row['base'] if pie else row['callback']
 row['symbol']=symbols.get(address,'unresolved')
 if '__module_radiation_driver_MOD_radiation_driver._omp_fn.' in row['symbol']:
  rows.append(row);g=groups.setdefault(row['symbol'],{'workers':set(),'teams':set(),'events':{'ENTER':0,'EXIT':0},'worker_cpu_ns':{}})
  g['workers'].add(row['worker']);g['teams'].add(row['team']);g['events'][row['event']]+=1
  key=(row['pid'],row['tid'],row['callback'])
  if row['event']=='ENTER':starts[key]=row['cpu_ns']
  elif key in starts:
   worker=row['worker'];g['worker_cpu_ns'][worker]=g['worker_cpu_ns'].get(worker,0)+row['cpu_ns']-starts.pop(key)
for name,g in groups.items():
 disassembly=subprocess.check_output(['objdump','-d','--disassemble='+name,str(a.exe)],text=True)
 g['contains_lw_and_sw_calls']='__module_ra_rrtmg_lw_MOD_rrtmg_lwrad' in disassembly and '__module_ra_rrtmg_sw_MOD_rrtmg_swrad' in disassembly
result={'executable':str(a.exe),'log':str(a.log),'pie':pie,'radiation_callbacks':{n:{'workers':sorted(g['workers']),'teams':sorted(g['teams']),'events':g['events'],'worker_cpu_ns':g['worker_cpu_ns'],'contains_lw_and_sw_calls':g['contains_lw_and_sw_calls']} for n,g in groups.items()},'radiation_records':rows,'verified_two_radiation_workers':any(g['contains_lw_and_sw_calls'] and g['workers']=={0,1} and g['teams']=={2} and g['events']['ENTER']==g['events']['EXIT'] and all(g['worker_cpu_ns'].get(i,0)>1000000 for i in (0,1)) for g in groups.values())}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='radiation_records'},indent=2))
if not result['verified_two_radiation_workers']:raise SystemExit(1)
