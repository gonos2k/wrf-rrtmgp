PROGRAM test_rrtmgp_cloud_inputs
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite, ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_build_cloud_inputs, RRTMGP_INPUT_CLEAR_CONDENSATE
  IMPLICIT NONE
  INTEGER, PARAMETER :: n=3
  REAL :: dp_hpa(n),cf(n),qc(n),qi(n),qs(n),rliq(n),rice(n),rsnow(n),gravity
  REAL :: lwp(n),iwp(n),swp(n),rliq_original(n),rice_original(n),rsnow_original(n)
  REAL :: omitted_grid_path(n)
  INTEGER :: reason,arg_status,layer_reason(n)
  CHARACTER(LEN=64) :: test_case

  CALL get_command_argument(1,test_case,status=arg_status)
  IF(arg_status/=0.OR.LEN_TRIM(test_case)==0.OR.TRIM(test_case)=='positive') THEN
    CALL run_positive_cases()
    WRITE(*,'(A)') 'RRTMGP_CLOUD_INPUT_POSITIVE_ASSERTIONS_PASS'
    STOP
  END IF
  CALL initialize_inputs()
  CALL make_invalid(TRIM(test_case))
  CALL rrtmgp_build_cloud_inputs(dp_hpa,cf,qc,qi,qs,rliq,rice,rsnow,gravity,lwp,iwp,swp,reason)
  WRITE(*,'(A)') 'INVALID_INPUT_ACCEPTED='//TRIM(test_case)
  ERROR STOP 2
