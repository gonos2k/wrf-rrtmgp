PROGRAM test_sw_predelta_direct
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE module_ra_rrtmgp, ONLY: rrtmgp_init,rrtmgp_sw_column
  USE module_ra_rrtmgp_trace, ONLY: trace_start,trace_end
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=2,nl=3,nv=nl+1
  CHARACTER(1024) :: data_path,which,table_path
  REAL :: play(nc,nl),plev(nc,nv),tlay(nc,nl)
  REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl)
  REAL :: cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rwp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl)
  REAL :: gwp(nc,nl),hwp(nc,nl),lambda_g(nc,nl),lambda_h(nc,nl)
  REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  REAL :: up(nc,nv),dn(nc,nv),hr(nc,nl),upc(nc,nv),dnc(nc,nv),hrc(nc,nl)
  REAL :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv),visdir(nc,nv),visdif(nc,nv),nirdir(nc,nv),nirdif(nc,nv)
  REAL :: du(nc,nv),dcu(nc,nv),vdu(nc,nv),ndu(nc,nv)
  REAL :: du_short(nc,nv-1)
  REAL :: old_up(nc,nv),old_dn(nc,nv),old_hr(nc,nl),old_upc(nc,nv),old_dnc(nc,nv),old_hrc(nc,nl)
  REAL :: old_direct(nc,nv),old_diffuse(nc,nv),old_directc(nc,nv)
  REAL :: old_visdir(nc,nv),old_visdif(nc,nv),old_nirdir(nc,nv),old_nirdif(nc,nv)
  INTEGER :: overlap,c
  LOGICAL :: frozen_enabled
  CALL GET_COMMAND_ARGUMENT(1,data_path)
  CALL GET_COMMAND_ARGUMENT(2,which)
  CALL GET_COMMAND_ARGUMENT(3,table_path)
  IF(LEN_TRIM(which)==0) which='cloud'
  DO c=1,nc
    plev(c,:)=[1000.,700.,300.,1.]; play(c,:)=[850.,500.,150.]
    tlay(c,:)=[285.,260.,230.]
    h2o(c,:)=[.01,.003,.0001];o3(c,:)=[.5e-6,1.e-6,5.e-6]
  END DO
  co2=420.e-6;n2o=330.e-9;ch4=1.8e-6;o2=.2095
  cf=0.;lwp=0.;iwp=0.;swp=0.;rwp=0.;rel=10.;rei=30.;res=100.
  avdir=.15;avdif=.10;andir=.25;andif=.20;mu0=.65;solar=1361.;overlap=1
  gwp=0.;hwp=0.;lambda_g=20000.;lambda_h=20000.;frozen_enabled=.FALSE.
  SELECT CASE(TRIM(which))
  CASE('cloud','capture','capture_precip')
    cf(1,:)=1.;lwp(1,2)=100.;iwp(1,3)=100.
    IF(TRIM(which)=='capture_precip') THEN
      rwp(1,2)=10.;swp(1,2)=15.
    END IF
  CASE('overlap_zero')
    cf(1,:)=1.;lwp(1,2)=100.;iwp(1,3)=100.;overlap=0
  CASE('capture_frozen_overlap_zero')
    cf(1,:)=1.;lwp(1,2)=100.;iwp(1,3)=100.;overlap=0
    gwp(1,:)=30.;hwp(1,:)=10.;lambda_g(1,:)=2000.;lambda_h(1,:)=800.;frozen_enabled=.TRUE.
  CASE('clear','night','partial_a','partial_b','bad_shape')
    IF(TRIM(which)=='night') mu0=0.
    CONTINUE
  CASE DEFAULT
    ERROR STOP 'expected clear, cloud, or overlap_zero'
  END SELECT
  IF(frozen_enabled) THEN
    IF(LEN_TRIM(table_path)==0) ERROR STOP 'frozen test requires a table path'
    CALL rrtmgp_init(TRIM(data_path),frozen_optics=1,frozen_table=TRIM(table_path))
  ELSE
    CALL rrtmgp_init(TRIM(data_path))
  END IF
  IF(TRIM(which)=='partial_a') THEN
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
      avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
      up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
      direct_unscaled=du,visdir_unscaled=vdu,nirdir_unscaled=ndu)
    ERROR STOP 'partial output group A unexpectedly accepted'
  ELSE IF(TRIM(which)=='partial_b') THEN
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
      avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
      up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
      directc_unscaled=dcu,visdir_unscaled=vdu,nirdir_unscaled=ndu)
    ERROR STOP 'partial output group B unexpectedly accepted'
  ELSE IF(TRIM(which)=='bad_shape') THEN
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
      avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
      up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
      direct_unscaled=du_short,directc_unscaled=dcu,visdir_unscaled=vdu,nirdir_unscaled=ndu)
    ERROR STOP 'wrong-sized pre-delta output unexpectedly accepted'
  END IF
  CALL call_sw(.FALSE.)
  old_up=up;old_dn=dn;old_hr=hr;old_upc=upc;old_dnc=dnc;old_hrc=hrc
  old_direct=direct;old_diffuse=diffuse;old_directc=directc
  old_visdir=visdir;old_visdif=visdif;old_nirdir=nirdir;old_nirdif=nirdif
  IF(TRIM(which)=='capture'.OR.TRIM(which)=='capture_precip'.OR. &
     TRIM(which)=='capture_frozen_overlap_zero') CALL trace_start('SW',1,1)
  CALL call_sw(.TRUE.)
  IF(TRIM(which)=='capture'.OR.TRIM(which)=='capture_precip'.OR. &
     TRIM(which)=='capture_frozen_overlap_zero') CALL trace_end('SW')
  IF(TRIM(which)=='night') THEN
    du=777.;dcu=777.;vdu=777.;ndu=777.
    CALL call_sw(.TRUE.)
    IF(ANY(up/=0.).OR.ANY(dn/=0.).OR.ANY(hr/=0.).OR.ANY(upc/=0.).OR.ANY(dnc/=0.).OR.ANY(hrc/=0.).OR. &
       ANY(direct/=0.).OR.ANY(diffuse/=0.).OR.ANY(directc/=0.).OR.ANY(visdir/=0.).OR.ANY(visdif/=0.).OR. &
       ANY(nirdir/=0.).OR.ANY(nirdif/=0.).OR.ANY(du/=0.).OR.ANY(dcu/=0.).OR.ANY(vdu/=0.).OR.ANY(ndu/=0.)) &
      ERROR STOP 'nighttime SW outputs were not all initialized to zero'
    WRITE(*,'(A)') 'SW pre-delta night initialization PASS'
    STOP
  END IF
  IF(ANY(up/=old_up).OR.ANY(dn/=old_dn).OR.ANY(hr/=old_hr).OR. &
     ANY(upc/=old_upc).OR.ANY(dnc/=old_dnc).OR.ANY(hrc/=old_hrc).OR. &
     ANY(direct/=old_direct).OR.ANY(diffuse/=old_diffuse).OR.ANY(directc/=old_directc).OR. &
     ANY(visdir/=old_visdir).OR.ANY(visdif/=old_visdif).OR.ANY(nirdir/=old_nirdir).OR.ANY(nirdif/=old_nirdif)) &
    ERROR STOP 'requesting pre-delta diagnostics changed legacy SW outputs'
  IF(.NOT.ALL(ieee_is_finite(du)).OR..NOT.ALL(ieee_is_finite(dcu)).OR. &
     .NOT.ALL(ieee_is_finite(vdu)).OR..NOT.ALL(ieee_is_finite(ndu))) ERROR STOP 'non-finite pre-delta direct output'
  IF(MAXVAL(ABS(dn-direct-diffuse))>1.e-4) ERROR STOP 'SW direct/diffuse closure changed'
  IF(MAXVAL(ABS(dn-visdir-visdif-nirdir-nirdif))>2.e-4) ERROR STOP 'SW VIS/NIR closure changed'
  SELECT CASE(TRIM(which))
  CASE('clear','overlap_zero')
    IF(MAXVAL(ABS(du-dcu))>1.e-5) ERROR STOP 'clear direct differs from gas-only direct'
    IF(MAXVAL(ABS(du-directc))>1.e-4) ERROR STOP 'clear/overlap-zero predelta direct differs from gas-only direct'
  CASE('capture_frozen_overlap_zero')
    IF(MAXVAL(ABS(du-dcu))<=1.e-4) ERROR STOP 'frozen path failed to attenuate overlap-zero direct beam'
  CASE('cloud')
    IF(MAXVAL(ABS(du-direct))<=1.e-4) ERROR STOP 'cloud fixture did not distinguish pre-delta from solver direct'
    IF(ANY(du(:,1:nl+1)>direct(:,1:nl+1)+1.e-4)) ERROR STOP 'pre-delta direct unexpectedly exceeds delta-scaled direct'
  END SELECT
    WRITE(*,'(A)') 'SW pre-delta direct contract PASS: '//TRIM(which)
