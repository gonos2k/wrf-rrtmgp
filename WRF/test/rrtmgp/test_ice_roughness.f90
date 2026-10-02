PROGRAM test_rrtmgp_ice_roughness
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE module_ra_rrtmgp, ONLY: rrtmgp_init, rrtmgp_lw_column, rrtmgp_sw_column
  USE mo_gas_optics_constants, ONLY: grav, cp_dry
  IMPLICIT NONE
  CHARACTER(LEN=512) :: data_path, output_path, arg
  INTEGER :: roughness, ios, outunit

  CALL get_command_argument(1,data_path)
  CALL get_command_argument(2,arg)
  IF(LEN_TRIM(data_path)==0.OR.LEN_TRIM(arg)==0) &
    ERROR STOP 'usage: test_rrtmgp_ice_roughness DATA_DIRECTORY ROUGHNESS_1_2_3 [CSV_OUTPUT]'
  READ(arg,*,IOSTAT=ios) roughness
  IF(ios/=0.OR.roughness<1.OR.roughness>3) &
    ERROR STOP 'ROUGHNESS_1_2_3 must be one of 1, 2, 3'
  CALL get_command_argument(3,output_path)
  outunit=6
  IF(LEN_TRIM(output_path)>0) THEN
    OPEN(NEWUNIT=outunit,FILE=TRIM(output_path),STATUS='REPLACE',ACTION='WRITE',IOSTAT=ios)
    IF(ios/=0) ERROR STOP 'could not open CSV output path'
  END IF

  CALL rrtmgp_init(TRIM(data_path),roughness)
  WRITE(outunit,'(A)') 'roughness,ncol,scenario,glw_w_m2,olr_w_m2,swdnb_w_m2,swupt_w_m2,'// &
    'swddir_w_m2,swddif_w_m2,lwhr_max_abs_k_day,swhr_max_abs_k_day,'// &
    'glw_clear_w_m2,olr_clear_w_m2,swdnb_clear_w_m2,swupt_clear_w_m2'
  CALL run_size(1)
  CALL run_size(8)
  CALL run_size(64)
  IF(outunit/=6) CLOSE(outunit)
  WRITE(*,'(A,I0)') 'RRTMGP ice-roughness cases completed for category ',roughness

