PROGRAM test_rrtmgp_input_validation
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_validate_column_inputs
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=2,nl=3
  REAL :: play(nc,nl),plev(nc,nl+1),tlay(nc,nl),cf(nc,nl)
  REAL :: lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl)
  CHARACTER(LEN=64) :: test_case
  INTEGER :: arg_status

  CALL get_command_argument(1,test_case,status=arg_status)
  CALL initialize_inputs()
  IF(arg_status==0 .AND. LEN_TRIM(test_case)>0 .AND. TRIM(test_case)/='positive') THEN
    CALL make_invalid(TRIM(test_case))
  END IF

  IF(TRIM(test_case)=='shape') THEN
    CALL rrtmgp_validate_column_inputs(play,plev(:,1:nl),tlay,cf,lwp,iwp,swp,rel,rei,res)
  ELSE
    CALL rrtmgp_validate_column_inputs(play,plev,tlay,cf,lwp,iwp,swp,rel,rei,res)
  END IF
  IF(arg_status/=0 .OR. LEN_TRIM(test_case)==0 .OR. TRIM(test_case)=='positive') THEN
    WRITE(*,'(A)') 'RRTMGP_INPUT_VALIDATION_POSITIVE_ASSERTIONS_PASS'
    STOP
  END IF
  WRITE(*,'(A)') 'RRTMGP_INPUT_VALIDATION_ACCEPTED='//TRIM(test_case)
  ERROR STOP 2

CONTAINS
  SUBROUTINE initialize_inputs()
    play(:,1)=[750.,750.]
    play(:,2)=[250.,250.]
    play(:,3)=[50.,50.]
    plev(:,1)=[1000.,1000.]
    plev(:,2)=[500.,500.]
    plev(:,3)=[100.,100.]
    plev(:,4)=0.
    tlay=250.
    cf=.2
    lwp=0.; iwp=0.; swp=0.
    rel=10.; rei=10.; res=10.
  END SUBROUTINE initialize_inputs

  SUBROUTINE make_invalid(name)
    CHARACTER(LEN=*), INTENT(IN) :: name
    SELECT CASE(name)
    CASE('cf_range')
      cf(1,2)=1.1
    CASE('cf_nan')
      cf(2,1)=ieee_value(0.,ieee_quiet_nan)
    CASE('path_negative')
      lwp(1,1)=-1.
    CASE('cf_zero_path')
      cf(1,2)=0.; lwp(1,2)=1.
    CASE('pressure_order')
      plev(1,2)=1000.
    CASE('radius_inactive_nan')
      res(2,3)=ieee_value(0.,ieee_quiet_nan)
    CASE('radius_active_zero')
      iwp(1,2)=1.; rei(1,2)=0.
    CASE('shape')
      CONTINUE
    CASE DEFAULT
      WRITE(*,'(A)') 'UNKNOWN_VALIDATION_CASE='//TRIM(name)
      ERROR STOP 2
    END SELECT
  END SUBROUTINE make_invalid
END PROGRAM test_rrtmgp_input_validation