CONTAINS
  SUBROUTINE initialize_inputs()
    dp_hpa=[1000.,700.,300.]
    cf=[.3,.6,.9]
    qc=[1.e-3,2.e-4,4.e-5]
    qi=[1.e-4,1.e-5,0.]
    qs=[5.e-5,3.e-5,1.e-5]
    rliq=[30.,200.,260.]
    rice=[30.,200.,260.]
    rsnow=[30.,200.,260.]
    gravity=9.80665
    rliq_original=rliq; rice_original=rice; rsnow_original=rsnow
  END SUBROUTINE initialize_inputs

  SUBROUTINE run_positive_cases()
    CALL run_fraction(1.,'cloud fraction one')
    CALL run_fraction(.3,'cloud fraction 0.3')
    CALL run_fraction(.001,'cloud fraction 0.001')
    CALL run_fraction(1.e-6,'cloud fraction 1e-6')
    CALL run_dry_case()
    CALL run_clear_condensate_policy()
  END SUBROUTINE run_positive_cases

  SUBROUTINE run_fraction(fraction,label)
    REAL, INTENT(IN) :: fraction
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL :: expected_lwp(n),expected_iwp(n),expected_swp(n),expected_total(n)
    CALL initialize_inputs()
    cf=fraction
    CALL rrtmgp_build_cloud_inputs(dp_hpa,cf,qc,qi,qs,rliq,rice,rsnow,gravity,lwp,iwp,swp,reason)
    IF(reason/=0) CALL fail(TRIM(label)//': reason must be zero')
    expected_lwp=qc*(dp_hpa*100.)/gravity*1000.
    expected_iwp=qi*(dp_hpa*100.)/gravity*1000.
    expected_swp=qs*(dp_hpa*100.)/gravity*1000.
    expected_total=(qc+qi+qs)*(dp_hpa*100.)/gravity*1000.
    CALL check_finite(TRIM(label)//' masses',lwp,iwp,swp)
    CALL check_vector_close(TRIM(label)//' liquid column mass',cf*lwp,expected_lwp,2.e-5)
    CALL check_vector_close(TRIM(label)//' ice column mass',cf*iwp,expected_iwp,2.e-5)
    CALL check_vector_close(TRIM(label)//' snow column mass',cf*swp,expected_swp,2.e-5)
    CALL check_vector_close(TRIM(label)//' total column mass',cf*(lwp+iwp+swp),expected_total,2.e-5)
    CALL check_radii_unchanged(label)
  END SUBROUTINE run_fraction

  SUBROUTINE run_dry_case()
    CALL initialize_inputs()
    cf=0.; qc=0.; qi=0.; qs=0.
    CALL rrtmgp_build_cloud_inputs(dp_hpa,cf,qc,qi,qs,rliq,rice,rsnow,gravity,lwp,iwp,swp,reason)
    IF(reason/=1) CALL fail('clear dry columns must have reason=1')
    CALL check_vector_close('clear dry liquid mass',lwp,0.*lwp,0.)
    CALL check_vector_close('clear dry ice mass',iwp,0.*iwp,0.)
    CALL check_vector_close('clear dry snow mass',swp,0.*swp,0.)
    CALL check_radii_unchanged('clear dry columns')
  END SUBROUTINE run_dry_case

  SUBROUTINE run_clear_condensate_policy()
    REAL :: expected_lwp(n),expected_iwp(n),expected_swp(n),expected_omitted(n)
    CALL initialize_inputs()
    cf=[.001,0.,.3]
    CALL rrtmgp_build_cloud_inputs(dp_hpa,cf,qc,qi,qs,rliq,rice,rsnow,gravity, &
         lwp,iwp,swp,reason,allow_clear_condensate=.TRUE., &
         omitted_grid_path=omitted_grid_path,layer_reason=layer_reason)
    IF(reason/=RRTMGP_INPUT_CLEAR_CONDENSATE) &
      CALL fail('clear-condensate policy must return aggregate reason=6')
    IF(ANY(layer_reason/=[0,RRTMGP_INPUT_CLEAR_CONDENSATE,0])) &
      CALL fail('clear-condensate layer reasons must be [0,6,0]')

    expected_lwp=0.; expected_iwp=0.; expected_swp=0.; expected_omitted=0.
    expected_lwp(1)=qc(1)*(dp_hpa(1)*100.)/gravity*1000./cf(1)
    expected_iwp(1)=qi(1)*(dp_hpa(1)*100.)/gravity*1000./cf(1)
    expected_swp(1)=qs(1)*(dp_hpa(1)*100.)/gravity*1000./cf(1)
    expected_lwp(3)=qc(3)*(dp_hpa(3)*100.)/gravity*1000./cf(3)
    expected_iwp(3)=qi(3)*(dp_hpa(3)*100.)/gravity*1000./cf(3)
    expected_swp(3)=qs(3)*(dp_hpa(3)*100.)/gravity*1000./cf(3)
    expected_omitted(2)=(qc(2)+qi(2)+qs(2))*(dp_hpa(2)*100.)/gravity*1000.
    CALL check_vector_close('clear-condensate liquid paths',lwp,expected_lwp,2.e-5)
    CALL check_vector_close('clear-condensate ice paths',iwp,expected_iwp,2.e-5)
    CALL check_vector_close('clear-condensate snow paths',swp,expected_swp,2.e-5)
    CALL check_vector_close('omitted clear-grid condensate path',omitted_grid_path,expected_omitted,2.e-5)
    CALL check_radii_unchanged('clear-condensate policy')
  END SUBROUTINE run_clear_condensate_policy

  SUBROUTINE check_radii_unchanged(label)
    CHARACTER(LEN=*), INTENT(IN) :: label
    CALL check_vector_close(TRIM(label)//' rliq unchanged',rliq,rliq_original,0.)
    CALL check_vector_close(TRIM(label)//' rice unchanged',rice,rice_original,0.)
    CALL check_vector_close(TRIM(label)//' rsnow unchanged',rsnow,rsnow_original,0.)
  END SUBROUTINE check_radii_unchanged

  SUBROUTINE make_invalid(name)
    CHARACTER(LEN=*), INTENT(IN) :: name
    SELECT CASE(name)
    CASE('cf_negative')
      cf(1)=-.01
    CASE('cf_above_one')
      cf(2)=1.01
    CASE('cf_nan')
      cf(2)=ieee_value(0.,ieee_quiet_nan)
    CASE('qc_negative')
      qc(1)=-1.e-3
    CASE('qc_nan')
      qc(1)=ieee_value(0.,ieee_quiet_nan)
    CASE('dp_negative')
      dp_hpa(1)=-100.
    CASE('cf_zero_wet')
      cf(1)=0.; qc(1)=1.e-3
    CASE('tiny_cf_overflow')
      cf(1)=1.e-38; qc(1)=1.
    CASE DEFAULT
      WRITE(*,'(A)') 'UNKNOWN_INVALID_CASE='//TRIM(name)
      ERROR STOP 2
    END SELECT
  END SUBROUTINE make_invalid

  SUBROUTINE check_finite(label,a,b,c)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: a(:),b(:),c(:)
    IF(.NOT.ALL(ieee_is_finite(a)).OR..NOT.ALL(ieee_is_finite(b)).OR..NOT.ALL(ieee_is_finite(c))) &
      CALL fail(TRIM(label)//' contains non-finite values')
  END SUBROUTINE check_finite

  SUBROUTINE check_vector_close(label,actual,expected,tolerance)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: actual(:),expected(:),tolerance
    REAL :: scale,error
    IF(SIZE(actual)/=SIZE(expected)) CALL fail(TRIM(label)//' shape mismatch')
    IF(.NOT.ALL(ieee_is_finite(actual)).OR..NOT.ALL(ieee_is_finite(expected))) &
      CALL fail(TRIM(label)//' contains non-finite values')
    scale=MAX(1.,MAXVAL(ABS(expected)),MAXVAL(ABS(actual)))
    error=MAXVAL(ABS(actual-expected))
    IF(error>tolerance*scale) THEN
      WRITE(*,'(A,ES12.4)') TRIM(label)//' max error: ',error
      CALL fail(label)
    END IF
  END SUBROUTINE check_vector_close

  SUBROUTINE fail(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    WRITE(*,'(A)') 'FAIL: '//TRIM(message)
    ERROR STOP 1
  END SUBROUTINE fail
END PROGRAM test_rrtmgp_cloud_inputs
