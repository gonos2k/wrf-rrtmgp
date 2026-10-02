! Checked bridge for pinned BSD-3-Clause SOCRATES mie_scatter.
! The caller's ceiling is a numerical workspace bound, not a particle-size policy.
MODULE mie_dynamic_api
  USE, INTRINSIC :: iso_c_binding, ONLY: c_double,c_int
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE realtype_rd, ONLY: RealK
  IMPLICIT NONE
CONTAINS
  SUBROUTINE mie_checked(nr,ki,x,max_terms,qext,qsca,g,needed,ierr) BIND(C,NAME='mie_checked')
    REAL(c_double), VALUE :: nr,ki,x
    INTEGER(c_int), VALUE :: max_terms
    REAL(c_double), INTENT(OUT) :: qext,qsca,g
    INTEGER(c_int), INTENT(OUT) :: needed,ierr
    REAL(RealK) :: series_count,downward_count,qe,qs,gg,mu(1)
    COMPLEX(RealK) :: index,s1(1),s2(1)
    INTEGER :: n_term,n_y,n_down,status
    qext=0.;qsca=0.;g=0.;needed=0;ierr=1
    IF(.NOT.ieee_is_finite(nr).OR..NOT.ieee_is_finite(ki).OR..NOT.ieee_is_finite(x)) RETURN
    IF(nr<=0..OR.ki<0..OR.x<=0..OR.max_terms<1) RETURN
    index=CMPLX(REAL(nr,RealK),REAL(ki,RealK),RealK)
    series_count=2._RealK+4._RealK*REAL(x,RealK)**3.333e-01_RealK+REAL(x,RealK)
    downward_count=1.1_RealK*ABS(REAL(x,RealK)*index)
    ierr=2
    IF(.NOT.ieee_is_finite(series_count).OR..NOT.ieee_is_finite(downward_count)) RETURN
    IF(MAX(series_count,downward_count)>REAL(HUGE(n_term)-32,RealK)) RETURN
    n_term=INT(series_count);n_y=INT(downward_count)
    n_down=MAX(n_term,n_y)+15
    needed=INT(n_down,c_int);ierr=3
    IF(n_down>max_terms) RETURN
    status=0;mu=1._RealK
    CALL mie_scatter(status,REAL(x,RealK),index,qs,qe,gg,.FALSE.,0,mu,s1,s2,1,n_down)
    qext=REAL(qe,c_double);qsca=REAL(qs,c_double);g=REAL(gg,c_double)
    ierr=INT(status,c_int)
  END SUBROUTINE
END MODULE
