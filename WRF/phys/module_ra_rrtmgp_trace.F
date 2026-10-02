! Opt-in, serial text capture for one RRTMGP column.  This module deliberately
! has no RTE/RRTMGP dependencies so it can be linked into standalone drivers.
! Capture state is process-global and not thread safe; call only from the
! serialized wrapper path.  With no WRF_RRTMGP_CAPTURE_DIR it is a no-op.
MODULE module_ra_rrtmgp_trace
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  IMPLICIT NONE
  PRIVATE

  PUBLIC :: trace_configure, trace_start, trace_active
  PUBLIC :: trace_input_start, trace_input, trace_input_end
  PUBLIC :: trace_result_start, trace_result, trace_raw_start, trace_raw
  PUBLIC :: trace_raw_end, trace_end

  INTERFACE trace_result
    MODULE PROCEDURE trace_result_real2, trace_result_real64_2, trace_result_real64_3
  END INTERFACE

  CHARACTER(len=2), PARAMETER :: phases(2) = [ CHARACTER(len=2) :: 'lw', 'sw' ]
  CHARACTER(len=1024), SAVE :: capture_dir = ''
  LOGICAL, SAVE :: env_checked = .FALSE., enabled = .FALSE., call_select_set = .FALSE.
  INTEGER, SAVE :: selected_call = 1, call_count(2) = 0
  LOGICAL, SAVE :: phase_done(2) = .FALSE., phase_active(2) = .FALSE.
  INTEGER, SAVE :: active_i(2) = 0, active_j(2) = 0
  INTEGER, SAVE :: result_unit(2) = 0, raw_unit(2) = 0

