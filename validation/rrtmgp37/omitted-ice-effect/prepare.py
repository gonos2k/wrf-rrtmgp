#!/usr/bin/env python3
"""Prepare isolated baseline/diagnostic column builds; production bytes untouched."""
import argparse,difflib,gzip,hashlib,json,shutil
from pathlib import Path


def prepare(root,out):
    out.mkdir(parents=True,exist_ok=False)
    src=out/'src';src.mkdir()
    names=['module_ra_rrtmgp','module_ra_rrtmgp_input','module_ra_rrtmgp_trace','module_ra_rrtmgp_precip','module_ra_rrtmgp_hash','module_ra_rrtmgp_frozen']
    pins={}
    for name in names:
        p=root/'WRF/phys'/(name+'.F');shutil.copyfile(p,src/p.name)
        pins[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
    shutil.copyfile(root/'WRF/test/rrtmgp/standalone_wrf_error.f90',src/'standalone_wrf_error.f90')
    source=(src/'module_ra_rrtmgp.F').read_text();changed=source
    # One isolated local optical bundle in each recursive column call.
    for phase,typ in [('LW','1scl'),('SW','2str')]:
        start=changed.index('  RECURSIVE SUBROUTINE rrtmgp_'+phase.lower()+'_column')
        end=changed.index('  END SUBROUTINE',start)
        part=changed[start:end]
        marker='    INTEGER :: nc,nl,precip_status' if phase=='LW' else '    INTEGER :: nc,nl'
        # Match the declaration line prefix, preserving existing trailing variables.
        pos=part.index(marker)
        part=part[:pos]+f'    TYPE(ty_optical_props_{typ}) :: diagnostic_ice\n    REAL(wp), ALLOCATABLE :: diagnostic_iwp(:,:)\n    LOGICAL :: diagnostic_present\n'+part[pos:]
        needle=f"    IF(trace_active('{phase}')) THEN\n      CALL trace_result('{phase}','TOTAL_TAU',atmos%tau)"
        if phase=='SW':
            needle="    IF(rrtmgp_frozen_enabled()) THEN\n      IF(need_unscaled) THEN"
            part=part.replace('    LOGICAL :: diagnostic_present','    REAL(wp), ALLOCATABLE :: diagnostic_raw_ice(:,:,:)\n    LOGICAL :: diagnostic_present')
        require_count=part.count(needle)
        if require_count!=1:raise ValueError((phase,'TOTAL_TAU anchor',require_count))
        injection=f"""    ! DIAGNOSTIC_ICE_BEGIN: occurrence one, after unchanged native sampling.
    CALL read_diagnostic_ice('{phase}',cf,diagnostic_iwp,diagnostic_present)
    IF(diagnostic_present) THEN
      CALL require(diagnostic_ice%alloc_{typ}(nc,nl,cloud_{phase.lower()}))
      CALL require(cloud_{phase.lower()}%cloud_optics(zero,diagnostic_iwp, &
           MAX(cloud_{phase.lower()}%get_min_radius_liq(),MIN(cloud_{phase.lower()}%get_max_radius_liq(),REAL(rel,wp))), &
           MAX(cloud_{phase.lower()}%get_min_radius_ice(),MIN(cloud_{phase.lower()}%get_max_radius_ice(),rrtmgp_ice_lut_coordinate(rei,iceflag))), &
           diagnostic_ice))
      CALL trace_result('{phase}','ICE_EXTRA_TAU_RAW',diagnostic_ice%tau)
"""
        if phase=='SW':
            injection=injection.replace('    IF(diagnostic_present) THEN', '    ALLOCATE(diagnostic_raw_ice(nc,nl,gas_sw%get_nband())); diagnostic_raw_ice=0._wp\n    IF(diagnostic_present) THEN')
            injection+="      diagnostic_raw_ice=diagnostic_ice%tau\n"
            injection+="""      CALL trace_result('SW','ICE_EXTRA_SSA_RAW',diagnostic_ice%ssa)
      CALL trace_result('SW','ICE_EXTRA_G_RAW',diagnostic_ice%g)
      ! Scale only this new cloud component once; never rescale atmos/precip.
      CALL require(diagnostic_ice%delta_scale())
      CALL trace_result('SW','ICE_EXTRA_SSA',diagnostic_ice%ssa)
      CALL trace_result('SW','ICE_EXTRA_G',diagnostic_ice%g)
"""
        injection+=f"""      CALL trace_result('{phase}','ICE_EXTRA_TAU',diagnostic_ice%tau)
      IF(ANY(diagnostic_iwp>0._wp)) CALL require(diagnostic_ice%increment(atmos))
      CALL diagnostic_ice%finalize()
    END IF
    ! DIAGNOSTIC_ICE_END
"""
        part=part.replace(needle,injection+needle)
        if phase=='SW':
            part=part.replace('work%raw_frozen_h(c,k,b))/REAL(mu0(c),wp)', 'work%raw_frozen_h(c,k,b)+diagnostic_raw_ice(c,k,b))/REAL(mu0(c),wp)')
        changed=changed[:start]+part+changed[end:]
    for phase in ('LW','SW'):
        needle=f"      CALL trace_result('{phase}','UP',up)"
        addition=f"      CALL trace_result('{phase}','ICE_DIAG_UP64',fu)\n      CALL trace_result('{phase}','ICE_DIAG_DN64',fd)\n      CALL trace_result('{phase}','ICE_DIAG_HR64',heat*86400._wp)\n"
        if phase=='SW':
            addition+="      CALL trace_result('SW','ICE_DIAG_DIRECT64',fdir)\n      IF(need_unscaled) CALL trace_result('SW','ICE_DIAG_PREDELTA64',SUM(work%direct_gpt,DIM=3))\n"
        if changed.count(needle)!=1:raise ValueError('allsky WP64 record anchor')
        changed=changed.replace(needle,addition+needle)
    helper="""
  ! DIAGNOSTIC_ICE_READER_BEGIN
  SUBROUTINE read_diagnostic_ice(phase,cf,path,enabled)
    USE, INTRINSIC :: iso_fortran_env, ONLY: iostat_end
    CHARACTER(LEN=*), INTENT(IN) :: phase
    REAL, INTENT(IN) :: cf(:,:)
    REAL(wp), ALLOCATABLE, INTENT(OUT) :: path(:,:)
    LOGICAL, INTENT(OUT) :: enabled
    CHARACTER(LEN=2048) :: filename
    CHARACTER(LEN=40) :: magic,p,tail
    INTEGER :: status,u,ios,nc,nl,native,k,index
    REAL :: occurrence,value,scale
    CHARACTER(LEN=64) :: scale_text
    CALL GET_ENVIRONMENT_VARIABLE('WRF_DIAGNOSTIC_ICE_FILE',filename,STATUS=status)
    enabled=status==0.AND.LEN_TRIM(filename)>0
    ALLOCATE(path(SIZE(cf,1),SIZE(cf,2)));path=0._wp
    IF(.NOT.enabled) RETURN
    scale=1.
    CALL GET_ENVIRONMENT_VARIABLE('WRF_DIAGNOSTIC_ICE_SCALE',scale_text,STATUS=status)
    IF(status==0) THEN
      READ(scale_text,*,IOSTAT=ios) scale
      IF(ios/=0.OR.(scale/=0..AND.scale/=1.)) CALL require('ICE diagnostic scale must be zero or one')
    END IF
    OPEN(NEWUNIT=u,FILE=TRIM(filename),STATUS='old',ACTION='read',IOSTAT=ios)
    IF(ios/=0) CALL require('ICE diagnostic file missing')
    READ(u,*,IOSTAT=ios) magic
    IF(ios/=0.OR.magic/='CF0_ICE_DIAGNOSTIC_V1') CALL require('ICE diagnostic magic')
    READ(u,*,IOSTAT=ios) p,nc,nl,native,occurrence
    IF(ios/=0.OR.p/=phase.OR.nc/=1.OR.nc/=SIZE(cf,1).OR.nl/=SIZE(cf,2).OR.native/=59.OR.occurrence/=1.) &
       CALL require('ICE diagnostic shape/occurrence')
    DO k=1,nl
      READ(u,*,IOSTAT=ios) index,value
      IF(ios/=0.OR.index/=k.OR..NOT.ieee_is_finite(value).OR.value<0.) CALL require('ICE diagnostic value/sequence')
      IF(value>0..AND.(k>native.OR.cf(1,k)/=0.)) CALL require('ICE diagnostic must be native CF0 only')
      path(1,k)=REAL(value,wp)*REAL(scale,wp)
    END DO
    READ(u,*,IOSTAT=ios) tail
    IF(ios/=iostat_end) CALL require('ICE diagnostic trailing data')
    CLOSE(u)
  END SUBROUTINE
  ! DIAGNOSTIC_ICE_READER_END
"""
    changed=changed.replace('END MODULE',helper+'\nEND MODULE')
    (src/'module_ra_rrtmgp_diagnostic.F').write_text(changed)
    (out/'diagnostic.patch').write_text(''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),fromfile='production/module_ra_rrtmgp.F',tofile='diagnostic/module_ra_rrtmgp.F')))
    pkg=Path(__file__).resolve().parent
    shutil.copyfile(pkg/'driver.f90',src/'driver.f90')
    cmake=f'''cmake_minimum_required(VERSION 3.20)
project(ICE_EFFECT LANGUAGES Fortran)
add_compile_options(-ffree-form)
add_subdirectory("{root}/WRF/external/rte_rrtmgp" rte)
add_library(helpers STATIC src/standalone_wrf_error.f90 src/module_ra_rrtmgp_trace.F src/module_ra_rrtmgp_input.F src/module_ra_rrtmgp_precip.F src/module_ra_rrtmgp_hash.F src/module_ra_rrtmgp_frozen.F)
set_target_properties(helpers PROPERTIES Fortran_MODULE_DIRECTORY "${{CMAKE_BINARY_DIR}}/helper-modules")
file(MAKE_DIRECTORY "${{CMAKE_BINARY_DIR}}/helper-modules")
target_include_directories(helpers PUBLIC "${{CMAKE_BINARY_DIR}}/helper-modules" "{root.parent.parent}/deps/netcdf/include")
target_link_libraries(helpers PUBLIC wrf_rrtmgp)
foreach(variant IN ITEMS baseline diagnostic)
  if(variant STREQUAL "baseline")
    set(adapter src/module_ra_rrtmgp.F)
  else()
    set(adapter src/module_ra_rrtmgp_diagnostic.F)
  endif()
  add_library(${{variant}}_adapter STATIC ${{adapter}})
  set_target_properties(${{variant}}_adapter PROPERTIES Fortran_MODULE_DIRECTORY "${{CMAKE_BINARY_DIR}}/${{variant}}-modules")
  file(MAKE_DIRECTORY "${{CMAKE_BINARY_DIR}}/${{variant}}-modules")
  target_include_directories(${{variant}}_adapter PUBLIC "${{CMAKE_BINARY_DIR}}/${{variant}}-modules")
  target_link_libraries(${{variant}}_adapter PUBLIC helpers)
  add_executable(${{variant}} src/driver.f90)
  target_link_libraries(${{variant}} PRIVATE ${{variant}}_adapter)
endforeach()
'''
    # NetCDF include is resolved from the explicit dependency root, not a worktree parent.
    cmake=cmake.replace(str(root.parent.parent)+'/deps/netcdf/include','/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/include')
    (out/'CMakeLists.txt').write_text(cmake)
    (out/'source-pins.json').write_text(json.dumps({'production':pins,'patched_source_sha256':hashlib.sha256(changed.encode()).hexdigest(),'scope':'isolated diagnostic only; production untouched'},indent=2)+'\n')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);ap.add_argument('output',type=Path);args=ap.parse_args();prepare(args.root.resolve(),args.output)
