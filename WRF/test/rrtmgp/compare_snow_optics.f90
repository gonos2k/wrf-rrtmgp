! SPDX-License-Identifier: Apache-2.0
!
! Exploratory source comparison only. The CCPP snow-optics constants and
! formulas below are attributed to Apache-2.0 NCAR/ccpp-physics at
! 3e6660c6df54e95a0871e990c2294dd397ae3860:
!   physics/Radiation/RRTMGP/rrtmgp_sw_cloud_optics.F90 (a0s/a1s/b0s/b1s/c0s)
!   physics/Radiation/RRTMGP/rrtmgp_sw_main.F90 (SW snow formula/delta scaling)
!   physics/Radiation/RRTMGP/rrtmgp_lw_cloud_optics.F90 (LW snow constants)
!   physics/Radiation/RRTMGP/rrtmgp_lw_main.F90 (LW snow tau formula)
! This executable calls the pinned RTE-RRTMGP cloud-optics library directly;
! it does not use the WRF adapter and does not propose a production change.
! Equations are evaluated in wp; default-real CCPP literals are not emulated
! bit for bit. Radius definitions and precipitation fractions remain host contracts.
PROGRAM compare_snow_optics
  USE mo_rte_kind, ONLY: wp
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite, ieee_value, ieee_quiet_nan
  USE mo_cloud_optics_rrtmgp, ONLY: ty_cloud_optics_rrtmgp
  USE mo_optical_props, ONLY: ty_optical_props_1scl, ty_optical_props_2str
  USE mo_load_cloud_coefficients, ONLY: load_cld_lutcoeff
  IMPLICIT NONE

  INTEGER, PARAMETER :: nsw_band = 14
  REAL(wp), PARAMETER :: snow_path = 50._wp
  REAL(wp), PARAMETER :: radii(4) = [10._wp, 30._wp, 60._wp, 130._wp]
  REAL(wp), PARAMETER :: a0s = 0._wp, a1s = 1.5_wp
  REAL(wp), PARAMETER :: snow_radius_factor = 1.0315_wp
  REAL(wp), PARAMETER :: snow_tau_factor_sw = 1.09087_wp
  REAL(wp), PARAMETER :: snow_tau_factor_lw = 1.05756_wp
  REAL(wp), PARAMETER :: snow_abs_lw = 1.5_wp
  REAL(wp), PARAMETER :: sw_bounds(2,nsw_band) = RESHAPE([ &
    820._wp,2680._wp, 2680._wp,3250._wp, 3250._wp,4000._wp, 4000._wp,4650._wp, &
    4650._wp,5150._wp, 5150._wp,6150._wp, 6150._wp,7700._wp, 7700._wp,8050._wp, &
    8050._wp,12850._wp, 12850._wp,16000._wp, 16000._wp,22650._wp, 22650._wp,29000._wp, &
    29000._wp,38000._wp, 38000._wp,50000._wp ], [2,nsw_band])
  REAL(wp), PARAMETER :: b0s(nsw_band) = [ &
    .460_wp,.460_wp,.460_wp,.460_wp,.460_wp,.460_wp,.460_wp,.460_wp, &
    0._wp,0._wp,0._wp,0._wp,0._wp,0._wp ]
  REAL(wp), PARAMETER :: b1s(nsw_band) = [ &
    0._wp,0._wp,0._wp,0._wp,0._wp,0._wp,0._wp,0._wp, &
    1.62e-5_wp,1.62e-5_wp,0._wp,0._wp,0._wp,0._wp ]
  REAL(wp), PARAMETER :: c0s(nsw_band) = [ &
    .970_wp,.970_wp,.970_wp,.970_wp,.970_wp,.970_wp,.970_wp,.970_wp, &
    .970_wp,.970_wp,.700_wp,.700_wp,.700_wp,.700_wp ]

  CHARACTER(LEN=512) :: data_dir, sw_file, lw_file
  INTEGER :: arg_count, roughness, ir, ib, u
  REAL(wp) :: radius, input_diameter, used_diameter, lw_used_diameter, minimum_diameter, maximum_diameter
  REAL(wp) :: ccpp_tau, ccpp_ssa, ccpp_g, ccpp_tau_scaled, ccpp_ssa_scaled, ccpp_g_scaled
  REAL(wp) :: tau_rain, tau_snow, ssa_rain, ssa_snow, g_rain, g_snow
  REAL(wp) :: ssa_tau, g_ssa_tau, za1, za2, tiny_floor
  REAL(wp) :: nan_value
  REAL(wp), ALLOCATABLE :: one(:,:), zero(:,:), ice_radius(:,:), band_limits(:,:)
  REAL(wp), ALLOCATABLE :: sw_raw_tau(:,:,:), sw_raw_ssa(:,:,:), sw_raw_g(:,:,:)
  REAL(wp), ALLOCATABLE :: sw_scaled_tau(:,:,:), sw_scaled_ssa(:,:,:), sw_scaled_g(:,:,:)
  REAL(wp), ALLOCATABLE :: lw_raw_tau(:,:,:)
  TYPE(ty_cloud_optics_rrtmgp) :: cloud_sw, cloud_lw
  TYPE(ty_optical_props_2str) :: optics_sw
  TYPE(ty_optical_props_1scl) :: optics_lw
  CHARACTER(LEN=128) :: err

  arg_count = COMMAND_ARGUMENT_COUNT()
  IF (arg_count /= 1) ERROR STOP 'usage: compare_snow_optics RRTMGP_DATA_DIR'
  CALL GET_COMMAND_ARGUMENT(1, data_dir)
  IF (LEN_TRIM(data_dir) == 0) ERROR STOP 'empty coefficient data directory'
  sw_file = TRIM(data_dir)//'/rrtmgp-clouds-sw-bnd.nc'
  lw_file = TRIM(data_dir)//'/rrtmgp-clouds-lw-bnd.nc'

  CALL load_cld_lutcoeff(cloud_sw, TRIM(sw_file))
  CALL load_cld_lutcoeff(cloud_lw, TRIM(lw_file))
  IF (cloud_sw%get_nband() /= nsw_band) ERROR STOP 'SW LUT does not contain 14 bands'
  band_limits = cloud_sw%get_band_lims_wavenumber()
  IF (ANY(ABS(band_limits - sw_bounds) > 0.01_wp)) &
    ERROR STOP 'SW coefficient band bounds differ from pinned CCPP comparison map'

  ALLOCATE(one(1,1), zero(1,1), ice_radius(1,1))
  ALLOCATE(sw_raw_tau(1,1,nsw_band), sw_raw_ssa(1,1,nsw_band), sw_raw_g(1,1,nsw_band))
  ALLOCATE(sw_scaled_tau(1,1,nsw_band), sw_scaled_ssa(1,1,nsw_band), sw_scaled_g(1,1,nsw_band))
  ALLOCATE(lw_raw_tau(1,1,cloud_lw%get_nband()))
  one = snow_path
  zero = 0._wp
  nan_value = ieee_value(0._wp, ieee_quiet_nan)
  tiny_floor = 1.e-12_wp

  CALL check_error(optics_sw%alloc_2str(1,1,cloud_sw))
  CALL check_error(optics_lw%alloc_1scl(1,1,cloud_lw))

  WRITE(*,'(A)') 'phase,band,wavenumber_low_cm1,wavenumber_high_cm1,snow_radius_um,input_diameter_um,used_diameter_um,roughness,'// &
    'lut_raw_tau,lut_raw_ssa,lut_raw_g,lut_scaled_tau,lut_scaled_ssa,lut_scaled_g,'// &
    'ccpp_raw_tau,ccpp_raw_ssa,ccpp_raw_g,ccpp_scaled_tau,ccpp_scaled_ssa,ccpp_scaled_g'

  DO roughness = 1, 3
    CALL check_error(cloud_sw%set_ice_roughness(roughness))
    CALL check_error(cloud_lw%set_ice_roughness(roughness))
    minimum_diameter = cloud_sw%get_min_radius_ice()
    maximum_diameter = cloud_sw%get_max_radius_ice()
    DO ir = 1, SIZE(radii)
      radius = radii(ir)
      input_diameter = 2._wp * radius
      used_diameter = MAX(minimum_diameter, MIN(maximum_diameter, input_diameter))
      ice_radius = used_diameter

      ! Same numeric 50 g m-2 path, represented as cloud ice for the LUT and
      ! snow for the CCPP equations. Cloud fraction is implicitly 1 here.
      CALL check_error(cloud_sw%cloud_optics(zero, one, zero, ice_radius, optics_sw))
      sw_raw_tau = optics_sw%tau
      sw_raw_ssa = optics_sw%ssa
      sw_raw_g = optics_sw%g
      CALL check_finite_and_physical(sw_raw_tau, sw_raw_ssa, sw_raw_g, 'raw SW LUT')
      CALL check_error(optics_sw%delta_scale())
      sw_scaled_tau = optics_sw%tau
      sw_scaled_ssa = optics_sw%ssa
      sw_scaled_g = optics_sw%g
      CALL check_finite_and_physical(sw_scaled_tau, sw_scaled_ssa, sw_scaled_g, 'scaled SW LUT')

      minimum_diameter = cloud_lw%get_min_radius_ice()
      maximum_diameter = cloud_lw%get_max_radius_ice()
      lw_used_diameter = MAX(minimum_diameter, MIN(maximum_diameter, input_diameter))
      ice_radius = lw_used_diameter
      CALL check_error(cloud_lw%cloud_optics(zero, one, zero, ice_radius, optics_lw))
      lw_raw_tau = optics_lw%tau
      IF (ANY(.NOT. ieee_is_finite(lw_raw_tau)) .OR. ANY(lw_raw_tau < 0._wp)) &
        ERROR STOP 'nonphysical LW LUT optical depth'

      tau_rain = 0._wp
      IF (radius > 10._wp) THEN
        tau_snow = snow_path * snow_tau_factor_sw * (a0s + a1s/(snow_radius_factor*radius))
      ELSE
        tau_snow = 0._wp
      END IF
      DO ib = 1, nsw_band
        ! Reproduce CCPP rrtmgp_sw_main.F90's precipitation combination and
        ! delta scaling literally, including its small floors at zero path.
        ssa_rain = tau_rain * (1._wp - 0._wp)
        g_rain = ssa_rain * 0._wp
        ssa_snow = tau_snow * (1._wp - (b0s(ib) + b1s(ib)*snow_radius_factor*radius))
        g_snow = ssa_snow * c0s(ib)
        ccpp_tau = MAX(tiny_floor, tau_rain + tau_snow)
        ssa_tau = MAX(tiny_floor, ssa_rain + ssa_snow)
        g_ssa_tau = MAX(tiny_floor, g_rain + g_snow)
        ccpp_ssa = MIN(1._wp - 1.e-6_wp, ssa_tau / ccpp_tau)
        ccpp_g = g_ssa_tau / MAX(tiny_floor, ssa_tau)
        za1 = ccpp_g * ccpp_g
        za2 = ccpp_ssa * za1
        ccpp_tau_scaled = (1._wp - za2) * ccpp_tau
        ccpp_ssa_scaled = (ccpp_ssa - za2) / (1._wp - za2)
        ccpp_g_scaled = ccpp_g / (1._wp + ccpp_g)
        CALL check_ccpp(ccpp_tau, ccpp_ssa, ccpp_g, ccpp_tau_scaled, ccpp_ssa_scaled, ccpp_g_scaled)
        CALL emit_row('SW', ib, sw_bounds(1,ib), sw_bounds(2,ib), radius, input_diameter, used_diameter, &
          roughness, sw_raw_tau(1,1,ib), sw_raw_ssa(1,1,ib), sw_raw_g(1,1,ib), &
          sw_scaled_tau(1,1,ib), sw_scaled_ssa(1,1,ib), sw_scaled_g(1,1,ib), &
          ccpp_tau, ccpp_ssa, ccpp_g, ccpp_tau_scaled, ccpp_ssa_scaled, ccpp_g_scaled)
      END DO

      IF (cloud_lw%get_nband() < 1) ERROR STOP 'LW LUT has no bands'
      IF (radius > 10._wp) THEN
        tau_snow = snow_abs_lw * snow_tau_factor_lw * snow_path / radius
      ELSE
        tau_snow = 0._wp
      END IF
      IF (.NOT. ieee_is_finite(tau_snow) .OR. tau_snow < 0._wp) ERROR STOP 'invalid CCPP LW snow tau'
      band_limits = cloud_lw%get_band_lims_wavenumber()
      DO ib = 1, cloud_lw%get_nband()
        CALL emit_row('LW', ib, band_limits(1,ib), band_limits(2,ib), radius, input_diameter, lw_used_diameter, &
          roughness, lw_raw_tau(1,1,ib), nan_value, nan_value, lw_raw_tau(1,1,ib), nan_value, nan_value, &
          tau_snow, nan_value, nan_value, tau_snow, nan_value, nan_value)
      END DO
    END DO
  END DO

