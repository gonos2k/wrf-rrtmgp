! The Python runner supplies the verbatim native semi_lagrangian module, or
! compiles the complete original/candidate UDM module for OUTER_UDM.
#ifndef OUTER_UDM
program sedimentation_density
  use native_sedimentation, only: semi_lagrangian
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, parameter :: nk=6
  real :: rho(1,nk), weight(1,nk), dz(1,nk), tk(1,nk), fac(1,nk)
  real :: qv(nk), q0(nk), q1(nk), transported(nk), velocity(nk), p(nk), precip
  real, parameter :: rd=287., rv=461.6
  integer :: moisture, basis, k
  if (storage_size(1.)/=32) error stop 'fixture requires default REAL32'
  dz(1,:)=[80.,90.,100.,110.,120.,130.]
  tk=256.; velocity=[1.2,1.6,2.,2.4,2.8,3.2]
  fac=1.
  q0=[1.e-4,4.e-4,8.e-4,1.2e-3,5.e-4,1.e-4]
  do moisture=0,1
    if (moisture==0) then
      ! Binary power densities make p/T and the qv=0 DEND arithmetic exact.
      rho(1,:)=[1.,1.,.5,.5,.25,.125]; qv=0.
    else
      rho(1,:)=[1.2,.95,.7,.45,.25,.12]
      qv=[.020,.016,.012,.008,.004,.001]
    endif
    p=rho(1,:)*tk(1,:)*(rd+rv*qv)
    do basis=0,1
      if (basis==0) then
        weight(1,:)=(p/tk(1,:)-rho(1,:)*rv)/(rd-rv)
      else
        weight=rho
      endif
      transported=weight(1,:)*q0
      precip=-99.
      call semi_lagrangian(1,nk,nk,weight,fac,tk,dz,velocity,transported,precip,60.,1,1)
      q1=max(transported/weight(1,:),0.)
      if (.not.all(ieee_is_finite(q1)) .or. any(q1<0.) .or. &
          .not.ieee_is_finite(precip) .or. precip<=0.) error stop 'invalid native sedimentation output'
      write(*,'(A,2(1X,I0),1X,ES26.17)') 'SED',moisture,basis,real(precip,8)
      do k=1,nk
        write(*,'(A,1X,I0,7(1X,ES26.17))') 'ROW',k,real(rho(1,k),8),real(weight(1,k),8), &
             real(dz(1,k),8),real(qv(k),8),real(q0(k),8),real(q1(k),8),real(transported(k),8)
      enddo
    enddo
  enddo
end program sedimentation_density
#else
program outer_udm_density
  use module_mp_udm, only: udm,udminit,udm_funct_svp_setup,udm_funct_shape_setup,udm_funct_lb2017_setup
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use, intrinsic :: iso_fortran_env, only: int32
  implicit none
  integer, parameter :: nz=6
  real :: th(1,nz,1),q(1,nz,1),qc(1,nz,1),qi(1,nz,1),qr(1,nz,1),qs(1,nz,1),qg(1,nz,1),qh(1,nz,1)
  real :: nn(1,nz,1),nc(1,nz,1),nr(1,nz,1),den(1,nz,1),pii(1,nz,1),p(1,nz,1),delz(1,nz,1)
  real :: land(1,1),ice(1,1),rain(1,1),rainncv(1,1),snow(1,1),snowncv(1,1),hail(1,1),hailncv(1,1)
  real :: graupel(1,1),graupelncv(1,1),sr(1,1),refl(1,nz,1),rec(1,nz,1),rei(1,nz,1),res(1,nz,1),cf(1,nz,1)
  integer :: step(1,1),top(1,1),moisture,branch,mode,lastmode
  real, allocatable :: values(:)
  if (storage_size(1.)/=32) error stop 'fixture requires default REAL32'
  call udminit(1.,1000.,100.,4186.,1004.,1.e8,.false.)
  call udm_funct_svp_setup
  call udm_funct_shape_setup
  call udm_funct_lb2017_setup
  lastmode=0
#ifndef BASELINE_UDM
  lastmode=2
