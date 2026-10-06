! SPDX-License-Identifier: Apache-2.0
! Exploratory shortwave benchmark of three cloud/precipitation delta-scaling
! compositions. At pinned NCAR/ccpp-physics commit
! 3e6660c6df54e95a0871e990c2294dd397ae3860,
! physics/Radiation/RRTMGP/rrtmgp_sw_main.F90:440-478 manually delta-scales
! precipitation before adding it to cloud optics; the later whole-cloud call
! at line 606 is commented out. Thus the pinned routine implements C+D(P),
! while the other two benchmark policies are counterfactual comparisons.
! This exploratory benchmark does not recommend a production policy.
PROGRAM test_rrtmgp_delta_policy
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE mo_rte_kind, ONLY: wp
  USE mo_gas_concentrations, ONLY: ty_gas_concs
  USE mo_gas_optics_rrtmgp, ONLY: ty_gas_optics_rrtmgp
  USE mo_cloud_optics_rrtmgp, ONLY: ty_cloud_optics_rrtmgp
  USE mo_optical_props, ONLY: ty_optical_props_2str
  USE mo_fluxes_byband, ONLY: ty_fluxes_byband
  USE mo_rte_sw, ONLY: rte_sw
  USE mo_heating_rates, ONLY: compute_heating_rate
  USE mo_load_coefficients, ONLY: load_and_init
  USE mo_load_cloud_coefficients, ONLY: load_cld_lutcoeff
  USE module_ra_rrtmgp_precip, ONLY: rrtmgp_precip_sw_optics, RRTMGP_SW_NBAND
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=1,nl=1,ni=nl+1,nb=RRTMGP_SW_NBAND
  CHARACTER(LEN=512) :: data_dir,output_path
  CHARACTER(LEN=24), PARAMETER :: names(9)=[CHARACTER(LEN=24) :: &
       'liquid','ice','rain','snow','liquid_plus_rain','ice_plus_snow','mixed', &
       'graupel_omitted','graupel_as_snow_assumed']
  CHARACTER(LEN=24), PARAMETER :: policies(3)=[CHARACTER(LEN=24) :: &
       'D(C)+D(P)','C+D(P)','D(C+P)']
  REAL(wp) :: play(nc,nl),plev(nc,ni),tlay(nc,nl),h2o(nc,nl),co2(nc,nl),o3(nc,nl)
  REAL(wp) :: n2o(nc,nl),ch4(nc,nl),o2(nc,nl),lwp(nc,nl),iwp(nc,nl),rwp(nc,nl),swp(nc,nl)
  REAL(wp) :: rel(nc,nl),rei(nc,nl),res(nc,nl),mu0(nc),solar
  REAL(wp), ALLOCATABLE :: toa(:,:)
  REAL(wp) :: albedo_dir(nb,nc),albedo_dif(nb,nc),bands(2,nb)
  REAL(wp) :: p_tau_raw(nc,nl,nb),p_ssa_raw(nc,nl,nb),p_g_raw(nc,nl,nb)
  REAL(wp) :: p_tau_delta(nc,nl,nb),p_ssa_delta(nc,nl,nb),p_g_delta(nc,nl,nb)
  REAL(wp) :: c_tau_raw(nc,nl,nb),c_ssa_raw(nc,nl,nb),c_g_raw(nc,nl,nb)
  REAL(wp) :: out_tau(nc,nl,nb),out_ssa(nc,nl,nb),out_g(nc,nl,nb)
  REAL(wp), TARGET :: up(nc,ni),dn(nc,ni),direct(nc,ni),bdn(nc,ni,nb),bdir(nc,ni,nb)
  REAL(wp) :: heat(nc,nl),max_heat
  INTEGER :: u,ios,rough,angle,scenario,policy,band,ierr,b
  REAL(wp), PARAMETER :: angles(3)=[0.2_wp,0.5_wp,0.9_wp]
  TYPE(ty_gas_concs) :: gases
  TYPE(ty_gas_optics_rrtmgp) :: gas_sw
  TYPE(ty_cloud_optics_rrtmgp) :: cloud_sw
  TYPE(ty_optical_props_2str) :: cloud,cloud_gpt,precip,atmos
  TYPE(ty_fluxes_byband) :: flux
  CHARACTER(LEN=3), PARAMETER :: gas_names(6)=['h2o','co2','o3 ','n2o','ch4','o2 ']
  CHARACTER(LEN=256) :: err

  CALL get_command_argument(1,data_dir)
  CALL get_command_argument(2,output_path)
  IF(LEN_TRIM(data_dir)==0.OR.LEN_TRIM(output_path)==0) &
    ERROR STOP 'usage: test_delta_policy DATA_DIRECTORY OUTPUT_CSV'

  plev(1,:)=[1000._wp,400._wp]
  play(1,1)=700._wp; tlay(1,1)=260._wp
  h2o(1,1)=2.e-3_wp; co2=420.e-6_wp; o3=1.e-6_wp
  n2o=330.e-9_wp; ch4=1.8e-6_wp; o2=0.2095_wp
  rel=10._wp; rei=60._wp; res=30._wp
  solar=1361._wp
  CALL check_error(gases%init(gas_names))
  CALL load_and_init(gas_sw,TRIM(data_dir)//'/rrtmgp-gas-sw-g112.nc',gases)
  CALL load_cld_lutcoeff(cloud_sw,TRIM(data_dir)//'/rrtmgp-clouds-sw-bnd.nc')
  ALLOCATE(toa(nc,gas_sw%get_ngpt()))
  CALL check_error(gases%set_vmr('h2o',h2o)); CALL check_error(gases%set_vmr('co2',co2))
  CALL check_error(gases%set_vmr('o3',o3)); CALL check_error(gases%set_vmr('n2o',n2o))
  CALL check_error(gases%set_vmr('ch4',ch4)); CALL check_error(gases%set_vmr('o2',o2))
  bands=gas_sw%get_band_lims_wavenumber()
  albedo_dir=0.2_wp; albedo_dif=0.2_wp

  OPEN(NEWUNIT=u,FILE=TRIM(output_path),STATUS='REPLACE',ACTION='WRITE',IOSTAT=ios)
  IF(ios/=0) ERROR STOP 'could not open delta-policy CSV'
  WRITE(u,'(A)') 'case,roughness,mu0,policy,band,band_lo_cm1,band_hi_cm1,'// &
       'cloud_tau_raw,cloud_ssa_raw,cloud_g_raw,precip_tau_raw,precip_ssa_raw,precip_g_raw,'// &
       'combined_tau,combined_ssa,combined_g,surface_dn_w_m2,surface_up_w_m2,'// &
       'toa_dn_w_m2,toa_up_w_m2,surface_direct_w_m2,max_abs_heating_k_day'

  DO scenario=1,SIZE(names)
    DO rough=1,3
      CALL check_error(cloud_sw%set_ice_roughness(rough))
      DO angle=1,SIZE(angles)
        mu0=angles(angle)
        CALL set_case(scenario)
        ! Capture C and P independently before any delta transformation.
        CALL check_error(cloud%alloc_2str(nc,nl,cloud_sw))
        CALL check_error(cloud_sw%cloud_optics(lwp,iwp,rel,rei,cloud))
        c_tau_raw=cloud%tau; c_ssa_raw=cloud%ssa; c_g_raw=cloud%g
        CALL rrtmgp_precip_sw_optics(rwp,swp,res,bands,p_tau_delta,p_ssa_delta,p_g_delta,ierr, &
             raw_tau=p_tau_raw,raw_ssa=p_ssa_raw,raw_asymmetry=p_g_raw)
        CALL require(ierr==0,'precip optics returned an error')

        DO policy=1,3
          CALL run_policy(policy)
          IF(.NOT.ALL(ieee_is_finite(up)).OR..NOT.ALL(ieee_is_finite(dn)).OR. &
             .NOT.ALL(ieee_is_finite(heat)).OR..NOT.ALL(ieee_is_finite(out_tau)).OR. &
             .NOT.ALL(ieee_is_finite(out_ssa)).OR..NOT.ALL(ieee_is_finite(out_g))) &
             ERROR STOP 'delta-policy benchmark produced non-finite values'
          max_heat=MAXVAL(ABS(heat))
          DO b=1,nb
            WRITE(u,'(A,",",I0,",",ES16.8E3,",",A,",",I0,",",20(ES16.8E3,:,","))') &
              TRIM(names(scenario)),rough,angles(angle),TRIM(policies(policy)),b, &
              bands(1,b),bands(2,b),c_tau_raw(1,1,b),c_ssa_raw(1,1,b),c_g_raw(1,1,b), &
              p_tau_raw(1,1,b),p_ssa_raw(1,1,b),p_g_raw(1,1,b), &
              out_tau(1,1,b),out_ssa(1,1,b),out_g(1,1,b),dn(1,1),up(1,1), &
              dn(1,ni),up(1,ni),direct(1,1),max_heat
          END DO
        END DO
      END DO
    END DO
  END DO
  CLOSE(u)
  WRITE(*,'(A,A)') 'Delta policy benchmark written: ',TRIM(output_path)

CONTAINS
  SUBROUTINE set_case(which)
    INTEGER, INTENT(IN) :: which
    lwp=0._wp; iwp=0._wp; rwp=0._wp; swp=0._wp
    SELECT CASE(which)
    CASE(1); lwp=100._wp
    CASE(2); iwp=100._wp
    CASE(3); rwp=100._wp
    CASE(4); swp=100._wp
    CASE(5); lwp=100._wp; rwp=100._wp
    CASE(6); iwp=100._wp; swp=100._wp
    CASE(7); lwp=50._wp; iwp=50._wp; rwp=50._wp; swp=50._wp
    CASE(8); ! 100 g/m2 of graupel is omitted from optics by design.
    CASE(9); ! Counterfactual: same 100 g/m2 treated as snow at native res=30 um.
      swp=100._wp
    CASE DEFAULT
      ERROR STOP 'invalid scenario index'
    END SELECT
  END SUBROUTINE set_case

  SUBROUTINE run_policy(which)
    INTEGER, INTENT(IN) :: which
    CALL check_error(cloud%alloc_2str(nc,nl,cloud_sw))
    CALL check_error(cloud_sw%cloud_optics(lwp,iwp,rel,rei,cloud))
    CALL check_error(precip%alloc_2str(nc,nl,cloud_sw))
    SELECT CASE(which)
    CASE(1) ! D(C) + D(P): current adapter composition.
      CALL check_error(cloud%delta_scale())
      precip%tau=p_tau_delta; precip%ssa=p_ssa_delta; precip%g=p_g_delta
      CALL check_error(precip%increment(cloud))
    CASE(2) ! C + D(P): cloud LUT remains unscaled.
      precip%tau=p_tau_delta; precip%ssa=p_ssa_delta; precip%g=p_g_delta
      CALL check_error(precip%increment(cloud))
    CASE(3) ! D(C+P): combine raw cloud and raw precip, then scale once.
      precip%tau=p_tau_raw; precip%ssa=p_ssa_raw; precip%g=p_g_raw
      CALL check_error(precip%increment(cloud))
      CALL check_error(cloud%delta_scale())
    CASE DEFAULT
      ERROR STOP 'invalid delta policy index'
    END SELECT
    out_tau=cloud%tau; out_ssa=cloud%ssa; out_g=cloud%g

    CALL check_error(atmos%alloc_2str(nc,nl,gas_sw))
    CALL check_error(cloud_gpt%alloc_2str(nc,nl,gas_sw))
    DO b=1,gas_sw%get_ngpt()
      band=gas_sw%convert_gpt2band(b)
      cloud_gpt%tau(:,:,b)=cloud%tau(:,:,band)
      cloud_gpt%ssa(:,:,b)=cloud%ssa(:,:,band)
      cloud_gpt%g(:,:,b)=cloud%g(:,:,band)
    END DO
    CALL check_error(gas_sw%gas_optics(play*100._wp,plev*100._wp,tlay,gases,atmos,toa))
    IF(SUM(toa(1,:))<=0._wp) ERROR STOP 'TOA solar spectrum is not positive'
    toa=toa*(solar/SUM(toa(1,:)))
    CALL check_error(cloud_gpt%increment(atmos))
    flux%flux_up=>up; flux%flux_dn=>dn; flux%flux_dn_dir=>direct
    flux%bnd_flux_dn=>bdn; flux%bnd_flux_dn_dir=>bdir
    CALL check_error(rte_sw(atmos,.FALSE.,mu0,toa,albedo_dir,albedo_dif,flux))
    CALL check_error(compute_heating_rate(up,dn,plev*100._wp,heat))
    heat=heat*86400._wp
  END SUBROUTINE run_policy

  SUBROUTINE check_error(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF(LEN_TRIM(message)>0) THEN
      WRITE(*,'(A)') TRIM(message)
      ERROR STOP 1
    END IF
  END SUBROUTINE check_error

  SUBROUTINE require(condition,message)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF(.NOT.condition) THEN
      WRITE(*,'(A)') TRIM(message)
      ERROR STOP 1
    END IF
  END SUBROUTINE require
END PROGRAM test_rrtmgp_delta_policy
