PROGRAM test_native_gas_columns
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan, ieee_positive_inf, ieee_is_finite
  USE module_ra_rrtmgp, ONLY: rrtmgp_init, rrtmgp_lw_column, rrtmgp_sw_column
  USE module_ra_rrtmgp_trace, ONLY: trace_start, trace_end
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=2, nl=4, nnative=3, nlev=nl+1
  CHARACTER(LEN=512) :: data_path
  CHARACTER(LEN=64) :: mode,invalid_phase
  REAL :: play(nc,nl),plev(nc,nlev),tlay(nc,nl),tlev(nc,nlev),tsfc(nc)
  REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl)
  REAL :: emis(nc,1),cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl)
  REAL :: rel(nc,nl),rei(nc,nl),res(nc,nl),native_mass(nc,nnative)
  REAL :: up(nc,nlev),dn(nc,nlev),hr(nc,nl),upc(nc,nlev),dnc(nc,nlev),hrc(nc,nl)
  REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  REAL :: direct(nc,nlev),diffuse(nc,nlev),directc(nc,nlev)
  REAL :: visdir(nc,nlev),visdif(nc,nlev),nirdir(nc,nlev),nirdif(nc,nlev)
  REAL :: bad_shape(nc+1,nnative),empty_mass(nc,0),wide_mass(nc,nl+1),invalid_mass(nc,nnative)
  INTEGER :: k

  CALL get_command_argument(1,data_path)
  CALL get_command_argument(2,mode)
  CALL get_command_argument(3,invalid_phase)
  IF(LEN_TRIM(invalid_phase)==0) invalid_phase='LW'
  IF(LEN_TRIM(data_path)==0) ERROR STOP 'usage: test_rrtmgp_native_gas_columns DATA_DIRECTORY [positive|invalid_case]'
  IF(LEN_TRIM(mode)==0) mode='positive'
  CALL initialize_inputs()
  CALL rrtmgp_init(TRIM(data_path))

  IF(TRIM(mode)/='positive') THEN
    CALL exercise_invalid(TRIM(mode))
    ERROR STOP 'invalid native gas-column input was accepted'
  END IF

  CALL trace_start('LW',1,1)
  CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,777,up,dn,hr,upc,dnc,hrc, &
       native_dry_layer_mass_kg_m2=native_mass)
  CALL trace_end('LW')
  CALL assert_finite('LW native gas column',up,dn,hr)
  CALL perturb_pressure_and_vapor()
  CALL trace_start('LW',1,1)
  CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,778,up,dn,hr,upc,dnc,hrc, &
       native_dry_layer_mass_kg_m2=native_mass)
  CALL trace_end('LW')
  CALL assert_finite('LW perturbed native gas column',up,dn,hr)

  CALL restore_pressure_and_vapor()
  CALL trace_start('SW',1,1)
  CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,777,up,dn,hr,upc,dnc,hrc, &
       direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
       native_dry_layer_mass_kg_m2=native_mass)
  CALL trace_end('SW')
  CALL assert_finite('SW native gas column',up,dn,hr)
  CALL perturb_pressure_and_vapor()
  CALL trace_start('SW',1,1)
  CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
       cf,lwp,iwp,swp,rel,rei,res,4,2,778,up,dn,hr,upc,dnc,hrc, &
       direct,diffuse,directc,visdir,visdif,nirdir,nirdif, &
       native_dry_layer_mass_kg_m2=native_mass)
  CALL trace_end('SW')
  CALL assert_finite('SW perturbed native gas column',up,dn,hr)
  WRITE(*,'(A)') 'NATIVE_GAS_COLUMNS_FIXTURE_PASS'