CONTAINS
  SUBROUTINE call_sw(with_optional)
    LOGICAL, INTENT(IN) :: with_optional
    IF(with_optional) THEN
      IF(frozen_enabled) THEN
        CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
          avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
          up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
          gwp=gwp,hwp=hwp,lambda_g=lambda_g,lambda_h=lambda_h, &
          direct_unscaled=du,directc_unscaled=dcu,visdir_unscaled=vdu,nirdir_unscaled=ndu)
      ELSE IF(TRIM(which)=='capture_precip') THEN
        CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
          avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
          up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
          rwp=rwp,direct_unscaled=du,directc_unscaled=dcu,visdir_unscaled=vdu,nirdir_unscaled=ndu)
      ELSE
        CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
          avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
          up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
          direct_unscaled=du,directc_unscaled=dcu,visdir_unscaled=vdu,nirdir_unscaled=ndu)
      END IF
    ELSE
      IF(frozen_enabled) THEN
        CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
          avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
          up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
          gwp=gwp,hwp=hwp,lambda_g=lambda_g,lambda_h=lambda_h)
      ELSE IF(TRIM(which)=='capture_precip') THEN
        CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
          avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
          up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif,rwp=rwp)
      ELSE
        CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
          avdir,avdif,andir,andif,mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
          up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif)
      END IF
    END IF
  END SUBROUTINE
END PROGRAM test_sw_predelta_direct
