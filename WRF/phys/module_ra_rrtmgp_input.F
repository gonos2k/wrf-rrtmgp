! Shared validation and cloud-path construction for the WRF RRTMGP adapter.
! This module intentionally has no RTE or WRF-module dependencies.
MODULE module_ra_rrtmgp_input
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_OK = 0
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_CLEAR = 1
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_INVALID = 2
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_SHAPE = 3
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_RANGE = 4
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_OVERFLOW = 5
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_CLEAR_CONDENSATE = 6
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED = 7

  ! Column indices for the UDM-only six-phase path arrays, in g/m2.
  ! The graupel column is diagnostic only; this adapter has no graupel optics.
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_UDM_LIQUID = 1, RRTMGP_UDM_ICE = 2
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_UDM_RAIN = 3, RRTMGP_UDM_SNOW = 4
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_UDM_GRAUPEL = 5, RRTMGP_UDM_HAIL = 6
  ! Radius output columns (micrometers): cloud, ice, snow.
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_UDM_CLOUD_RADIUS = 1, RRTMGP_UDM_ICE_RADIUS = 2
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_UDM_SNOW_RADIUS = 3

  PUBLIC :: rrtmgp_build_cloud_inputs
  PUBLIC :: rrtmgp_build_udm_inputs
  PUBLIC :: rrtmgp_validate_column_inputs
  PUBLIC :: rrtmgp_check_unit_interval
  PUBLIC :: rrtmgp_check_positive
  PUBLIC :: rrtmgp_check_nonnegative

  EXTERNAL :: wrf_error_fatal3

