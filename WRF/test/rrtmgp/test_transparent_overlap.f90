PROGRAM test_rrtmgp_transparent_overlap
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE mo_rte_kind, ONLY: i8
  USE module_ra_rrtmgp, ONLY: cloud_mask
  IMPLICIT NONE
  INTEGER, PARAMETER :: m=2048,nl=3,ngpt_lw=128,ngpt_sw=112
  REAL :: cf_a(m,nl),cf_b(m,nl),paths_a(m,nl),paths_b(m,nl)
  INTEGER :: seeds(m),hit1_a,hit3_a,joint_a,hit_mid_b,joint_b,joint_lw_a,joint_lw_b
  INTEGER(i8) :: stream_state
  LOGICAL, ALLOCATABLE :: mask_a_lw(:,:,:),mask_b_lw(:,:,:)
  LOGICAL, ALLOCATABLE :: mask_a_sw(:,:,:),mask_b_sw(:,:,:)
  INTEGER :: c
  REAL(real64) :: fraction_a,fraction_b,tolerance_lw_a,tolerance_lw_b,tolerance_sw_a,tolerance_sw_b
  REAL(real64) :: n_samples_lw,n_samples_sw

  ALLOCATE(mask_a_lw(m,nl,ngpt_lw),mask_b_lw(m,nl,ngpt_lw))
  ALLOCATE(mask_a_sw(m,nl,ngpt_sw),mask_b_sw(m,nl,ngpt_sw))
  stream_state=987654321_i8
  DO c=1,m
    ! Deterministic dispersed column seeds avoid highly correlated consecutive streams.
    stream_state=MODULO(48271_i8*stream_state,2147483647_i8)
    seeds(c)=INT(stream_state)
  END DO

  ! A: the middle layer is optically transparent and has zero CF.
  ! B: keep exactly the same path arrays but make that zero-path layer CF=.5.
  ! cloud_mask has no path argument, so this intentionally exposes its present
  ! CF-only maximum-random behavior, not a path-aware overlap contract.
  cf_a=.5; cf_a(:,2)=0.
  cf_b=.5
  paths_a=0.; paths_a(:,1)=100.; paths_a(:,3)=100.
  paths_b=paths_a
  IF(ANY(paths_a/=paths_b).OR.ANY(paths_a(:,2)/=0.)) ERROR STOP 'fixture paths are not transparent/equal'

  CALL cloud_mask(cf_a,ngpt_lw,2,173,mask_a_lw,column_seeds=seeds)
  CALL cloud_mask(cf_b,ngpt_lw,2,173,mask_b_lw,column_seeds=seeds)
  CALL cloud_mask(cf_a,ngpt_sw,2,173,mask_a_sw,column_seeds=seeds)
  CALL cloud_mask(cf_b,ngpt_sw,2,173,mask_b_sw,column_seeds=seeds)

  IF(.NOT.ALL(.NOT.mask_a_lw(:,2,:))) ERROR STOP 'CF=0 transparent layer must be clear in A'
  IF(.NOT.ALL(.NOT.mask_a_sw(:,2,:))) ERROR STOP 'CF=0 transparent layer must be clear in SW A'
  CALL count_joint(mask_a_lw,joint_lw_a,hit1_a,hit3_a)
  CALL count_joint(mask_b_lw,joint_lw_b,hit1_a,hit3_a)
  CALL check_fraction('LW A separated layers',joint_lw_a,m*ngpt_lw,.25_real64)
  CALL check_fraction('LW B contiguous layers',joint_lw_b,m*ngpt_lw,.5_real64)
  CALL check_fraction('LW B middle layer',COUNT(mask_b_lw(:,2,:)),m*ngpt_lw,.5_real64)
  IF(.NOT.ALL(mask_b_lw(:,1,:).EQV.mask_b_lw(:,2,:)).OR. &
     .NOT.ALL(mask_b_lw(:,2,:).EQV.mask_b_lw(:,3,:))) &
    ERROR STOP 'B contiguous cloudy layers should share one maximum-random mask'

  CALL count_joint(mask_a_sw,joint_a,hit1_a,hit3_a)
  CALL count_joint(mask_b_sw,joint_b,hit_mid_b,hit3_a)
  fraction_a=REAL(joint_a,real64)/REAL(m*ngpt_sw,real64)
  fraction_b=REAL(joint_b,real64)/REAL(m*ngpt_sw,real64)
  n_samples_lw=REAL(m*ngpt_lw,real64)
  n_samples_sw=REAL(m*ngpt_sw,real64)
  tolerance_lw_a=6._real64*SQRT(.25_real64*.75_real64/n_samples_lw)+.001_real64
  tolerance_lw_b=6._real64*SQRT(.5_real64*.5_real64/n_samples_lw)+.001_real64
  tolerance_sw_a=6._real64*SQRT(.25_real64*.75_real64/n_samples_sw)+.001_real64
  tolerance_sw_b=6._real64*SQRT(.5_real64*.5_real64/n_samples_sw)+.001_real64
  CALL check_fraction('SW A separated layers',joint_a,m*ngpt_sw,.25_real64)
  CALL check_fraction('SW B contiguous layers',joint_b,m*ngpt_sw,.5_real64)
  CALL check_fraction('SW B middle layer',hit_mid_b,m*ngpt_sw,.5_real64)

  WRITE(*,'(A)') 'case,ngpt,columns,samples,joint_count,joint_fraction,expected_fraction,tolerance'
  WRITE(*,'(A,",",I0,",",I0,",",I0,",",I0,",",F10.7,",",F5.2,",",F10.7)') &
    'LW_A',ngpt_lw,m,m*ngpt_lw,joint_lw_a,REAL(joint_lw_a,real64)/REAL(m*ngpt_lw,real64),.25,tolerance_lw_a
  WRITE(*,'(A,",",I0,",",I0,",",I0,",",I0,",",F10.7,",",F5.2,",",F10.7)') &
    'LW_B',ngpt_lw,m,m*ngpt_lw,joint_lw_b,REAL(joint_lw_b,real64)/REAL(m*ngpt_lw,real64),.5,tolerance_lw_b
  WRITE(*,'(A,",",I0,",",I0,",",I0,",",I0,",",F10.7,",",F5.2,",",F10.7)') &
    'SW_A',ngpt_sw,m,m*ngpt_sw,joint_a,fraction_a,.25,tolerance_sw_a
  WRITE(*,'(A,",",I0,",",I0,",",I0,",",I0,",",F10.7,",",F5.2,",",F10.7)') &
    'SW_B',ngpt_sw,m,m*ngpt_sw,joint_b,fraction_b,.5,tolerance_sw_b
  WRITE(*,'(A)') 'NOTE: current cloud_mask samples max-random overlap from CF only; zero-path CF=.5 in B remains mask-cloudy.'
  WRITE(*,'(A)') 'transparent-overlap statistics passed'

