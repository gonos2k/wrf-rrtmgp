PROGRAM test_rrtmgp_output_finite_fault
  USE mo_rte_kind, ONLY: wp
  USE module_ra_rrtmgp, ONLY: rrtmgp_init,rrtmgp_lw_column,rrtmgp_sw_column
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=2,nl=3,nv=nl+1
  CHARACTER(LEN=512) :: data_path,case_name
  REAL :: play(nc,nl),plev(nc,nv),tlay(nc,nl),tlev(nc,nv),tsfc(nc)
  REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl)
  REAL :: emis(nc,1),cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl)
  REAL :: rel(nc,nl),rei(nc,nl),res(nc,nl)
  REAL :: lwup(nc,nv),lwdn(nc,nv),lwhr(nc,nl),lwupc(nc,nv),lwdnc(nc,nv),lwhrc(nc,nl)
  REAL :: swup(nc,nv),swdn(nc,nv),swhr(nc,nl),swupc(nc,nv),swdnc(nc,nv),swhrc(nc,nl)
  REAL :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv),visdir(nc,nv),visdif(nc,nv),nirdir(nc,nv),nirdif(nc,nv)
  REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  INTEGER :: status

  CALL get_command_argument(1,data_path,status=status)
  IF(status/=0.OR.LEN_TRIM(data_path)==0) ERROR STOP 'usage: test_output_finite_fault DATA_DIRECTORY'
  CALL get_command_argument(2,case_name,status=status)
  IF(status/=0.OR.LEN_TRIM(case_name)==0) ERROR STOP 'usage: test_output_finite_fault DATA_DIRECTORY CASE'
  IF(TRIM(case_name)=='lw_allsky_default_overflow'.AND.HUGE(1.)>=HUGE(1._wp)) THEN
    WRITE(*,'(A)') 'OUTPUT_FINITE_TEST_SKIPPED_DEFAULT_REAL_NOT_NARROWER_THAN_WP'
    STOP 77
  END IF
  plev(:,1)=[1000.,980.]; plev(:,2)=[700.,680.]; plev(:,3)=[300.,280.]; plev(:,4)=[1.,1.]
  play(1,:)=[850.,500.,150.]; play(2,:)=[830.,480.,140.]
  tlay(1,:)=[285.,260.,230.]; tlay(2,:)=[284.,259.,229.]
  tlev(1,:)=[290.,275.,245.,210.]; tlev(2,:)=[289.,274.,244.,209.]
  tsfc=[290.,289.]
  h2o(1,:)=[.01,.003,.0001]; h2o(2,:)=[.009,.0025,.00009]
  co2=420.e-6; o3(1,:)=[.5e-6,1.e-6,5.e-6]; o3(2,:)=[.4e-6,.9e-6,4.e-6]
  n2o=330.e-9; ch4=1.8e-6; o2=.2095; emis=.98
  cf=0.; lwp=0.; iwp=0.; swp=0.; rel=10.; rei=30.; res=30.
  avdir=.15; avdif=.10; andir=.25; andif=.20; mu0=.65; solar=1361.

  CALL rrtmgp_init(TRIM(data_path))
  CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,117,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
  CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,117,swup,swdn,swhr,swupc,swdnc,swhrc, &
       direct,diffuse,directc,visdir,visdif,nirdir,nirdif)
  WRITE(*,'(A)') 'OUTPUT_FINITE_FAULT_WAS_NOT_DETECTED'
  ERROR STOP 2
END PROGRAM test_rrtmgp_output_finite_fault