CONTAINS

  ! UDM's explicit six-species contract.  This routine does not infer phases
  ! from a microphysics scheme: each input species maps only to its named path.
  ! grid_path and omitted_grid_path columns are L/I/R/S/G/H; radius_um columns
  ! are cloud/ice/snow.  Input radii are already micrometres and are copied
  ! unchanged, without clipping or a Fu conversion.
  SUBROUTINE rrtmgp_build_udm_inputs(dp_hpa,cf,qc,qr,qi,qs,qg,qh, &
                                    re_cloud_um,re_ice_um,re_snow_um,gravity, &
                                    grid_path,incloud_path,radius_um,reason,errmsg, &
                                    column_context,allow_clear_condensate, &
                                    omitted_grid_path,layer_reason,negative_q_limits, &
                                    clipped_negative_q,negative_grid_correction,dry_layer_mass_kg_m2)
    REAL, INTENT(IN) :: dp_hpa(:),cf(:),qc(:),qr(:),qi(:),qs(:),qg(:),qh(:)
    REAL, INTENT(IN) :: re_cloud_um(:),re_ice_um(:),re_snow_um(:),gravity
    REAL, INTENT(OUT) :: grid_path(:,:),incloud_path(:,:),radius_um(:,:)
    INTEGER, INTENT(OUT) :: reason
    CHARACTER(LEN=*), INTENT(OUT) :: errmsg
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: column_context
    LOGICAL, OPTIONAL, INTENT(IN) :: allow_clear_condensate
    REAL, OPTIONAL, INTENT(OUT) :: omitted_grid_path(:,:)
    INTEGER, OPTIONAL, INTENT(OUT) :: layer_reason(:)
    ! Default remains strict.  A host may explicitly supply six nonnegative
    ! bounds in L/I/R/S/G/H order (kg/kg); only -bound < q < 0 is corrected.
    ! The raw mixing ratios are never modified.  Outputs retain the raw
    ! corrected negatives and the positive addition to signed grid water path.
    REAL, OPTIONAL, INTENT(IN) :: negative_q_limits(:)
    REAL, OPTIONAL, INTENT(OUT) :: clipped_negative_q(:,:),negative_grid_correction(:,:)
    ! Physical host layers may supply exact native dry-air mass (kg/m2).
    ! If absent, direct legacy callers explicitly retain their pressure/g
    ! approximation; WRF option 37 callers require the native array.
    REAL, OPTIONAL, INTENT(IN) :: dry_layer_mass_kg_m2(:)
    REAL(real64) :: q(6),path64,radius64,mass64,g64,correction64
    REAL :: masses(SIZE(dp_hpa),6),clipped(SIZE(dp_hpa),6),limits(6)
    INTEGER :: n,k,p
    LOGICAL :: allow_clear,clear_column,omitted_any
    CHARACTER(LEN=8), PARAMETER :: qnames(6)=[CHARACTER(LEN=8) :: 'QC','QI','QR','QS','QG','QH']
    CHARACTER(LEN=160) :: input_label
    INTEGER, PARAMETER :: q_to_path(6)=[RRTMGP_UDM_LIQUID,RRTMGP_UDM_ICE, &
                                        RRTMGP_UDM_RAIN,RRTMGP_UDM_SNOW, &
                                        RRTMGP_UDM_GRAUPEL,RRTMGP_UDM_HAIL]

    reason=RRTMGP_INPUT_OK
    errmsg=''
    allow_clear=.FALSE.
    IF(PRESENT(allow_clear_condensate)) allow_clear=allow_clear_condensate
    n=SIZE(dp_hpa)
    IF(n<1 .OR. SIZE(cf)/=n .OR. SIZE(qc)/=n .OR. SIZE(qr)/=n .OR. &
       SIZE(qi)/=n .OR. SIZE(qs)/=n .OR. SIZE(qg)/=n .OR. SIZE(qh)/=n .OR. &
       SIZE(re_cloud_um)/=n .OR. SIZE(re_ice_um)/=n .OR. SIZE(re_snow_um)/=n .OR. &
       SIZE(grid_path,1)/=n .OR. SIZE(grid_path,2)/=6 .OR. &
       SIZE(incloud_path,1)/=n .OR. SIZE(incloud_path,2)/=6 .OR. &
       SIZE(radius_um,1)/=n .OR. SIZE(radius_um,2)/=3) THEN
      reason=RRTMGP_INPUT_SHAPE
      CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in rrtmgp_build_udm_inputs',column_context)
      RETURN
    END IF
    IF(PRESENT(dry_layer_mass_kg_m2)) THEN
      IF(SIZE(dry_layer_mass_kg_m2)/=n) THEN
        reason=RRTMGP_INPUT_SHAPE
        CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in UDM dry_layer_mass_kg_m2',column_context)
        RETURN
      END IF
      DO k=1,n
        IF(.NOT.ieee_is_finite(dry_layer_mass_kg_m2(k)) .OR. dry_layer_mass_kg_m2(k)<=0.) THEN
          CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID, &
               'RRTMGP_INPUT_UDM_DRY_LAYER_MASS_NOT_POSITIVE_FINITE',k,column_context)
          RETURN
        END IF
      END DO
    END IF
    IF(PRESENT(omitted_grid_path)) THEN
      IF(SIZE(omitted_grid_path,1)/=n .OR. SIZE(omitted_grid_path,2)/=6) THEN
        reason=RRTMGP_INPUT_SHAPE
        CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in UDM omitted_grid_path',column_context)
        RETURN
      END IF
    END IF
    IF(PRESENT(layer_reason)) THEN
      IF(SIZE(layer_reason)/=n) THEN
        reason=RRTMGP_INPUT_SHAPE
        CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in UDM layer_reason',column_context)
        RETURN
      END IF
    END IF

    IF(PRESENT(negative_q_limits)) THEN
      IF(SIZE(negative_q_limits)/=6) THEN
        reason=RRTMGP_INPUT_SHAPE
        CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in UDM negative_q_limits',column_context)
        RETURN
      END IF
    END IF
    IF(PRESENT(clipped_negative_q)) THEN
      IF(SIZE(clipped_negative_q,1)/=n .OR. SIZE(clipped_negative_q,2)/=6) THEN
        reason=RRTMGP_INPUT_SHAPE
        CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in UDM clipped_negative_q',column_context)
        RETURN
      END IF
    END IF
    IF(PRESENT(negative_grid_correction)) THEN
      IF(SIZE(negative_grid_correction,1)/=n .OR. SIZE(negative_grid_correction,2)/=6) THEN
        reason=RRTMGP_INPUT_SHAPE
        CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in UDM negative_grid_correction',column_context)
        RETURN
      END IF
    END IF
    limits=0.0
    IF(PRESENT(negative_q_limits)) limits=negative_q_limits
    DO p=1,6
      IF(.NOT.ieee_is_finite(limits(p)) .OR. limits(p)<0.0) THEN
        reason=RRTMGP_INPUT_RANGE
        CALL fatal_builder_message('RRTMGP_INPUT_UDM_NEGATIVE_LIMIT_INVALID',column_context)
        RETURN
      END IF
    END DO
    clipped=0.0
    IF(PRESENT(clipped_negative_q)) clipped_negative_q=0.0
    IF(PRESENT(negative_grid_correction)) negative_grid_correction=0.0
    grid_path=0.0; incloud_path=0.0; radius_um=0.0
    IF(PRESENT(omitted_grid_path)) omitted_grid_path=0.0
    IF(PRESENT(layer_reason)) layer_reason=RRTMGP_INPUT_OK
    IF(.NOT.ieee_is_finite(gravity) .OR. gravity<=0.0) THEN
      reason=RRTMGP_INPUT_INVALID
      CALL fatal_builder_message('RRTMGP_INPUT_GRAVITY_NOT_POSITIVE',column_context)
      RETURN
    END IF

    CALL rrtmgp_check_positive('dp_hpa',RESHAPE(dp_hpa,[n,1]))
    CALL rrtmgp_check_unit_interval('cf',RESHAPE(cf,[n,1]))
    masses(:,1) = qc
    masses(:,2) = qi
    masses(:,3) = qr
    masses(:,4) = qs
    masses(:,5) = qg
    masses(:,6) = qh
    DO p=1,6
      DO k=1,n
        IF(.NOT.ieee_is_finite(masses(k,p))) THEN
          CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID, &
               'RRTMGP_INPUT_UDM_'//TRIM(qnames(p))//'_NOT_FINITE',k,column_context)
          RETURN
        END IF
        IF(masses(k,p)<0.) THEN
          IF(-masses(k,p)<limits(p)) THEN
            clipped(k,p)=masses(k,p)
            masses(k,p)=0.0
          ELSE
            IF(PRESENT(negative_q_limits)) THEN
              WRITE(input_label,'(A,A,A,ES23.15E3,A,ES23.15E3)') 'RRTMGP_INPUT_UDM_',TRIM(qnames(p)), &
                   '_NEGATIVE value_kgkg=',REAL(masses(k,p),real64),' limit_kgkg=',REAL(limits(p),real64)
            ELSE
              WRITE(input_label,'(A,A,A,ES23.15E3)') 'RRTMGP_INPUT_UDM_',TRIM(qnames(p)), &
                   '_NEGATIVE value_kgkg=',REAL(masses(k,p),real64)
            END IF
            CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,TRIM(input_label),k,column_context)
            RETURN
          END IF
        END IF
      END DO
    END DO
    CALL check_finite('UDM_RE_CLOUD',RESHAPE(re_cloud_um,[n,1]))
    CALL check_finite('UDM_RE_ICE',RESHAPE(re_ice_um,[n,1]))
    CALL check_finite('UDM_RE_SNOW',RESHAPE(re_snow_um,[n,1]))
    DO k=1,n
      IF(qc(k)>0.0 .AND. re_cloud_um(k)<=0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_UDM_RE_CLOUD_NOT_POSITIVE',k,column_context)
        RETURN
      END IF
      IF(qi(k)>0.0 .AND. re_ice_um(k)<=0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_UDM_RE_ICE_NOT_POSITIVE',k,column_context)
        RETURN
      END IF
      IF(qs(k)>0.0 .AND. re_snow_um(k)<=0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_UDM_RE_SNOW_NOT_POSITIVE',k,column_context)
        RETURN
      END IF
    END DO

    ! No hail optics are available. Return a machine-readable refusal before
    ! producing paths that a caller could accidentally pass to radiation.
    IF(ANY(qh>0.0)) THEN
      reason=RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED
      errmsg='RRTMGP_INPUT_UDM_HAIL_OPTICS_UNSUPPORTED'
      RETURN
    END IF

    g64=REAL(gravity,real64)
    clear_column=.TRUE.; omitted_any=.FALSE.
    DO k=1,n
      q=REAL(masses(k,:),real64)
      IF(cf(k)>0.0 .OR. ANY(q>0.0_real64)) clear_column=.FALSE.
      IF(cf(k)==0.0 .AND. ANY(q>0.0_real64)) THEN
        IF(.NOT.allow_clear) THEN
          CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID, &
               'RRTMGP_INPUT_ZERO_CLOUD_FRACTION_WITH_CONDENSATE',k,column_context)
          RETURN
        END IF
        omitted_any=.TRUE.
        IF(PRESENT(layer_reason)) layer_reason(k)=RRTMGP_INPUT_CLEAR_CONDENSATE
      ELSE IF(cf(k)==0.0) THEN
        IF(PRESENT(layer_reason)) layer_reason(k)=RRTMGP_INPUT_CLEAR
      END IF
      IF(PRESENT(dry_layer_mass_kg_m2)) THEN
        mass64=REAL(dry_layer_mass_kg_m2(k),real64)*1000.0_real64
      ELSE
        mass64=REAL(dp_hpa(k),real64)*100.0_real64/g64*1000.0_real64
      END IF
      DO p=1,6
        path64=q(p)*mass64
        IF(.NOT.ieee_is_finite(path64) .OR. path64>REAL(HUGE(0.0),real64)) THEN
          CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_PATH_OVERFLOW',k,column_context)
          RETURN
        END IF
        correction64=-REAL(clipped(k,p),real64)*mass64
        IF(.NOT.ieee_is_finite(correction64) .OR. correction64>REAL(HUGE(0.0),real64)) THEN
          CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_PATH_OVERFLOW',k,column_context)
          RETURN
        END IF
        IF(PRESENT(negative_grid_correction)) negative_grid_correction(k,q_to_path(p))=REAL(correction64)
        grid_path(k,q_to_path(p))=REAL(path64)
        IF(cf(k)>0.0) THEN
          radius64=path64/REAL(cf(k),real64)
          IF(.NOT.ieee_is_finite(radius64) .OR. radius64>REAL(HUGE(0.0),real64)) THEN
            CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_PATH_OVERFLOW',k,column_context)
            RETURN
          END IF
          incloud_path(k,q_to_path(p))=REAL(radius64)
        ELSE IF(path64>0.0_real64 .AND. PRESENT(omitted_grid_path)) THEN
          omitted_grid_path(k,q_to_path(p))=REAL(path64)
        END IF
      END DO
      radius64=REAL(re_cloud_um(k),real64)
      IF(.NOT.ieee_is_finite(radius64) .OR. ABS(radius64)>REAL(HUGE(0.0),real64)) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_UDM_RADIUS_OVERFLOW',k,column_context)
        RETURN
      END IF
      radius_um(k,RRTMGP_UDM_CLOUD_RADIUS)=REAL(radius64)
      radius64=REAL(re_ice_um(k),real64)
      IF(.NOT.ieee_is_finite(radius64) .OR. ABS(radius64)>REAL(HUGE(0.0),real64)) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_UDM_RADIUS_OVERFLOW',k,column_context)
        RETURN
      END IF
      radius_um(k,RRTMGP_UDM_ICE_RADIUS)=REAL(radius64)
      radius64=REAL(re_snow_um(k),real64)
      IF(.NOT.ieee_is_finite(radius64) .OR. ABS(radius64)>REAL(HUGE(0.0),real64)) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_UDM_RADIUS_OVERFLOW',k,column_context)
        RETURN
      END IF
      radius_um(k,RRTMGP_UDM_SNOW_RADIUS)=REAL(radius64)
    END DO
    IF(PRESENT(clipped_negative_q)) clipped_negative_q=clipped
    IF(clear_column) reason=RRTMGP_INPUT_CLEAR
    IF(omitted_any) reason=RRTMGP_INPUT_CLEAR_CONDENSATE
  END SUBROUTINE rrtmgp_build_udm_inputs

  SUBROUTINE rrtmgp_build_cloud_inputs(dp_hpa,cf,qc,qi,qs,rliq,rice,rsnow,gravity, &
                                       lwp,iwp,swp,reason,column_context,allow_clear_condensate, &
                                       omitted_grid_path,layer_reason)
    REAL, INTENT(IN) :: dp_hpa(:),cf(:),qc(:),qi(:),qs(:)
    REAL, INTENT(IN) :: rliq(:),rice(:),rsnow(:),gravity
    REAL, INTENT(OUT) :: lwp(:),iwp(:),swp(:)
    INTEGER, INTENT(OUT) :: reason
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: column_context
    LOGICAL, OPTIONAL, INTENT(IN) :: allow_clear_condensate
    REAL, OPTIONAL, INTENT(OUT) :: omitted_grid_path(:)
    INTEGER, OPTIONAL, INTENT(OUT) :: layer_reason(:)
    REAL(real64) :: layer_mass, cloud_fraction, ql, qi_layer, qs_layer, omitted_mass
    REAL(real64) :: lwp64,iwp64,swp64
    INTEGER :: n, k
    LOGICAL :: clear_column,allow_clear,omitted_any
    CHARACTER(LEN=256) :: message

    reason=RRTMGP_INPUT_OK
    allow_clear=.FALSE.
    IF(PRESENT(allow_clear_condensate)) allow_clear=allow_clear_condensate

    ! Check every extent before indexing any input or output array.
    n=SIZE(dp_hpa)
    IF(n<1 .OR. SIZE(cf)/=n .OR. SIZE(qc)/=n .OR. SIZE(qi)/=n .OR. SIZE(qs)/=n .OR. &
       SIZE(rliq)/=n .OR. SIZE(rice)/=n .OR. SIZE(rsnow)/=n .OR. &
       SIZE(lwp)/=n .OR. SIZE(iwp)/=n .OR. SIZE(swp)/=n) THEN
      reason=RRTMGP_INPUT_SHAPE
      CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in rrtmgp_build_cloud_inputs',column_context)
      RETURN
    END IF
    IF(PRESENT(omitted_grid_path)) THEN
      IF(SIZE(omitted_grid_path)/=n) THEN
        reason=RRTMGP_INPUT_SHAPE
        CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in omitted_grid_path',column_context)
        RETURN
      END IF
    END IF
    IF(PRESENT(layer_reason)) THEN
      IF(SIZE(layer_reason)/=n) THEN
        reason=RRTMGP_INPUT_SHAPE
        CALL fatal_builder_message('RRTMGP_INPUT_SHAPE_MISMATCH in layer_reason',column_context)
        RETURN
      END IF
    END IF
    lwp=0.0
    iwp=0.0
    swp=0.0
    IF(PRESENT(omitted_grid_path)) omitted_grid_path=0.0
    IF(PRESENT(layer_reason)) layer_reason=RRTMGP_INPUT_OK

    IF(.NOT.ieee_is_finite(gravity) .OR. gravity<=0.0) THEN
      reason=RRTMGP_INPUT_INVALID
      CALL fatal_builder_message('RRTMGP_INPUT_GRAVITY_NOT_POSITIVE',column_context)
      RETURN
    END IF

    clear_column=.TRUE.
    omitted_any=.FALSE.
    DO k=1,n
      IF(.NOT.ieee_is_finite(dp_hpa(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_DP_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(dp_hpa(k)<=0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_DP_NOT_POSITIVE',k,column_context)
        RETURN
      END IF
      IF(.NOT.ieee_is_finite(cf(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_CF_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(cf(k)<0.0 .OR. cf(k)>1.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_CF_OUT_OF_RANGE',k,column_context)
        RETURN
      END IF
      IF(.NOT.ieee_is_finite(qc(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_QC_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(qc(k)<0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_QC_NEGATIVE',k,column_context)
        RETURN
      END IF
      IF(.NOT.ieee_is_finite(qi(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_QI_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(qi(k)<0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_QI_NEGATIVE',k,column_context)
        RETURN
      END IF
      IF(.NOT.ieee_is_finite(qs(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_QS_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(qs(k)<0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_QS_NEGATIVE',k,column_context)
        RETURN
      END IF

      ! Inactive radii are allowed to be zero, but must still be finite.
      IF(.NOT.ieee_is_finite(rliq(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_RLIQ_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(.NOT.ieee_is_finite(rice(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_RICE_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(.NOT.ieee_is_finite(rsnow(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_RSNOW_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(qc(k)>0.0 .AND. rliq(k)<=0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_RLIQ_NOT_POSITIVE',k,column_context)
        RETURN
      END IF
      IF(qi(k)>0.0 .AND. rice(k)<=0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_RICE_NOT_POSITIVE',k,column_context)
        RETURN
      END IF
      IF(qs(k)>0.0 .AND. rsnow(k)<=0.0) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_RSNOW_NOT_POSITIVE',k,column_context)
        RETURN
      END IF

      IF(cf(k)>0.0 .OR. qc(k)>0.0 .OR. qi(k)>0.0 .OR. qs(k)>0.0) clear_column=.FALSE.

      IF(cf(k)==0.0) THEN
        IF(qc(k)>0.0 .OR. qi(k)>0.0 .OR. qs(k)>0.0) THEN
          IF(.NOT.allow_clear) THEN
            CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID, &
                                    'RRTMGP_INPUT_ZERO_CLOUD_FRACTION_WITH_CONDENSATE',k,column_context)
            RETURN
          END IF
          omitted_any=.TRUE.
          IF(PRESENT(layer_reason)) layer_reason(k)=RRTMGP_INPUT_CLEAR_CONDENSATE
        ELSE
          IF(PRESENT(layer_reason)) layer_reason(k)=RRTMGP_INPUT_CLEAR
        END IF
      END IF
    END DO
    IF(clear_column) reason=RRTMGP_INPUT_CLEAR
    IF(omitted_any) reason=RRTMGP_INPUT_CLEAR_CONDENSATE

    DO k=1,n
      IF(cf(k)==0.0) THEN
        IF(qc(k)>0.0 .OR. qi(k)>0.0 .OR. qs(k)>0.0) THEN
          layer_mass=(REAL(dp_hpa(k),real64)*100.0_real64/REAL(gravity,real64))*1000.0_real64
          omitted_mass=layer_mass*(REAL(qc(k),real64)+REAL(qi(k),real64)+REAL(qs(k),real64))
          IF(.NOT.ieee_is_finite(omitted_mass) .OR. &
             ABS(omitted_mass)>REAL(HUGE(0.0),real64)) THEN
            CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW, &
                                    'RRTMGP_INPUT_PATH_OVERFLOW',k,column_context)
            RETURN
          END IF
          IF(PRESENT(omitted_grid_path)) omitted_grid_path(k)=REAL(omitted_mass)
        END IF
        CYCLE
      END IF
      cloud_fraction=REAL(cf(k),real64)
      layer_mass=(REAL(dp_hpa(k),real64)*100.0_real64/REAL(gravity,real64))*1000.0_real64
      ql=REAL(qc(k),real64)
      qi_layer=REAL(qi(k),real64)
      qs_layer=REAL(qs(k),real64)
      lwp64=(layer_mass*ql)/cloud_fraction
      iwp64=(layer_mass*qi_layer)/cloud_fraction
      swp64=(layer_mass*qs_layer)/cloud_fraction
      IF(.NOT.ieee_is_finite(lwp64) .OR. .NOT.ieee_is_finite(iwp64) .OR. &
         .NOT.ieee_is_finite(swp64) .OR. ABS(lwp64)>REAL(HUGE(0.0),real64) .OR. &
         ABS(iwp64)>REAL(HUGE(0.0),real64) .OR. ABS(swp64)>REAL(HUGE(0.0),real64)) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_PATH_OVERFLOW',k,column_context)
        RETURN
      END IF
      lwp(k)=REAL(lwp64)
      iwp(k)=REAL(iwp64)
      swp(k)=REAL(swp64)
    END DO
  END SUBROUTINE rrtmgp_build_cloud_inputs

  SUBROUTINE rrtmgp_validate_column_inputs(play,plev,tlay,cf,lwp,iwp,swp,rel,rei,res)
    REAL, INTENT(IN) :: play(:,:),plev(:,:),tlay(:,:),cf(:,:),lwp(:,:),iwp(:,:),swp(:,:)
    REAL, INTENT(IN) :: rel(:,:),rei(:,:),res(:,:)
    INTEGER :: nc,nl,c,k,reason
    CHARACTER(LEN=256) :: message

    nc=SIZE(play,1)
    nl=SIZE(play,2)
    IF(nc<1 .OR. nl<1 .OR. SIZE(plev,1)/=nc .OR. SIZE(plev,2)/=nl+1 .OR. &
       SIZE(tlay,1)/=nc .OR. SIZE(tlay,2)/=nl .OR. &
       SIZE(cf,1)/=nc .OR. SIZE(cf,2)/=nl .OR. &
       SIZE(lwp,1)/=nc .OR. SIZE(lwp,2)/=nl .OR. &
       SIZE(iwp,1)/=nc .OR. SIZE(iwp,2)/=nl .OR. &
       SIZE(swp,1)/=nc .OR. SIZE(swp,2)/=nl .OR. &
       SIZE(rel,1)/=nc .OR. SIZE(rel,2)/=nl .OR. &
       SIZE(rei,1)/=nc .OR. SIZE(rei,2)/=nl .OR. &
       SIZE(res,1)/=nc .OR. SIZE(res,2)/=nl) THEN
      CALL fatal_message('RRTMGP_INPUT_SHAPE_MISMATCH in rrtmgp_validate_column_inputs')
      RETURN
    END IF

    CALL rrtmgp_check_positive('play',play)
    CALL rrtmgp_check_nonnegative('plev',plev)
    CALL rrtmgp_check_positive('tlay',tlay)
    CALL rrtmgp_check_unit_interval('cf',cf)
    CALL rrtmgp_check_nonnegative('lwp',lwp)
    CALL rrtmgp_check_nonnegative('iwp',iwp)
    CALL rrtmgp_check_nonnegative('swp',swp)
    CALL check_finite('rel',rel)
    CALL check_finite('rei',rei)
    CALL check_finite('res',res)

    DO c=1,nc
      DO k=1,nl+1
        IF(k>1) THEN
          IF(plev(c,k)>=plev(c,k-1)) THEN
            CALL fail_layer(reason,RRTMGP_INPUT_RANGE, &
                            'RRTMGP_INPUT_PLEV_NOT_STRICTLY_DECREASING',c,k)
            RETURN
          END IF
        END IF
      END DO
      DO k=1,nl
        IF(play(c,k)<plev(c,k+1) .OR. play(c,k)>plev(c,k)) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_RANGE, &
                          'RRTMGP_INPUT_PLAY_OUTSIDE_LAYER_INTERFACES',c,k)
          RETURN
        END IF
        IF(cf(c,k)==0.0 .AND. (lwp(c,k)>0.0 .OR. iwp(c,k)>0.0 .OR. swp(c,k)>0.0)) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_INVALID, &
                          'RRTMGP_INPUT_ZERO_CLOUD_FRACTION_WITH_PATH',c,k)
          RETURN
        END IF
        IF(lwp(c,k)>0.0 .AND. rel(c,k)<=0.0) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_REL_NOT_POSITIVE',c,k)
          RETURN
        END IF
        IF(iwp(c,k)>0.0 .AND. rei(c,k)<=0.0) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_REI_NOT_POSITIVE',c,k)
          RETURN
        END IF
        IF(swp(c,k)>0.0 .AND. res(c,k)<=0.0) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_RES_NOT_POSITIVE',c,k)
          RETURN
        END IF
      END DO
    END DO
  END SUBROUTINE rrtmgp_validate_column_inputs

  SUBROUTINE rrtmgp_check_unit_interval(name,values)
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL, INTENT(IN) :: values(:,:)
    INTEGER :: c,k,reason
    CALL check_finite(name,values)
    DO c=1,SIZE(values,1)
      DO k=1,SIZE(values,2)
        IF(values(c,k)<0.0 .OR. values(c,k)>1.0) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_RANGE, &
                          'RRTMGP_INPUT_'//TRIM(uppercase(name))//'_OUT_OF_RANGE',c,k)
          RETURN
        END IF
      END DO
    END DO
  END SUBROUTINE rrtmgp_check_unit_interval

  SUBROUTINE rrtmgp_check_positive(name,values)
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL, INTENT(IN) :: values(:,:)
    INTEGER :: c,k,reason
    CALL check_finite(name,values)
    DO c=1,SIZE(values,1)
      DO k=1,SIZE(values,2)
        IF(values(c,k)<=0.0) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_RANGE, &
                          'RRTMGP_INPUT_'//TRIM(uppercase(name))//'_NOT_POSITIVE',c,k)
          RETURN
        END IF
      END DO
    END DO
  END SUBROUTINE rrtmgp_check_positive

  SUBROUTINE rrtmgp_check_nonnegative(name,values)
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL, INTENT(IN) :: values(:,:)
    INTEGER :: c,k,reason
    CALL check_finite(name,values)
    DO c=1,SIZE(values,1)
      DO k=1,SIZE(values,2)
        IF(values(c,k)<0.0) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_RANGE, &
                          'RRTMGP_INPUT_'//TRIM(uppercase(name))//'_NEGATIVE',c,k)
          RETURN
        END IF
      END DO
    END DO
  END SUBROUTINE rrtmgp_check_nonnegative

  SUBROUTINE check_finite(name,values)
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL, INTENT(IN) :: values(:,:)
    INTEGER :: c,k,reason
    DO c=1,SIZE(values,1)
      DO k=1,SIZE(values,2)
        IF(.NOT.ieee_is_finite(values(c,k))) THEN
          CALL fail_layer(reason,RRTMGP_INPUT_INVALID, &
                          'RRTMGP_INPUT_'//TRIM(uppercase(name))//'_NOT_FINITE',c,k)
          RETURN
        END IF
      END DO
    END DO
  END SUBROUTINE check_finite

  SUBROUTINE fail_layer(reason,code,label,column,layer)
    INTEGER, INTENT(INOUT) :: reason
    INTEGER, INTENT(IN) :: code,column,layer
    CHARACTER(LEN=*), INTENT(IN) :: label
    CHARACTER(LEN=256) :: message
    reason=code
    WRITE(message,'(A,A,I0,A,I0)') TRIM(label),' at column=',column,' layer=',layer
    CALL fatal_message(TRIM(message))
  END SUBROUTINE fail_layer

  SUBROUTINE fail_builder_layer(reason,code,label,layer,column_context)
    INTEGER, INTENT(INOUT) :: reason
    INTEGER, INTENT(IN) :: code,layer
    CHARACTER(LEN=*), INTENT(IN) :: label
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: column_context
    CHARACTER(LEN=512) :: message
    reason=code
    IF(PRESENT(column_context)) THEN
      WRITE(message,'(A,A,A,A,I0)') TRIM(column_context),' ',TRIM(label),' layer=',layer
    ELSE
      WRITE(message,'(A,A,I0,A,I0)') TRIM(label),' at column=',1,' layer=',layer
    END IF
    CALL fatal_message(TRIM(message))
  END SUBROUTINE fail_builder_layer

  SUBROUTINE fatal_builder_message(label,column_context)
    CHARACTER(LEN=*), INTENT(IN) :: label
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: column_context
    CHARACTER(LEN=512) :: message
    IF(PRESENT(column_context)) THEN
      WRITE(message,'(A,A,A)') TRIM(column_context),' ',TRIM(label)
    ELSE
      message=label
    END IF
    CALL fatal_message(TRIM(message))
  END SUBROUTINE fatal_builder_message

  SUBROUTINE fatal_message(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL wrf_error_fatal3('module_ra_rrtmgp_input.F',0,message)
  END SUBROUTINE fatal_message

  FUNCTION uppercase(text) RESULT(result)
    CHARACTER(LEN=*), INTENT(IN) :: text
    CHARACTER(LEN=LEN(text)) :: result
    INTEGER :: i,code
    result=text
    DO i=1,LEN(text)
      code=IACHAR(result(i:i))
      IF(code>=IACHAR('a') .AND. code<=IACHAR('z')) result(i:i)=ACHAR(code-32)
    END DO
  END FUNCTION uppercase

END MODULE module_ra_rrtmgp_input
