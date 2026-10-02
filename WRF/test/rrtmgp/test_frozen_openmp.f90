PROGRAM test_frozen_openmp
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE module_ra_rrtmgp_frozen, ONLY: initialize,query_sw,query_lw,frozen_table_sha256
  IMPLICIT NONE
  INTEGER, PARAMETER :: wp=real64,nc=64,nl=3,nspecies=2
  CHARACTER(LEN=1024) :: table_path,message
  CHARACTER(LEN=64) :: initial_hash
  INTEGER :: status,ios,i,k,s,t,n
  REAL(wp) :: lambda(nc,nl),temperature(nc,nl),path(nc,nl)
  REAL(wp) :: sw_ref(nc,nl,14,3,nspecies),lw_ref(nc,nl,16,nspecies)
  REAL(wp) :: sw_got(nc,nl,14,3,nspecies),lw_got(nc,nl,16,nspecies)
  INTEGER :: failures(nc)

  CALL get_command_argument(1,table_path)
  IF(LEN_TRIM(table_path)==0) ERROR STOP 'usage: test_frozen_openmp TABLE'
  CALL initialize(TRIM(table_path),status,message)
  IF(status/=0) THEN
    WRITE(*,'(A)') 'FROZEN_OPENMP_INIT_FAILED: '//TRIM(message)
    ERROR STOP 1
  END IF
  initial_hash=frozen_table_sha256()
  IF(LEN_TRIM(initial_hash)/=64) ERROR STOP 'table hash unavailable after initialization'

  DO k=1,nl
    DO i=1,nc
      lambda(i,k)=350._wp+137._wp*MOD(i+11*k,140)
      temperature(i,k)=180._wp+1.2_wp*MOD(3*i+7*k,100)
      path(i,k)=0._wp
      IF(MOD(i+2*k,5)==0) path(i,k)=1.e-12_wp
      IF(MOD(i+2*k,5)==1) path(i,k)=1.e-8_wp
      IF(MOD(i+2*k,5)==2) path(i,k)=0.25_wp+MOD(i,19)
      IF(MOD(i+2*k,5)==3) path(i,k)=1._wp+MOD(3*i,71)
    END DO
  END DO

  ! Produce the one-thread reference before any concurrent calls.
  DO s=1,nspecies
    DO i=1,nc
      CALL evaluate_column(i,s,sw_ref(i,:,:,:,s),lw_ref(i,:,:,s),status,message)
      IF(status/=0) THEN
        WRITE(*,'(A,I0,A,I0,A)') 'serial query failed species=',s,' column=',i,': '//TRIM(message)
        ERROR STOP 1
      END IF
    END DO
  END DO

  DO n=2,4,2
    failures=0
    DO s=1,nspecies
      !$OMP PARALLEL DO DEFAULT(NONE) SHARED(s,lambda,temperature,path,sw_got,lw_got,failures) &
      !$OMP PRIVATE(i,status,message) NUM_THREADS(n)
      DO i=1,nc
        CALL evaluate_column(i,s,sw_got(i,:,:,:,s),lw_got(i,:,:,s),status,message)
        IF(status/=0) failures(i)=1
      END DO
      !$OMP END PARALLEL DO
      IF(ANY(failures/=0)) THEN
        WRITE(*,'(A,I0,A,I0)') 'parallel query failed at thread count ',n,' species ',s
        ERROR STOP 1
      END IF
      IF(ANY(TRANSFER(sw_got(:,:,:,:,s),[0._wp],SIZE(sw_got(:,:,:,:,s)))/= &
             TRANSFER(sw_ref(:,:,:,:,s),[0._wp],SIZE(sw_ref(:,:,:,:,s))))) THEN
        WRITE(*,'(A,I0,A,I0)') 'SW output changed at thread count ',n,' species ',s
        ERROR STOP 1
      END IF
      IF(ANY(TRANSFER(lw_got(:,:,:,s),[0._wp],SIZE(lw_got(:,:,:,s)))/= &
             TRANSFER(lw_ref(:,:,:,s),[0._wp],SIZE(lw_ref(:,:,:,s))))) THEN
        WRITE(*,'(A,I0,A,I0)') 'LW output changed at thread count ',n,' species ',s
        ERROR STOP 1
      END IF
    END DO
    IF(frozen_table_sha256()/=initial_hash) ERROR STOP 'table hash changed during concurrent queries'
  END DO
  WRITE(*,'(A)') 'FROZEN_OPENMP_READONLY_PASS'

CONTAINS

  SUBROUTINE evaluate_column(column,species,sw_values,lw_values,rc,msg)
    INTEGER, INTENT(IN) :: column,species
    REAL(wp), INTENT(OUT) :: sw_values(nl,14,3),lw_values(nl,16)
    INTEGER, INTENT(OUT) :: rc
    CHARACTER(LEN=*), INTENT(OUT) :: msg
    REAL(wp) :: lam_col(1,nl),temp_col(1,nl),path_col(1,nl)
    REAL(wp) :: sw_tau(1,nl,14),sw_sca(1,nl,14),sw_sg(1,nl,14),lw_tau(1,nl,16)
    lam_col(1,:)=lambda(column,:)
    temp_col(1,:)=temperature(column,:)
    path_col(1,:)=path(column,:)
    CALL query_sw(species,lam_col,path_col,sw_tau,sw_sca,sw_sg,rc,msg)
    IF(rc/=0) RETURN
    CALL query_lw(species,lam_col,temp_col,path_col,lw_tau,rc,msg)
    IF(rc/=0) RETURN
    sw_values(:, :, 1)=sw_tau(1,:,:)
    sw_values(:, :, 2)=sw_sca(1,:,:)
    sw_values(:, :, 3)=sw_sg(1,:,:)
    lw_values=lw_tau(1,:,:)
  END SUBROUTINE evaluate_column

END PROGRAM test_frozen_openmp
