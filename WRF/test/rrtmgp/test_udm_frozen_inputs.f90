PROGRAM test_udm_frozen_inputs
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_build_udm_inputs, rrtmgp_udm_frozen_lambdas, &
       RRTMGP_INPUT_OK,RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED,RRTMGP_INPUT_UDM_FROZEN_INVALID
  IMPLICIT NONE
  INTEGER, PARAMETER :: n=4
  REAL :: dp(n),cf(n),qc(n),qr(n),qi(n),qs(n),qg(n),qh(n),re(n),mass(n)
  REAL :: grid(n,6),incloud(n,6),radii(n,3),omitted(n,6),clipped(n,6),correction(n,6),limits(6)
  REAL :: rho(n),lambda_g(n),lambda_h(n),badq(n),badrho(n)
  INTEGER :: reason,k
  CHARACTER(LEN=256) :: errmsg
  REAL(real64), PARAMETER :: pi=3.1415926535897932384626433832795_real64
  REAL(real64) :: expected_g,expected_h,closure

  dp=100.; cf=[0.,1.e-30,0.25,0.]
  qc=0.; qr=0.; qi=0.; qs=0.
  qg=[1.e-12,1.e-10,1.e-5,0.]
  qh=[1.e-20,1.e-9,1.e-5,2.e-5]
  re=0.; mass=[100.,10.,50.,100.]; limits=0.
  CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re,re,re,9.80665, &
       grid,incloud,radii,reason,errmsg,allow_clear_condensate=.TRUE., &
       omitted_grid_path=omitted,negative_q_limits=limits,clipped_negative_q=clipped, &
       negative_grid_correction=correction,dry_layer_mass_kg_m2=mass,frozen_uniform=.TRUE.)
  CALL assert(reason==RRTMGP_INPUT_OK,'uniform G/H builder status: '//TRIM(errmsg))
  DO k=1,n
    CALL close_enough('graupel grid path',grid(k,5),REAL(REAL(qg(k),real64)*REAL(mass(k),real64)*1000.),2.e-6)
    CALL close_enough('hail grid path',grid(k,6),REAL(REAL(qh(k),real64)*REAL(mass(k),real64)*1000.),2.e-6)
  END DO
  CALL assert(ALL(grid(:,5)>0. .EQV. qg>0.),'positive graupel path was lost')
  CALL assert(ALL(grid(:,6)>0. .EQV. qh>0.),'positive hail path was lost')
  CALL assert(ALL(incloud(:,5:6)==grid(:,5:6)),'uniform G/H must equal grid path without CF division')
  CALL assert(ALL(omitted(:,5:6)==0.),'uniform G/H must not be marked omitted at zero/tiny CF')

  ! Default mode remains strict: positive hail cannot pass into old optics.
  CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re,re,re,9.80665, &
       grid,incloud,radii,reason,errmsg,allow_clear_condensate=.TRUE., &
       omitted_grid_path=omitted,dry_layer_mass_kg_m2=mass)
  CALL assert(reason==RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED,'legacy mode no longer rejects positive hail')

  rho=[1.2,0.9,0.4,1.1]
  CALL rrtmgp_udm_frozen_lambdas(qg,qh,rho,lambda_g,lambda_h,reason,errmsg)
  CALL assert(reason==RRTMGP_INPUT_OK,'lambda helper status: '//TRIM(errmsg))
  CALL assert(lambda_g(1)==20000. .AND.lambda_g(2)==20000.,'graupel cutoff cap')
  CALL assert(lambda_h(1)==20000. .AND.lambda_h(2)==20000.,'hail cutoff cap')
  CALL assert(lambda_g(4)==20000. .AND.lambda_h(4)<20000.,'zero-q sentinel / active hail slope')
  expected_g=pi*500._real64*4.e6_real64
  expected_h=pi*912._real64*4.e4_real64
  closure=REAL(lambda_g(3),real64)**4*REAL(rho(3),real64)*REAL(qg(3),real64)
  CALL close_enough64('graupel PSD mass closure',closure,expected_g,3.e-6_real64)
  closure=REAL(lambda_h(3),real64)**4*REAL(rho(3),real64)*REAL(qh(3),real64)
  CALL close_enough64('hail PSD mass closure',closure,expected_h,3.e-6_real64)

  badq=qg; badq(2)=-1.e-12
  CALL rrtmgp_udm_frozen_lambdas(badq,qh,rho,lambda_g,lambda_h,reason,errmsg)
  CALL assert(reason==RRTMGP_INPUT_UDM_FROZEN_INVALID,'negative q was accepted by lambda helper')
  badrho=rho; badrho(3)=ieee_value(0.,ieee_quiet_nan)
  CALL rrtmgp_udm_frozen_lambdas(qg,qh,badrho,lambda_g,lambda_h,reason,errmsg)
  CALL assert(reason==RRTMGP_INPUT_UDM_FROZEN_INVALID,'nonfinite density was accepted by lambda helper')

  WRITE(*,'(A)') 'UDM_FROZEN_INPUTS_PASS'
CONTAINS
  SUBROUTINE assert(condition,message)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF(.NOT.condition) THEN
      WRITE(*,'(A)') TRIM(message)
      ERROR STOP 1
    END IF
  END SUBROUTINE assert

  SUBROUTINE close_enough(label,actual,expected,tolerance)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: actual,expected,tolerance
    REAL :: scale
    scale=MAX(ABS(expected),1.e-30)
    IF(ABS(actual-expected)>tolerance*scale) THEN
      WRITE(*,'(A,3(1X,ES16.8))') TRIM(label),actual,expected,tolerance
      ERROR STOP 1
    END IF
  END SUBROUTINE close_enough

  SUBROUTINE close_enough64(label,actual,expected,tolerance)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL(real64), INTENT(IN) :: actual,expected,tolerance
    REAL(real64) :: scale
    scale=MAX(ABS(expected),1.e-300_real64)
    IF(ABS(actual-expected)>tolerance*scale) THEN
      WRITE(*,'(A,3(1X,ES24.15E3))') TRIM(label),actual,expected,tolerance
      ERROR STOP 1
    END IF
  END SUBROUTINE close_enough64
END PROGRAM test_udm_frozen_inputs

SUBROUTINE wrf_error_fatal3(file,line,msg)
  CHARACTER(LEN=*), INTENT(IN) :: file,msg
  INTEGER, INTENT(IN) :: line
  WRITE(*,'(A,1X,I0,1X,A)') TRIM(file),line,TRIM(msg)
  ERROR STOP 2
END SUBROUTINE wrf_error_fatal3