CONTAINS

  SUBROUTINE trace_configure()
    ! Call during rrtmgp_init, before any parallel column work begins.
    CALL trace_initialize()
  END SUBROUTINE trace_configure

  SUBROUTINE trace_start(phase, i, j)
    CHARACTER(len=*), INTENT(IN) :: phase
    INTEGER, INTENT(IN) :: i, j
    INTEGER :: p

    CALL trace_initialize()
    p = phase_index(phase)
    IF (.NOT. enabled) RETURN
    IF (p == 0) THEN
      CALL trace_fatal('RRTMGP_TRACE_INVALID_PHASE: phase must be LW or SW')
      RETURN
    END IF
    IF (i <= 0 .OR. j <= 0) THEN
      CALL trace_fatal('RRTMGP_TRACE_INVALID_INDEX: i and j must be positive')
      RETURN
    END IF
    IF (phase_done(p) .OR. phase_active(p)) RETURN
    IF (i /= 1 .OR. j /= 1) RETURN
    call_count(p) = call_count(p) + 1
    IF (call_count(p) /= selected_call) RETURN
    phase_active(p) = .TRUE.
    active_i(p) = i
    active_j(p) = j
  END SUBROUTINE trace_start

  LOGICAL FUNCTION trace_active(phase)
    CHARACTER(len=*), INTENT(IN) :: phase
    INTEGER :: p
    p = phase_index(phase)
    trace_active = p /= 0
    IF (p /= 0) trace_active = phase_active(p)
  END FUNCTION trace_active

  SUBROUTINE trace_input_start(phase, nc, nl, overlap, seed, iceflag,udm_precip)
    CHARACTER(len=*), INTENT(IN) :: phase
    INTEGER, INTENT(IN) :: nc, nl, overlap, seed, iceflag
    LOGICAL, OPTIONAL, INTENT(IN) :: udm_precip
    LOGICAL :: v4
    INTEGER :: p, unit, ios
    CHARACTER(len=1200) :: filename
    p = active_phase(phase)
    IF (p == 0) RETURN
    CALL check_dimensions(nc, nl)
    filename = trim(capture_dir)//'/'//trim(phases(p))//'.input'
    OPEN(NEWUNIT=unit, FILE=trim(filename), STATUS='replace', ACTION='write', IOSTAT=ios)
    CALL check_io(ios, 'opening input capture')
    v4=.FALSE.
    IF(PRESENT(udm_precip)) v4=udm_precip
    IF(v4) THEN
      WRITE(unit,'(a)',IOSTAT=ios) 'RRTMGP_REPLAY_V4'
    ELSE
      WRITE(unit,'(a)',IOSTAT=ios) 'RRTMGP_REPLAY_V3'
    END IF
    CALL check_io(ios, 'writing input magic')
    WRITE(unit,'(a,5(1x,i0))',IOSTAT=ios) uppercase(phases(p)), nc, nl, overlap, seed, iceflag
    CALL check_io(ios, 'writing input header')
    CLOSE(unit, IOSTAT=ios)
    CALL check_io(ios, 'closing input header')
  END SUBROUTINE trace_input_start

  SUBROUTINE trace_input(phase, name, values)
    CHARACTER(len=*), INTENT(IN) :: phase, name
    REAL, INTENT(IN) :: values(:,:)
    INTEGER :: p, unit, ios, r, c
    CHARACTER(len=1200) :: filename
    p = active_phase(phase)
    IF (p == 0) RETURN
    filename = trim(capture_dir)//'/'//trim(phases(p))//'.input'
    OPEN(NEWUNIT=unit, FILE=trim(filename), STATUS='old', POSITION='append', ACTION='write', IOSTAT=ios)
    CALL check_io(ios, 'opening input record')
    WRITE(unit,'(a,1x,i0,1x,i0)',IOSTAT=ios) trim(name), size(values,1), size(values,2)
    CALL check_io(ios, 'writing input record header')
    DO c=1,size(values,2)
      DO r=1,size(values,1)
        WRITE(unit,'(es25.16e3)',IOSTAT=ios) REAL(values(r,c),real64)
        CALL check_io(ios, 'writing input value')
      END DO
    END DO
    CLOSE(unit, IOSTAT=ios)
    CALL check_io(ios, 'closing input record')
  END SUBROUTINE trace_input

  SUBROUTINE trace_input_end(phase)
    CHARACTER(len=*), INTENT(IN) :: phase
    IF (active_phase(phase) == 0) RETURN
  END SUBROUTINE trace_input_end

  SUBROUTINE trace_result_start(phase, nc, nl)
    CHARACTER(len=*), INTENT(IN) :: phase
    INTEGER, INTENT(IN) :: nc, nl
    INTEGER :: p, ios
    CHARACTER(len=1200) :: filename
    p = active_phase(phase)
    IF (p == 0) RETURN
    CALL check_dimensions(nc, nl)
    filename = trim(capture_dir)//'/'//trim(phases(p))//'.result'
    OPEN(NEWUNIT=result_unit(p), FILE=trim(filename), STATUS='replace', ACTION='write', IOSTAT=ios)
    CALL check_io(ios, 'opening result capture')
    WRITE(result_unit(p),'(a)',IOSTAT=ios) 'RRTMGP_RESULT_V1'
    CALL check_io(ios, 'writing result magic')
    WRITE(result_unit(p),'(a,2(1x,i0))',IOSTAT=ios) uppercase(phases(p)), nc, nl
    CALL check_io(ios, 'writing result header')
  END SUBROUTINE trace_result_start

  SUBROUTINE trace_result_real2(phase, name, values)
    CHARACTER(len=*), INTENT(IN) :: phase, name
    REAL, INTENT(IN) :: values(:,:)
    INTEGER :: p
    p = active_phase(phase)
    IF (p == 0) RETURN
    CALL result_record_start(p, name, size(values,1), size(values,2), 1)
    CALL write_real2(result_unit(p), values)
  END SUBROUTINE trace_result_real2

  SUBROUTINE trace_result_real64_2(phase, name, values)
    CHARACTER(len=*), INTENT(IN) :: phase, name
    REAL(real64), INTENT(IN) :: values(:,:)
    INTEGER :: p, r, c, ios
    p = active_phase(phase)
    IF (p == 0) RETURN
    CALL result_record_start(p, name, size(values,1), size(values,2), 1)
    DO c=1,size(values,2)
      DO r=1,size(values,1)
        WRITE(result_unit(p),'(es25.16e3)',IOSTAT=ios) values(r,c)
        CALL check_io(ios, 'writing real64 result value')
      END DO
    END DO
  END SUBROUTINE trace_result_real64_2

  SUBROUTINE trace_result_real64_3(phase, name, values)
    CHARACTER(len=*), INTENT(IN) :: phase, name
    REAL(real64), INTENT(IN) :: values(:,:,:)
    INTEGER :: p, a, b, c, ios
    p = active_phase(phase)
    IF (p == 0) RETURN
    CALL result_record_start(p, name, size(values,1), size(values,2), size(values,3))
    DO c=1,size(values,3)
      DO b=1,size(values,2)
        DO a=1,size(values,1)
          WRITE(result_unit(p),'(es25.16e3)',IOSTAT=ios) values(a,b,c)
          CALL check_io(ios, 'writing rank3 result value')
        END DO
      END DO
    END DO
  END SUBROUTINE trace_result_real64_3

  SUBROUTINE trace_raw_start(phase, nl)
    CHARACTER(len=*), INTENT(IN) :: phase
    INTEGER, INTENT(IN) :: nl
    INTEGER :: p, ios
    CHARACTER(len=1200) :: filename
    p = active_phase(phase)
    IF (p == 0) RETURN
    IF (nl < 1) CALL trace_fatal('RRTMGP_TRACE_INVALID_DIMENSION: nl must be positive')
    filename = trim(capture_dir)//'/'//trim(phases(p))//'.raw'
    OPEN(NEWUNIT=raw_unit(p), FILE=trim(filename), STATUS='replace', ACTION='write', IOSTAT=ios)
    CALL check_io(ios, 'opening raw capture')
    WRITE(raw_unit(p),'(a)',IOSTAT=ios) 'RRTMGP_RAW_V1'
    CALL check_io(ios, 'writing raw magic')
    WRITE(raw_unit(p),'(a,3(1x,i0))',IOSTAT=ios) uppercase(phases(p)), active_i(p), active_j(p), nl
    CALL check_io(ios, 'writing raw header')
  END SUBROUTINE trace_raw_start

  SUBROUTINE trace_raw(phase, name, values)
    CHARACTER(len=*), INTENT(IN) :: phase, name
    REAL, INTENT(IN) :: values(:)
    INTEGER :: p, n, ios
    p = active_phase(phase)
    IF (p == 0) RETURN
    n = size(values)
    WRITE(raw_unit(p),'(a,1x,i0)',IOSTAT=ios) trim(name), n
    CALL check_io(ios, 'writing raw record header')
    DO n=1,size(values)
      WRITE(raw_unit(p),'(es25.16e3)',IOSTAT=ios) REAL(values(n),real64)
      CALL check_io(ios, 'writing raw value')
    END DO
  END SUBROUTINE trace_raw

  SUBROUTINE trace_raw_end(phase)
    CHARACTER(len=*), INTENT(IN) :: phase
    INTEGER :: p, ios
    p = active_phase(phase)
    IF (p == 0 .OR. raw_unit(p) == 0) RETURN
    CLOSE(raw_unit(p), IOSTAT=ios)
    CALL check_io(ios, 'closing raw capture')
    raw_unit(p) = 0
  END SUBROUTINE trace_raw_end

  SUBROUTINE trace_end(phase)
    CHARACTER(len=*), INTENT(IN) :: phase
    INTEGER :: p, ios
    p = active_phase(phase)
    IF (p == 0) RETURN
    IF (result_unit(p) /= 0) THEN
      CLOSE(result_unit(p), IOSTAT=ios)
      CALL check_io(ios, 'closing result capture')
      result_unit(p) = 0
    END IF
    CALL trace_raw_end(phase)
    phase_active(p) = .FALSE.
    phase_done(p) = .TRUE.
  END SUBROUTINE trace_end

  SUBROUTINE trace_initialize()
    INTEGER :: ios, env_status, n
    CHARACTER(len=128) :: value
    IF (env_checked) RETURN
    env_checked = .TRUE.
    CALL GET_ENVIRONMENT_VARIABLE('WRF_RRTMGP_CAPTURE_DIR', capture_dir, STATUS=env_status)
    enabled = env_status == 0 .AND. LEN_TRIM(capture_dir) > 0
    IF (.NOT.enabled) RETURN
    CALL GET_ENVIRONMENT_VARIABLE('WRF_RRTMGP_CAPTURE_CALL', value, STATUS=env_status)
    IF (env_status == 0 .AND. LEN_TRIM(value) > 0) THEN
      READ(value,*,IOSTAT=ios) n
      IF (ios /= 0 .OR. n < 1) THEN
        CALL trace_fatal('RRTMGP_TRACE_INVALID_CALL: WRF_RRTMGP_CAPTURE_CALL must be a positive integer')
      END IF
      selected_call = n
      call_select_set = .TRUE.
    END IF
    INQUIRE(FILE=trim(capture_dir)//'/.', EXIST=enabled)
    IF (.NOT.enabled) CALL trace_fatal('RRTMGP_TRACE_DIRECTORY_NOT_FOUND: capture directory must already exist')
  END SUBROUTINE trace_initialize

  INTEGER FUNCTION phase_index(phase)
    CHARACTER(len=*), INTENT(IN) :: phase
    CHARACTER(len=2) :: key
    INTEGER :: p
    key = '  '
    IF (LEN_TRIM(phase) >= 2) key = phase(1:2)
    phase_index = 0
    DO p=1,size(phases)
      IF (uppercase(key) == uppercase(phases(p))) phase_index = p
    END DO
  END FUNCTION phase_index

  FUNCTION uppercase(text) RESULT(out)
    CHARACTER(len=*), INTENT(IN) :: text
    CHARACTER(len=LEN(text)) :: out
    INTEGER :: k, code
    out = text
    DO k=1,LEN_TRIM(text)
      code = IACHAR(text(k:k))
      IF (code >= IACHAR('a') .AND. code <= IACHAR('z')) out(k:k) = ACHAR(code-32)
    END DO
  END FUNCTION uppercase

  INTEGER FUNCTION active_phase(phase)
    CHARACTER(len=*), INTENT(IN) :: phase
    INTEGER :: p
    p = phase_index(phase)
    active_phase = 0
    IF (p /= 0) THEN
      IF (phase_active(p)) active_phase = p
    END IF
  END FUNCTION active_phase

  SUBROUTINE check_dimensions(nc, nl)
    INTEGER, INTENT(IN) :: nc, nl
    IF (nc < 1 .OR. nl < 1) CALL trace_fatal('RRTMGP_TRACE_INVALID_DIMENSION: nc and nl must be positive')
  END SUBROUTINE check_dimensions

  SUBROUTINE result_record_start(p, name, n1, n2, n3)
    INTEGER, INTENT(IN) :: p, n1, n2, n3
    CHARACTER(len=*), INTENT(IN) :: name
    INTEGER :: ios
    IF (result_unit(p) == 0) CALL trace_fatal('RRTMGP_TRACE_RESULT_NOT_OPEN: call trace_result_start first')
    WRITE(result_unit(p),'(a,3(1x,i0))',IOSTAT=ios) trim(name), n1, n2, n3
    CALL check_io(ios, 'writing result record header')
  END SUBROUTINE result_record_start

  SUBROUTINE write_real2(unit, values)
    INTEGER, INTENT(IN) :: unit
    REAL, INTENT(IN) :: values(:,:)
    INTEGER :: r, c, ios
    DO c=1,size(values,2)
      DO r=1,size(values,1)
        WRITE(unit,'(es25.16e3)',IOSTAT=ios) REAL(values(r,c),real64)
        CALL check_io(ios, 'writing result value')
      END DO
    END DO
  END SUBROUTINE write_real2

  SUBROUTINE check_io(ios, operation)
    INTEGER, INTENT(IN) :: ios
    CHARACTER(len=*), INTENT(IN) :: operation
    CHARACTER(len=256) :: message
    IF (ios /= 0) THEN
      WRITE(message,'(a,": ",a)') 'RRTMGP_TRACE_IO_ERROR', trim(operation)
      CALL trace_fatal(trim(message))
    END IF
  END SUBROUTINE check_io

  SUBROUTINE trace_fatal(message)
    CHARACTER(len=*), INTENT(IN) :: message
    CALL wrf_error_fatal3('module_ra_rrtmgp_trace.F', 0, trim(message))
  END SUBROUTINE trace_fatal

END MODULE module_ra_rrtmgp_trace
