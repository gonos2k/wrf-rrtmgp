! SPDX-License-Identifier: Apache-2.0
! Rain and snow optical-property formulas transcribed from the pinned public
! CCPP RRTMGP implementation, commit 3e6660c6df54e95a0871e990c2294dd397ae3860:
! physics/Radiation/RRTMGP/rrtmgp_{sw,lw}_main.F90 and
! rrtmgp_{sw,lw}_cloud_optics.F90. Copyright 2017 NOAA, UCAR/NCAR CU/CIRES.
!
! Inputs are in-cloud paths in g m-2 and snow effective radius in microns.
! These pure optical helpers do not apply cloud-fraction/precipitation-fraction
! decisions. CCPP invokes precipitation optics only inside its cloud-fraction
! gate; the host remains responsible for that gate. In particular, no mass
! floor or host-specific cloud fraction is introduced here.
MODULE module_ra_rrtmgp_precip
  USE mo_rte_kind, ONLY: wp
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: RRTMGP_PRECIP_OK = 0
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_PRECIP_BAD_PATH = 1
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_PRECIP_BAD_SNOW_RADIUS = 2
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_PRECIP_BAD_BANDS = 3
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_PRECIP_BAD_SHAPE = 4
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_SW_NBAND = 14
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_LW_NBAND = 16
  REAL, PARAMETER, PUBLIC :: RRTMGP_SNOW_RADIUS_CUTOFF_UM = 10.0

  REAL(wp), PARAMETER :: LW_BANDS(2,RRTMGP_LW_NBAND) = RESHAPE([ &
       10.,250., 250.,500., 500.,630., 630.,700., 700.,820., 820.,980., &
       980.,1080., 1080.,1180., 1180.,1390., 1390.,1480., 1480.,1800., &
       1800.,2080., 2080.,2250., 2250.,2390., 2390.,2680., 2680.,3250. ], &
       [2,RRTMGP_LW_NBAND])
  REAL(wp), PARAMETER :: SW_BANDS(2,RRTMGP_SW_NBAND) = RESHAPE([ &
       820.,2680., 2680.,3250., 3250.,4000., 4000.,4650., 4650.,5150., &
       5150.,6150., 6150.,7700., 7700.,8050., 8050.,12850., 12850.,16000., &
       16000.,22650., 22650.,29000., 29000.,38000., 38000.,50000. ], &
       [2,RRTMGP_SW_NBAND])

  ! SW rain/snow coefficient tables, in the pinned CCPP/RRTMGP band order.
  REAL(wp), PARAMETER :: A0R=3.07E-3_wp, A0S=0.0_wp, A1S=1.5_wp
  REAL(wp), PARAMETER :: B0R(RRTMGP_SW_NBAND) = [ &
       .496,.466,.437,.416,.391,.374,.352,.183,.048,.012,0.,0.,0.,0. ]
  REAL(wp), PARAMETER :: B0S(RRTMGP_SW_NBAND) = [ &
       .460,.460,.460,.460,.460,.460,.460,.460,.000,.000,.000,.000,.000,.000 ]
  REAL(wp), PARAMETER :: B1S(RRTMGP_SW_NBAND) = [ &
       0.,0.,0.,0.,0.,0.,0.,0.,1.62E-5,1.62E-5,0.,0.,0.,0. ]
  REAL(wp), PARAMETER :: C0R(RRTMGP_SW_NBAND) = [ &
       .980,.975,.965,.960,.955,.952,.950,.944,.894,.884,.883,.883,.883,.883 ]
  REAL(wp), PARAMETER :: C0S(RRTMGP_SW_NBAND) = [ &
       .970,.970,.970,.970,.970,.970,.970,.970,.970,.970,.700,.700,.700,.700 ]

  REAL(wp), PARAMETER :: ABSRAIN=0.33E-3_wp, ABSSNOW0=1.5_wp

  PUBLIC :: rrtmgp_precip_lw_optics, rrtmgp_precip_sw_optics
  PUBLIC :: rrtmgp_precip_lw_band_bounds, rrtmgp_precip_sw_band_bounds

