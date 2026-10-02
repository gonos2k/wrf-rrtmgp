PROGRAM test_lw_trace_gases
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp, ONLY: rrtmgp_init, rrtmgp_lw_column
  USE module_ra_rrtmgp_trace, ONLY: trace_start, trace_end
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=1,nl=3,nv=nl+1
  CHARACTER(LEN=512) :: data_dir,mode
  REAL :: play(nc,nl),plev(nc,nv),tlay(nc,nl),tlev(nc,nv),tsfc(nc),emis(nc,1)
  REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl)
  REAL :: cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl)
  REAL :: c11(nc,nl),c12(nc,nl),c22(nc,nl),ccl4(nc,nl)
  REAL :: up(nc,nv),dn(nc,nv),hr(nc,nl),upc(nc,nv),dnc(nc,nv),hrc(nc,nl)

  CALL get_command_argument(1,data_dir)
  CALL get_command_argument(2,mode)
  IF(LEN_TRIM(data_dir)==0.OR.LEN_TRIM(mode)==0) ERROR STOP 'usage: test_lw_trace_gases DATA_DIR MODE'
  CALL set_case()
  CALL rrtmgp_init(TRIM(data_dir))
  c11=0.; c12=0.; c22=0.; ccl4=0.
  SELECT CASE(TRIM(mode))
  CASE('absent','zero','cfc11','cfc12','cfc22','ccl4','all','partial','shape','nan','negative')
  CASE DEFAULT
    ERROR STOP 'unknown test mode'
  END SELECT

  ! These are synthetic regression fixtures based on the legacy WRF GHG_INPUT=0
  ! fallback constants; they are not claimed to be observed SCM concentrations.
  SELECT CASE(TRIM(mode))
  CASE('cfc11'); c11=2.51e-10
  CASE('cfc12'); c12=5.38e-10
  CASE('cfc22'); c22=1.69e-10
  CASE('ccl4');  ccl4=9.30e-11
  CASE('all')
    c11=2.51e-10; c12=5.38e-10; c22=1.69e-10; ccl4=9.30e-11
  END SELECT

  CALL trace_start('LW',1,1)
  SELECT CASE(TRIM(mode))
  CASE('absent')
    CALL run()
  CASE('partial')
    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
      cf,lwp,iwp,swp,rel,rei,res,4,2,173,up,dn,hr,upc,dnc,hrc,cfc11vmr=c11)
  CASE('shape')
    BLOCK
      REAL :: bad_shape(nc,nl+1)
      bad_shape=0.
      CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
        cf,lwp,iwp,swp,rel,rei,res,4,2,173,up,dn,hr,upc,dnc,hrc, &
        cfc11vmr=bad_shape,cfc12vmr=c12,cfc22vmr=c22,ccl4vmr=ccl4)
    END BLOCK
  CASE('nan')
    c11(1,1)=ieee_value(0.,ieee_quiet_nan)
    CALL run_with_gases()
  CASE('negative')
    c11(1,1)=-1.e-10
    CALL run_with_gases()
  CASE DEFAULT
    IF(TRIM(mode)=='absent') THEN
      CALL run()
    ELSE
      CALL run_with_gases()
    END IF
  END SELECT
  CALL trace_end('LW')
  WRITE(*,'(A,1X,ES24.16E3)') 'SURFACE_UP',up(1,1)
  WRITE(*,'(A,1X,ES24.16E3)') 'TOA_DOWN',dn(1,nv)
  WRITE(*,'(A,1X,ES24.16E3)') 'MAX_ABS_HEATING',MAXVAL(ABS(hr))

CONTAINS
  SUBROUTINE set_case()
    plev(1,:)=[1000.,700.,300.,1.]
    play(1,:)=[850.,500.,150.]
    tlay(1,:)=[285.,260.,230.]
    tlev(1,:)=[290.,275.,245.,210.]
    tsfc=290.; emis=.98
    h2o(1,:)=[.01,.003,.0001]
    co2=420.e-6; o3(1,:)=[.5e-6,1.e-6,5.e-6]
    n2o=330.e-9; ch4=1.8e-6; o2=.2095
    cf=0.; lwp=0.; iwp=0.; swp=0.; rel=10.; rei=30.; res=30.
  END SUBROUTINE

  SUBROUTINE run()
    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
      cf,lwp,iwp,swp,rel,rei,res,4,2,173,up,dn,hr,upc,dnc,hrc)
  END SUBROUTINE

  SUBROUTINE run_with_gases()
    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
      cf,lwp,iwp,swp,rel,rei,res,4,2,173,up,dn,hr,upc,dnc,hrc, &
      cfc11vmr=c11,cfc12vmr=c12,cfc22vmr=c22,ccl4vmr=ccl4)
  END SUBROUTINE
END PROGRAM test_lw_trace_gases
