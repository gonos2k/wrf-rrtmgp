from pathlib import Path
import sys,os,json,shutil
root=Path.cwd();sys.path.insert(0,str(root/'tools'));import compare_radiation_scm as scm
out=root/'build/port-audit-inputs/controls';out.mkdir()
deps=root.parent/'deps';env=os.environ.copy();env['LD_LIBRARY_PATH']=str(deps/'netcdf/lib')+':'+str(deps/'root/usr/lib/x86_64-linux-gnu')+':'+env.get('LD_LIBRARY_PATH','');env['OMP_NUM_THREADS']='1';env['OPENBLAS_NUM_THREADS']='1'
exe=root/'build/port-audit-inputs/wrf-audit.exe';receipt={'binary_sha256':scm.sha256(exe),'cases':[]}
for spec in scm.scenarios():
 for mode in ['clear','allcloud']:
  for option in [4,37]:
   case=out/spec['name']/mode/f'ra{option}'
   text=scm.set_clock(scm.configured_namelist(spec['mp_physics'],option,spec['overlap'],1),0,10)
   scm.create_case(case,text)
   initial=root/'build/port-audit-inputs/cases-v2'/spec['name']/'initial/wrfinput_d01'
   scm.copy_initial_state(initial,case/'wrfinput_d01',option)
   cap=case/'capture';cap.mkdir();e=env.copy();e['WRF_PORT_AUDIT_DIR']=str(cap);e['WRF_PORT_AUDIT_MODE']=mode
   if option==37:e['WRF_RRTMGP_CAPTURE_DIR']=str(cap)
   r=scm.run_logged(exe,case,'wrf.log',e)
   if r['returncode'] or 'SUCCESS COMPLETE WRF' not in (case/'wrf.log').read_text():raise RuntimeError(str(case))
   validation=scm.validate_case(case,option)
   receipt['cases'].append({'scenario':spec['name'],'mode':mode,'option':option,'log':r,'state_validation':'PASS'})
  print(spec['name'],mode,'PASS',flush=True)
receipt['status']='PASS';(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
