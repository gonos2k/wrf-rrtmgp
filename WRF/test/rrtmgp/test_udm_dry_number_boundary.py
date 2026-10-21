#!/usr/bin/env python3
"""Compile the exact current input scope guard, including specified metadata.

Probe I/O is a stub: full NetCDF loading and a forcing-record crossing are tested
by validation/rrtmgp37/specified-number-boundary, not inferred from this probe.
"""
import argparse,hashlib,importlib.util,json,os,shutil
from pathlib import Path

def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 p=argparse.ArgumentParser();p.add_argument('wrf_root',type=Path);p.add_argument('--workdir',required=True,type=Path);p.add_argument('--exe',type=Path);p.add_argument('--seed',type=Path);a=p.parse_args()
 root=a.wrf_root.resolve();work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
 h=load(root/'test/rrtmgp/test_netcdf_zz.py','helper');r=h.Runner(work,180,{**os.environ,'OMP_NUM_THREADS':'1'},60)
 raw=(root/'share/input_wrf.F').read_text();start=raw.index('        IF (config_flags%udm_number_policy == 1) THEN');end=raw.index('      ENDIF\n    ENDIF',start);guard=raw[start:end]
 probe='''module probe_metadata
integer::tag=1,tag_count=1
end module
program guard_probe
use probe_metadata
implicit none
type config
 integer::udm_number_policy,mp_physics,ra_lw_physics,ra_sw_physics,scalar_adv_opt,max_dom,numtiles
 integer::udm_population_policy,rrtmgp_capacity_policy,rrtmgp_liquid_size_policy
 logical::specified,nested,periodic_x,periodic_y,have_bcs_scalar,have_bcs_moist
end type
type domain
 integer::id
end type
type(config)::config_flags
type(domain)::grid
integer,parameter::UDMSCHEME=27,RRTMGP_LWSCHEME=37,RRTMGP_SWSCHEME=37
integer::c,fid,gp_file_policy,icnt,udm_policy_ierr
character(8)::arg
call get_command_argument(1,arg);read(arg,*)c
config_flags%udm_number_policy=1;config_flags%mp_physics=27
config_flags%ra_lw_physics=37;config_flags%ra_sw_physics=37;config_flags%scalar_adv_opt=0
config_flags%max_dom=1;config_flags%numtiles=1;config_flags%udm_population_policy=0
config_flags%rrtmgp_capacity_policy=0;config_flags%rrtmgp_liquid_size_policy=0
config_flags%specified=.false.;config_flags%nested=.false.
config_flags%periodic_x=.true.;config_flags%periodic_y=.true.
config_flags%have_bcs_scalar=.true.;config_flags%have_bcs_moist=.true.;grid%id=1;fid=1
if(c==1.or.c>=8)then
config_flags%specified=.true.;config_flags%periodic_x=.false.;config_flags%periodic_y=.false.
endif
select case(c)
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
config_flags%udm_number_policy=0;config_flags%specified=.true.;config_flags%nested=.true.
case(8)
config_flags%udm_population_policy=2
case(9)
config_flags%have_bcs_scalar=.false.
case(10)
tag=0
case(11)
config_flags%ra_lw_physics=4
case(12)
tag_count=2
case(13)
config_flags%rrtmgp_capacity_policy=1
case(14)
config_flags%numtiles=2
case(15)
config_flags%have_bcs_moist=.false.
end select
'''+guard+'''
print *, 'GUARD_ACCEPTED'
end program
subroutine wrf_error_fatal(text)
character(*),intent(in)::text
print *, 'FATAL CALLED ',text
stop
end subroutine
subroutine wrf_get_dom_ti_integer(fid,name,value,num,icnt,ierr)
use probe_metadata
integer::fid,value,num,icnt,ierr
character(*)::name
value=tag;icnt=tag_count;ierr=0
end subroutine
'''
 (work/'probe.f90').write_text(probe);outcomes={}
 for opt in ['O0','O2']:
  exe=work/opt;r.run(['gfortran','-cpp','-'+opt,'-ffree-line-length-none',work/'probe.f90','-o',exe],work,'compile_'+opt)
  for c in range(16):
   text=r.run([exe,str(c)],work,opt+'_'+str(c)).read_text();accepted=c in (0,1,7)
   assert ('GUARD_ACCEPTED' in text and 'FATAL CALLED' not in text) if accepted else ('FATAL CALLED' in text and 'GUARD_ACCEPTED' not in text),(opt,c,text)
   outcomes[opt+':'+str(c)]='ACCEPTED' if accepted else 'REJECTED'
 for macro in ['DM_PARALLEL','_OPENMP']:
  exe=work/macro;r.run(['gfortran','-cpp','-D'+macro,'-O0','-ffree-line-length-none',work/'probe.f90','-o',exe],work,'compile_'+macro)
  text=r.run([exe,'1'],work,'refuse_'+macro).read_text();assert 'require a serial build' in text and 'GUARD_ACCEPTED' not in text
  outcomes[macro]='REJECTED'
 if a.exe:
  if a.seed is None:raise ValueError('seed required')
  # Preserve the optional old periodic SCM regression; specified execution is
  # intentionally exercised with full real files by the separate integration.
  setup=load(root/'test/rrtmgp/test_udm_startup_snow_scm.py','setup');scm=load(root/'test/rrtmgp/test_udm_dry_number_scm.py','scm')
  r.maximum+=2
  for policy in [0,1]:
   d=work/('periodic'+str(policy));d.mkdir()
   for f in a.seed.iterdir():
    if f.is_file() and not f.name.startswith(('wrfout','wrfrst','rsl.','udm_')) and f.name not in ['namelist.output','stdout.log','namelist.input']:shutil.copy2(f,d/f.name)
   text=(a.seed/'namelist.input').read_text()
   for k,v,g in [('run_minutes','1','time_control'),('run_seconds','0','time_control'),('end_minute','1','time_control'),('end_second','0','time_control'),('udm_number_policy',str(policy),'physics')]:text=setup.set_assignment(text,k,v,group=g)
   (d/'namelist.input').write_text(text)
   if policy:scm.convert_input(d/'wrfinput_d01')
   log=r.run([a.exe],d,'WRF_periodic'+str(policy)).read_text();assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log
 h.write_json(work/'receipt.json',{'status':'PASS_CURRENT_DRY_NUMBER_BOUNDARY_SCOPE','source_sha256':hashlib.sha256(raw.encode()).hexdigest(),'guard_sha256':hashlib.sha256(guard.encode()).hexdigest(),'outcomes':outcomes,'commands':r.commands,'production_accepted':False})
 print('CURRENT_DRY_NUMBER_BOUNDARY_SCOPE_COMPLETE')
if __name__=='__main__':main()
