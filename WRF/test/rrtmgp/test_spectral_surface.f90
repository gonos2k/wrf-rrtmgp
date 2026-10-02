PROGRAM test_rrtmgp_spectral_surface
  USE, INTRINSIC :: iso_fortran_env, ONLY: output_unit
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE mo_rte_kind, ONLY: wp
  USE mo_gas_concentrations, ONLY: ty_gas_concs
  USE mo_gas_optics_rrtmgp, ONLY: ty_gas_optics_rrtmgp
  USE mo_cloud_optics_rrtmgp, ONLY: ty_cloud_optics_rrtmgp
  USE mo_optical_props, ONLY: ty_optical_props_2str
  USE mo_fluxes_byband, ONLY: ty_fluxes_byband
  USE mo_rte_sw, ONLY: rte_sw
  USE mo_cloud_sampling, ONLY: draw_samples
  USE mo_load_coefficients, ONLY: load_and_init
  USE mo_load_cloud_coefficients, ONLY: load_cld_lutcoeff
  USE module_ra_rrtmgp, ONLY: rrtmgp_init, rrtmgp_sw_column
  IMPLICIT NONE

  INTEGER, PARAMETER :: nc=1, nl=3, nv=nl+1, nb=14
  REAL(wp), PARAMETER :: expected_lo(nb)=[820._wp,2680._wp,3250._wp,4000._wp,4650._wp, &
       5150._wp,6150._wp,7700._wp,8050._wp,12850._wp,16000._wp,22650._wp,29000._wp,38000._wp]
  REAL(wp), PARAMETER :: expected_hi(nb)=[2680._wp,3250._wp,4000._wp,4650._wp,5150._wp, &
       6150._wp,7700._wp,8050._wp,12850._wp,16000._wp,22650._wp,29000._wp,38000._wp,50000._wp]
  CHARACTER(LEN=512) :: data_dir,csv_path
  CHARACTER(LEN=3), PARAMETER :: gas_names(6)=[character(len=3) :: 'h2o','co2','o3','n2o','ch4','o2']
  TYPE(ty_gas_concs) :: gases
  TYPE(ty_gas_optics_rrtmgp) :: gas_sw
  TYPE(ty_cloud_optics_rrtmgp) :: cloud_sw
  REAL(wp) :: play(nc,nl),plev(nc,nv),tlay(nc,nl),h2o(nc,nl),co2(nc,nl),o3(nc,nl)
  REAL(wp) :: n2o(nc,nl),ch4(nc,nl),o2(nc,nl),toa(nc,112),bands(2,nb)
  REAL(wp) :: cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl)
  REAL(wp) :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  REAL :: wrf_up(nc,nv),wrf_dn(nc,nv),wrf_hr(nc,nl),wrf_upc(nc,nv),wrf_dnc(nc,nv),wrf_hrc(nc,nl)
  REAL :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv)
  REAL :: visdir(nc,nv),visdif(nc,nv),nirdir(nc,nv),nirdif(nc,nv)
  REAL(wp), TARGET :: fu(nc,nv),fd(nc,nv),fdir(nc,nv),bd(nc,nv,nb),bdir(nc,nv,nb)
  REAL(wp) :: old_up(nc,nv),expected_up(nc,nv),expected_dn(nc,nv)
  REAL(wp) :: expected_upc(nc,nv),expected_dnc(nc,nv),expected_direct(nc,nv)
  REAL(wp) :: expected_visdir(nc,nv),expected_visdif(nc,nv)
  REAL(wp) :: expected_nirdir(nc,nv),expected_nirdif(nc,nv),expected_reflected
  REAL(wp) :: alb_dir(nb,nc),alb_dif(nb,nc),old_alb_dir(nb,nc),old_alb_dif(nb,nc)
  REAL(wp) :: zero(nc,nl),rl(nc,nl),di(nc,nl),ds(nc,nl)
  LOGICAL :: mask(nc,nl,112)
  TYPE(ty_optical_props_2str) :: atmos,clouds,snow,sampled
  TYPE(ty_fluxes_byband) :: flux
  INTEGER :: kind,albedo_case,angle_case,b,checked,io,csv_unit
  REAL(wp) :: max_old_policy_delta,delta
  CHARACTER(LEN=32), PARAMETER :: kind_names(4)=[character(len=32) :: 'clear','liquid','ice','snow']
  CHARACTER(LEN=32), PARAMETER :: albedo_names(6)=[character(len=32) :: 'gray_0','gray_02','gray_099', &
       'gray_1','distinct','reversed']

  CALL get_command_argument(1,data_dir)
  CALL get_command_argument(2,csv_path)
  IF(LEN_TRIM(data_dir)==0) ERROR STOP 'usage: test_rrtmgp_spectral_surface DATA_DIRECTORY'
  csv_unit=output_unit
  IF(LEN_TRIM(csv_path)>0) THEN
    OPEN(NEWUNIT=csv_unit,FILE=TRIM(csv_path),STATUS='REPLACE',ACTION='WRITE',IOSTAT=io)
    IF(io/=0) ERROR STOP 'could not open spectral surface CSV'
  END IF
  CALL rrtmgp_init(TRIM(data_dir))
  CALL check_error(gases%init(gas_names))
  CALL load_and_init(gas_sw,TRIM(data_dir)//'/rrtmgp-gas-sw-g112.nc',gases)
  CALL load_cld_lutcoeff(cloud_sw,TRIM(data_dir)//'/rrtmgp-clouds-sw-bnd.nc')
  bands=gas_sw%get_band_lims_wavenumber()
  IF(SIZE(bands,1)/=2 .OR. SIZE(bands,2)/=nb) CALL fail('SW112 must expose exactly 14 bands')
  DO b=1,nb
    IF(ABS(bands(1,b)-expected_lo(b))>1.e-10_wp .OR. ABS(bands(2,b)-expected_hi(b))>1.e-10_wp) THEN
      WRITE(*,'(A,I0,2(A,F10.2),2(A,F10.2))') 'band ',b,' got ',bands(1,b),'..',bands(2,b), &
           ' expected ',expected_lo(b),'..',expected_hi(b)
      CALL fail('pinned SW112 band boundaries differ from the 14-band contract')
    END IF
  END DO
  IF(bands(1,10)/=12850._wp .OR. bands(2,10)/=16000._wp) CALL fail('band 10 is not the transition band')

  plev(1,:)=[1000._wp,700._wp,300._wp,1._wp]
  play(1,:)=[850._wp,500._wp,150._wp]
  tlay(1,:)=[285._wp,260._wp,230._wp]
  h2o(1,:)=[.01_wp,.003_wp,.0001_wp]
  co2=420.e-6_wp; o3(1,:)=[.5e-6_wp,1.e-6_wp,5.e-6_wp]
  n2o=330.e-9_wp; ch4=1.8e-6_wp; o2=.2095_wp
  solar=1361._wp
  max_old_policy_delta=0._wp; checked=0
  WRITE(csv_unit,'(A)') 'case,albedo,mu0,SWUP_surface,VISDIR_surface,VISDIF_surface,NIRDIR_surface,NIRDIF_surface,old_all_VIS_delta'
  DO kind=0,3
    DO albedo_case=1,6
      DO angle_case=1,2
        mu0(1)=MERGE(.65_wp,.35_wp,angle_case==1)
        CALL choose_albedo(albedo_case)
        CALL check_one(kind,albedo_case)
      END DO
    END DO
  END DO
  IF(max_old_policy_delta<1.e-3_wp) CALL fail('distinct albedos did not distinguish the old all-visible rule')
  WRITE(*,'(A,I0,A,ES12.4)') 'spectral surface contract passed; cases=',checked, &
       '; max old-policy surface-up difference (W/m2)=',max_old_policy_delta
  IF(csv_unit/=output_unit) CLOSE(csv_unit)

CONTAINS
  SUBROUTINE choose_albedo(which)
    INTEGER, INTENT(IN) :: which
    SELECT CASE(which)
    CASE(1); avdir=.0_wp; avdif=.0_wp; andir=.0_wp; andif=.0_wp
    CASE(2); avdir=.2_wp; avdif=.2_wp; andir=.2_wp; andif=.2_wp
    CASE(3); avdir=.99_wp; avdif=.99_wp; andir=.99_wp; andif=.99_wp
    CASE(4); avdir=1._wp; avdif=1._wp; andir=1._wp; andif=1._wp
    CASE(5); avdir=.78_wp; avdif=.61_wp; andir=.13_wp; andif=.27_wp
    CASE(6); avdir=.11_wp; avdif=.24_wp; andir=.83_wp; andif=.69_wp
    CASE DEFAULT; CALL fail('invalid albedo case')
    END SELECT
  END SUBROUTINE choose_albedo

  SUBROUTINE check_one(cloud_kind,alb_kind)
    INTEGER, INTENT(IN) :: cloud_kind,alb_kind
    CHARACTER(LEN=256) :: label
    CALL check_error(gases%init(gas_names))
    CALL check_error(gases%set_vmr('h2o',h2o)); CALL check_error(gases%set_vmr('co2',co2))
    CALL check_error(gases%set_vmr('o3',o3)); CALL check_error(gases%set_vmr('n2o',n2o))
    CALL check_error(gases%set_vmr('ch4',ch4)); CALL check_error(gases%set_vmr('o2',o2))
    CALL check_error(atmos%alloc_2str(nc,nl,gas_sw))
    CALL check_error(clouds%alloc_2str(nc,nl,cloud_sw))
    CALL check_error(snow%alloc_2str(nc,nl,cloud_sw))
    CALL check_error(sampled%alloc_2str(nc,nl,gas_sw))
    CALL check_error(gas_sw%gas_optics(play*100._wp,plev*100._wp,tlay,gases,atmos,toa))
    toa=toa*(solar/SUM(toa))

    alb_dir=0._wp; alb_dif=0._wp
    DO b=1,nb
      IF(b<=9) THEN
        alb_dir(b,:)=REAL(andir,wp); alb_dif(b,:)=REAL(andif,wp)
      ELSE IF(b==10) THEN
        alb_dir(b,:)=.5_wp*(REAL(andir,wp)+REAL(avdir,wp))
        alb_dif(b,:)=.5_wp*(REAL(andif,wp)+REAL(avdif,wp))
      ELSE
        alb_dir(b,:)=REAL(avdir,wp); alb_dif(b,:)=REAL(avdif,wp)
      END IF
    END DO
    old_alb_dir=alb_dir; old_alb_dif=alb_dif
    old_alb_dir(10,:)=REAL(avdir,wp); old_alb_dif(10,:)=REAL(avdif,wp)

    flux%flux_up=>fu; flux%flux_dn=>fd; flux%flux_dn_dir=>fdir
    flux%bnd_flux_dn=>bd; flux%bnd_flux_dn_dir=>bdir
    CALL check_error(rte_sw(atmos,.FALSE.,REAL(mu0,wp),toa,alb_dir,alb_dif,flux))
    expected_upc=fu; expected_dnc=fd
    cf=0._wp; lwp=0._wp; iwp=0._wp; swp=0._wp
    rel=10._wp; rei=30._wp; res=60._wp
    SELECT CASE(cloud_kind)
    CASE(0)
      CONTINUE
    CASE(1)
      cf(1,2)=1._wp; lwp(1,2)=120._wp
    CASE(2)
      cf(1,2)=1._wp; iwp(1,2)=80._wp
    CASE(3)
      cf(1,2)=1._wp; swp(1,2)=80._wp
    CASE DEFAULT
      CALL fail('invalid cloud kind')
    END SELECT
    zero=0._wp; rl=MAX(cloud_sw%get_min_radius_liq(),MIN(cloud_sw%get_max_radius_liq(),rel))
    di=MAX(cloud_sw%get_min_radius_ice(),MIN(cloud_sw%get_max_radius_ice(),2._wp*rei))
    ds=MAX(cloud_sw%get_min_radius_ice(),MIN(cloud_sw%get_max_radius_ice(),2._wp*res))
    CALL check_error(cloud_sw%cloud_optics(lwp,iwp,rl,di,clouds))
    CALL check_error(cloud_sw%cloud_optics(zero,swp,rl,ds,snow))
    CALL check_error(snow%increment(clouds))
    IF(cloud_kind/=0) CALL check_error(clouds%delta_scale())
    mask=.FALSE.
    IF(cloud_kind/=0) mask(1,2,:)=.TRUE. ! fully cloudy, deterministic and independent of overlap helper
    IF(cloud_kind/=0) THEN
      CALL check_error(draw_samples(mask,clouds,sampled))
      CALL check_error(sampled%increment(atmos))
    END IF
    CALL check_error(rte_sw(atmos,.FALSE.,REAL(mu0,wp),toa,alb_dir,alb_dif,flux))
    CALL check_finite(fu,fd,fdir,bd,bdir)
    expected_up=fu; expected_dn=fd; expected_direct=fdir
    CALL derive_band_fluxes()
    expected_reflected=SUM(alb_dir(:,1)*bdir(1,1,:)+ &
         alb_dif(:,1)*(bd(1,1,:)-bdir(1,1,:)))
    CALL check_close('reference surface reflected-band budget',RESHAPE([fu(1,1)],[1,1]), &
         RESHAPE([expected_reflected],[1,1]),3.e-5_wp)

    ! Old behavior is a test-only counterfactual: index 10 entirely visible.
    CALL check_error(rte_sw(atmos,.FALSE.,REAL(mu0,wp),toa,old_alb_dir,old_alb_dif,flux))
    old_up=fu
    delta=ABS(old_up(1,1)-expected_reflected)
    IF(alb_kind>=5) max_old_policy_delta=MAX(max_old_policy_delta,delta)

    ! Production adapter must agree with independent core oracle at every output.
    CALL rrtmgp_sw_column(REAL(play),REAL(plev),REAL(tlay),REAL(h2o),REAL(co2),REAL(o3), &
         REAL(n2o),REAL(ch4),REAL(o2),REAL(avdir),REAL(avdif),REAL(andir),REAL(andif), &
         REAL(mu0),REAL(solar),REAL(cf),REAL(lwp),REAL(iwp),REAL(swp),REAL(rel),REAL(rei),REAL(res), &
         4,2,173,wrf_up,wrf_dn,wrf_hr,wrf_upc,wrf_dnc,wrf_hrc,direct,diffuse,directc, &
         visdir,visdif,nirdir,nirdif)
    CALL check_close('RTE core vs adapter SW up',REAL(wrf_up,wp),expected_up,4.e-5_wp)
    CALL check_close('RTE core vs adapter SW down',REAL(wrf_dn,wp),expected_dn,4.e-5_wp)
    CALL check_close('RTE direct core vs adapter direct',REAL(direct,wp),expected_direct,4.e-5_wp)
    CALL check_close('RTE core direct+diffuse closure',REAL(direct+diffuse,wp),REAL(wrf_dn,wp),4.e-5_wp)
    CALL check_close('CCPP half-transition VIS direct',REAL(visdir,wp),expected_visdir,4.e-5_wp)
    CALL check_close('CCPP half-transition VIS diffuse',REAL(visdif,wp),expected_visdif,4.e-5_wp)
    CALL check_close('CCPP half-transition NIR direct',REAL(nirdir,wp),expected_nirdir,4.e-5_wp)
    CALL check_close('CCPP half-transition NIR diffuse',REAL(nirdif,wp),expected_nirdif,4.e-5_wp)
    IF(alb_kind<=4 .AND. delta>1.e-4_wp) CALL fail('gray-albedo old-policy counterfactual should be identical')
    IF(alb_kind>=5 .AND. delta<1.e-3_wp) CALL fail('distinct albedo did not produce a non-vacuous transition-band response')
    checked=checked+1
    CALL check_close('RTE core vs adapter SW clear up',REAL(wrf_upc,wp),expected_upc,4.e-5_wp)
    CALL check_close('RTE core vs adapter SW clear down',REAL(wrf_dnc,wp),expected_dnc,4.e-5_wp)
    WRITE(csv_unit,'(A,",",A,",",F4.2,6(",",ES12.4))') TRIM(kind_names(cloud_kind+1)), &
         TRIM(albedo_names(alb_kind)),mu0(1),wrf_up(1,1),visdir(1,1),visdif(1,1), &
         nirdir(1,1),nirdif(1,1),delta
  END SUBROUTINE check_one

  SUBROUTINE derive_band_fluxes()
    INTEGER :: band
    expected_visdir=0._wp; expected_visdif=0._wp; expected_nirdir=0._wp; expected_nirdif=0._wp
    DO band=1,nb
      IF(band<=9) THEN
        expected_nirdir=expected_nirdir+bdir(:,:,band)
        expected_nirdif=expected_nirdif+bd(:,:,band)-bdir(:,:,band)
      ELSE IF(band==10) THEN
        expected_nirdir=expected_nirdir+.5_wp*bdir(:,:,band)
        expected_nirdif=expected_nirdif+.5_wp*(bd(:,:,band)-bdir(:,:,band))
        expected_visdir=expected_visdir+.5_wp*bdir(:,:,band)
        expected_visdif=expected_visdif+.5_wp*(bd(:,:,band)-bdir(:,:,band))
      ELSE
        expected_visdir=expected_visdir+bdir(:,:,band)
        expected_visdif=expected_visdif+bd(:,:,band)-bdir(:,:,band)
      END IF
    END DO
  END SUBROUTINE derive_band_fluxes

  SUBROUTINE check_finite(a,b,c,d,e)
    REAL(wp), INTENT(IN) :: a(:,:),b(:,:),c(:,:),d(:,:,:),e(:,:,:)
    IF(.NOT.ALL(ieee_is_finite(a)).OR..NOT.ALL(ieee_is_finite(b)).OR. &
       .NOT.ALL(ieee_is_finite(c)).OR..NOT.ALL(ieee_is_finite(d)).OR. &
       .NOT.ALL(ieee_is_finite(e))) CALL fail('RTE core produced non-finite fluxes')
  END SUBROUTINE check_finite

  SUBROUTINE check_close(label,a,b,tol)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL(wp), INTENT(IN) :: a(:,:),b(:,:),tol
    IF(ANY(SHAPE(a)/=SHAPE(b))) CALL fail(TRIM(label)//' shape mismatch')
    IF(.NOT.ALL(ieee_is_finite(a)).OR..NOT.ALL(ieee_is_finite(b))) CALL fail(TRIM(label)//' non-finite')
    IF(MAXVAL(ABS(a-b))>tol*MAX(1._wp,MAXVAL(ABS(a)),MAXVAL(ABS(b)))) THEN
      WRITE(*,'(A,ES12.4)') TRIM(label)//' max error ',MAXVAL(ABS(a-b))
      CALL fail(TRIM(label))
    END IF
  END SUBROUTINE check_close

  SUBROUTINE check_error(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF(LEN_TRIM(message)>0) THEN
      WRITE(*,'(A)') TRIM(message)
      CALL fail('RRTMGP direct-core operation failed')
    END IF
  END SUBROUTINE check_error

  SUBROUTINE fail(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    WRITE(*,'(A)') 'FAIL: '//TRIM(message)
    ERROR STOP 1
  END SUBROUTINE fail
END PROGRAM test_rrtmgp_spectral_surface
