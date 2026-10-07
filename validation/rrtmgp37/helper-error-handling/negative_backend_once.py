import hashlib,importlib.util,json,os,shlex,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
run=Path(sys.argv[2]).resolve()
run.mkdir(exist_ok=False)
harness=root/'WRF/test/rrtmgp/test_netcdf_zz.py'
spec=importlib.util.spec_from_file_location('backend_runner',harness)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
toolchain=json.loads(Path(sys.argv[3]).read_text())
flags=toolchain['fflags'];libs=toolchain['flibs']
env=os.environ.copy();env['LD_LIBRARY_PATH']=toolchain['LD_LIBRARY_PATH']
runner=module.Runner(run,120,env,4)
backend=root/'WRF/external/io_netcdf';ioapi=root/'WRF/external/ioapi_share'
source=run/'parent_wrf_io.F90'
source.write_bytes(subprocess.run(['git','show','HEAD:WRF/external/io_netcdf/wrf_io.F90'],cwd=root,check=True,stdout=subprocess.PIPE).stdout)
probe=run/'invalid_probe.F90'
probe.write_text("""program invalid_probe
 use wrf_data
 use ext_ncd_support_routines
 implicit none
 include 'wrf_status_codes.h'
 character(80) :: names(4),ordered(4)
 integer :: status
 names='first';ordered='sentinel'
 call ExtOrderStr('qq',names,ordered,status)
 if(status/=WRF_WARN_BAD_MEMORYORDER) error stop 71
 print *, 'ERROR_STATUS_RETURNED'
end program
subroutine wrf_debug(level,message)
 integer,intent(in)::level
 character(*),intent(in)::message
end subroutine
""")
plan={'schema':'UDM37_NETCDF_PARENT_NEGATIVE_V1','parent_commit':'9d7e79182395cd81bc7ed3805126575f64005bc3','source':module.pin(source),'probe':module.pin(probe),'maximum_direct_children':4,'optimization':'O0','expected_failure':'actual backend ExtOrderStr qq bounds error','full_wrf_builds':0,'forecasts':0,'rte_calls':0,'physical_acceptance':False}
module.write_json(run/'plan.json',plan)
try:
 cpp=run/'backend.cpp.f90';expanded=run/'backend.f90'
 runner.run(['/usr/bin/cpp','-P','-traditional-cpp','-DUSE_NETCDF4_FEATURES','-I'+str(ioapi),'-I'+str(backend),str(source)],run,'cpp_parent',cpp)
 runner.run(['/usr/bin/m4','-G','-Uinclude','-Uindex','-Ulen',str(cpp)],run,'m4_parent',expanded)
 exe=run/'parent_probe.exe'
 runner.run(['/usr/bin/gfortran','-O0','-g','-fcheck=all','-finit-integer=99','-fallow-argument-mismatch','-ffree-form','-ffree-line-length-none','-cpp','-I'+str(ioapi)]+flags+[str(expanded),str(backend/'field_routines.F90'),str(probe)]+libs+['-o',str(exe)],run,'compile_parent_actual_backend')
 try:
  runner.run([str(exe)],run,'expected_parent_failure')
 except RuntimeError:
  record=runner.commands[-1]
  error=(run/'command-04.stderr').read_text()
  if record['actual_returncode'] is None or record['actual_returncode']==0 or 'Index' not in error or 'above upper bound' not in error:
   raise RuntimeError('parent did not produce expected bounds failure')
  module.write_json(run/'result.json',{'status':'PASS_EXPECTED_PARENT_BOUNDS_FAILURE','plan':plan,'commands':runner.commands,'actual_probe_returncode':record['actual_returncode'],'stderr':error,'physical_acceptance':False})
  print('PASS_EXPECTED_PARENT_BOUNDS_FAILURE',record['actual_returncode'])
 else:
  raise RuntimeError('parent unexpectedly succeeded')
except BaseException as error:
 module.write_json(run/'failure.json',{'error':repr(error),'commands':runner.commands,'physical_acceptance':False})
 raise
