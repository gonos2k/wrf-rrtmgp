! Numerical interface test, NOT a full WRF/Noah integration test.
program test_noah_surface
  use iso_fortran_env,only:real32,real64
  use ieee_arithmetic,only:ieee_value,ieee_quiet_nan
  use rrtmgp37_noah_surface
  implicit none
  real(real64) :: raw(3),glw64(3),emiss(3),absorbed(3),bad(3),old(3)
  real(real32) :: glw32(3)
  integer :: checks=0
  character(200) :: msg
  raw=[300.0_real64,350.0_real64,400.0_real64]
  emiss=[0.0_real64,0.95_real64,1.0_real64]
  glw64=-42.0_real64;glw32=-42.0_real32
  call map_noah_glw(raw,glw64,msg)
  call check(msg=='','real64 accepted')
  call check(all(glw64==raw),'raw downward LW preserved, real64')
  call map_noah_glw(raw,glw32,msg)
  call check(msg=='','real32 accepted')
  call check(all(real(glw32,real64)==raw),'raw downward LW preserved, real32')
  ! Equivalent to the observed official Noah statement LWDN=GLW*EMISSI.
  absorbed=glw64*emiss
  call check(all(absorbed==[0.0_real64,332.5_real64,400.0_real64]),'one emissivity factor')
  call check(glw64(2)==350.0_real64,'GLW itself must not be 332.5')
  call check(abs(absorbed(2)-raw(2)*emiss(2)**2)>1.0_real64,'double emissivity would differ')
  old=glw64
  bad=raw;bad(2)=-1.0_real64;call map_noah_glw(bad,glw64,msg)
  call check(msg/=''.and.all(glw64==old),'negative flux rejected atomically')
  bad=raw;bad(2)=ieee_value(0.0_real64,ieee_quiet_nan)
  call map_noah_glw(bad,glw64,msg)
  call check(msg/=''.and.all(glw64==old),'NaN rejected atomically')
  call map_noah_glw(raw(1:2),glw64,msg)
  call check(msg/=''.and.all(glw64==old),'shape mismatch rejected atomically')
  bad=raw;bad(2)=huge(0.0_real64);call map_noah_glw(bad,glw32,msg)
  call check(msg/=''.and.all(real(glw32,real64)==raw),'real32 overflow rejected atomically')
  raw=0.0_real64;call map_noah_glw(raw,glw64,msg)
  call check(msg==''.and.all(glw64==0.0_real64),'zero flux accepted')
  print '(a,i0)', 'PASS Noah GLW adapter checks: ',checks
contains
  subroutine check(ok,label)
    logical,intent(in)::ok
    character(*),intent(in)::label
    if(.not.ok) then
      print *, 'FAIL: ',label
      error stop 1
    end if
    checks=checks+1
  end subroutine
end program
