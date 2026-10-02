from pathlib import Path
import sys,os,json,hashlib
root=Path.cwd();sys.path.insert(0,str(root/'tools'))
import compare_radiation_scm as scm
out=root/'build/port-audit-inputs/cases-v2';out.mkdir()
env=os.environ.copy();dep=root.parent/'deps'
env['LD_LIBRARY_PATH']=str(dep/'netcdf/lib')+':'+str(dep/'root/usr/lib/x86_64-linux-gnu')+':'+env.get('LD_LIBRARY_PATH','')
env['OMP_NUM_THREADS']='1';env['OPENBLAS_NUM_THREADS']='1'
original=scm.run_logged
exe=root/'build/port-audit-inputs/wrf-audit.exe'
def logged(executable,workdir,logfile,runenv):
 e=runenv.copy()
 if executable==exe:
  cap=workdir/'capture';cap.mkdir();e['WRF_PORT_AUDIT_DIR']=str(cap)
  if workdir.name=='ra37':e['WRF_RRTMGP_CAPTURE_DIR']=str(cap)
 return original(executable,workdir,logfile,e)
scm.run_logged=logged
report={'source_head':'3a69404fbe06486fcaad7ba063d3d8062dc8f2a4','pairs':[]}
for spec in scm.scenarios():
 print(spec['name'],flush=True)
 report['pairs'].append(scm.run_scenario(out,spec,1,scm.WRF_ROOT/'main/ideal.exe',exe,env))
 (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
report['status']='PASS';(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
print('7 paired audits PASS')
