PROGRAM test_hydro_snapshot
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp_audit, ONLY: hydro_snapshot
  IMPLICIT NONE
  INTEGER, PARAMETER :: ims=10,ime=13,kms=3,kme=5,jms=20,jme=21
  REAL :: plev(ims:ime,kms:kme,jms:jme),cf(ims:ime,kms:kme,jms:jme)
  REAL :: qc(ims:ime,kms:kme,jms:jme),qi(ims:ime,kms:kme,jms:jme)
  REAL :: qr(ims:ime,kms:kme,jms:jme),qs(ims:ime,kms:kme,jms:jme)
  REAL :: qg(ims:ime,kms:kme,jms:jme),qh(ims:ime,kms:kme,jms:jme)
  INTEGER(int32) :: plev_bits(SIZE(plev)),cf_bits(SIZE(cf))
  INTEGER(int32) :: qc_bits(SIZE(qc)),qi_bits(SIZE(qi)),qr_bits(SIZE(qr))
  INTEGER(int32) :: qs_bits(SIZE(qs)),qg_bits(SIZE(qg)),qh_bits(SIZE(qh))
  CHARACTER(LEN=24) :: mode

  CALL get_command_argument(1,mode)
  CALL initialize_fields()
  IF(TRIM(mode)=='invalid') THEN
    qc=0.;qi=0.;qr=0.;qs=0.;qg=0.;qh=0.
    qi(10,3,20)=ieee_value(0.,ieee_quiet_nan)
    plev(11,4,21)=80000.
    plev(11,5,21)=90000.
  END IF
  CALL save_input_bits()

  SELECT CASE(TRIM(mode))
  CASE('valid')
    !$OMP PARALLEL SECTIONS NUM_THREADS(2)
    !$OMP SECTION
      CALL snapshot_tile(10,11,6,50.)
    !$OMP SECTION
      CALL snapshot_tile(12,13,6,50.)
    !$OMP END PARALLEL SECTIONS
    !$OMP PARALLEL SECTIONS NUM_THREADS(2)
    !$OMP SECTION
      CALL snapshot_tile(10,11,7,60.)
    !$OMP SECTION
      CALL snapshot_tile(12,13,7,60.)
    !$OMP END PARALLEL SECTIONS
  CASE('invalid')
    CALL snapshot_tile(10,11,8,70.)
  CASE('disabled')
    CALL snapshot_tile(10,11,9,80.)
  CASE DEFAULT
    ERROR STOP 'unknown fixture mode'
  END SELECT
  CALL assert_input_bits_unchanged()
  WRITE(*,'(A)') 'HYDRO_FIXTURE_PASS'

CONTAINS

  SUBROUTINE initialize_fields()
    INTEGER :: i,j
    plev=0.;cf=0.;qc=0.;qi=0.;qr=0.;qs=0.;qg=0.;qh=0.
    DO j=jms,jme
      DO i=ims,ime
        plev(i,3,j)=100000.
        plev(i,4,j)=90000.
        plev(i,5,j)=80000.
        cf(i,3:4,j)=0.5
      END DO
    END DO

    ! Tile one: two negatives, including a tiny representable diagnostic, and
    ! positive liquid/ice/graupel/hail paths, including CF=0 contributions.
    qc(10,3,20)=-2.0**(-100)
    qc(11,4,21)=-0.125
    qc(10,3,21)=0.25
    qc(11,3,20)=0.125
    cf(10,3,21)=0.
    cf(11,4,21)=0.
    qi(10,4,20)=0.0625
    cf(10,4,20)=0.25
    qg(10,3,20)=0.125
    qh(11,4,21)=0.0625

    ! Tile two supplies distinct negative and positive rain/snow paths.
    qr(12,3,20)=-0.0625
    qr(13,4,21)=0.03125
    qs(12,4,21)=-2.0**(-90)
    qs(13,4,20)=0.125
    cf(13,4,20)=0.
    qg(12,4,20)=0.25
    qh(13,3,21)=0.0625
    qc(12,3,21)=0.125
    qi(13,3,20)=0.0625
    cf(13,3,20)=0.25
  END SUBROUTINE initialize_fields

  SUBROUTINE save_input_bits()
    plev_bits=TRANSFER(plev,plev_bits); cf_bits=TRANSFER(cf,cf_bits)
    qc_bits=TRANSFER(qc,qc_bits); qi_bits=TRANSFER(qi,qi_bits)
    qr_bits=TRANSFER(qr,qr_bits); qs_bits=TRANSFER(qs,qs_bits)
    qg_bits=TRANSFER(qg,qg_bits); qh_bits=TRANSFER(qh,qh_bits)
  END SUBROUTINE save_input_bits

  SUBROUTINE assert_input_bits_unchanged()
    IF(ANY(TRANSFER(plev,plev_bits)/=plev_bits)) ERROR STOP 'plev was modified'
    IF(ANY(TRANSFER(cf,cf_bits)/=cf_bits)) ERROR STOP 'cf was modified'
    IF(ANY(TRANSFER(qc,qc_bits)/=qc_bits)) ERROR STOP 'qc was modified'
    IF(ANY(TRANSFER(qi,qi_bits)/=qi_bits)) ERROR STOP 'qi was modified'
    IF(ANY(TRANSFER(qr,qr_bits)/=qr_bits)) ERROR STOP 'qr was modified'
    IF(ANY(TRANSFER(qs,qs_bits)/=qs_bits)) ERROR STOP 'qs was modified'
    IF(ANY(TRANSFER(qg,qg_bits)/=qg_bits)) ERROR STOP 'qg was modified'
    IF(ANY(TRANSFER(qh,qh_bits)/=qh_bits)) ERROR STOP 'qh was modified'
  END SUBROUTINE assert_input_bits_unchanged

  SUBROUTINE snapshot_tile(ilo,ihi,step,seconds)
    INTEGER, INTENT(IN) :: ilo,ihi,step
    REAL, INTENT(IN) :: seconds
    CALL hydro_snapshot(2,step,seconds,37,37,10.,ims,ime,kms,kme,jms,jme, &
                        ilo,ihi,3,4,20,21,plev,cf,qc,qi,qr,qs,qg,qh)
  END SUBROUTINE snapshot_tile
END PROGRAM test_hydro_snapshot

SUBROUTINE wrf_error_fatal(message)
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: message
  CALL wrf_error_fatal3('module_ra_rrtmgp_audit.F',0,message)
END SUBROUTINE wrf_error_fatal
