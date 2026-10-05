program test_udm_rain_only_slopes
  use module_mp_udm, only: udm, udminit, udm_funct_svp_setup, &
       udm_funct_shape_setup, udm_funct_lb2017_setup
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use, intrinsic :: iso_fortran_env, only: int32
  implicit none
  integer, parameter :: nz=7
  real :: th(1,nz,1),q(1,nz,1),qc(1,nz,1),qi(1,nz,1),qr(1,nz,1),qs(1,nz,1),qg(1,nz,1),qh(1,nz,1)
  real :: nn(1,nz,1),nc(1,nz,1),nr(1,nz,1),den(1,nz,1),pii(1,nz,1),p(1,nz,1),delz(1,nz,1)
  real :: land(1,1),ice(1,1),rain(1,1),rainncv(1,1),snow(1,1),snowncv(1,1),hail(1,1),hailncv(1,1)
  real :: graupel(1,1),graupelncv(1,1),sr(1,1),refl(1,nz,1),rec(1,nz,1),rei(1,nz,1),res(1,nz,1),cf(1,nz,1)
  real :: values(16*nz+9),dt
  integer :: step(1,1),top(1,1),profile,branch,mode,k
  integer(int32) :: bits(size(values))
  character(32) :: argument

  if(storage_size(1.)/=32) error stop 'fixture requires default REAL32'
  call get_command_argument(1,argument)
  read(argument,*) profile
  if(profile<1 .or. profile>5) error stop 'profile id must be 1..5'
  call udminit(1.,1000.,100.,4186.,1004.,1.e8,.false.)
  call udm_funct_svp_setup
  call udm_funct_shape_setup
  call udm_funct_lb2017_setup

  do branch=1,3
    do mode=0,2
      th=290.; pii=1.; q=0.001; den=1.; delz=1000.
      p=den*290.*(287.+461.6*q)
      qc=0.; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.
      nn=1.e8; nc=0.; nr=0.
      select case(profile)
      case(1) ! rain only; large-drop controls suppress later physical rain-to-cloud conversion.
        qr(1,2:5,1)=1.e-3
        nr(1,2:5,1)=3.e8
        dt=1.
      case(2) ! rain extends above the initialized liquid-cloud top.
        qc(1,2,1)=1.e-4; nc(1,2,1)=1.e8
        qr(1,4:5,1)=1.e-3; nr(1,4:5,1)=3.e8
        dt=1.
      case(3) ! cloud-only initialized reference control.
        qc(1,2:5,1)=1.e-4; nc(1,2:5,1)=1.e8
        dt=1.
      case(4) ! full rain/cloud overlap, with the same warm/subsaturated thermodynamics.
        qc(1,2:5,1)=1.e-4; nc(1,2:5,1)=1.e8
        qr(1,2:5,1)=1.e-3; nr(1,2:5,1)=3.e8
        dt=1.
      case(5) ! a trace cloud top may evaporate during repeated substeps.
        qc(1,2:4,1)=1.e-4; nc(1,2:4,1)=1.e8
        qc(1,5,1)=2.e-12; nc(1,5,1)=1.e8
        dt=3600.
      end select
      land=1.; ice=0.; rain=0.; rainncv=0.; snow=0.; snowncv=0.; hail=0.; hailncv=0.
      graupel=0.; graupelncv=0.; sr=0.; refl=0.; rec=-99.; rei=-99.; res=-99.
      cf=-1.; step=-1; top=-1
      write(*,'(A,3(1X,I0))') 'CALL',profile,branch,mode
      if(mode==0) then
        call call_branch(branch)
      else
        call call_branch(branch,mode==2)
      endif
      if(profile==1) then
        if(any(qc/=0.) .or. any(nc/=0.)) error stop 'rain-only test formed cloud in controlled warm/subsaturated case'
      endif
      values=[reshape(th,[nz]),reshape(q,[nz]),reshape(qc,[nz]),reshape(qi,[nz]),reshape(qr,[nz]), &
           reshape(qs,[nz]),reshape(qg,[nz]),reshape(qh,[nz]),reshape(nn,[nz]),reshape(nc,[nz]),reshape(nr,[nz]), &
           rain(1,1),rainncv(1,1),snow(1,1),snowncv(1,1),hail(1,1),hailncv(1,1),graupel(1,1),graupelncv(1,1), &
           sr(1,1),reshape(refl,[nz]),reshape(rec,[nz]),reshape(rei,[nz]),reshape(res,[nz]),reshape(cf,[nz])]
      if(.not.all(ieee_is_finite(values))) error stop 'nonfinite UDM state in slope fixture'
      if(any(cf < -1.) .or. any(cf > 1.)) error stop 'invalid optional cloud-fraction diagnostic'
      bits=transfer(values,bits)
      write(*,'(A,4(1X,I0))') 'RESULT',profile,branch,mode,size(bits)
      write(*,'(*(Z8.8,1X))') bits
      write(*,'(A,2(1X,I0))') 'DIAG',step(1,1),top(1,1)
    enddo
  enddo
contains
  subroutine call_branch(b,dry)
    integer,intent(in) :: b
    logical,optional,intent(in) :: dry
    if(b==1) then
      call invoke(dry=dry)
    else if(b==2) then
      call invoke(cf_arg=cf,step_arg=step,dry=dry)
    else
      call invoke(cf_arg=cf,step_arg=step,top_arg=top,dry=dry)
    endif
  end subroutine call_branch

  subroutine invoke(cf_arg,step_arg,top_arg,dry)
    real,optional,intent(inout) :: cf_arg(1,nz,1)
    integer,optional,intent(inout) :: step_arg(1,1),top_arg(1,1)
    logical,optional,intent(in) :: dry
    call udm(th=th,q=q,qc=qc,qr=qr,qi=qi,qs=qs,qg=qg,qh=qh,nn=nn,nc=nc,nr=nr, &
         den=den,pii=pii,p=p,delz=delz,delt=dt,g=9.81,cpd=1004.,cpv=1850.,ccn0=1.e8, &
         rd=287.,rv=461.6,t0c=273.15,ep1=.608,ep2=.622,qmin=1.e-12,xls=2.5e6,xlv0=2.5e6,xlf0=3.34e5, &
         den0=1.,denr=1000.,cliq=4186.,cice=2106.,psat=610.,xland=land,xice=ice,rain=rain,rainncv=rainncv, &
         snow=snow,snowncv=snowncv,hail=hail,hailncv=hailncv,sr=sr,refl_10cm=refl,diagflag=.false.,do_radar_ref=0, &
         graupel=graupel,graupelncv=graupelncv,itimestep=1,has_reqc=1,has_reqi=1,has_reqs=1, &
         re_cloud=rec,re_ice=rei,re_snow=res,ids=1,ide=1,jds=1,jde=1,kds=1,kde=nz, &
         ims=1,ime=1,jms=1,jme=1,kms=1,kme=nz,its=1,ite=1,jts=1,jte=1,kts=1,kte=nz, &
         udm_cldfra=cf_arg,udm_cf_step=step_arg,udm_cf_top=top_arg,input_density_is_dry=dry)
  end subroutine invoke
end program test_udm_rain_only_slopes
