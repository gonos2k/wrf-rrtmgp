PROGRAM test_frozen_adapter
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE module_ra_rrtmgp, ONLY: rrtmgp_init,rrtmgp_lw_column,rrtmgp_sw_column
  USE module_ra_rrtmgp_trace, ONLY: trace_start,trace_end
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=2,nl=3,nv=4
  CHARACTER(1024) :: data_path,table_path,which
  REAL :: play(nc,nl),plev(nc,nv),tlay(nc,nl),tlev(nc,nv),tsfc(nc)
  REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl),emis(nc,1)
  REAL :: cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rwp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl)
  REAL :: gwp(nc,nl),hwp(nc,nl),lg(nc,nl),lh(nc,nl)
  REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  REAL :: up(nc,nv),dn(nc,nv),hr(nc,nl),upc(nc,nv),dnc(nc,nv),hrc(nc,nl)
  REAL :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv),visdir(nc,nv),visdif(nc,nv),nirdir(nc,nv),nirdif(nc,nv)
  REAL :: blw(nc,nv),bsw(nc,nv),bhr(nc,nl),clear_lw(nc,nv),clear_sw(nc,nv)
  INTEGER :: k,overlap
  CALL get_command_argument(1,data_path)
  CALL get_command_argument(2,table_path)
  CALL get_command_argument(3,which)
  IF(LEN_TRIM(which)==0) which='mixed'
  DO k=1,nc
    plev(k,:)=[1000.,700.,300.,1.]; play(k,:)=[850.,500.,150.]
    tlay(k,:)=[285.,260.,230.];tlev(k,:)=[290.,275.,245.,210.]
    h2o(k,:)=[.01,.003,.0001];o3(k,:)=[.5e-6,1.e-6,5.e-6]
  END DO
  tsfc=290.;co2=420.e-6;n2o=330.e-9;ch4=1.8e-6;o2=.2095;emis=.98
  cf=0.;lwp=0.;iwp=0.;swp=0.;rwp=0.;rel=10.;rei=30.;res=100.
  avdir=.15;avdif=.10;andir=.25;andif=.20;mu0=.65;solar=1361.
  gwp=0.;hwp=0.;lg=20000.;lh=20000.;overlap=2
  IF(which=='mode_zero_input') THEN
    CALL rrtmgp_init(TRIM(data_path))
  ELSE IF(which=='bad_mode') THEN
    CALL rrtmgp_init(TRIM(data_path),frozen_optics=2,frozen_table=TRIM(table_path))
  ELSE
    CALL rrtmgp_init(TRIM(data_path),frozen_optics=1,frozen_table=TRIM(table_path))
  END IF
  IF(which=='changed_path') CALL rrtmgp_init(TRIM(data_path),frozen_optics=1,frozen_table='changed')
  IF(which=='missing_inputs') THEN
    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
      cf,lwp,iwp,swp,rel,rei,res,4,overlap,771,up,dn,hr,upc,dnc,hrc,rwp=rwp)
    ERROR STOP 'missing frozen inputs unexpectedly accepted'
  END IF
  CALL run_lw();blw=dn;clear_lw=dnc
  CALL run_sw();bsw=dn;clear_sw=dnc
  SELECT CASE(TRIM(which))
  CASE('graupel')
    gwp=50.;lg=2000.
  CASE('hail')
    hwp=50.;lh=800.
  CASE('tiny')
    gwp=1.e-10;hwp=1.e-10
  CASE('zero')
    ! No optical path must leave both all-sky and clear-sky unchanged.
    ! A zero-path upper layer outside the table T axis is valid.
    tlay(:,3)=170.
    CALL run_lw();blw=dn;clear_lw=dnc
    CALL run_sw();bsw=dn;clear_sw=dnc
  CASE('lambda_range')
    gwp=1.e-10;lg=299.
  CASE('temperature_range')
    hwp=1.e-10;tlay(:,1)=301.
  CASE('mode_zero_input','bad_mode','changed_path')
    gwp=1.
  CASE DEFAULT
    gwp=50.;hwp=10.;lg=2000.;lh=800.
    gwp(2,:)=20.;hwp(2,:)=25.;lg(2,:)=6000.;lh(2,:)=4700.
  END SELECT
  IF(which=='overlap_zero') overlap=0
  IF(which=='mixed_cloud') THEN
    cf=.4;lwp(:,1)=40.;iwp(:,2)=30.;rwp(:,1)=10.;swp(:,2)=20.
  END IF
  CALL trace_start('LW',1,1);CALL run_lw();CALL trace_end('LW')
  IF(.NOT.ALL(ieee_is_finite(up)).OR..NOT.ALL(ieee_is_finite(dn)).OR. &
     .NOT.ALL(ieee_is_finite(hr))) ERROR STOP 'nonfinite frozen LW'
  IF(ANY(dnc/=clear_lw)) ERROR STOP 'frozen LW modified clear-sky'
  IF(which/='zero'.AND.which/='tiny') THEN
    IF(MAXVAL(ABS(dn-blw))<=1.e-5) ERROR STOP 'positive frozen path did not modify LW'
  END IF
  CALL trace_start('SW',1,1);CALL run_sw();CALL trace_end('SW')
  IF(.NOT.ALL(ieee_is_finite(up)).OR..NOT.ALL(ieee_is_finite(dn)).OR. &
     .NOT.ALL(ieee_is_finite(hr))) ERROR STOP 'nonfinite frozen SW'
  IF(ANY(dnc/=clear_sw)) ERROR STOP 'frozen SW modified clear-sky'
  IF(MAXVAL(ABS(dn-direct-diffuse))>1.e-4) ERROR STOP 'SW direct diffuse closure'
  IF(MAXVAL(ABS(dn-visdir-visdif-nirdir-nirdif))>2.e-4) ERROR STOP 'SW spectral closure'
  IF(which=='zero') THEN
    IF(ANY(dn/=bsw)) ERROR STOP 'zero frozen path changed SW'
  ELSE IF(which/='tiny') THEN
    IF(MAXVAL(ABS(dn-bsw))<=1.e-5) ERROR STOP 'positive frozen path did not modify SW'
  END IF
  WRITE(*,'(A)') 'EXPERIMENTAL frozen adapter contract PASS: '//TRIM(which)
CONTAINS
  SUBROUTINE run_lw()
    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
      cf,lwp,iwp,swp,rel,rei,res,4,overlap,771,up,dn,hr,upc,dnc,hrc,rwp=rwp, &
      gwp=gwp,hwp=hwp,lambda_g=lg,lambda_h=lh)
  END SUBROUTINE
  SUBROUTINE run_sw()
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
      avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
      up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif,rwp=rwp, &
      gwp=gwp,hwp=hwp,lambda_g=lg,lambda_h=lh)
  END SUBROUTINE
END PROGRAM
