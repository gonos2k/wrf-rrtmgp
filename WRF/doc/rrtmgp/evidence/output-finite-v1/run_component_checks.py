#!/usr/bin/env python3
import os,json,hashlib,subprocess,datetime
from pathlib import Path
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
H=ROOT/'build/udm37-output-finite-components-v1'
S=ROOT/'build/udm37-output-finite-pr-work'
R=H/'component-receipt.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(v):
 q=R.with_suffix('.tmp');q.write_text(json.dumps(v,indent=2)+'\n');os.replace(q,R)
paths=['WRF/phys/module_ra_rrtmgp.F','WRF/test/rrtmgp/CMakeLists.txt','WRF/test/rrtmgp/test_columns.f90','WRF/test/rrtmgp/test_sw_predelta_direct.f90','WRF/test/rrtmgp/generate_output_finite_fault_sources.py','WRF/test/rrtmgp/test_output_finite_fault.f90','WRF/test/rrtmgp/test_output_finite_fault.py','config/registration37.json']
assert not R.exists()
v={'status':'RUNNING','schema':'output-finite-component-validation-v1','source_head':subprocess.check_output(['git','-C',str(S),'rev-parse','HEAD'],text=True).strip(),'source_pins':{p:sha(S/p) for p in paths},'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'model_invocations':0,'steps':[]}
save(v)
env=os.environ.copy();env['LD_LIBRARY_PATH']=':'.join(str(ROOT/p) for p in ['build/deps/netcdf/lib','build/deps/root/usr/lib/x86_64-linux-gnu','build/deps/mpich-sock/lib']);env['PYTHONDONTWRITEBYTECODE']='1';env['OMP_NUM_THREADS']='1'
cmds=[['/usr/local/bin/cmake','-S',str(S/'WRF/test/rrtmgp'),'-B',str(H),'-DNETCDF_INCLUDE_DIR='+str(ROOT/'build/deps/netcdf/include'),'-DNETCDF_LIBRARY_DIR='+str(ROOT/'build/deps/netcdf/lib'),'-DRRTMGP_DATA_DIR='+str(ROOT/'build/udm37-pr60-active-cu-current-build-v1/source-v3/WRF/run'),'-DPython3_EXECUTABLE=/usr/bin/python3.12'],['/usr/local/bin/cmake','--build',str(H),'-j','12','--target','test_rrtmgp_columns','test_rrtmgp_multicolumn','test_rrtmgp_workspace','test_rrtmgp_sw_predelta_direct','test_rrtmgp_output_finite_lw_clear_flux_nan','test_rrtmgp_output_finite_sw_allsky_heat_nan','test_rrtmgp_output_finite_lw_allsky_default_overflow'],['/usr/local/bin/ctest','--test-dir',str(H),'--output-on-failure','-R','^(wrf_rrtmgp_columns|multi_column_equivalence|workspace_reuse_states_mode[01]|sw_predelta_direct_(clear|cloud|overlap_zero|night)|reject_output_finite_.*)$']]
for n,cmd in enumerate(cmds):
 log=H/f'step-{n}.log';row={'command':cmd,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};v['steps'].append(row);save(v)
 with log.open('xb') as f:p=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT)
 row.update(returncode=p.returncode,log=str(log),log_sha256=sha(log),ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save(v)
 if p.returncode:break
v['postflight_pins']={p:sha(S/p) for p in paths};v['sources_unchanged']=v['postflight_pins']==v['source_pins'];v['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();v['status']='PASS_COMPONENT_CHECKS' if len(v['steps'])==3 and all(s['returncode']==0 for s in v['steps']) and v['sources_unchanged'] else 'FAIL_PRESERVED';save(v)
print(json.dumps({'status':v['status'],'steps':[s['returncode'] for s in v['steps']],'receipt':str(R)}));raise SystemExit(0 if v['status']=='PASS_COMPONENT_CHECKS' else 1)
