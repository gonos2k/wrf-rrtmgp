! Manufactured actual-module observation. No host storage/transport claim.
#ifdef OBSERVER_ONLY
module udm_test_observer
  use iso_fortran_env, only: int32
  implicit none
  logical :: observer_enabled=.false.
  integer :: case_id=0
contains
  subroutine capture(tag,i,k,subcycle,values)
    character(*),intent(in)::tag
    integer,intent(in)::i,k,subcycle
    real,intent(in)::values(:)
    if (.not.observer_enabled) return
    write(*,'(A,1X,A,5(1X,I0))') 'OBS',tag,case_id,i,k,subcycle,size(values)
    write(*,'(*(Z8.8,1X))') transfer(values,[0_int32],size(values))
  end subroutine
end module
#endif

#ifndef OBSERVER_ONLY
program partial_activation
  use module_mp_udm, only: udm,udminit,udm_funct_svp_setup,udm_funct_shape_setup, &
       udm_funct_lb2017_setup,fsvp_water
  use udm_test_observer
  use ieee_arithmetic, only: ieee_is_finite,ieee_next_after
  implicit none
  integer,parameter::nz=4
  real::th(1,nz,1),q(1,nz,1),qc(1,nz,1),qi(1,nz,1),qr(1,nz,1),qs(1,nz,1),qg(1,nz,1),qh(1,nz,1)
  real::nn(1,nz,1),nc(1,nz,1),nr(1,nz,1),den(1,nz,1),pii(1,nz,1),p(1,nz,1),delz(1,nz,1)
  real::land(1,1),ice(1,1),rain(1,1),rainncv(1,1),snow(1,1),snowncv(1,1),hail(1,1),hailncv(1,1)
  real::graupel(1,1),graupelncv(1,1),sr(1,1),refl(1,nz,1),rec(1,nz,1),rei(1,nz,1),res(1,nz,1),cf(1,nz,1)
  integer::step(1,1),top(1,1),a,b,k,iteration
  real::density,target_alpha,rh,sv,qsat
  real::raw_values(10)
  real,allocatable::values(:)
  character(8)::mode
  call get_command_argument(1,mode)
  if (trim(mode)/='on'.and.trim(mode)/='off') error stop 'select on/off'
  observer_enabled=trim(mode)=='on'
  if(storage_size(1.)/=32) error stop 'default REAL32 required'
  call udminit(1.,1000.,100.,4186.,1004.5,2.e8,.false.)
  call udm_funct_svp_setup
  call udm_funct_shape_setup
  call udm_funct_lb2017_setup
  raw_values=[0.,1.e7,ieee_next_after(5.e7,0.),5.e7,ieee_next_after(5.e7,huge(1.)), &
       1.e8,ieee_next_after(2.e10,0.),2.e10,ieee_next_after(2.e10,huge(1.)),3.e10]
  do a=1,2
    density=.7
    if(a==2) density=1.1
    do b=1,10
      target_alpha=0.
      case_id=10*(a-1)+b
      ! EOS-consistent cells: rho_d and T fix p only after qv is solved.
      ! The .622 saturation convention is the actual supplied UDM ep2.
      th=285.; pii=1.; den=density; q=0.; delz=100.
      rh=.8
      do iteration=1,20
        p=den*th*(287.+461.6*q)
        sv=fsvp_water(th(1,1,1),p(1,1,1))
        qsat=.622*sv/(p(1,1,1)-sv)
        q=rh*qsat
      enddo
      p=den*th*(287.+461.6*q)
      qc=0.; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.
      ! Same raw arrays across density arms, deliberately no unit assertion.
      nn=raw_values(b); nc=0.; nr=0.
      land=1.; ice=0.; rain=0.; rainncv=0.; snow=0.; snowncv=0.; hail=0.; hailncv=0.
      graupel=0.; graupelncv=0.; sr=0.; refl=0.; rec=-99.; rei=-99.; res=-99.
      cf=-1.; step=-1; top=-1
      do k=1,nz
        values=[nn(1,k,1),nc(1,k,1),nr(1,k,1),q(1,k,1),qc(1,k,1),qi(1,k,1),qr(1,k,1), &
                qs(1,k,1),qg(1,k,1),qh(1,k,1),th(1,k,1),p(1,k,1),den(1,k,1),rh,target_alpha]
        write(*,'(A,3(1X,I0))') 'INPUT',case_id,k,size(values)
        write(*,'(*(Z8.8,1X))') transfer(values,[0_int32],size(values))
      enddo
      call udm(th=th,q=q,qc=qc,qr=qr,qi=qi,qs=qs,qg=qg,qh=qh,nn=nn,nc=nc,nr=nr, &
           den=den,pii=pii,p=p,delz=delz,delt=360.,g=9.81,cpd=1004.5,cpv=1850.,ccn0=2.e8, &
           rd=287.,rv=461.6,t0c=273.15,ep1=.608,ep2=.622,qmin=1.e-12,xls=2.5e6, &
           xlv0=2.5e6,xlf0=3.34e5,den0=1.,denr=1000.,cliq=4186.,cice=2106.,psat=610., &
           xland=land,xice=ice,rain=rain,rainncv=rainncv,snow=snow,snowncv=snowncv, &
           hail=hail,hailncv=hailncv,sr=sr,refl_10cm=refl,diagflag=.false.,do_radar_ref=0, &
           graupel=graupel,graupelncv=graupelncv,itimestep=2,has_reqc=1,has_reqi=1,has_reqs=1, &
           re_cloud=rec,re_ice=rei,re_snow=res,ids=1,ide=1,jds=1,jde=1,kds=1,kde=nz, &
           ims=1,ime=1,jms=1,jme=1,kms=1,kme=nz,its=1,ite=1,jts=1,jte=1,kts=1,kte=nz, &
           udm_cldfra=cf,udm_cf_step=step,udm_cf_top=top,ccn_preinitialized=.true.,input_density_is_dry=.true.)
      values=[reshape(th,[nz]),reshape(q,[nz]),reshape(qc,[nz]),reshape(qi,[nz]),reshape(qr,[nz]), &
           reshape(qs,[nz]),reshape(qg,[nz]),reshape(qh,[nz]),reshape(nn,[nz]),reshape(nc,[nz]),reshape(nr,[nz]), &
           rain(1,1),rainncv(1,1),snow(1,1),snowncv(1,1),hail(1,1),hailncv(1,1), &
           graupel(1,1),graupelncv(1,1),sr(1,1),reshape(refl,[nz]),reshape(rec,[nz]), &
           reshape(rei,[nz]),reshape(res,[nz]),reshape(cf,[nz])]
      if(.not.all(ieee_is_finite(values))) error stop 'nonfinite return'
      write(*,'(A,2(1X,I0))') 'RETURN',case_id,size(values)
      write(*,'(*(Z8.8,1X))') transfer(values,[0_int32],size(values))
      write(*,'(A,3(1X,I0))') 'TAGS',case_id,step(1,1),top(1,1)
    enddo
  enddo
end program
#endif
