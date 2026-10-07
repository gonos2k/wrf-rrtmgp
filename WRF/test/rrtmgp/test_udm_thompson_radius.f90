! Isolated cloud-radius kernels. No Thompson host initialization or forecast.
#ifdef OBSERVER_ONLY
module radius_test_observer
  use iso_fortran_env, only: int32
  implicit none
  logical :: enabled=.false.
  integer :: case_id=0
contains
  subroutine radius_capture(tag,values)
    character(*),intent(in)::tag
    real,intent(in)::values(:)
    if (.not.enabled) return
    write(*,'(A,1X,A,2(1X,I0))') 'OBS',tag,case_id,size(values)
    write(*,'(*(Z8.8,1X))') transfer(values,[0_int32],size(values))
  end subroutine
end module
#else
program radius_comparison
  use module_mp_thompson, only: calc_effectRad,radius_test_setup
  use module_mp_udm, only: udminit,udm_mp_effective_radius,radius_test_constants
  use radius_test_observer
  use iso_fortran_env, only: int32
  implicit none
  real :: t(1),p(1),qv(1),qc(1),nc(1),qi(1),ni(1),qs(1),rho(1)
  real :: rec(1),rei(1),res(1),density,eta,constants(7)
  real :: before(9),after(9)
  integer :: c,base,mode
  character(8) :: argument
  call get_command_argument(1,argument)
  if(trim(argument)/='on'.and.trim(argument)/='off') error stop 'select on/off'
  enabled=trim(argument)=='on'
  if(storage_size(1.)/=32) error stop 'REAL32 required'
  call udminit(1.,1000.,100.,4186.,1004.5,2.e8,.false.)
  do c=1,12
    case_id=c
    base=c
    if(c==11) base=1
    if(c==12) base=3
    density=.7
    if(mod(base,2)==0) density=1.1
    t=285.; qv=.008; qc=1.e-4; qi=0.; ni=0.; qs=0.
    ! Invert the native Thompson density expression. UDM receives that
    ! computed density too; no host number conversion is being adopted.
    p=density*287.04*t*(qv+.622)/.622
    rho=.622*p/(287.04*t*(qv+.622))
    eta=5.e7
    if(base==5.or.base==6) eta=3.e8
    nc=eta
    mode=8
    if(base>=3.and.base<=6) mode=28
    if(base>=7) mode=27
    if(base>=9) nc=rho*eta ! Explicit conditional volume-number input arm.
    before=[t,p,qv,qc,nc,qi,ni,qs,rho]
    rec=-99.; rei=-99.; res=-99.
    if(mode/=27) then
      call radius_test_setup(mode==28,constants)
      call calc_effectRad(t,p,qv,qc,nc,qi,ni,qs,rec,rei,res,1,1)
    else
      call radius_test_constants(constants)
      call udm_mp_effective_radius(t,qc,qi,qs,rho,1.e-12,273.15,nc,rec,rei,res,1,1,1,1)
    endif
    after=[t,p,qv,qc,nc,qi,ni,qs,rho]
    if(any(transfer(before,[0_int32],9)/=transfer(after,[0_int32],9))) error stop 'input mutated'
    write(*,'(A,3(1X,I0))') 'CASE',c,mode,19
    write(*,'(*(Z8.8,1X))') transfer([before,constants,rec,rei,res],[0_int32],19)
  enddo
end program
#endif