CONTAINS
  SUBROUTINE count_joint(mask,joint,first_hits,last_hits)
    LOGICAL, INTENT(IN) :: mask(:,:,:)
    INTEGER, INTENT(OUT) :: joint,first_hits,last_hits
    joint=COUNT(mask(:,1,:).AND.mask(:,3,:))
    first_hits=COUNT(mask(:,1,:))
    last_hits=COUNT(mask(:,3,:))
  END SUBROUTINE count_joint

  SUBROUTINE check_fraction(label,hits,total,expected)
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(IN) :: hits,total
    REAL(real64), INTENT(IN) :: expected
    REAL(real64) :: observed,tolerance
    observed=REAL(hits,real64)/REAL(total,real64)
    tolerance=6._real64*SQRT(expected*(1._real64-expected)/REAL(total,real64))+.001_real64
    IF(.NOT.ieee_is_finite(observed).OR.ABS(observed-expected)>tolerance) THEN
      WRITE(*,'(A,A,A,F10.7,A,F10.7,A,F10.7)') 'FAIL ',TRIM(label),' observed=',observed, &
        ' expected=',expected,' tolerance=',tolerance
      ERROR STOP 1
    END IF
  END SUBROUTINE check_fraction
END PROGRAM test_rrtmgp_transparent_overlap
