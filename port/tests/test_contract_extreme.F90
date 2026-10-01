program test_contract_extreme
  use iso_fortran_env,only:real64
  use rrtmgp37_contract
  implicit none
  real(real64)::up(1,2),dn(1,2),cp(1,1),pi(1,1),q(1,1),p(1,2),h(1,1)
  integer::ierr,n=0
  character(256)::msg
  up=huge(0.0_real64);dn=-huge(0.0_real64);cp=1;pi=1;q=-999
  call column_flux_to_theta(up,dn,cp,pi,q,ierr,msg)
  call check(ierr/=0.and.all(q==-999),'net flux overflow refused before arithmetic')
  up(1,:)=[huge(0.0_real64),0.0_real64];dn(1,:)=[0.0_real64,huge(0.0_real64)]
  call column_flux_to_theta(up,dn,cp,pi,q,ierr,msg)
  call check(ierr/=0.and.all(q==-999),'flux divergence overflow refused')
  up(1,:)=[1.0_real64,0.0_real64];dn=0;cp=tiny(0.0_real64)*0.01_real64
  call column_flux_to_theta(up,dn,cp,pi,q,ierr,msg)
  call check(ierr/=0.and.all(q==-999),'tiny capacity division overflow refused')
  cp=1;pi=tiny(0.0_real64)*0.01_real64
  call column_flux_to_theta(up,dn,cp,pi,q,ierr,msg)
  call check(ierr/=0.and.all(q==-999),'tiny Exner division overflow refused')
  p(1,:)=[1.e5_real64,1.e4_real64];cp=huge(0.0_real64);h=-999
  call hydrostatic_heat_capacity(p,cp,10.0_real64,h,ierr,msg)
  call check(ierr/=0.and.all(h==-999),'cp dp product overflow refused')
  cp=1004;h=-999
  call hydrostatic_heat_capacity(p,cp,tiny(0.0_real64),h,ierr,msg)
  call check(ierr/=0.and.all(h==-999),'heat-capacity division overflow refused')
  print '(a,i0)','EXTREME_ARITHMETIC_ASSERTIONS_PASS=',n
contains
  subroutine check(ok,label)
    logical,intent(in)::ok
    character(*),intent(in)::label
    if(.not.ok)then
      print *, 'FAIL: ',label
      error stop 1
    end if
    n=n+1
  end subroutine
end program
