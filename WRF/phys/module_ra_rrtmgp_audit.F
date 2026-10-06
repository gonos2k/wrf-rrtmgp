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

! Bounded observer for the legacy RRTMG calculation inside the existing
! selected-column audit. It is activated only by the driver around the
! engine-4, seed-override -1 call. Production solver calls leave it
! inactive: wrapper checks are no-ops and do not write or copy arrays.
MODULE module_rrtmg4_optics_export
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
#ifdef _OPENMP
  USE omp_lib, ONLY: omp_get_max_threads
#endif
  IMPLICIT NONE
  EXTERNAL :: wrf_error_fatal
  PRIVATE
  PUBLIC :: rrtmg4_export_begin, rrtmg4_export_end, rrtmg4_export_active
  PUBLIC :: rrtmg4_export_stage, rrtmg4_export_real1, rrtmg4_export_real2
  PUBLIC :: rrtmg4_export_int1
  LOGICAL, SAVE :: active=.FALSE.
  LOGICAL, SAVE :: export_checked=.FALSE., export_requested=.FALSE.
  INTEGER, SAVE :: out_unit=0, stage_mask=0
  CHARACTER(LEN=1024), SAVE :: out_dir=''
  ! Historical selector remains the default; overrides require all five keys.
  INTEGER, SAVE :: selected_domain=1, selected_i=24, selected_j=55, selected_step=2161
  REAL(real64), SAVE :: selected_seconds=129600._real64
CONTAINS
  SUBROUTINE rrtmg4_export_begin(phase,domain,step,seconds,global_i,global_j,solar_cosine)
    CHARACTER(LEN=*), INTENT(IN) :: phase
    INTEGER, INTENT(IN) :: domain,step,global_i,global_j
    REAL, INTENT(IN) :: seconds
    REAL, OPTIONAL, INTENT(IN) :: solar_cosine
    CHARACTER(LEN=2048) :: filename
    INTEGER :: env_status,env_length,ios
    LOGICAL :: exists
    IF(active) CALL wrf_error_fatal('RRTMG4_EXPORT_NESTED_BEGIN')
    IF(.NOT.export_checked) THEN
      out_dir=''
      CALL get_environment_variable('WRF_RRTMGP_RRTMG4_EXPORT_DIR',out_dir, &
                                     LENGTH=env_length,STATUS=env_status)
      IF(env_status==-1) CALL wrf_error_fatal('RRTMG4_EXPORT_DIRECTORY_TOO_LONG')
      IF(env_status>0.AND.env_length>0) CALL wrf_error_fatal('RRTMG4_EXPORT_ENVIRONMENT_READ_FAILED')
      export_requested=env_length>0.AND.LEN_TRIM(out_dir)>0
      IF(export_requested) CALL read_export_selection()
      export_checked=.TRUE.
    END IF
    IF(.NOT.export_requested) RETURN
#ifdef DM_PARALLEL
    CALL wrf_error_fatal('RRTMG4_EXPORT_REQUIRES_SERIAL_EXECUTION')
    RETURN
#endif
#ifdef _OPENMP
    IF(omp_get_max_threads()>1) THEN
      CALL wrf_error_fatal('RRTMG4_EXPORT_REQUIRES_ONE_OPENMP_THREAD')
      RETURN
    END IF