CONTAINS

  SUBROUTINE check_error(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (LEN_TRIM(message) /= 0) THEN
      WRITE(*,'(A)') TRIM(message)
      STOP 1
    END IF
  END SUBROUTINE check_error

  SUBROUTINE check_finite_and_physical(tau, ssa, asymmetry, label)
    REAL(wp), INTENT(IN) :: tau(:,:,:), ssa(:,:,:), asymmetry(:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: label
    IF (ANY(.NOT. ieee_is_finite(tau)) .OR. ANY(.NOT. ieee_is_finite(ssa)) .OR. &
        ANY(.NOT. ieee_is_finite(asymmetry))) THEN
      WRITE(*,'(A)') 'non-finite '//TRIM(label)
      STOP 1
    END IF
    IF (ANY(tau < 0._wp) .OR. ANY(ssa < 0._wp) .OR. ANY(ssa > 1._wp) .OR. &
        ANY(asymmetry < -1._wp) .OR. ANY(asymmetry > 1._wp)) THEN
      WRITE(*,'(A)') 'out-of-range '//TRIM(label)
      STOP 1
    END IF
  END SUBROUTINE check_finite_and_physical

  SUBROUTINE check_ccpp(tau, ssa, asymmetry, tau_scaled, ssa_scaled, asymmetry_scaled)
    REAL(wp), INTENT(IN) :: tau, ssa, asymmetry, tau_scaled, ssa_scaled, asymmetry_scaled
    IF (ANY(.NOT. ieee_is_finite([tau,ssa,asymmetry,tau_scaled,ssa_scaled,asymmetry_scaled]))) &
      ERROR STOP 'non-finite CCPP SW snow properties'
    IF (tau < 0._wp .OR. tau_scaled < 0._wp .OR. ssa < 0._wp .OR. ssa > 1._wp .OR. &
        ssa_scaled < 0._wp .OR. ssa_scaled > 1._wp .OR. asymmetry < -1._wp .OR. &
        asymmetry > 1._wp .OR. asymmetry_scaled < -1._wp .OR. asymmetry_scaled > 1._wp) &
      ERROR STOP 'out-of-range CCPP SW snow properties'
  END SUBROUTINE check_ccpp

  SUBROUTINE emit_row(phase, band, lower, upper, snow_r, diam_in, diam_used, ice_rough, &
      lut_tau, lut_ssa, lut_g, lut_tau_scaled, lut_ssa_scaled, lut_g_scaled, &
      ref_tau, ref_ssa, ref_g, ref_tau_scaled, ref_ssa_scaled, ref_g_scaled)
    CHARACTER(LEN=*), INTENT(IN) :: phase
    INTEGER, INTENT(IN) :: band, ice_rough
    REAL(wp), INTENT(IN) :: lower, upper, snow_r, diam_in, diam_used
    REAL(wp), INTENT(IN) :: lut_tau, lut_ssa, lut_g, lut_tau_scaled, lut_ssa_scaled, lut_g_scaled
    REAL(wp), INTENT(IN) :: ref_tau, ref_ssa, ref_g, ref_tau_scaled, ref_ssa_scaled, ref_g_scaled
    WRITE(*,'(A,",",I0,",",17(ES16.8E3,","),ES16.8E3)') TRIM(phase), band, &
      lower, upper, snow_r, diam_in, diam_used, REAL(ice_rough,wp), &
      lut_tau, lut_ssa, lut_g, lut_tau_scaled, lut_ssa_scaled, lut_g_scaled, &
      ref_tau, ref_ssa, ref_g, ref_tau_scaled, ref_ssa_scaled, ref_g_scaled
  END SUBROUTINE emit_row

END PROGRAM compare_snow_optics
