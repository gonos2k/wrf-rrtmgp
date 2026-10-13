#!/usr/bin/env python3
"""Compile the exact input guard, optionally run tagged SCM input against WRF."""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path
sys.dont_write_bytecode=True
MESSAGE='dry-number-grid-v1 requires one periodic domain; specified/nested boundaries unsupported'
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def require(ok,msg):
 if not ok:raise ValueError(msg)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--workdir',required=True,type=Path);ap.add_argument('--exe',type=Path);ap.add_argument('--seed',type=Path);a=ap.parse_args()
 root=a.wrf_root.resolve();work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
 helper=load(root/'test/rrtmgp/test_netcdf_zz.py','helper');runner=helper.Runner(work,180,{**os.environ,'LC_ALL':'C','OMP_NUM_THREADS':'1','LD_LIBRARY_PATH':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/lib:'+os.environ.get('LD_LIBRARY_PATH','')},60)
 raw=(root/'share/input_wrf.F').read_bytes();text=raw.decode();start=text.index('        IF (config_flags%udm_number_policy == 1) THEN');end=text.index('        ENDIF',start)+len('        ENDIF');guard=text[start:end]
 # Exact source block, including preexisting engine/transport restriction.
 probe='''program guard_probe
implicit none
type config
 integer::udm_number_policy,mp_physics,ra_lw_physics,ra_sw_physics,scalar_adv_opt,max_dom
 logical::specified,nested,periodic_x,periodic_y
end type
type domain
 integer::id
end type
type(config)::config_flags
type(domain)::grid
integer,parameter::UDMSCHEME=27,RRTMGP_LWSCHEME=37,RRTMGP_SWSCHEME=37
integer::c
character(8)::arg
call get_command_argument(1,arg)
read(arg,*) c
config_flags=config(1,27,37,37,0,1,.false.,.false.,.true.,.true.)
grid%id=1
select case(c)
case(1)
 config_flags%specified=.true.
case(2)
 config_flags%nested=.true.
case(3)
 config_flags%max_dom=2
case(4)
 grid%id=2
case(5)
 config_flags%periodic_x=.false.
case(6)
 config_flags%periodic_y=.false.
case(7)
 config_flags%udm_number_policy=0
 config_flags%specified=.true.
 config_flags%nested=.true.
 config_flags%max_dom=2
 config_flags%periodic_x=.false.
 config_flags%periodic_y=.false.
end select
'''+guard+'''
print *, 'GUARD_ACCEPTED'
end program
subroutine wrf_error_fatal(text)
character(*),intent(in)::text
print *, 'FATAL CALLED ',text
! Deliberately RC0, matching serial WRF STOP semantics.
stop
end subroutine
'''
 (work/'input_guard.f90').write_text(probe)
 report={'schema':'UDM_POLICY1_BOUNDARY_SCOPE_V1','status':'PREPARED','production_accepted':False,'input_source_sha256':hashlib.sha256(raw).hexdigest(),'guard_block_sha256':hashlib.sha256(guard.encode()).hexdigest(),'processes':[],'probe':{},'WRF_runs':[]}
 def save():report['processes']=runner.commands;helper.write_json(work/'receipt.json',report)
 save()
 try:
  compiler=Path(shutil.which('gfortran')).resolve()
  for opt in ('O0','O2'):
   exe=work/opt;runner.run([compiler,'-'+opt,'-ffree-line-length-none',work/'input_guard.f90','-o',exe],work,'compile_guard_'+opt)
   for case in range(8):
    out=runner.run([exe,str(case)],work,'guard_'+opt+'_'+str(case));s=out.read_text();reject=1<=case<=6
    require((MESSAGE in s and 'FATAL CALLED' in s and 'GUARD_ACCEPTED' not in s) if reject else ('GUARD_ACCEPTED' in s and 'FATAL CALLED' not in s),'guard outcome differs')
    report['probe'][opt+':'+str(case)]='REJECTED' if reject else 'ACCEPTED';save()
  if a.exe:
   require(a.seed is not None,'WRF seed required');seed=a.seed.resolve();exe=a.exe.resolve();setup=load(root/'test/rrtmgp/test_udm_startup_snow_scm.py','setup');scm=load(root/'test/rrtmgp/test_udm_dry_number_scm.py','scm')
   report['executable']=helper.pin(exe);report['seed_input']=helper.pin(seed/'wrfinput_d01')
   for name,policy,reject in [('periodic_policy1',1,False),('periodic_policy0',0,False),('specified_policy1',1,True)]:
    d=work/name;d.mkdir()
    for p in seed.iterdir():
     if not p.is_file() or p.name.startswith(('wrfout','wrfrst','rsl.','udm_')) or p.name in ('namelist.output','stdout.log','namelist.input'):continue
     shutil.copy2(p,d/p.name)
    s=(seed/'namelist.input').read_text()
    for key,value,group in [('run_minutes','1','time_control'),('run_seconds','0','time_control'),('end_minute','1','time_control'),('end_second','0','time_control'),('udm_number_policy',str(policy),'physics')]:s=setup.set_assignment(s,key,value,group=group)
    if reject:
     for key,value in [('specified','.true.'),('periodic_x','.false.'),('periodic_y','.false.')]:s=setup.set_assignment(s,key,value,group='bdy_control')
    (d/'namelist.input').write_text(s)
    if policy:scm.convert_input(d/'wrfinput_d01')
    out=runner.run([exe],d,'WRF_'+name);s=out.read_text(errors='replace')
    require((MESSAGE in s and 'FATAL CALLED' in s and 'SUCCESS COMPLETE WRF' not in s and not list(d.glob('wrfout*'))) if reject else ('SUCCESS COMPLETE WRF' in s and 'FATAL CALLED' not in s),'actual WRF scope outcome differs '+name)
    report['WRF_runs'].append({'name':name,'outcome':'REJECTED' if reject else 'SUCCESS','input':helper.pin(d/'wrfinput_d01')});save()
  report.update(status='PASS_SCOPED_POLICY1_BOUNDARY_GUARD',limits=['Exact source guard probe covers nested/max_dom/id and nonperiodic combinations, not complete nested WRF integration.','Optional actual WRF campaign covers tagged specified input rejection and supported periodic policy0/policy1.','Policy0 boundary physics unchanged; boundary eta production remains unsupported.']);save();print(json.dumps({'status':report['status'],'receipt':str(work/'receipt.json')}))
 except BaseException as e:report.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':main()
