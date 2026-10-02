! Opt-in serial same-host-state radiation experiment. No results feed back to WRF.
MODULE module_ra_rrtmgp_audit
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
#ifdef _OPENMP
  USE omp_lib, ONLY: omp_get_max_threads
#endif
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: audit_enabled, audit_samples, audit_native4, audit_moments
  LOGICAL, SAVE :: checked=.FALSE., enabled=.FALSE.
  INTEGER, SAVE :: nsamples=128, csv_unit=0, native4=0
  TYPE :: audit_moments
    INTEGER :: ni,nj,nm,istart,jstart,n=0
    REAL(real64), ALLOCATABLE :: mean37(:,:,:),mean4(:,:,:),m237(:,:,:),m24(:,:,:),md(:,:,:),m2d(:,:,:)
  CONTAINS
    PROCEDURE :: init=>moments_init
    PROCEDURE :: add=>moments_add
    PROCEDURE :: write=>moments_write
  END TYPE
CONTAINS
  LOGICAL FUNCTION audit_enabled()
    CHARACTER(LEN=1024) :: path,value
    INTEGER :: stat,ios
    LOGICAL :: exists
    IF(.NOT.checked) THEN
      checked=.TRUE.
      CALL get_environment_variable('WRF_RRTMGP_AUDIT_DIR',path,STATUS=stat)
      enabled=stat==0.AND.LEN_TRIM(path)>0
      IF(enabled) THEN
#if defined(DM_PARALLEL)
        CALL wrf_error_fatal('RRTMGP_AUDIT_SERIAL_ONLY: MPI audit is unsupported')
#endif
#ifdef _OPENMP
        IF(omp_get_max_threads()>1) CALL wrf_error_fatal('RRTMGP_AUDIT_SERIAL_ONLY: OpenMP audit is unsupported')
#endif
        INQUIRE(FILE=TRIM(path)//'/.',EXIST=exists)
        IF(.NOT.exists) CALL wrf_error_fatal('RRTMGP_AUDIT_DIRECTORY_NOT_FOUND')
        CALL get_environment_variable('WRF_RRTMGP_AUDIT_SEEDS',value,STATUS=stat)
        IF(stat==0.AND.LEN_TRIM(value)>0) THEN
          READ(value,*,IOSTAT=ios) nsamples
          IF(ios/=0) CALL wrf_error_fatal('RRTMGP_AUDIT_INVALID_SEEDS')
          IF(nsamples<2.OR.nsamples>8192) CALL wrf_error_fatal('RRTMGP_AUDIT_SEEDS_RANGE: 2..8192')
        END IF
        CALL get_environment_variable('WRF_RRTMGP_AUDIT_NATIVE4',value,STATUS=stat)
        IF(stat==0.AND.LEN_TRIM(value)>0) THEN
          READ(value,*,IOSTAT=ios) native4
          IF(ios/=0) CALL wrf_error_fatal('RRTMGP_AUDIT_INVALID_NATIVE4')
          IF(native4/=0.AND.native4/=1) CALL wrf_error_fatal('RRTMGP_AUDIT_NATIVE4_RANGE: 0 or 1')
        END IF
        OPEN(NEWUNIT=csv_unit,FILE=TRIM(path)//'/same_state.csv',STATUS='replace',IOSTAT=ios)
        IF(ios/=0) CALL wrf_error_fatal('RRTMGP_AUDIT_OPEN_FAILED')
        WRITE(csv_unit,'(A)') 'phase,domain,step,source_seconds,i,j,metric,value37,value4,sample_count,mean37,sd37,mean4,sd4,sd_delta,radius_mode'
        FLUSH(csv_unit)
      END IF
    END IF
    audit_enabled=enabled
  END FUNCTION
  INTEGER FUNCTION audit_samples()
    audit_samples=nsamples
  END FUNCTION
  INTEGER FUNCTION audit_native4()
    audit_native4=native4
  END FUNCTION
  SUBROUTINE moments_init(this,ni,nj,nm,istart,jstart)
    CLASS(audit_moments),INTENT(INOUT) :: this
    INTEGER,INTENT(IN) :: ni,nj,nm,istart,jstart
    this%ni=ni;this%nj=nj;this%nm=nm;this%istart=istart;this%jstart=jstart;this%n=0
    ALLOCATE(this%mean37(ni,nj,nm),this%mean4(ni,nj,nm),this%m237(ni,nj,nm), &
      this%m24(ni,nj,nm),this%md(ni,nj,nm),this%m2d(ni,nj,nm))
    this%mean37=0;this%mean4=0;this%m237=0;this%m24=0;this%md=0;this%m2d=0
  END SUBROUTINE
  SUBROUTINE moments_add(this,x37,x4)
    CLASS(audit_moments),INTENT(INOUT) :: this
    REAL(real64),INTENT(IN) :: x37(:,:,:),x4(:,:,:)
    REAL(real64) :: d(this%ni,this%nj,this%nm),xd(this%ni,this%nj,this%nm)
    this%n=this%n+1
    d=x37-this%mean37;this%mean37=this%mean37+d/this%n;this%m237=this%m237+d*(x37-this%mean37)
    d=x4-this%mean4;this%mean4=this%mean4+d/this%n;this%m24=this%m24+d*(x4-this%mean4)
    xd=x37-x4;d=xd-this%md;this%md=this%md+d/this%n;this%m2d=this%m2d+d*(xd-this%md)
  END SUBROUTINE
  SUBROUTINE moments_write(this,phase,domain,step,time,x37,x4,labels)
    CLASS(audit_moments),INTENT(IN) :: this
    CHARACTER(LEN=*),INTENT(IN) :: phase,labels(:)
    INTEGER,INTENT(IN) :: domain,step
    REAL,INTENT(IN) :: time
    REAL(real64),INTENT(IN) :: x37(:,:,:),x4(:,:,:)
    INTEGER :: i,j,m,ios
    REAL(real64) :: s37,s4,sd
    DO m=1,this%nm
      DO j=1,this%nj
        DO i=1,this%ni
          s37=SQRT(MAX(0._real64,this%m237(i,j,m)/(this%n-1)))
          s4=SQRT(MAX(0._real64,this%m24(i,j,m)/(this%n-1)))
          sd=SQRT(MAX(0._real64,this%m2d(i,j,m)/(this%n-1)))
          WRITE(csv_unit,'(A,",",I0,",",I0,",",ES23.15E3,",",I0,",",I0,",",A,2(",",ES23.15E3),",",I0,5(",",ES23.15E3),",",I0)',IOSTAT=ios) &
            phase,domain,step,REAL(time,real64),this%istart+i-1,this%jstart+j-1,TRIM(labels(m)), &
            x37(i,j,m),x4(i,j,m),this%n,this%mean37(i,j,m),s37,this%mean4(i,j,m),s4,sd,native4
          IF(ios/=0) CALL wrf_error_fatal('RRTMGP_AUDIT_WRITE_FAILED')
        END DO
      END DO
    END DO
    FLUSH(csv_unit)
  END SUBROUTINE
END MODULE
