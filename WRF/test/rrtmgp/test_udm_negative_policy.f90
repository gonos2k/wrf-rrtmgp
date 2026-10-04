PROGRAM test_udm_negative_policy
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan,ieee_positive_inf
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_build_udm_inputs, &
       RRTMGP_INPUT_OK,RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED
  IMPLICIT NONE
  INTEGER, PARAMETER :: n=2
  REAL :: dp(n),cf(n),qc(n),qi(n),qr(n),qs(n),qg(n),qh(n)
  REAL :: re_cloud(n),re_ice(n),re_snow(n),gravity
  REAL :: grid(n,6),incloud(n,6),radius(n,3),omitted(n,6)
  REAL :: limits(6),clipped(n,6),correction(n,6),rawq(n,6),dp64(n)
  REAL :: grid_default(n,6),incloud_default(n,6),radius_default(n,3),omitted_default(n,6)
  REAL :: clipped_bad(n,5),correction_bad(n,5),limits_bad(5)
  REAL :: q_before(6*n),dp_before(n),cf_before(n),radius_before(3*n),limits_before(6)
  INTEGER(int32) :: bits_q(6*n),bits_dp(n),bits_cf(n),bits_radius(3*n),bits_limits(6)
  INTEGER :: reason,layers(n),layers_default(n),k,p
  CHARACTER(LEN=512) :: errmsg
  CHARACTER(LEN=40) :: mode

  CALL get_command_argument(1,mode)
  CALL initialize_inputs()
  SELECT CASE(TRIM(mode))
  CASE('mixed')
    qc(1)=-0.0625;qi(1)=-0.03125;qr(1)=-0.125
    qs(1)=-0.25;qg(1)=-0.125;qh(1)=-0.03125
    qc(2)=0.125;qi(2)=0.0625;qr(2)=0.25
    qs(2)=0.5;qg(2)=0.25;qh(2)=0.
    CALL save_input_bits()
    CALL build_with_limits()
    CALL assert_input_bits_unchanged()
    IF(reason/=RRTMGP_INPUT_OK.OR.LEN_TRIM(errmsg)/=0) ERROR STOP 'mixed accepted policy status'
    CALL assert_mixed_results()
  CASE('positive')
    qc=[0.125,0.0625];qi=[0.03125,0.125];qr=[0.25,0.125]
    qs=[0.125,0.0625];qg=[0.0625,0.125];qh=0.
    CALL save_input_bits()
    CALL build_default()
    grid_default=grid;incloud_default=incloud;radius_default=radius
    omitted_default=omitted;layers_default=layers
    CALL build_with_limits()
    CALL assert_input_bits_unchanged()
    IF(reason/=RRTMGP_INPUT_OK.OR.LEN_TRIM(errmsg)/=0) ERROR STOP 'positive invariant status'
    IF(ANY(grid/=grid_default).OR.ANY(incloud/=incloud_default).OR. &
       ANY(radius/=radius_default).OR.ANY(omitted/=omitted_default).OR. &
       ANY(layers/=layers_default)) ERROR STOP 'negative policy changed positive-only result'
    IF(ANY(clipped/=0.).OR.ANY(correction/=0.)) ERROR STOP 'positive-only clipping output was nonzero'
  CASE('hail_tiny')
    qc=[0.125,0.0625];qi=[0.03125,0.125];qr=[0.25,0.125]
    qs=[0.125,0.0625];qg=[0.0625,0.125];qh=0.
    qh(2)=NEAREST(0.,1.)
    grid=-91.;incloud=-92.;radius=-93.;omitted=-94.;clipped=-95.;correction=-96.
    CALL build_with_limits()
    IF(reason/=RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED) ERROR STOP 'positive tiny hail did not return reason 7'
    IF(TRIM(errmsg)/='RRTMGP_INPUT_UDM_HAIL_OPTICS_UNSUPPORTED') ERROR STOP 'hail refusal message mismatch'
    IF(ANY(grid/=0.).OR.ANY(incloud/=0.).OR.ANY(radius/=0.).OR.ANY(omitted/=0.) .OR. &
       ANY(clipped/=0.).OR.ANY(correction/=0.)) ERROR STOP 'positive hail refusal was not atomic zero'
  CASE('underflow')
    qc=0.;qi=0.;qr=0.;qs=0.;qg=0.;qh=0.
    dp(1)=1.e-38;qc(1)=NEAREST(0.,-1.);limits(1)=1.e-40
    CALL save_input_bits()
    CALL build_with_limits()
    CALL assert_input_bits_unchanged()
    IF(reason/=RRTMGP_INPUT_OK) ERROR STOP 'underflow correction did not pass'
    IF(clipped(1,1)/=qc(1)) ERROR STOP 'underflow lost accepted raw negative q'
    IF(grid(1,1)/=0..OR.correction(1,1)/=0.) ERROR STOP 'underflow fixture expected default-real zero path'
    IF(ANY(clipped(2,:)/=0.).OR.ANY(correction(2,:)/=0.)) ERROR STOP 'underflow polluted another layer'
  CASE('strict_default')
    qg(2)=-0.125
    CALL build_default()
    ERROR STOP 'default strict policy accepted negative input'
  CASE('boundary_equal')
    qc(1)=-limits(1)
    CALL build_with_limits()
    ERROR STOP 'negative value equal to limit was accepted'
  CASE('large_negative')
    qh(2)=-2.*limits(6)
    CALL build_with_limits()
    ERROR STOP 'negative value beyond limit was accepted'
  CASE('limit_shape')
    limits_bad=limits(1:5)
    CALL build_with_bad_limits()
    ERROR STOP 'wrong limit shape was accepted'
  CASE('limit_nan')
    limits(3)=ieee_value(0.,ieee_quiet_nan)
    CALL build_with_limits()
    ERROR STOP 'NaN limit was accepted'
  CASE('limit_inf')
    limits(4)=ieee_value(0.,ieee_positive_inf)
    CALL build_with_limits()
    ERROR STOP 'infinite limit was accepted'
  CASE('limit_negative')
    limits(5)=-0.25
    CALL build_with_limits()
    ERROR STOP 'negative limit was accepted'
  CASE('clipped_shape')
    CALL build_with_bad_clipped()
    ERROR STOP 'wrong clipped_negative_q shape was accepted'
  CASE('correction_shape')
    CALL build_with_bad_correction()
    ERROR STOP 'wrong negative_grid_correction shape was accepted'
  CASE('nonfinite_q')
    qi(2)=ieee_value(0.,ieee_quiet_nan)
    CALL build_with_limits()
    ERROR STOP 'nonfinite q was accepted'
  CASE('dp_nan_context')
    dp(2)=ieee_value(0.,ieee_quiet_nan)
    CALL build_with_limits()
    ERROR STOP 'nonfinite dp was accepted'
  CASE('dp_zero_context')
    dp(2)=0.
    CALL build_with_limits()
    ERROR STOP 'nonpositive dp was accepted'
  CASE('cf_nan_context')
    cf(2)=ieee_value(0.,ieee_quiet_nan)
    CALL build_with_limits()
    ERROR STOP 'nonfinite cf was accepted'
  CASE('cf_range_context')
    cf(2)=1.25
    CALL build_with_limits()
    ERROR STOP 'out-of-range cf was accepted'
  CASE('dp_nan_no_context')
    dp(2)=ieee_value(0.,ieee_quiet_nan)
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qi,qr,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg)
    ERROR STOP 'nonfinite dp without context was accepted'
  CASE DEFAULT
    ERROR STOP 'unknown negative-policy fixture mode'
  END SELECT
  WRITE(*,'(A,A)') 'NEGATIVE_POLICY_FIXTURE_PASS ',TRIM(mode)

