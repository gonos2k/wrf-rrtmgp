PROGRAM test_rrtmgp_udm_adapter
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE module_ra_rrtmgp, ONLY: rrtmgp_init, rrtmgp_lw_column, rrtmgp_sw_column
  USE module_ra_rrtmgp_trace, ONLY: trace_start, trace_end
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=1, nl=3, nv=nl+1
  CHARACTER(LEN=512) :: data_path
  REAL :: play(nc,nl),plev(nc,nv),tlay(nc,nl),tlev(nc,nv),tsfc(nc)
  REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl),emis(nc,1)
  REAL :: cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rwp(nc,nl)
  REAL :: rel(nc,nl),rei(nc,nl),res(nc,nl)
  REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  REAL :: lwup(nc,nv),lwdn(nc,nv),lwhr(nc,nl),lwupc(nc,nv),lwdnc(nc,nv),lwhrc(nc,nl)
  REAL :: swup(nc,nv),swdn(nc,nv),swhr(nc,nl),swupc(nc,nv),swdnc(nc,nv),swhrc(nc,nl)
  REAL :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv),visdir(nc,nv),visdif(nc,nv),nirdir(nc,nv),nirdif(nc,nv)
  REAL :: base_lwup(nc,nv),base_lwdn(nc,nv),base_swdown(nc,nv)

  CALL get_command_argument(1,data_path)
  IF(LEN_TRIM(data_path)==0) ERROR STOP 'usage: test_rrtmgp_udm_adapter DATA_DIRECTORY'

  plev(1,:)=[1000.,700.,300.,1.]
  play(1,:)=[850.,500.,150.]
  tlay(1,:)=[285.,260.,230.]
  tlev(1,:)=[290.,275.,245.,210.]
  tsfc=290.
  h2o(1,:)=[.01,.003,.0001]
  co2=420.e-6; o3(1,:)=[.5e-6,1.e-6,5.e-6]
  n2o=330.e-9; ch4=1.8e-6; o2=.2095
  emis=.98
  cf=1.; lwp=0.; iwp=0.; swp=0.; rwp=0.
  rel=10.; rei=30.; res(1,:)=[25.,300.,999.]
  avdir=.15; avdif=.10; andir=.25; andif=.20
  solar=1361.; mu0=.65

  CALL rrtmgp_init(TRIM(data_path))

  ! No-precipitation compatibility baseline.  Appending an all-zero RWP/SWP
  ! must leave the radiation unchanged (within the adapter's default-real
  ! roundoff), while keeping the old non-RWP call source-compatible.
  CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,771,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
  base_lwup=lwup; base_lwdn=lwdn
  CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,771,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc,rwp=rwp)
  CALL check_close('zero RWP LW up',lwup,base_lwup,2.e-6)
  CALL check_close('zero RWP LW down',lwdn,base_lwdn,2.e-6)

  ! Fully cloudy rain+snow test.  RWP is in-cloud g m-2 and RES remains the
  ! native snow radius in micrometres, including values outside the ice LUT.
  rwp(1,:)=[25.,50.,100.]
  swp(1,:)=[10.,20.,30.]
  CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,771,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
  base_lwup=lwup; base_lwdn=lwdn
  CALL trace_start('LW',1,1)
  CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,771,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc,rwp=rwp)
  CALL trace_end('LW')
  CALL check_finite('LW precipitation',lwup,lwdn,lwhr)
  IF(MAXVAL(ABS(lwup-base_lwup))+MAXVAL(ABS(lwdn-base_lwdn))<=1.e-5) &
       CALL fail('rain/snow did not change LW output')

  ! Reset SW paths for a no-precipitation baseline, then trace positive rain
  ! and snow optics through the adapter's V4 replay input.
  swp=0.; rwp=0.
  CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,771,swup,swdn,swhr,swupc,swdnc,swhrc, &
       direct,diffuse,directc,visdir,visdif,nirdir,nirdif)
  base_swdown=swdn
  rwp(1,:)=[25.,50.,100.]
  swp(1,:)=[10.,20.,30.]
  CALL trace_start('SW',1,1)
  CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,771,swup,swdn,swhr,swupc,swdnc,swhrc, &
       direct,diffuse,directc,visdir,visdif,nirdir,nirdif,rwp=rwp)
  CALL trace_end('SW')
  CALL check_finite('SW precipitation',swup,swdn,swhr)
  IF(MAXVAL(ABS(swdn-base_swdown))<=1.e-5) CALL fail('rain/snow did not change SW down flux')

  WRITE(*,'(A)') 'UDM precipitation adapter checks passed.'
CONTAINS
  SUBROUTINE fail(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    WRITE(*,'(A)') 'FAIL: '//TRIM(message)
    ERROR STOP 1
  END SUBROUTINE fail

  SUBROUTINE check_close(label,a,b,tol)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: a(:,:),b(:,:),tol
    REAL :: scale
    IF(.NOT.ALL(ieee_is_finite(a)).OR..NOT.ALL(ieee_is_finite(b))) CALL fail(TRIM(label)//' non-finite')
    scale=MAX(1.,MAXVAL(ABS(a)),MAXVAL(ABS(b)))
    IF(MAXVAL(ABS(a-b))>tol*scale) CALL fail(label)
  END SUBROUTINE check_close

  SUBROUTINE check_finite(label,a,b,c)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: a(:,:),b(:,:),c(:,:)
    IF(.NOT.ALL(ieee_is_finite(a)).OR..NOT.ALL(ieee_is_finite(b)).OR..NOT.ALL(ieee_is_finite(c))) &
      CALL fail(TRIM(label)//' non-finite')
  END SUBROUTINE check_finite
END PROGRAM test_rrtmgp_udm_adapter
