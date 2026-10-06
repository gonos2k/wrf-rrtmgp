PROGRAM test_udm_entry_density_trace
  USE module_ra_rrtmgp_trace, ONLY: trace_configure, trace_udm_entry_density_enabled, &
       trace_udm_entry_density_state
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  IMPLICIT NONE
  CHARACTER(LEN=32) :: mode
  REAL :: th(3),pii(3),p(3),qv(3),rho(3),qc(3),qi(3),qr(3),qs(3),qg(3),qh(3)
  REAL :: nn(3),nc(3),nr(3),bad(2)
  CALL GET_COMMAND_ARGUMENT(1,mode)
  th=[250.,251.,252.]; pii=[1.0,0.99,0.98]; p=[90000.,80000.,70000.]
  qv=[0.004,0.006,0.008]; rho=[1.1,1.0,0.3]
  qc=[1.e-5,-2.e-8,3.e-6]; qi=[4.e-7,5.e-7,-1.e-9]
  qr=[6.e-6,7.e-6,8.e-6]; qs=[9.e-8,1.e-7,2.e-7]
  qg=[3.e-8,4.e-8,5.e-8]; qh=[0.,-1.e-10,0.]
  nn=[1.e8,2.e8,-3.e6]; nc=[4.e7,5.e7,6.e7]; nr=[7.e6,8.e6,9.e6]
  bad=[1.,2.]

  ! Calling the public query before configuration must not initialize capture.
  IF(trace_udm_entry_density_enabled()) ERROR STOP 'gate active before trace_configure'
  CALL trace_configure()
  IF(TRIM(mode)=='disabled') THEN
    IF(trace_udm_entry_density_enabled()) ERROR STOP 'unset entry gate unexpectedly active'
    ! Even malformed arguments are ignored when the opt-in is disabled.
    CALL emit(2,3,bad)
  ELSE
    IF(.NOT.trace_udm_entry_density_enabled()) ERROR STOP 'entry gate was not enabled'
    SELECT CASE(TRIM(mode))
    CASE('packet')
      CALL emit(7,9,rho)
    CASE('selection')
      CALL emit(7,9,rho)
      CALL emit(2,3,rho)
    CASE('badshape')
      CALL emit(2,3,bad)
    CASE('nan')
      th(2)=ieee_value(0.,ieee_quiet_nan)
      CALL emit(2,3,rho)
    CASE('rawnan')
      qv(1)=ieee_value(0.,ieee_quiet_nan)
      CALL emit(2,3,rho)
    CASE('badclock')
      CALL trace_udm_entry_density_state(1,23,2,3,4,6,th,pii,p,qv,rho,qc,qi,qr,qs,qg,qh, &
           nn,nc,nr,287.,461.,1004.,1850.,9.81,30.,1.e-12,273.15,1000.,1000.,-1.)
    CASE('duplicate')
      CALL emit(2,3,rho)
      CALL emit(2,3,rho)
    CASE DEFAULT
      ERROR STOP 'unknown fixture mode'
    END SELECT
  END IF
  WRITE(*,'(A)') 'UDM entry density trace fixture completed: '//TRIM(mode)
CONTAINS
  SUBROUTINE emit(i,j,density)
    INTEGER,INTENT(IN) :: i,j
    REAL,INTENT(IN) :: density(:)
    CALL trace_udm_entry_density_state(1,23,i,j,4,6,th,pii,p,qv,density,qc,qi,qr,qs,qg,qh, &
         nn,nc,nr,287.,461.,1004.,1850.,9.81,30.,1.e-12,273.15,1000.,1000.,60.)
  END SUBROUTINE emit
END PROGRAM test_udm_entry_density_trace
