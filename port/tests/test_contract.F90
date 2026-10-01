program test_contract
  use, intrinsic :: iso_fortran_env, only: real64
  use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan
  use rrtmgp37_contract
  implicit none
  real(real64) :: up(2,3),dn(2,3),cap(2,2),pi(2,2),q(2,2)
  real(real64) :: p(2,3),cp(2,2),bad(2,2),short_up(2,2),nan
  integer :: ierr, checks
  character(len=256) :: msg
  checks=0
  call require_paired_37(37,37,ierr,msg); call check(ierr==0,'paired37')
  call require_paired_37(4,4,ierr,msg); call check(ierr==0,'other paired scheme unaffected')
  call require_paired_37(4,14,ierr,msg); call check(ierr==0,'other mixed scheme not owned by helper')
  call require_paired_37(37,4,ierr,msg); call check(ierr/=0,'mixed LW37 rejected')
  call require_paired_37(4,37,ierr,msg); call check(ierr/=0,'mixed SW37 rejected')
  up(1,:)=[100.0_real64,70.0_real64,20.0_real64]; up(2,:)=100.0_real64
  dn=0.0_real64
  cap(:,1)=10000.0_real64; cap(:,2)=20000.0_real64
  pi(:,1)=1.0_real64; pi(:,2)=0.8_real64
  q=-999.0_real64
  call column_flux_to_theta(up,dn,cap,pi,q,ierr,msg)
  call check(ierr==0,'valid flux accepted')
  call check(abs(q(1,1)-0.003_real64)<1.e-15_real64,'lower-layer heating')
  call check(abs(q(1,2)-0.003125_real64)<1.e-15_real64,'Exner exactly once')
  call check(all(abs(q(2,:))<1.e-15_real64),'constant net flux has zero heating')
  call check(abs(sum(cap(1,:)*pi(1,:)*q(1,:))-80.0_real64)<1.e-12_real64,'column conservation')
  dn=2.0_real64*up
  call column_flux_to_theta(up,dn,cap,pi,q,ierr,msg)
  call check(ierr==0 .and. all(q(1,:)<0.0_real64),'cooling sign')
  dn=0.0_real64
  q=-999.0_real64; bad=cap; bad(1,1)=0.0_real64
  call column_flux_to_theta(up,dn,bad,pi,q,ierr,msg)
  call check(ierr/=0 .and. all(q==-999.0_real64),'invalid heat capacity output unchanged')
  bad=pi; bad(2,2)=-1.0_real64
  call column_flux_to_theta(up,dn,cap,bad,q,ierr,msg)
  call check(ierr/=0 .and. all(q==-999.0_real64),'invalid Exner output unchanged')
  nan=ieee_value(0.0_real64,ieee_quiet_nan); up(1,1)=nan
  call column_flux_to_theta(up,dn,cap,pi,q,ierr,msg)
  call check(ierr/=0 .and. all(q==-999.0_real64),'NaN flux rejected')
  up(1,1)=100.0_real64; short_up=0.0_real64
  call column_flux_to_theta(short_up,dn,cap,pi,q,ierr,msg)
  call check(ierr/=0 .and. all(q==-999.0_real64),'wrong interface shape rejected')
  p(:,1)=100000.0_real64; p(:,2)=80000.0_real64; p(:,3)=50000.0_real64
  cp=1004.0_real64
  call hydrostatic_heat_capacity(p,cp,10.0_real64,cap,ierr,msg)
  call check(ierr==0,'hydrostatic convention accepted')
  call check(all(abs(cap(:,1)-2008000.0_real64)<1.e-8_real64),'dp Pa conversion')
  call check(all(abs(cap(:,2)-3012000.0_real64)<1.e-8_real64),'second layer cp dp g')
  cap=-999.0_real64; p(:,2)=110000.0_real64
  call hydrostatic_heat_capacity(p,cp,10.0_real64,cap,ierr,msg)
  call check(ierr/=0 .and. all(cap==-999.0_real64),'wrong pressure ordering not hidden with abs')
  p(:,2)=80000.0_real64
  call hydrostatic_heat_capacity(p,cp,0.0_real64,cap,ierr,msg)
  call check(ierr/=0 .and. all(cap==-999.0_real64),'zero gravity rejected')
  cp(1,1)=nan
  call hydrostatic_heat_capacity(p,cp,10.0_real64,cap,ierr,msg)
  call check(ierr/=0,'NaN cp rejected')
  write(*,'(A,I0)') 'FORTRAN_CONTRACT_CHECKS_PASS=',checks
contains
  subroutine check(ok,label)
    logical,intent(in)::ok
    character(len=*),intent(in)::label
    if (.not.ok) then
      write(*,'(A)') 'FAIL: '//label
      stop 1
    end if
    checks=checks+1
  end subroutine
end program
