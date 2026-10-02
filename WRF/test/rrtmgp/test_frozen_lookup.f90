PROGRAM test_frozen_lookup
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp_frozen, ONLY: initialize, query_sw, query_lw
  IMPLICIT NONE
  INTEGER, PARAMETER :: wp=real64
  CHARACTER(LEN=1024) :: table_path, query_path, output_path, alternate_table, message
  INTEGER :: status, ios, nc, nl, i, k, b, species, unit_in, unit_out
  REAL(wp), ALLOCATABLE :: sw_lambda(:,:), sw_path(:,:), lw_lambda(:,:), lw_temp(:,:), lw_path(:,:)
  REAL(wp), ALLOCATABLE :: sw_tau(:,:,:), sw_scatter(:,:,:), sw_sg(:,:,:), lw_abs(:,:,:)

  CALL get_command_argument(1,table_path)
  CALL get_command_argument(2,query_path)
  CALL get_command_argument(3,output_path)
  CALL get_command_argument(4,alternate_table)
  IF(LEN_TRIM(table_path)==0 .OR. LEN_TRIM(query_path)==0 .OR. LEN_TRIM(output_path)==0) &
    ERROR STOP 'usage: test_frozen_lookup TABLE QUERY_FILE OUTPUT_CSV'

  CALL initialize(TRIM(table_path),status,message)
  IF(status/=0) THEN
    WRITE(*,'(A)') 'FROZEN_LOOKUP_INIT_FAILED: '//TRIM(message)
    ERROR STOP 1
  END IF
  CALL initialize(TRIM(table_path),status,message)
  IF(status/=0) ERROR STOP 'same-path initialize was not idempotent'
  IF(LEN_TRIM(alternate_table)>0) THEN
    CALL initialize(TRIM(alternate_table),status,message)
    IF(status==0) ERROR STOP 'different-path initialize was accepted'
  END IF

  OPEN(NEWUNIT=unit_in,FILE=TRIM(query_path),STATUS='old',ACTION='read',IOSTAT=ios)
  IF(ios/=0) ERROR STOP 'cannot open lookup query file'
  READ(unit_in,*,IOSTAT=ios) nc,nl
  IF(ios/=0 .OR. nc<1 .OR. nl<1) ERROR STOP 'invalid query dimensions'
  ALLOCATE(sw_lambda(nc,nl),sw_path(nc,nl),lw_lambda(nc,nl),lw_temp(nc,nl),lw_path(nc,nl))
  READ(unit_in,*,IOSTAT=ios) sw_lambda
  IF(ios/=0) ERROR STOP 'invalid SW lambda values'
  READ(unit_in,*,IOSTAT=ios) sw_path
  IF(ios/=0) ERROR STOP 'invalid SW paths'
  READ(unit_in,*,IOSTAT=ios) lw_lambda
  IF(ios/=0) ERROR STOP 'invalid LW lambda values'
  READ(unit_in,*,IOSTAT=ios) lw_temp
  IF(ios/=0) ERROR STOP 'invalid LW temperatures'
  READ(unit_in,*,IOSTAT=ios) lw_path
  IF(ios/=0) ERROR STOP 'invalid LW paths'
  CLOSE(unit_in)

  ALLOCATE(sw_tau(nc,nl,14),sw_scatter(nc,nl,14),sw_sg(nc,nl,14),lw_abs(nc,nl,16))
  OPEN(NEWUNIT=unit_out,FILE=TRIM(output_path),STATUS='replace',ACTION='write',IOSTAT=ios)
  IF(ios/=0) ERROR STOP 'cannot open output CSV'
  WRITE(unit_out,'(A)') 'phase,species,column,layer,band,lambda_m_inv,temperature_k,path_g_m2,tau_ext,tau_scat,tau_scat_g,tau_abs'

  DO species=1,2
    CALL query_sw(species,sw_lambda,sw_path,sw_tau,sw_scatter,sw_sg,status,message)
    IF(status/=0) THEN
      WRITE(*,'(A)') 'FROZEN_LOOKUP_SW_FAILED: '//TRIM(message)
      ERROR STOP 1
    END IF
    DO k=1,nl
      DO i=1,nc
        DO b=1,14
          WRITE(unit_out,'(A,",",I0,",",I0,",",I0,",",I0,7(",",ES25.16E3))') &
            'SW',species,i,k,b,sw_lambda(i,k),-1._wp,sw_path(i,k), &
            sw_tau(i,k,b),sw_scatter(i,k,b),sw_sg(i,k,b),sw_tau(i,k,b)-sw_scatter(i,k,b)
        END DO
      END DO
    END DO

    CALL query_lw(species,lw_lambda,lw_temp,lw_path,lw_abs,status,message)
    IF(status/=0) THEN
      WRITE(*,'(A)') 'FROZEN_LOOKUP_LW_FAILED: '//TRIM(message)
      ERROR STOP 1
    END IF
    DO k=1,nl
      DO i=1,nc
        DO b=1,16
          WRITE(unit_out,'(A,",",I0,",",I0,",",I0,",",I0,7(",",ES25.16E3))') &
            'LW',species,i,k,b,lw_lambda(i,k),lw_temp(i,k),lw_path(i,k), &
            -1._wp,-1._wp,-1._wp,lw_abs(i,k,b)
        END DO
      END DO
    END DO
  END DO
  CLOSE(unit_out)

  CALL test_invalid_calls()
  WRITE(*,'(A)') 'FROZEN_LOOKUP_FORTRAN_PASS'