CONTAINS

  SUBROUTINE initialize_inputs()
    dp=[1000.,500.];cf=[0.5,0.5];gravity=10.
    qc=0.;qi=0.;qr=0.;qs=0.;qg=0.;qh=0.
    re_cloud=[10.,20.];re_ice=[30.,40.];re_snow=[50.,60.]
    limits=[0.125,0.0625,0.25,0.5,0.25,0.0625]
    grid=-11.;incloud=-12.;radius=-13.;omitted=-14.;clipped=-15.;correction=-16.
    clipped_bad=-17.;correction_bad=-18.
  END SUBROUTINE initialize_inputs

  SUBROUTINE save_input_bits()
    q_before=[qc,qi,qr,qs,qg,qh]
    dp_before=dp;cf_before=cf;radius_before=[re_cloud,re_ice,re_snow];limits_before=limits
    bits_q=TRANSFER(q_before,bits_q);bits_dp=TRANSFER(dp_before,bits_dp)
    bits_cf=TRANSFER(cf_before,bits_cf);bits_radius=TRANSFER(radius_before,bits_radius)
    bits_limits=TRANSFER(limits_before,bits_limits)
  END SUBROUTINE save_input_bits

  SUBROUTINE assert_input_bits_unchanged()
    IF(ANY(TRANSFER([qc,qi,qr,qs,qg,qh],bits_q)/=bits_q)) ERROR STOP 'raw q input bits changed'
    IF(ANY(TRANSFER(dp, bits_dp)/=bits_dp)) ERROR STOP 'dp input bits changed'
    IF(ANY(TRANSFER(cf, bits_cf)/=bits_cf)) ERROR STOP 'cf input bits changed'
    IF(ANY(TRANSFER([re_cloud,re_ice,re_snow],bits_radius)/=bits_radius)) ERROR STOP 'radius input bits changed'
    IF(ANY(TRANSFER(limits,bits_limits)/=bits_limits)) ERROR STOP 'negative limit input bits changed'
  END SUBROUTINE assert_input_bits_unchanged

  SUBROUTINE build_with_limits()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='column=d01:i=19:j=8', &
         omitted_grid_path=omitted,layer_reason=layers,negative_q_limits=limits, &
         clipped_negative_q=clipped,negative_grid_correction=correction)
  END SUBROUTINE build_with_limits

  SUBROUTINE build_default()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='column=d01:i=19:j=8', &
         omitted_grid_path=omitted,layer_reason=layers)
  END SUBROUTINE build_default

  SUBROUTINE build_with_bad_limits()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='column=d01:i=19:j=8', &
         negative_q_limits=limits_bad)
  END SUBROUTINE build_with_bad_limits

  SUBROUTINE build_with_bad_clipped()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='column=d01:i=19:j=8', &
         negative_q_limits=limits,clipped_negative_q=clipped_bad)
  END SUBROUTINE build_with_bad_clipped

  SUBROUTINE build_with_bad_correction()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='column=d01:i=19:j=8', &
         negative_q_limits=limits,negative_grid_correction=correction_bad)
  END SUBROUTINE build_with_bad_correction

  SUBROUTINE assert_mixed_results()
    REAL(real64) :: g64
    REAL :: expected_raw
    INTEGER, PARAMETER :: pathcol(6)=[1,2,3,4,5,6]
    rawq(:,1)=qc;rawq(:,2)=qi;rawq(:,3)=qr
    rawq(:,4)=qs;rawq(:,5)=qg;rawq(:,6)=qh
    DO k=1,n
      g64=REAL(dp(k),real64)*100.0_real64/REAL(gravity,real64)*1000.0_real64
      DO p=1,6
        IF(k==1) THEN
          IF(clipped(k,p)/=rawq(k,p)) ERROR STOP 'accepted negative not preserved in clipped output'
          IF(grid(k,pathcol(p))/=0.) ERROR STOP 'accepted negative not clipped in grid path'
          IF(correction(k,pathcol(p))/=REAL(-REAL(rawq(k,p),real64)*g64)) &
            ERROR STOP 'negative path correction mismatch'
        ELSE
          IF(clipped(k,p)/=0..OR.correction(k,pathcol(p))/=0.) &
            ERROR STOP 'positive q created a clipping output'
          IF(grid(k,pathcol(p))/=REAL(REAL(rawq(k,p),real64)*g64)) &
            ERROR STOP 'positive q grid path changed'
        END IF
        expected_raw=REAL(REAL(rawq(k,p),real64)*g64)
        IF(expected_raw+correction(k,pathcol(p))/=grid(k,pathcol(p))) &
          ERROR STOP 'signed raw path plus correction differs from sanitized path'
        IF(incloud(k,pathcol(p))/=grid(k,pathcol(p))/cf(k)) &
          ERROR STOP 'in-cloud path mismatch'
      END DO
    END DO
    IF(ANY(radius(:,1)/=re_cloud).OR.ANY(radius(:,2)/=re_ice).OR. &
       ANY(radius(:,3)/=re_snow)) ERROR STOP 'radii changed'
    IF(ANY(omitted/=0.)) ERROR STOP 'unexpected CF-zero omitted path'
    IF(ANY(layers/=RRTMGP_INPUT_OK)) ERROR STOP 'unexpected layer reason'
  END SUBROUTINE assert_mixed_results
END PROGRAM test_udm_negative_policy
