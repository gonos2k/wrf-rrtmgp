PROGRAM test_udm_radius_trace
  USE module_ra_rrtmgp_trace, ONLY: trace_configure,trace_udm_radius_state,trace_udm_radius_enabled
  IMPLICIT NONE
  CHARACTER(LEN=32) :: mode
  REAL :: t(2),qc(2),qi(2),qs(2),nc(2),rho(2),rec(2),rei(2),res(2),cf(2)
  CALL GET_COMMAND_ARGUMENT(1,mode)
  IF(trace_udm_radius_enabled()) ERROR STOP 'radius gate must not be active before trace_configure'
  CALL trace_configure()
  IF(TRIM(mode)=='disabled'.AND.trace_udm_radius_enabled()) ERROR STOP 'radius gate unexpectedly enabled'
  IF(TRIM(mode)/='disabled'.AND..NOT.trace_udm_radius_enabled()) ERROR STOP 'radius gate was not configured'
  t=[250.,251.]; qc=[1.e-5,2.e-5]; qi=[3.e-6,4.e-6]; qs=[5.e-7,6.e-7]
  nc=[7.e7,8.e7]; rho=[1.1,1.2]; rec=[8.e-6,9.e-6]; rei=[2.e-5,3.e-5]
  res=[4.e-5,5.e-5]; cf=[0.4,0.5]
  SELECT CASE(TRIM(mode))
  CASE('disabled')
    CALL emit(2,3)
  CASE('selected')
    CALL emit(3,3)
    CALL emit(2,3)
  CASE('badshape')
    CALL trace_udm_radius_state(1,123,2,3,10,11,t,qc(:1),qi,qs,nc,rho,rec,rei,res,cf, &
                                1,2,1.e-12,273.15,1000.,100.)
  CASE('duplicate')
    CALL emit(2,3)
  CASE DEFAULT
    ERROR STOP 'unknown mode'
  END SELECT
  WRITE(*,'(A)') 'UDM radius trace fixture completed'
CONTAINS
  SUBROUTINE emit(i,j)
    INTEGER,INTENT(IN) :: i,j
    CALL trace_udm_radius_state(1,123,i,j,10,11,t,qc,qi,qs,nc,rho,rec,rei,res,cf, &
                                1,2,1.e-12,273.15,1000.,100.,60.)
  END SUBROUTINE emit
END PROGRAM test_udm_radius_trace