CONTAINS

  PURE SUBROUTINE rrtmgp_precip_lw_band_bounds(bands)
    REAL(wp), INTENT(OUT) :: bands(2,RRTMGP_LW_NBAND)
    bands = LW_BANDS
  END SUBROUTINE rrtmgp_precip_lw_band_bounds

  PURE SUBROUTINE rrtmgp_precip_sw_band_bounds(bands)
    REAL(wp), INTENT(OUT) :: bands(2,RRTMGP_SW_NBAND)
    bands = SW_BANDS
  END SUBROUTINE rrtmgp_precip_sw_band_bounds

  PURE SUBROUTINE rrtmgp_precip_lw_optics(rwp_gm2, swp_gm2, snow_radius_um, bands, tau, ierr)
    REAL(wp), INTENT(IN) :: rwp_gm2(:,:), swp_gm2(:,:), snow_radius_um(:,:)
    REAL(wp), INTENT(IN) :: bands(2,RRTMGP_LW_NBAND)
    REAL(wp), INTENT(OUT) :: tau(:,:,:)
    INTEGER, INTENT(OUT) :: ierr
    REAL(wp) :: rain_tau, snow_tau
    INTEGER :: i,k

    tau = 0.0_wp
    ierr = RRTMGP_PRECIP_OK
    IF (SIZE(tau,1) /= SIZE(rwp_gm2,1) .OR. SIZE(tau,1) /= SIZE(swp_gm2,1) .OR. &
        SIZE(tau,1) /= SIZE(snow_radius_um,1) .OR. SIZE(tau,2) /= SIZE(rwp_gm2,2) .OR. &
        SIZE(tau,2) /= SIZE(swp_gm2,2) .OR. SIZE(tau,2) /= SIZE(snow_radius_um,2) .OR. &
        SIZE(tau,3) /= RRTMGP_LW_NBAND) THEN
      ierr = RRTMGP_PRECIP_BAD_SHAPE
      RETURN
    END IF
    IF (ANY(.NOT.ieee_is_finite(rwp_gm2)) .OR. ANY(.NOT.ieee_is_finite(swp_gm2)) .OR. &
        ANY(.NOT.ieee_is_finite(snow_radius_um))) THEN
      ierr = RRTMGP_PRECIP_BAD_PATH
      RETURN
    END IF
    IF (ANY(rwp_gm2 < 0.0_wp) .OR. ANY(swp_gm2 < 0.0_wp)) THEN
      ierr = RRTMGP_PRECIP_BAD_PATH
      RETURN
    END IF
    IF (ANY(swp_gm2 > 0.0_wp .AND. snow_radius_um <= 0.0_wp)) THEN
      ierr = RRTMGP_PRECIP_BAD_SNOW_RADIUS
      RETURN
    END IF
    IF (.NOT.valid_bands(bands,LW_BANDS)) THEN
      ierr = RRTMGP_PRECIP_BAD_BANDS
      RETURN
    END IF

    DO k=1,SIZE(rwp_gm2,2)
      DO i=1,SIZE(rwp_gm2,1)
        rain_tau = ABSRAIN*rwp_gm2(i,k)
        snow_tau = 0.0_wp
        IF (swp_gm2(i,k) > 0.0_wp .AND. &
            snow_radius_um(i,k) > RRTMGP_SNOW_RADIUS_CUTOFF_UM) &
          snow_tau = ABSSNOW0*1.05756_wp*swp_gm2(i,k)/snow_radius_um(i,k)
        tau(i,k,:) = rain_tau + snow_tau
      END DO
    END DO
  END SUBROUTINE rrtmgp_precip_lw_optics

  PURE SUBROUTINE rrtmgp_precip_sw_optics(rwp_gm2, swp_gm2, snow_radius_um, bands, &
                                          tau, ssa, asymmetry, ierr)
    REAL(wp), INTENT(IN) :: rwp_gm2(:,:), swp_gm2(:,:), snow_radius_um(:,:)
    REAL(wp), INTENT(IN) :: bands(2,RRTMGP_SW_NBAND)
    REAL(wp), INTENT(OUT) :: tau(:,:,:), ssa(:,:,:), asymmetry(:,:,:)
    INTEGER, INTENT(OUT) :: ierr
    REAL(wp) :: tau_rain, tau_snow, ssa_rain, ssa_snow, asy_rain, asy_snow
    REAL(wp) :: tau_prec, ssa_prec, asy_prec, asyw, ssaw, za1, za2
    INTEGER :: b,i,k

    tau = 0.0_wp
    ssa = 0.0_wp
    asymmetry = 0.0_wp
    ierr = RRTMGP_PRECIP_OK
    IF (SIZE(tau,1) /= SIZE(rwp_gm2,1) .OR. SIZE(tau,1) /= SIZE(swp_gm2,1) .OR. &
        SIZE(tau,1) /= SIZE(snow_radius_um,1) .OR. SIZE(tau,2) /= SIZE(rwp_gm2,2) .OR. &
        SIZE(tau,2) /= SIZE(swp_gm2,2) .OR. SIZE(tau,2) /= SIZE(snow_radius_um,2) .OR. &
        SIZE(tau,3) /= RRTMGP_SW_NBAND .OR. ANY(SHAPE(ssa) /= SHAPE(tau)) .OR. &
        ANY(SHAPE(asymmetry) /= SHAPE(tau))) THEN
      ierr = RRTMGP_PRECIP_BAD_SHAPE
      RETURN
    END IF
    IF (ANY(.NOT.ieee_is_finite(rwp_gm2)) .OR. ANY(.NOT.ieee_is_finite(swp_gm2)) .OR. &
        ANY(.NOT.ieee_is_finite(snow_radius_um))) THEN
      ierr = RRTMGP_PRECIP_BAD_PATH
      RETURN
    END IF
    IF (ANY(rwp_gm2 < 0.0_wp) .OR. ANY(swp_gm2 < 0.0_wp)) THEN
      ierr = RRTMGP_PRECIP_BAD_PATH
      RETURN
    END IF
    IF (ANY(swp_gm2 > 0.0_wp .AND. snow_radius_um <= 0.0_wp)) THEN
      ierr = RRTMGP_PRECIP_BAD_SNOW_RADIUS
      RETURN
    END IF
    IF (.NOT.valid_bands(bands,SW_BANDS)) THEN
      ierr = RRTMGP_PRECIP_BAD_BANDS
      RETURN
    END IF

    DO k=1,SIZE(rwp_gm2,2)
      DO i=1,SIZE(rwp_gm2,1)
        tau_rain = rwp_gm2(i,k)*A0R
        tau_snow = 0.0_wp
        IF (swp_gm2(i,k) > 0.0_wp .AND. &
            snow_radius_um(i,k) > RRTMGP_SNOW_RADIUS_CUTOFF_UM) &
          tau_snow = swp_gm2(i,k)*1.09087_wp*(A0S+A1S/(1.0315_wp*snow_radius_um(i,k)))
        DO b=1,RRTMGP_SW_NBAND
          ssa_rain = tau_rain*(1.0_wp-B0R(b))
          asy_rain = ssa_rain*C0R(b)
          ssa_snow = tau_snow*(1.0_wp-(B0S(b)+B1S(b)*1.0315_wp*snow_radius_um(i,k)))
          asy_snow = ssa_snow*C0S(b)
          tau_prec = MAX(1.0E-12_wp,tau_rain+tau_snow)
          ssa_prec = MAX(1.0E-12_wp,ssa_rain+ssa_snow)
          asy_prec = MAX(1.0E-12_wp,asy_rain+asy_snow)
          asyw = asy_prec/MAX(1.0E-12_wp,ssa_prec)
          ssaw = MIN(1.0_wp-1.0E-6_wp,ssa_prec/tau_prec)
          za1 = asyw*asyw
          za2 = ssaw*za1
          tau(i,k,b) = (1.0_wp-za2)*tau_prec
          ssa(i,k,b) = (ssaw-za2)/(1.0_wp-za2)
          asymmetry(i,k,b) = asyw/(1.0_wp+asyw)
        END DO
      END DO
    END DO
  END SUBROUTINE rrtmgp_precip_sw_optics

  PURE LOGICAL FUNCTION valid_bands(actual, expected)
    REAL(wp), INTENT(IN) :: actual(:,:), expected(:,:)
    valid_bands = .FALSE.
    IF (ANY(SHAPE(actual) /= SHAPE(expected))) RETURN
    IF (ANY(.NOT.ieee_is_finite(actual))) RETURN
    IF (ANY(actual /= expected)) RETURN
    valid_bands = .TRUE.
  END FUNCTION valid_bands

END MODULE module_ra_rrtmgp_precip
