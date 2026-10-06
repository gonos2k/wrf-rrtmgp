SUBROUTINE wrf_error_fatal(message)
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: message
  WRITE(*,'(A)') TRIM(message)
  ERROR STOP 1
END SUBROUTINE wrf_error_fatal
