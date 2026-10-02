PROGRAM test_domain_seed
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_column_seed
  IMPLICIT NONE
  INTEGER, PARAMETER :: n=64
  INTEGER :: seeds(n), reordered(n), partitioned(n), order(n)
  INTEGER :: k, slot, s0

  ! Fixed vectors independently evaluated with the documented int64 recurrence.
  CALL require(rrtmgp_column_seed(1,1,1,2026,1,1)==1300300312, 'vector 1')
  CALL require(rrtmgp_column_seed(7,123,456,2024,366,2)==1388878755, 'vector 2')
  CALL require(rrtmgp_column_seed(HUGE(0),HUGE(0),HUGE(0),HUGE(0),366,2)==908371465, &
                'near-default-integer-maximum vector')
  CALL require(rrtmgp_column_seed(4,9,3,2026,278,1)==2041640358, 'vector 4')

  ! A column seed is a pure function of identity, independent of traversal order.
  DO k=1,n
    seeds(k)=rrtmgp_column_seed(4,k,7,2026,278,2)
    order(k)=n+1-k
  END DO
  DO k=1,n
    reordered(k)=rrtmgp_column_seed(4,order(k),7,2026,278,2)
  END DO
  DO k=1,n
    CALL require(seeds(k)==reordered(n+1-k), 'reverse traversal changed column seed')
  END DO

  ! Recombine three MPI-like index chunks in global-column order.
  partitioned=0
  DO slot=1,3
    DO k=slot,n,3
      partitioned(k)=rrtmgp_column_seed(4,k,7,2026,278,2)
    END DO
  END DO
  CALL require(ALL(partitioned==seeds), 'partitioning changed column seed')
  CALL require(ALL(seeds>0), 'valid column produced nonpositive seed')

  ! Representative key changes.  Finite 31-bit seeds can collide in general;
  ! these checks cover selected pairs only and make no global uniqueness claim.
  s0=rrtmgp_column_seed(4,9,3,2026,278,1)
  CALL require(s0/=rrtmgp_column_seed(5,9,3,2026,278,1), 'domain sample')
  CALL require(s0/=rrtmgp_column_seed(4,9,3,2025,278,1), 'year sample')
  CALL require(s0/=rrtmgp_column_seed(4,9,3,2026,277,1), 'day sample')
  CALL require(s0/=rrtmgp_column_seed(4,9,3,2026,278,2), 'phase sample')

  CALL require(rrtmgp_column_seed(0,1,1,2026,1,1)==-1, 'invalid domain')
  CALL require(rrtmgp_column_seed(1,0,1,2026,1,1)==-1, 'invalid i')
  CALL require(rrtmgp_column_seed(1,1,-1,2026,1,1)==-1, 'invalid j')
  CALL require(rrtmgp_column_seed(1,1,1,0,1,1)==-1, 'invalid year')
  CALL require(rrtmgp_column_seed(1,1,1,2026,0,1)==-1, 'day below range')
  CALL require(rrtmgp_column_seed(1,1,1,2026,367,1)==-1, 'day above range')
  CALL require(rrtmgp_column_seed(1,1,1,2026,1,0)==-1, 'phase below range')
  CALL require(rrtmgp_column_seed(1,1,1,2026,1,3)==-1, 'phase above range')
  CALL require(rrtmgp_column_seed(HUGE(0),HUGE(0),HUGE(0),HUGE(0),1,1)>0, &
               'maximum valid integer fields')

  WRITE(*,'(A)') 'DOMAIN_SEED_FIXTURE_PASS'
CONTAINS
  SUBROUTINE require(condition,label)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: label
    IF(.NOT.condition) THEN
      WRITE(*,'(A)') 'FAIL: '//label
      ERROR STOP 1
    END IF
  END SUBROUTINE require
END PROGRAM test_domain_seed