#endif
    ! This export is intentionally pinned to the exact same-state comparison
    ! point. Other calls, including all production calls, are no-ops.
    IF(domain/=selected_domain.OR.step/=selected_step.OR. &
       global_i/=selected_i.OR.global_j/=selected_j) RETURN
    IF(.NOT.ieee_is_finite(seconds)) CALL wrf_error_fatal('RRTMG4_EXPORT_NONFINITE_CALL_TIME')
    IF(ABS(REAL(seconds,real64)-selected_seconds)>0.01_real64) RETURN
    IF(phase/='lw'.AND.phase/='sw') CALL wrf_error_fatal('RRTMG4_EXPORT_INVALID_PHASE')
    IF(phase=='sw') THEN
      IF(.NOT.PRESENT(solar_cosine)) CALL wrf_error_fatal('RRTMG4_EXPORT_MISSING_SOLAR_COSINE')
      IF(.NOT.ieee_is_finite(solar_cosine)) CALL wrf_error_fatal('RRTMG4_EXPORT_NONFINITE_SOLAR_COSINE')
      ! The wrapper does not visit any optics stages below the horizon.
      IF(solar_cosine<=0.) RETURN
    END IF
    INQUIRE(FILE=TRIM(out_dir)//'/.',EXIST=exists)
    IF(.NOT.exists) CALL wrf_error_fatal('RRTMG4_EXPORT_DIRECTORY_NOT_FOUND')
    WRITE(filename,'(A,"/rrtmg4_d",I2.2,"_i",I0,"_j",I0,"_step",I0,"_",A,".txt")') &
      TRIM(out_dir),domain,global_i,global_j,step,TRIM(phase)
    OPEN(NEWUNIT=out_unit,FILE=TRIM(filename),STATUS='new',ACTION='write',IOSTAT=ios)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_OUTPUT_CREATE_FAILED')
    active=.TRUE.; stage_mask=0
    WRITE(out_unit,'(A)',IOSTAT=ios) 'RRTMG4_SELECTED_COLUMN_EXPORT_V1'
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_HEADER_WRITE_FAILED')
    WRITE(out_unit,'(A,1X,A)',IOSTAT=ios) 'phase',TRIM(phase)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_HEADER_WRITE_FAILED')
    WRITE(out_unit,'(A,1X,I0)',IOSTAT=ios) 'domain',domain
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_HEADER_WRITE_FAILED')
    WRITE(out_unit,'(A,1X,I0)',IOSTAT=ios) 'step',step
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_HEADER_WRITE_FAILED')
    WRITE(out_unit,'(A,1X,ES24.16E3)',IOSTAT=ios) 'source_seconds',REAL(seconds,real64)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_HEADER_WRITE_FAILED')
    WRITE(out_unit,'(A,1X,I0)',IOSTAT=ios) 'i',global_i
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_HEADER_WRITE_FAILED')
    WRITE(out_unit,'(A,1X,I0)',IOSTAT=ios) 'j',global_j
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_HEADER_WRITE_FAILED')
    WRITE(out_unit,'(A)',IOSTAT=ios) 'layout fortran_order_first_index_fastest; numeric values use REAL64 text precision'
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_HEADER_WRITE_FAILED')
  END SUBROUTINE

  SUBROUTINE read_export_selection()
    CHARACTER(LEN=40), PARAMETER :: suffix(5)=[CHARACTER(LEN=40):: &
      'DOMAIN','I','J','STEP','SECONDS']
    CHARACTER(LEN=128) :: value(5)
    CHARACTER(LEN=80) :: key
    INTEGER :: n,length,stat,ios,key_count,indices(4)
    LOGICAL :: present(5)
    REAL(real64) :: time_value
    present=.FALSE.;value=''
    DO n=1,5
      key='WRF_RRTMGP_RRTMG4_EXPORT_'//TRIM(suffix(n))
      CALL get_environment_variable(TRIM(key),value(n),LENGTH=length,STATUS=stat)
      IF(stat==-1) CALL wrf_error_fatal('RRTMG4_EXPORT_SELECTOR_TOO_LONG')
      IF(stat>1) CALL wrf_error_fatal('RRTMG4_EXPORT_SELECTOR_READ_FAILED')
      present(n)=stat==0
      IF(present(n).AND.length==0) CALL wrf_error_fatal('RRTMG4_EXPORT_EMPTY_SELECTOR')
    END DO
    key_count=COUNT(present)
    IF(key_count==0) RETURN
    IF(key_count/=5) CALL wrf_error_fatal('RRTMG4_EXPORT_SELECTOR_REQUIRES_ALL_FIVE_KEYS')
    DO n=1,4
      value(n)=ADJUSTL(value(n))
      IF(VERIFY(TRIM(value(n)),'0123456789')/=0) &
        CALL wrf_error_fatal('RRTMG4_EXPORT_INVALID_INTEGER_SELECTOR')
      READ(value(n),*,IOSTAT=ios) indices(n)
      IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_INVALID_INTEGER_SELECTOR')
      IF(indices(n)<1) CALL wrf_error_fatal('RRTMG4_EXPORT_NONPOSITIVE_INTEGER_SELECTOR')
    END DO
    IF(indices(1)>99) CALL wrf_error_fatal('RRTMG4_EXPORT_DOMAIN_OUT_OF_RANGE')
    value(5)=ADJUSTL(value(5))
    IF(VERIFY(TRIM(value(5)),'0123456789.eEdD+-')/=0) &
      CALL wrf_error_fatal('RRTMG4_EXPORT_INVALID_SECONDS_SELECTOR')
    READ(value(5),*,IOSTAT=ios) time_value
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_INVALID_SECONDS_SELECTOR')
    IF(.NOT.ieee_is_finite(time_value)) CALL wrf_error_fatal('RRTMG4_EXPORT_NONFINITE_SECONDS_SELECTOR')
    IF(time_value<0._real64) CALL wrf_error_fatal('RRTMG4_EXPORT_NEGATIVE_SECONDS_SELECTOR')
    selected_domain=indices(1);selected_i=indices(2);selected_j=indices(3);selected_step=indices(4)
    selected_seconds=time_value
  END SUBROUTINE read_export_selection

  LOGICAL FUNCTION rrtmg4_export_active()
    rrtmg4_export_active=active
  END FUNCTION

  SUBROUTINE rrtmg4_export_stage(stage)
    CHARACTER(LEN=*), INTENT(IN) :: stage
    INTEGER :: bit,bit_index,ios
    IF(.NOT.active) RETURN
    SELECT CASE(TRIM(stage))
    CASE('INPUT'); bit=1; bit_index=0
    CASE('CLOUD'); bit=2; bit_index=1
    CASE('GAS'); bit=4; bit_index=2
    CASE('RESULT'); bit=8; bit_index=3
    CASE DEFAULT; CALL wrf_error_fatal('RRTMG4_EXPORT_UNKNOWN_STAGE')
    END SELECT
    IF(BTEST(stage_mask,bit_index)) &
      CALL wrf_error_fatal('RRTMG4_EXPORT_DUPLICATE_STAGE')
    stage_mask=stage_mask+bit
    WRITE(out_unit,'(A,1X,A)',IOSTAT=ios) 'stage',TRIM(stage)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_STAGE_WRITE_FAILED')
  END SUBROUTINE

  SUBROUTINE rrtmg4_export_real1(name,units,x)
    CHARACTER(LEN=*), INTENT(IN) :: name,units
    REAL, INTENT(IN) :: x(:)
    INTEGER :: n,ios
    IF(.NOT.active) RETURN
    WRITE(out_unit,'(A,1X,A,1X,I0)',IOSTAT=ios) TRIM(name),TRIM(units),SIZE(x)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_ARRAY_WRITE_FAILED')
    WRITE(out_unit,'(*(ES24.16E3,1X))',IOSTAT=ios) (REAL(x(n),real64),n=1,SIZE(x))
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_ARRAY_WRITE_FAILED')
  END SUBROUTINE

  SUBROUTINE rrtmg4_export_real2(name,units,x)
    CHARACTER(LEN=*), INTENT(IN) :: name,units
    REAL, INTENT(IN) :: x(:,:)
    INTEGER :: i,j,ios
    IF(.NOT.active) RETURN
    WRITE(out_unit,'(A,1X,A,1X,I0,1X,I0)',IOSTAT=ios) &
      TRIM(name),TRIM(units),SIZE(x,1),SIZE(x,2)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_ARRAY_WRITE_FAILED')
    WRITE(out_unit,'(*(ES24.16E3,1X))',IOSTAT=ios) &
      ((REAL(x(i,j),real64),i=1,SIZE(x,1)),j=1,SIZE(x,2))
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_ARRAY_WRITE_FAILED')
  END SUBROUTINE

  SUBROUTINE rrtmg4_export_int1(name,x)
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(IN) :: x(:)
    INTEGER :: i,ios
    IF(.NOT.active) RETURN
    WRITE(out_unit,'(A,1X,A,1X,I0)',IOSTAT=ios) TRIM(name),'1',SIZE(x)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_ARRAY_WRITE_FAILED')
    WRITE(out_unit,'(*(I0,1X))',IOSTAT=ios) x
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_ARRAY_WRITE_FAILED')
  END SUBROUTINE

  SUBROUTINE rrtmg4_export_end()
    INTEGER :: ios
    IF(.NOT.active) RETURN
    IF(stage_mask/=15) CALL wrf_error_fatal('RRTMG4_EXPORT_INCOMPLETE_CAPTURE')
    FLUSH(out_unit,IOSTAT=ios)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_FLUSH_FAILED')
    CLOSE(out_unit,IOSTAT=ios)
    IF(ios/=0) CALL wrf_error_fatal('RRTMG4_EXPORT_CLOSE_FAILED')
    active=.FALSE.;out_unit=0;stage_mask=0
  END SUBROUTINE
END MODULE module_rrtmg4_optics_export
