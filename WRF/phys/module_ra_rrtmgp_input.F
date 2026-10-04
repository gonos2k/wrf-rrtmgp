! Shared validation and cloud-path construction for the WRF RRTMGP adapter.
! This module intentionally has no RTE or WRF-module dependencies.
MODULE module_ra_rrtmgp_input
  USE, INTRINSIC :: iso_fortran_env, ONLY: int64, real64, error_unit
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
  INTEGER, PARAMETER, PUBLIC :: RRTMGP_INPUT_UDM_FROZEN_INVALID = 8

  ! Column indices for the UDM-only six-phase path arrays, in g/m2.
  ! G/H are diagnostic-only unless the caller explicitly selects frozen mode.
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
  PUBLIC :: rrtmgp_column_seed
  PUBLIC :: rrtmgp_udm_frozen_lambdas
  PUBLIC :: rrtmgp_summarize_path_clipping
  PUBLIC :: rrtmgp_build_cu_inputs, rrtmgp_summarize_cu_filter
  PUBLIC :: rrtmgp_fatal

  EXTERNAL :: wrf_error_fatal3

CONTAINS

  ! Experimental diagnosed-KF population policy: exclude negative diagnosed
  ! condensate from radiation only. This never corrects native UDM inputs or
  ! modifies the stored convection fields. Both populations share host CF.
  SUBROUTINE rrtmgp_build_cu_inputs(combined_cf,cu_cf,cu_dp,cu_sh,qc_cu,qi_cu,dry_mass, &
                                   grid_path,incloud_path,rejected_grid_path,omitted_grid_path, &
                                   reason,column_context)
    REAL, INTENT(IN) :: combined_cf(:),cu_cf(:),cu_dp(:),cu_sh(:),qc_cu(:),qi_cu(:),dry_mass(:)
    REAL, INTENT(OUT) :: grid_path(:,:),incloud_path(:,:),rejected_grid_path(:,:),omitted_grid_path(:,:)
    INTEGER, INTENT(OUT) :: reason
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: column_context
    INTEGER :: n,k,p
    REAL :: q(2)
    REAL(real64) :: mass64,path64,rejected64,incloud64
    reason=RRTMGP_INPUT_OK
    n=SIZE(combined_cf)
    IF(n<1.OR.SIZE(cu_cf)/=n.OR.SIZE(cu_dp)/=n.OR.SIZE(cu_sh)/=n.OR. &
       SIZE(qc_cu)/=n.OR.SIZE(qi_cu)/=n.OR.SIZE(dry_mass)/=n.OR. &
       ANY(SHAPE(grid_path)/=[n,2]).OR.ANY(SHAPE(incloud_path)/=[n,2]).OR. &
       ANY(SHAPE(rejected_grid_path)/=[n,2]).OR.ANY(SHAPE(omitted_grid_path)/=[n,2])) THEN
      reason=RRTMGP_INPUT_SHAPE
      CALL fatal_builder_message('RRTMGP_INPUT_CU_SHAPE_MISMATCH',column_context)
      RETURN
    END IF
    grid_path=0.; incloud_path=0.; rejected_grid_path=0.; omitted_grid_path=0.
    DO k=1,n
      IF(.NOT.ieee_is_finite(combined_cf(k)).OR..NOT.ieee_is_finite(cu_cf(k)).OR. &
         .NOT.ieee_is_finite(cu_dp(k)).OR..NOT.ieee_is_finite(cu_sh(k))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_CU_CF_NOT_FINITE',k,column_context)
        RETURN
      END IF
      IF(combined_cf(k)<0..OR.combined_cf(k)>1..OR.cu_cf(k)<0..OR.cu_cf(k)>1..OR. &
         cu_dp(k)<0..OR.cu_dp(k)>1..OR.cu_sh(k)<0..OR.cu_sh(k)>1.) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_RANGE,'RRTMGP_INPUT_CU_CF_OUT_OF_RANGE',k,column_context)
        RETURN
      END IF
      IF(cu_cf(k)/=cu_dp(k)+cu_sh(k)) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_CU_CF_SUM_MISMATCH',k,column_context)
        RETURN
      END IF
      IF(combined_cf(k)==0..AND.cu_cf(k)>0.) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_CU_CF_ZERO_COMBINED',k,column_context)
        RETURN
      END IF
      IF(combined_cf(k)<cu_cf(k)) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_CU_CF_EXCEEDS_COMBINED',k,column_context)
        RETURN
      END IF
      IF(.NOT.ieee_is_finite(dry_mass(k)).OR.dry_mass(k)<=0.) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_CU_DRY_MASS_NOT_POSITIVE_FINITE',k,column_context)
        RETURN
      END IF
      q=[qc_cu(k),qi_cu(k)]
      IF(ANY(.NOT.ieee_is_finite(q))) THEN
        CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID,'RRTMGP_INPUT_CU_Q_NOT_FINITE',k,column_context)
        RETURN
      END IF
      mass64=REAL(dry_mass(k),real64)*1000._real64*REAL(cu_cf(k),real64)
      DO p=1,2
        path64=MAX(0._real64,REAL(q(p),real64))*mass64
        rejected64=MAX(0._real64,-REAL(q(p),real64))*mass64
        IF(.NOT.ieee_is_finite(path64).OR..NOT.ieee_is_finite(rejected64).OR. &
           path64>REAL(HUGE(0.),real64).OR.rejected64>REAL(HUGE(0.),real64)) THEN
          CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_CU_PATH_OVERFLOW',k,column_context)
          RETURN
        END IF
        grid_path(k,p)=REAL(path64); rejected_grid_path(k,p)=REAL(rejected64)
        IF(combined_cf(k)>0.) THEN
          incloud64=path64/REAL(combined_cf(k),real64)
          IF(.NOT.ieee_is_finite(incloud64).OR.incloud64>REAL(HUGE(0.),real64)) THEN
            CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_CU_PATH_OVERFLOW',k,column_context)
            RETURN
          END IF
          incloud_path(k,p)=REAL(incloud64)
        ELSE
          omitted_grid_path(k,p)=REAL(path64)
        END IF
      END DO
    END DO
  END SUBROUTINE rrtmgp_build_cu_inputs

  PURE SUBROUTINE rrtmgp_summarize_cu_filter(qc_cu,qi_cu,cu_cf,grid_path,rejected_grid_path, &
                                           negative_source_count,negative_active_count, &
                                           rejected_sum,rejected_max,accepted_sum)
    REAL, INTENT(IN) :: qc_cu(:),qi_cu(:),cu_cf(:),grid_path(:,:),rejected_grid_path(:,:)
    INTEGER(int64), INTENT(OUT) :: negative_source_count(2),negative_active_count(2)
    REAL(real64), INTENT(OUT) :: rejected_sum(2),rejected_max(2),accepted_sum(2)
    INTEGER :: p,k
    REAL :: q(2)
    negative_source_count=0_int64; negative_active_count=0_int64
    rejected_sum=0._real64; rejected_max=0._real64; accepted_sum=0._real64
    DO k=1,SIZE(cu_cf)
      q=[qc_cu(k),qi_cu(k)]
      DO p=1,2
        IF(q(p)<0.) negative_source_count(p)=negative_source_count(p)+1_int64
        IF(q(p)<0..AND.cu_cf(k)>0.) negative_active_count(p)=negative_active_count(p)+1_int64
        rejected_sum(p)=rejected_sum(p)+REAL(rejected_grid_path(k,p),real64)
        rejected_max(p)=MAX(rejected_max(p),REAL(rejected_grid_path(k,p),real64))
        accepted_sum(p)=accepted_sum(p)+REAL(grid_path(k,p),real64)
      END DO
    END DO
  END SUBROUTINE rrtmgp_summarize_cu_filter

  ! Summarize LUT-clipped portions of a column without changing paths or
  ! coordinates. The caller supplies grid-mean paths in g/m2 and coordinates
  ! in the exact LUT coordinate used by the adapter. Only positive paths in
  ! cloudy layers contribute; overlap/daylight gating remains the caller's.
  PURE SUBROUTINE rrtmgp_summarize_path_clipping(grid_path,cf,coordinate,lower,upper, &
                                                 n_low,sum_low,max_low,n_high,sum_high,max_high,total)
    REAL, INTENT(IN) :: grid_path(:),cf(:)
    REAL(real64), INTENT(IN) :: coordinate(:),lower,upper
    INTEGER(int64), INTENT(OUT) :: n_low,n_high
    REAL(real64), INTENT(OUT) :: sum_low,max_low,sum_high,max_high,total
    INTEGER :: k
    n_low=0_int64; n_high=0_int64
    sum_low=0._real64; max_low=0._real64
    sum_high=0._real64; max_high=0._real64; total=0._real64
    DO k=1,SIZE(grid_path)
      IF(grid_path(k)<=0. .OR. cf(k)<=0.) CYCLE
      total=total+REAL(grid_path(k),real64)
      IF(coordinate(k)<lower) THEN
        n_low=n_low+1_int64
        sum_low=sum_low+REAL(grid_path(k),real64)
        max_low=MAX(max_low,REAL(grid_path(k),real64))
      ELSE IF(coordinate(k)>upper) THEN
        n_high=n_high+1_int64
        sum_high=sum_high+REAL(grid_path(k),real64)
        max_high=MAX(max_high,REAL(grid_path(k),real64))
      END IF
    END DO
  END SUBROUTINE rrtmgp_summarize_path_clipping

  ! Stable engineering hash for a physical column and radiation phase.  The
  ! 31-bit modulus and multiplier are chosen for deterministic bounded
  ! arithmetic, not as a guarantee of independent Monte Carlo realizations.
  ! Products stay below (modulus-1)*48271 and therefore fit signed int64.
  PURE INTEGER FUNCTION rrtmgp_column_seed(domain_id,i,j,year,day_of_year,phase) RESULT(seed)
    INTEGER, INTENT(IN) :: domain_id,i,j,year,day_of_year,phase
    INTEGER(int64), PARAMETER :: modulus=2147483647_int64, multiplier=48271_int64
    INTEGER(int64) :: state
    INTEGER(int64) :: fields(6)
    INTEGER :: k

    seed=-1
    IF(domain_id<=0 .OR. i<=0 .OR. j<=0 .OR. year<=0) RETURN
    IF(day_of_year<1 .OR. day_of_year>366) RETURN
    IF(phase/=1 .AND. phase/=2) RETURN

    fields=[INT(domain_id,int64),INT(i,int64),INT(j,int64),INT(year,int64), &
            INT(day_of_year,int64),INT(phase,int64)]
    state=1_int64
    DO k=1,SIZE(fields)
      state=1_int64+MODULO(state*multiplier+fields(k),modulus-1_int64)
    END DO
    seed=INT(state)
  END FUNCTION rrtmgp_column_seed

  ! Diagnostic PSD slope for the experimental homogeneous-ice G/H optics.
  ! This does not alter the UDM process state or suppress positive path mass.
  ! A sub-cutoff positive q uses the 20000 m-1 cap as a size sentinel.
  PURE SUBROUTINE rrtmgp_udm_frozen_lambdas(qg,qh,rho,lambda_g,lambda_h,reason,errmsg)
    REAL, INTENT(IN) :: qg(:),qh(:),rho(:)
    REAL, INTENT(OUT) :: lambda_g(:),lambda_h(:)
    INTEGER, INTENT(OUT) :: reason
    CHARACTER(LEN=*), INTENT(OUT) :: errmsg
    REAL(real64), PARAMETER :: pi64=3.1415926535897932384626433832795_real64
    REAL(real64), PARAMETER :: cutoff=1.0e-9_real64, cap=20000.0_real64
    REAL(real64), PARAMETER :: graupel_n0=4.0e6_real64, graupel_rho=500.0_real64
    REAL(real64), PARAMETER :: hail_n0=4.0e4_real64, hail_rho=912.0_real64
    REAL(real64) :: lg,lh
    INTEGER :: k,n
    reason=RRTMGP_INPUT_OK
    errmsg=''
    lambda_g=0.; lambda_h=0.
    n=SIZE(qg)
    IF(SIZE(qh)/=n .OR. SIZE(rho)/=n .OR. SIZE(lambda_g)/=n .OR. SIZE(lambda_h)/=n) THEN
      reason=RRTMGP_INPUT_SHAPE
      errmsg='RRTMGP_INPUT_SHAPE_MISMATCH in UDM frozen lambda inputs'
      RETURN
    END IF
    DO k=1,n
      IF(.NOT.ieee_is_finite(qg(k)) .OR. .NOT.ieee_is_finite(qh(k)) .OR. .NOT.ieee_is_finite(rho(k))) THEN
        reason=RRTMGP_INPUT_UDM_FROZEN_INVALID
        WRITE(errmsg,'(A,I0)') 'RRTMGP_INPUT_UDM_FROZEN_NOT_FINITE layer=',k
        RETURN
      END IF
      IF(qg(k)<0. .OR. qh(k)<0. .OR. rho(k)<=0.) THEN
        reason=RRTMGP_INPUT_UDM_FROZEN_INVALID
        WRITE(errmsg,'(A,I0)') 'RRTMGP_INPUT_UDM_FROZEN_Q_OR_RHO_OUT_OF_RANGE layer=',k
        RETURN
      END IF
      lg=cap; lh=cap
      IF(qg(k)>cutoff) THEN
        lg=EXP(0.25_real64*(LOG(pi64)+LOG(graupel_rho)+LOG(graupel_n0)- &
                            LOG(REAL(rho(k),real64))-LOG(REAL(qg(k),real64))))
        lg=MIN(lg,cap)
      END IF
      IF(qh(k)>cutoff) THEN
        lh=EXP(0.25_real64*(LOG(pi64)+LOG(hail_rho)+LOG(hail_n0)- &
                            LOG(REAL(rho(k),real64))-LOG(REAL(qh(k),real64))))
        lh=MIN(lh,cap)
      END IF
      IF(.NOT.ieee_is_finite(lg) .OR. .NOT.ieee_is_finite(lh) .OR. lg<=0. .OR. lh<=0. .OR. &
         lg>REAL(HUGE(0.),real64) .OR. lh>REAL(HUGE(0.),real64)) THEN
        reason=RRTMGP_INPUT_UDM_FROZEN_INVALID
        WRITE(errmsg,'(A,I0)') 'RRTMGP_INPUT_UDM_FROZEN_LAMBDA_INVALID layer=',k
        RETURN
      END IF
      lambda_g(k)=REAL(lg); lambda_h(k)=REAL(lh)
    END DO
  END SUBROUTINE rrtmgp_udm_frozen_lambdas

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
                                    clipped_negative_q,negative_grid_correction,dry_layer_mass_kg_m2, &
                                    frozen_uniform)
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
    LOGICAL, OPTIONAL, INTENT(IN) :: frozen_uniform
    REAL(real64) :: q(6),path64,radius64,mass64,g64,correction64
    REAL :: masses(SIZE(dp_hpa),6),clipped(SIZE(dp_hpa),6),limits(6)
    INTEGER :: n,k,p
    LOGICAL :: allow_clear,clear_column,omitted_any,uniform_frozen,omitted_layer
    CHARACTER(LEN=8), PARAMETER :: qnames(6)=[CHARACTER(LEN=8) :: 'QC','QI','QR','QS','QG','QH']
    CHARACTER(LEN=160) :: input_label
    INTEGER, PARAMETER :: q_to_path(6)=[RRTMGP_UDM_LIQUID,RRTMGP_UDM_ICE, &
                                        RRTMGP_UDM_RAIN,RRTMGP_UDM_SNOW, &
                                        RRTMGP_UDM_GRAUPEL,RRTMGP_UDM_HAIL]

    reason=RRTMGP_INPUT_OK
    errmsg=''
    allow_clear=.FALSE.
    IF(PRESENT(allow_clear_condensate)) allow_clear=allow_clear_condensate
    uniform_frozen=.FALSE.
    IF(PRESENT(frozen_uniform)) uniform_frozen=frozen_uniform
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
        ! Fortran does not require short-circuit evaluation of .OR.; reject
        ! NaN before ordered comparisons, including builds with FPE traps.
        IF(.NOT.ieee_is_finite(dry_layer_mass_kg_m2(k))) THEN
          CALL fail_builder_layer(reason,RRTMGP_INPUT_INVALID, &
               'RRTMGP_INPUT_UDM_DRY_LAYER_MASS_NOT_POSITIVE_FINITE',k,column_context)
          RETURN
        END IF
        IF(dry_layer_mass_kg_m2(k)<=0.) THEN
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
    IF(.NOT.uniform_frozen .AND. ANY(qh>0.0)) THEN
      reason=RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED
      errmsg='RRTMGP_INPUT_UDM_HAIL_OPTICS_UNSUPPORTED'
      RETURN
    END IF

    g64=REAL(gravity,real64)
    clear_column=.TRUE.; omitted_any=.FALSE.
    DO k=1,n
      q=REAL(masses(k,:),real64)
      IF(cf(k)>0.0 .OR. ANY(q>0.0_real64)) clear_column=.FALSE.
      omitted_layer=ANY(q(1:4)>0.0_real64)
      IF(.NOT.uniform_frozen) omitted_layer=ANY(q>0.0_real64)
      IF(cf(k)==0.0 .AND. omitted_layer) THEN
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
        IF(uniform_frozen .AND. p>=5) THEN
          ! Uniform G/H occurrence is one, so the radiation path equals the
          ! grid path and is never divided by cloud fraction.
          incloud_path(k,q_to_path(p))=REAL(path64)
        ELSE IF(cf(k)>0.0) THEN
          radius64=path64/REAL(cf(k),real64)
          IF(.NOT.ieee_is_finite(radius64) .OR. radius64>REAL(HUGE(0.0),real64)) THEN
            CALL fail_builder_layer(reason,RRTMGP_INPUT_OVERFLOW,'RRTMGP_INPUT_PATH_OVERFLOW',k,column_context)
            RETURN
          END IF
          incloud_path(k,q_to_path(p))=REAL(radius64)
        ELSE IF(path64>0.0_real64 .AND. PRESENT(omitted_grid_path) .AND. &
                (.NOT.uniform_frozen .OR. p<=4)) THEN
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

  SUBROUTINE rrtmgp_fatal(message,source)
    CHARACTER(LEN=*), INTENT(IN) :: message
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: source
    CHARACTER(LEN=128) :: source_name
    source_name='module_ra_rrtmgp_input.F'
    IF(PRESENT(source)) source_name=source
    !$OMP CRITICAL (rrtmgp_fatal_message_output)
    WRITE(error_unit,'(A)') 'RRTMGP_FATAL ['//TRIM(source_name)//']: '//TRIM(message)
    FLUSH(error_unit)
    !$OMP END CRITICAL (rrtmgp_fatal_message_output)
    CALL wrf_error_fatal3(TRIM(source_name),0,TRIM(message))
  END SUBROUTINE rrtmgp_fatal

  SUBROUTINE fatal_message(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL rrtmgp_fatal(message,'module_ra_rrtmgp_input.F')
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
