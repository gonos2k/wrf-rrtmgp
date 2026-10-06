program test_openmp_fatal_reason
  use module_ra_rrtmgp_input, only: rrtmgp_fatal
  use omp_lib, only: omp_get_thread_num
  implicit none
  integer :: tid

  !$omp parallel num_threads(2) private(tid)
  tid = omp_get_thread_num()
  if (tid == 1) call rrtmgp_fatal('OMP_WORKER_FATAL_REASON_VISIBLE', 'worker-fixture.F90')
  !$omp end parallel
  error stop 99
end program test_openmp_fatal_reason

subroutine wrf_error_fatal3(source, line, message)
  use, intrinsic :: iso_fortran_env, only: error_unit
  use omp_lib, only: omp_get_thread_num
  implicit none
  character(len=*), intent(in) :: source, message
  integer, intent(in) :: line

  ! Mimic the problematic WRF behavior: only the master thread prints the
  ! normal WRF fatal message, but the call from a worker still aborts.
  !$omp master
  write(error_unit, '(A,I0,2A)') 'WRF_MASTER_ONLY_MESSAGE line=', line, ' ', trim(message)
  flush(error_unit)
  !$omp end master
  if (trim(source) /= 'worker-fixture.F90') error stop 74
  if (line /= 0) error stop 75
  error stop 73
end subroutine wrf_error_fatal3