CONTAINS

  SUBROUTINE expect_sw_reject(label,species,lambda,path)
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(IN) :: species
    REAL(wp), INTENT(IN) :: lambda(:,:),path(:,:)
    INTEGER :: rc
    CHARACTER(LEN=1024) :: msg
    REAL(wp) :: tau(size(lambda,1),size(lambda,2),14)
    REAL(wp) :: scat(size(lambda,1),size(lambda,2),14),sg(size(lambda,1),size(lambda,2),14)
    CALL query_sw(species,lambda,path,tau,scat,sg,rc,msg)
    IF(rc==0) THEN
      WRITE(*,'(A)') 'FROZEN_LOOKUP_ACCEPTED_INVALID_SW_'//TRIM(label)
      ERROR STOP 1
    END IF
  END SUBROUTINE expect_sw_reject

  SUBROUTINE expect_lw_reject(label,species,lambda,temp,path)
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(IN) :: species
    REAL(wp), INTENT(IN) :: lambda(:,:),temp(:,:),path(:,:)
    INTEGER :: rc
    CHARACTER(LEN=1024) :: msg
    REAL(wp) :: tauabs(size(lambda,1),size(lambda,2),16)
    CALL query_lw(species,lambda,temp,path,tauabs,rc,msg)
    IF(rc==0) THEN
      WRITE(*,'(A)') 'FROZEN_LOOKUP_ACCEPTED_INVALID_LW_'//TRIM(label)
      ERROR STOP 1
    END IF
  END SUBROUTINE expect_lw_reject

  SUBROUTINE test_invalid_calls()
    REAL(wp) :: lam(2,2),path(2,2),temp(2,2),badpath(1,1),badtemp(1,1)
    REAL(wp) :: nan
    nan=ieee_value(0._wp,ieee_quiet_nan)
    lam=sw_lambda(1,1); path=1._wp; temp=lw_temp(1,1)
    CALL expect_sw_reject('lambda_low',1,lam*0.5_wp,path)
    CALL expect_sw_reject('lambda_high',1,lam*1.e9_wp,path)
    lam(1,1)=0._wp; CALL expect_sw_reject('lambda_zero',1,lam,path); lam=sw_lambda(1,1)
    lam(1,1)=nan; CALL expect_sw_reject('lambda_nan',1,lam,path); lam=sw_lambda(1,1)
    path(1,1)=-1._wp; CALL expect_sw_reject('path_negative',1,lam,path); path=1._wp
    path(1,1)=nan; CALL expect_sw_reject('path_nan',1,lam,path); path=1._wp
    CALL expect_sw_reject('species',99,lam,path)
    CALL expect_sw_reject('shape',1,lam,badpath)

    CALL expect_lw_reject('lambda_low',1,lam*0.5_wp,temp,path)
    CALL expect_lw_reject('lambda_high',1,lam*1.e9_wp,temp,path)
    temp(1,1)=nan; CALL expect_lw_reject('temperature_nan',1,lam,temp,path); temp=lw_temp(1,1)
    temp(1,1)=1._wp; CALL expect_lw_reject('temperature_low',1,lam,temp,path); temp=lw_temp(1,1)
    temp(1,1)=1000._wp; CALL expect_lw_reject('temperature_high',1,lam,temp,path); temp=lw_temp(1,1)
    CALL expect_lw_reject('species',99,lam,temp,path)
    CALL expect_lw_reject('shape',1,lam,temp,badpath)
    CALL expect_lw_reject('temperature_shape',1,lam,badtemp,path)
  END SUBROUTINE test_invalid_calls
END PROGRAM test_frozen_lookup