CONTAINS

  SUBROUTINE run_size(nc)
    INTEGER, INTENT(IN) :: nc
    INTEGER, PARAMETER :: nl=3, nv=nl+1
    REAL :: play(nc,nl),plev(nc,nv),tlay(nc,nl),tlev(nc,nv),tsfc(nc)
    REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl)
    REAL :: emis(nc,1),cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl)
    REAL :: rel(nc,nl),rei(nc,nl),res(nc,nl)
    REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
    REAL :: lwup(nc,nv),lwdn(nc,nv),lwhr(nc,nl),lwupc(nc,nv),lwdnc(nc,nv),lwhrc(nc,nl)
    REAL :: swup(nc,nv),swdn(nc,nv),swhr(nc,nl),swupc(nc,nv),swdnc(nc,nv),swhrc(nc,nl)
    REAL :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv)
    REAL :: visdir(nc,nv),visdif(nc,nv),nirdir(nc,nv),nirdif(nc,nv)
    REAL :: clear_lwup(nc,nv),clear_lwdn(nc,nv),clear_lwhr(nc,nl)
    REAL :: clear_swup(nc,nv),clear_swdn(nc,nv),clear_swhr(nc,nl)
    REAL :: lw_check(nc,nl),sw_check(nc,nl)
    INTEGER :: c,layer,scenario
    CHARACTER(LEN=16) :: label
    REAL :: values(12),scale

    plev(:,1)=1000.; plev(:,2)=700.; plev(:,3)=300.; plev(:,4)=1.
    play(:,1)=850.; play(:,2)=500.; play(:,3)=150.
    tlev(:,1)=290.; tlev(:,2)=275.; tlev(:,3)=245.; tlev(:,4)=210.
    DO layer=1,nl
      tlay(:,layer)=0.5*(tlev(:,layer)+tlev(:,layer+1))
    END DO
    tsfc=290.; h2o(:,1)=.01; h2o(:,2)=.003; h2o(:,3)=.0001
    co2=420.e-6; o3(:,1)=.5e-6; o3(:,2)=1.e-6; o3(:,3)=5.e-6
    n2o=330.e-9; ch4=1.8e-6; o2=.2095; emis=.98
    rel=10.; rei=30.; res=60.
    avdir=.15; avdif=.10; andir=.25; andif=.20; mu0=.65; solar=1361.
    cf=0.; lwp=0.; iwp=0.; swp=0.

    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
      cf,lwp,iwp,swp,rel,rei,res,4,2,173,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
      cf,lwp,iwp,swp,rel,rei,res,4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
      direct,diffuse,directc,visdir,visdif,nirdir,nirdif)
    IF(.NOT.ALL(ieee_is_finite(lwup)).OR..NOT.ALL(ieee_is_finite(lwdn)).OR. &
       .NOT.ALL(ieee_is_finite(lwhr)).OR..NOT.ALL(ieee_is_finite(swup)).OR. &
       .NOT.ALL(ieee_is_finite(swdn)).OR..NOT.ALL(ieee_is_finite(swhr)).OR. &
       .NOT.ALL(ieee_is_finite(direct)).OR..NOT.ALL(ieee_is_finite(diffuse))) &
      ERROR STOP 'non-finite clear-sky radiation output'
    DO layer=1,nl
      lw_check(:,layer)=(lwup(:,layer+1)-lwup(:,layer)-lwdn(:,layer+1)+lwdn(:,layer))* &
        REAL(grav)/(REAL(cp_dry)*(plev(:,layer+1)-plev(:,layer))*100.)*86400.
      sw_check(:,layer)=(swup(:,layer+1)-swup(:,layer)-swdn(:,layer+1)+swdn(:,layer))* &
        REAL(grav)/(REAL(cp_dry)*(plev(:,layer+1)-plev(:,layer))*100.)*86400.
    END DO
    IF(MAXVAL(ABS(lwhr-lw_check))>2.e-5*MAX(1.,MAXVAL(ABS(lwhr))).OR. &
       MAXVAL(ABS(swhr-sw_check))>2.e-5*MAX(1.,MAXVAL(ABS(swhr)))) &
      ERROR STOP 'clear heating is inconsistent with net-flux divergence'
    clear_lwup=lwup; clear_lwdn=lwdn; clear_lwhr=lwhr
    clear_swup=swup; clear_swdn=swdn; clear_swhr=swhr
    label='clear'
    values=[SUM(lwdn(:,1))/nc,SUM(lwup(:,nv))/nc,SUM(swdn(:,1))/nc,SUM(swup(:,nv))/nc, &
      SUM(direct(:,1))/nc,SUM(diffuse(:,1))/nc,MAXVAL(ABS(lwhr)),MAXVAL(ABS(swhr)), &
      SUM(lwdn(:,1))/nc,SUM(lwup(:,nv))/nc,SUM(swdn(:,1))/nc,SUM(swup(:,nv))/nc]
    WRITE(outunit,'(I0,A,I0,A,A,12(A,ES24.16E3))') roughness,',',nc,',',TRIM(label), &
      (',',values(c),c=1,SIZE(values))

    DO scenario=1,8
      cf=1.; lwp=0.; iwp=0.; swp=0.
      SELECT CASE(scenario)
      CASE(1)
        label='liquid-only'; lwp=50.
      CASE(2)
        label='ice-10um'; iwp=50.; rei=10.
      CASE(3)
        label='ice-30um'; iwp=50.; rei=30.
      CASE(4)
        label='ice-60um'; iwp=50.; rei=60.
      CASE(5)
        label='snow-30um'; swp=50.; res=30.
      CASE(6)
        label='snow-60um'; swp=50.; res=60.
      CASE(7)
        label='snow-130um'; swp=50.; res=130.
      CASE(8)
        label='mixed-phase'; lwp=20.; iwp=50.; swp=30.; rei=30.; res=60.
      END SELECT
      CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
        cf,lwp,iwp,swp,rel,rei,res,4,2,173,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
      CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
        cf,lwp,iwp,swp,rel,rei,res,4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
        direct,diffuse,directc,visdir,visdif,nirdir,nirdif)
      IF(.NOT.ALL(ieee_is_finite(lwup)).OR..NOT.ALL(ieee_is_finite(lwdn)).OR. &
         .NOT.ALL(ieee_is_finite(lwhr)).OR..NOT.ALL(ieee_is_finite(swup)).OR. &
         .NOT.ALL(ieee_is_finite(swdn)).OR..NOT.ALL(ieee_is_finite(swhr)).OR. &
         .NOT.ALL(ieee_is_finite(direct)).OR..NOT.ALL(ieee_is_finite(diffuse))) &
        ERROR STOP 'non-finite cloudy radiation output'
      DO layer=1,nl
        lw_check(:,layer)=(lwup(:,layer+1)-lwup(:,layer)-lwdn(:,layer+1)+lwdn(:,layer))* &
          REAL(grav)/(REAL(cp_dry)*(plev(:,layer+1)-plev(:,layer))*100.)*86400.
        sw_check(:,layer)=(swup(:,layer+1)-swup(:,layer)-swdn(:,layer+1)+swdn(:,layer))* &
          REAL(grav)/(REAL(cp_dry)*(plev(:,layer+1)-plev(:,layer))*100.)*86400.
      END DO
      IF(MAXVAL(ABS(lwhr-lw_check))>2.e-5*MAX(1.,MAXVAL(ABS(lwhr))).OR. &
         MAXVAL(ABS(swhr-sw_check))>2.e-5*MAX(1.,MAXVAL(ABS(swhr)))) &
        ERROR STOP 'cloudy heating is inconsistent with net-flux divergence'
      scale=MAX(1.,MAXVAL(ABS(clear_lwup)),MAXVAL(ABS(clear_lwdn)), &
        MAXVAL(ABS(clear_lwhr)),MAXVAL(ABS(clear_swup)),MAXVAL(ABS(clear_swdn)),MAXVAL(ABS(clear_swhr)))
      IF(MAXVAL(ABS(lwupc-clear_lwup))>8.*EPSILON(1.)*scale.OR. &
         MAXVAL(ABS(lwdnc-clear_lwdn))>8.*EPSILON(1.)*scale.OR. &
         MAXVAL(ABS(lwhrc-clear_lwhr))>8.*EPSILON(1.)*scale.OR. &
         MAXVAL(ABS(swupc-clear_swup))>8.*EPSILON(1.)*scale.OR. &
         MAXVAL(ABS(swdnc-clear_swdn))>8.*EPSILON(1.)*scale.OR. &
         MAXVAL(ABS(swhrc-clear_swhr))>8.*EPSILON(1.)*scale) ERROR STOP 'clear-sky flux changed'
      IF(ANY(lwp<0.).OR.ANY(iwp<0.).OR.ANY(swp<0.)) ERROR STOP 'invalid fixture path'
      IF(MAXVAL(ABS(lwup-clear_lwup))+MAXVAL(ABS(lwdn-clear_lwdn))<=1.e-8) &
        ERROR STOP 'LW cloud fixture produced no flux response'
      IF(MAXVAL(ABS(swup-clear_swup))+MAXVAL(ABS(swdn-clear_swdn))<=1.e-8) &
        ERROR STOP 'SW cloud fixture produced no flux response'
      values=[SUM(lwdn(:,1))/nc,SUM(lwup(:,nv))/nc,SUM(swdn(:,1))/nc,SUM(swup(:,nv))/nc, &
        SUM(direct(:,1))/nc,SUM(diffuse(:,1))/nc,MAXVAL(ABS(lwhr)),MAXVAL(ABS(swhr)), &
        SUM(lwdnc(:,1))/nc,SUM(lwupc(:,nv))/nc,SUM(swdnc(:,1))/nc,SUM(swupc(:,nv))/nc]
      IF(.NOT.ALL(ieee_is_finite(values))) ERROR STOP 'non-finite roughness result row'
      WRITE(outunit,'(I0,A,I0,A,A,12(A,ES24.16E3))') roughness,',',nc,',',TRIM(label), &
        (',',values(c),c=1,SIZE(values))
    END DO
  END SUBROUTINE run_size
END PROGRAM test_rrtmgp_ice_roughness
