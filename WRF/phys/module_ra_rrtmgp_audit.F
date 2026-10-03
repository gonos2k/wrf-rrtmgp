! Opt-in observations; no results feed back to WRF. Same-state engine replay
! remains serial-only. Native hydrometeor snapshots also support MPI/OpenMP.
MODULE module_ra_rrtmgp_audit
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
#ifdef _OPENMP
  USE omp_lib, ONLY: omp_get_max_threads
#endif
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: audit_enabled, audit_samples, audit_native4, audit_moments
  PUBLIC :: hydro_snapshot
  LOGICAL, SAVE :: hydro_checked=.FALSE., hydro_enabled=.FALSE.
  CHARACTER(LEN=1024), SAVE :: hydro_directory=''
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
  ! Native UDM input observation only, before either radiation wrapper can
  ! reject or clip it. A separate file for each physical tile avoids MPI file
  ! collisions. Critical regions protect configuration and local OpenMP I/O.
  ! Values are never written back, and no numerical tolerance is imposed.
  SUBROUTINE hydro_snapshot(domain,step,seconds,lw,sw,gravity, &
                            ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte, &
                            plev,cf,qc,qi,qr,qs,qg,qh)
    INTEGER, INTENT(IN) :: domain,step,lw,sw,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
    REAL, INTENT(IN) :: seconds,gravity
    REAL, INTENT(IN) :: plev(ims:ime,kms:kme,jms:jme),cf(ims:ime,kms:kme,jms:jme)
    REAL, INTENT(IN) :: qc(ims:ime,kms:kme,jms:jme),qi(ims:ime,kms:kme,jms:jme)
    REAL, INTENT(IN) :: qr(ims:ime,kms:kme,jms:jme),qs(ims:ime,kms:kme,jms:jme)
    REAL, INTENT(IN) :: qg(ims:ime,kms:kme,jms:jme),qh(ims:ime,kms:kme,jms:jme)
    CHARACTER(LEN=8), PARAMETER :: names(6)=[CHARACTER(LEN=8)::'QC','QI','QR','QS','QG','QH']
    CHARACTER(LEN=1400) :: filename
    CHARACTER(LEN=160) :: tile
    INTEGER :: stat,ios,unit,p,i,j,k,imin,jmin,kmin,nnegative,npositive,ninvalid,npathinvalid
    REAL(real64) :: values(6),q,qmin,qmax,wp,dp,sumpositive,maxpositive,clearpath,negativepath
    LOGICAL :: exists
    !$OMP CRITICAL(rrtmgp_hydro_configuration)
    IF(.NOT.hydro_checked) THEN
      CALL get_environment_variable('WRF_RRTMGP_HYDRO_DIAG_DIR',hydro_directory,STATUS=stat)
      hydro_enabled=stat==0.AND.LEN_TRIM(hydro_directory)>0
      IF(hydro_enabled) THEN
        INQUIRE(FILE=TRIM(hydro_directory)//'/.',EXIST=exists)
        IF(.NOT.exists) CALL wrf_error_fatal('RRTMGP_HYDRO_DIAG_DIRECTORY_NOT_FOUND')
      END IF
      hydro_checked=.TRUE.
    END IF
    !$OMP END CRITICAL(rrtmgp_hydro_configuration)
    IF(.NOT.hydro_enabled) RETURN
    IF(its>ite.OR.jts>jte.OR.kts>kte) RETURN
    IF(its<ims.OR.ite>ime.OR.jts<jms.OR.jte>jme.OR.kts<kms.OR.kte+1>kme) &
      CALL wrf_error_fatal('RRTMGP_HYDRO_DIAG_INVALID_BOUNDS')
    IF(.NOT.ieee_is_finite(gravity).OR.gravity<=0.) &
      CALL wrf_error_fatal('RRTMGP_HYDRO_DIAG_INVALID_GRAVITY')
    WRITE(tile,'(A,I0,A,I0,A,I0,A,I0,A,I0)') 'd',domain,'_i',its,'-',ite,'_j',jts,'-',jte
    filename=TRIM(hydro_directory)//'/hydro_'//TRIM(tile)//'.csv'
    !$OMP CRITICAL(rrtmgp_hydro_output)
    INQUIRE(FILE=TRIM(filename),EXIST=exists)
    OPEN(NEWUNIT=unit,FILE=TRIM(filename),STATUS='unknown',POSITION='append',ACTION='write',IOSTAT=ios)
    IF(ios/=0) CALL wrf_error_fatal('RRTMGP_HYDRO_DIAG_OPEN_FAILED')
    IF(.NOT.exists) THEN
      WRITE(unit,'(A)',IOSTAT=ios) &
        'kind,domain,step,seconds,lw,sw,species,negative_count,positive_count,nonfinite_count,path_invalid_count,min_q_kgkg,max_q_kgkg,min_i,min_j,min_k,sum_positive_path_gm2,max_positive_path_gm2,cf0_positive_path_gm2,sum_negative_path_gm2'
      IF(ios/=0) CALL wrf_error_fatal('RRTMGP_HYDRO_DIAG_WRITE_FAILED')
    END IF
    DO p=1,6
      nnegative=0; npositive=0; ninvalid=0; npathinvalid=0
      qmin=HUGE(0._real64); qmax=-HUGE(0._real64)
      imin=0; jmin=0; kmin=0
      sumpositive=0; maxpositive=0; clearpath=0; negativepath=0
      DO j=jts,jte
        DO k=kts,kte
          DO i=its,ite
            values=REAL([qc(i,k,j),qi(i,k,j),qr(i,k,j),qs(i,k,j),qg(i,k,j),qh(i,k,j)],real64)
            q=values(p)
            IF(.NOT.ieee_is_finite(q)) THEN
              ninvalid=ninvalid+1
              CYCLE
            END IF
            IF(q<qmin) THEN
              qmin=q; imin=i; jmin=j; kmin=k
            END IF
            qmax=MAX(qmax,q)
            IF(q<0._real64) nnegative=nnegative+1
            IF(q>0._real64) npositive=npositive+1
            dp=REAL(plev(i,k,j),real64)-REAL(plev(i,k+1,j),real64)
            wp=0._real64
            IF(.NOT.ieee_is_finite(dp).OR.dp<=0._real64) THEN
              npathinvalid=npathinvalid+1
            ELSE
              wp=q*dp/REAL(gravity,real64)*1000._real64
              IF(q>0._real64) THEN
                sumpositive=sumpositive+wp; maxpositive=MAX(maxpositive,wp)
                IF(cf(i,k,j)==0.) clearpath=clearpath+wp
              ELSE IF(q<0._real64) THEN
                negativepath=negativepath+wp
              END IF
            END IF
            ! Every negative, including its actual WRF indices, is preserved.
            IF(q<0._real64) THEN
              CALL write_row('negative',1,0,0,0,q,q,i,j,k,0._real64,0._real64,0._real64,wp)
            END IF
          END DO
        END DO
      END DO
      IF(ninvalid==(ite-its+1)*(jte-jts+1)*(kte-kts+1)) THEN
        qmin=0._real64; qmax=0._real64 ! Counts identify the absence of finite extrema.
      END IF
      CALL write_row('summary',nnegative,npositive,ninvalid,npathinvalid,qmin,qmax,imin,jmin,kmin, &
                     sumpositive,maxpositive,clearpath,negativepath)
    END DO
    FLUSH(unit,IOSTAT=ios)
    IF(ios/=0) CALL wrf_error_fatal('RRTMGP_HYDRO_DIAG_FLUSH_FAILED')
    CLOSE(unit,IOSTAT=ios)
    IF(ios/=0) CALL wrf_error_fatal('RRTMGP_HYDRO_DIAG_CLOSE_FAILED')
    !$OMP END CRITICAL(rrtmgp_hydro_output)
  CONTAINS
    SUBROUTINE write_row(kind,nn,np,nf,nd,lo,hi,ii,jj,kk,total,peak,clear,neg)
      CHARACTER(LEN=*), INTENT(IN) :: kind
      INTEGER, INTENT(IN) :: nn,np,nf,nd,ii,jj,kk
      REAL(real64), INTENT(IN) :: lo,hi,total,peak,clear,neg
      WRITE(unit,'(A,2(",",I0),",",ES23.15E3,2(",",I0),",",A,4(",",I0),2(",",ES23.15E3),3(",",I0),4(",",ES23.15E3))',IOSTAT=ios) &
        kind,domain,step,REAL(seconds,real64),lw,sw,TRIM(names(p)),nn,np,nf,nd,lo,hi,ii,jj,kk,total,peak,clear,neg
      IF(ios/=0) CALL wrf_error_fatal('RRTMGP_HYDRO_DIAG_WRITE_FAILED')
    END SUBROUTINE write_row
  END SUBROUTINE hydro_snapshot

  LOGICAL FUNCTION audit_enabled()
    CHARACTER(LEN=1024) :: path,value
    INTEGER :: stat,ios
    LOGICAL :: exists
    !$OMP CRITICAL(rrtmgp_audit_configuration)
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
        WRITE(csv_unit,'(A)') 'phase,domain,step,source_seconds,i,j,metric,value37,value4,sample_count,mean37,sd37,mean4,sd4,sd_delta,radius_mode,scope'
        FLUSH(csv_unit)
      END IF
    END IF
    !$OMP END CRITICAL(rrtmgp_audit_configuration)
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
  SUBROUTINE moments_write(this,phase,domain,step,time,x37,x4,labels,scope)
    CLASS(audit_moments),INTENT(IN) :: this
    CHARACTER(LEN=*),INTENT(IN) :: phase,labels(:),scope
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
          WRITE(csv_unit,'(A,",",I0,",",I0,",",ES23.15E3,",",I0,",",I0,",",A,2(",",ES23.15E3),",",I0,5(",",ES23.15E3),",",I0,",",A)',IOSTAT=ios) &
            phase,domain,step,REAL(time,real64),this%istart+i-1,this%jstart+j-1,TRIM(labels(m)), &
            x37(i,j,m),x4(i,j,m),this%n,this%mean37(i,j,m),s37,this%mean4(i,j,m),s4,sd,native4,TRIM(scope)
          IF(ios/=0) CALL wrf_error_fatal('RRTMGP_AUDIT_WRITE_FAILED')
        END DO
      END DO
    END DO
    FLUSH(csv_unit)
  END SUBROUTINE
END MODULE