CONTAINS

  SUBROUTINE initialize_inputs()
    plev(1,:)=[1000.,800.,500.,200.,1.]
    plev(2,:)=[990.,760.,490.,180.,0.8]
    play(1,:)=[900.,650.,350.,100.5]
    play(2,:)=[875.,625.,335.,90.4]
    tlay(1,:)=[288.,270.,245.,220.]
    tlay(2,:)=[286.,268.,243.,218.]
    tlev(1,:)=[292.,280.,255.,232.,210.]
    tlev(2,:)=[290.,278.,253.,230.,208.]
    tsfc=[292.,290.]
    h2o(1,:)=[.008,.004,.001,.0001]
    h2o(2,:)=[.007,.0035,.0008,.00008]
    co2=420.e-6; o3(1,:)=[.5e-6,1.e-6,3.e-6,5.e-6]; o3(2,:)=o3(1,:)
    n2o=330.e-9; ch4=1.8e-6; o2=.2095
    emis=.98; cf=0.; lwp=0.; iwp=0.; swp=0.; rel=10.; rei=30.; res=30.
    native_mass(1,:)=[80.,110.,140.]
    native_mass(2,:)=[90.,120.,150.]
    avdir=[.15,.20]; avdif=[.10,.12]; andir=[.25,.30]; andif=[.20,.22]
    mu0=[.65,.52]; solar=1361.
  END SUBROUTINE initialize_inputs

  SUBROUTINE perturb_pressure_and_vapor()
    plev(1,:)=[1000.,700.,350.,100.,0.5]
    plev(2,:)=[995.,720.,360.,110.,0.4]
    play(1,:)=[850.,525.,225.,50.25]
    play(2,:)=[857.5,540.,235.,55.2]
    h2o(1,:)=[.016,.009,.003,.0002]
    h2o(2,:)=[.014,.008,.0025,.00015]
  END SUBROUTINE perturb_pressure_and_vapor

  SUBROUTINE restore_pressure_and_vapor()
    plev(1,:)=[1000.,800.,500.,200.,1.]
    plev(2,:)=[990.,760.,490.,180.,0.8]
    play(1,:)=[900.,650.,350.,100.5]
    play(2,:)=[875.,625.,335.,90.4]
    h2o(1,:)=[.008,.004,.001,.0001]
    h2o(2,:)=[.007,.0035,.0008,.00008]
  END SUBROUTINE restore_pressure_and_vapor

  SUBROUTINE exercise_invalid(case_name)
    CHARACTER(LEN=*), INTENT(IN) :: case_name
    invalid_mass=native_mass
    SELECT CASE(case_name)
    CASE('shape')
      bad_shape=1.
      CALL call_checked(bad_shape)
    CASE('empty')
      CALL call_checked(empty_mass)
    CASE('too_wide')
      wide_mass=1.
      CALL call_checked(wide_mass)
    CASE('zero')
      invalid_mass(1,1)=0.
      CALL call_checked(invalid_mass)
    CASE('negative')
      invalid_mass(1,2)=-1.
      CALL call_checked(invalid_mass)
    CASE('nan')
      invalid_mass(1,1)=ieee_value(0.,ieee_quiet_nan)
      CALL call_checked(invalid_mass)
    CASE('inf')
      invalid_mass(2,3)=ieee_value(0.,ieee_positive_inf)
      CALL call_checked(invalid_mass)
    CASE DEFAULT
      ERROR STOP 'unknown invalid native dry mass mode'
    END SELECT
  END SUBROUTINE exercise_invalid

  SUBROUTINE call_checked(mass)
    REAL, INTENT(IN) :: mass(:,:)
    SELECT CASE(TRIM(invalid_phase))
    CASE('LW')
      CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
           cf,lwp,iwp,swp,rel,rei,res,4,2,777,up,dn,hr,upc,dnc,hrc, &
           native_dry_layer_mass_kg_m2=mass)
    CASE('SW','SW_NIGHT')
      IF(TRIM(invalid_phase)=='SW_NIGHT') mu0=0.
      CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
           cf,lwp,iwp,swp,rel,rei,res,4,2,777,up,dn,hr,upc,dnc,hrc, &
           direct,diffuse,directc,visdir,visdif,nirdir,nirdif,native_dry_layer_mass_kg_m2=mass)
    CASE DEFAULT
      ERROR STOP 'invalid test phase'
    END SELECT
  END SUBROUTINE call_checked

  SUBROUTINE assert_finite(label,a,b,c)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: a(:,:),b(:,:),c(:,:)
    IF(ANY(.NOT.ieee_is_finite(a)).OR.ANY(.NOT.ieee_is_finite(b)).OR. &
       ANY(.NOT.ieee_is_finite(c))) THEN
      WRITE(*,'(A)') TRIM(label)//' contains non-finite flux/heating'
      ERROR STOP 'non-finite native gas-column result'
    END IF
  END SUBROUTINE assert_finite

END PROGRAM test_native_gas_columns