#endif
  do moisture=0,1
    do branch=1,3
      do mode=1,1
        th=256.; pii=1.; q=0.; den=1.; delz=100.
        if (moisture==1) then
          q(1,:,1)=[.001,.0015,.002,.0025,.003,.0035]
          den(1,:,1)=[1.2,1.05,.9,.75,.6,.45]
        endif
        p=den*256.*(287.+461.6*q)
        qc=0.; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.
        ! Keep the original scheme's cloud slopes initialized through the rain
        ! top. A rain-only manufactured case traps on the native rslopec2 use
        ! above ktopqc; that separate source hazard is not repaired by this test.
        qc(1,1:5,1)=0.
        qr(1,2:5,1)=[1.e-4,4.e-4,8.e-4,2.e-4]
        qs(1,3,1)=1.e-4
        nn=1.e8; nc=1.e8; nr=1.e6
        land=1.; ice=0.; rain=0.; rainncv=0.; snow=0.; snowncv=0.; hail=0.; hailncv=0.
        graupel=0.; graupelncv=0.; sr=0.; refl=0.; rec=-99.; rei=-99.; res=-99.
        cf=-1.; step=-1; top=-1
        if (mode==0) then
          call call_branch(branch)
        else
          call call_branch(branch,mode==2)
        endif
        values=[reshape(th,[nz]),reshape(q,[nz]),reshape(qc,[nz]),reshape(qi,[nz]),reshape(qr,[nz]), &
             reshape(qs,[nz]),reshape(qg,[nz]),reshape(qh,[nz]),reshape(nn,[nz]),reshape(nc,[nz]),reshape(nr,[nz]), &
             rain(1,1),rainncv(1,1),snow(1,1),snowncv(1,1),hail(1,1),hailncv(1,1), &
             graupel(1,1),graupelncv(1,1),sr(1,1),reshape(refl,[nz]),reshape(rec,[nz]), &
             reshape(rei,[nz]),reshape(res,[nz]),reshape(cf,[nz])]
        if (.not.all(ieee_is_finite(values))) error stop 'nonfinite outer UDM state'
        write(*,'(A,3(1X,I0),1X,I0)') 'OUTER',moisture,branch,mode,size(values)
        write(*,'(*(Z8.8,1X))') transfer(values,[0_int32],size(values))
        write(*,'(A,2(1X,I0))') 'TAGS',step(1,1),top(1,1)
      enddo
    enddo
  enddo
contains
  subroutine call_branch(b,dry)
    integer,intent(in) :: b
    logical,optional,intent(in) :: dry
    if (b==1) then
      call invoke(dry=dry)
    else if (b==2) then
      call invoke(cf_arg=cf,step_arg=step,dry=dry)
    else
      call invoke(cf_arg=cf,step_arg=step,top_arg=top,dry=dry)
    endif
  end subroutine
  subroutine invoke(cf_arg,step_arg,top_arg,dry)
    real,optional,intent(inout) :: cf_arg(1,nz,1)
    integer,optional,intent(inout) :: step_arg(1,1),top_arg(1,1)
    logical,optional,intent(in) :: dry
    call udm(th=th,q=q,qc=qc,qr=qr,qi=qi,qs=qs,qg=qg,qh=qh,nn=nn,nc=nc,nr=nr, &
         den=den,pii=pii,p=p,delz=delz,delt=1.,g=9.81,cpd=1004.,cpv=1850.,ccn0=1.e8, &
         rd=287.,rv=461.6,t0c=273.15,ep1=.608,ep2=.622,qmin=1.e-12,xls=2.5e6, &
         xlv0=2.5e6,xlf0=3.34e5,den0=1.,denr=1000.,cliq=4186.,cice=2106.,psat=610., &
         xland=land,xice=ice,rain=rain,rainncv=rainncv,snow=snow,snowncv=snowncv, &
         hail=hail,hailncv=hailncv,sr=sr,refl_10cm=refl,diagflag=.false.,do_radar_ref=0, &
         graupel=graupel,graupelncv=graupelncv,itimestep=2,has_reqc=1,has_reqi=1,has_reqs=1, &
         re_cloud=rec,re_ice=rei,re_snow=res,ids=1,ide=1,jds=1,jde=1,kds=1,kde=nz, &
         ims=1,ime=1,jms=1,jme=1,kms=1,kme=nz,its=1,ite=1,jts=1,jte=1,kts=1,kte=nz, &
         udm_cldfra=cf_arg,udm_cf_step=step_arg,udm_cf_top=top_arg &
#ifndef BASELINE_UDM
         ,input_density_is_dry=dry &
#endif
         )
  end subroutine
end program outer_udm_density
#endif
