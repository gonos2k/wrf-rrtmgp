program test_udm_sr_rows
  use module_mp_udm, only: udm, udminit, udm_funct_svp_setup, udm_funct_shape_setup, &
       udm_funct_lb2017_setup
  implicit none
  integer, parameter :: nx=2, ny=2, nz=2
  real :: th(nx,nz,ny), q(nx,nz,ny), qc(nx,nz,ny), qr(nx,nz,ny)
  real :: qi(nx,nz,ny), qs(nx,nz,ny), qg(nx,nz,ny), qh(nx,nz,ny)
  real :: nn(nx,nz,ny), nc(nx,nz,ny), nr(nx,nz,ny)
  real :: den(nx,nz,ny), pii(nx,nz,ny), p(nx,nz,ny), delz(nx,nz,ny)
  real :: xland(nx,ny), xice(nx,ny), rain(nx,ny), rainncv(nx,ny), sr(nx,ny)
  real :: snow(nx,ny), snowncv(nx,ny), hail(nx,ny), hailncv(nx,ny)
  real :: graupel(nx,ny), graupelncv(nx,ny)
  real :: refl(nx,nz,ny), re_cloud(nx,nz,ny), re_ice(nx,nz,ny), re_snow(nx,nz,ny)
  integer :: j

  call udminit(1.0,1000.0,100.0,4186.0,1004.0,1.0e8,.false.)
  call udm_funct_svp_setup
  call udm_funct_shape_setup
  call udm_funct_lb2017_setup
  th=250.0/0.99; q=0.; qc=0.; qr=0.; qi=0.; qs=0.; qg=0.; qh=0.
  nn=1.e8; nc=1.e8; nr=1.e6
  den=1.0; pii=0.99; p=90000.; delz=100.
  xland=1.; xice=0.
  rain=0.; rainncv=0.; snow=0.; snowncv=0.; hail=0.; hailncv=0.
  graupel=0.; graupelncv=0.; refl=0.; re_cloud=0.; re_ice=0.; re_snow=0.
  sr(:,1)=[11.,12.]
  sr(:,2)=[21.,22.]

  ! All three has_req flags are zero, selecting the legacy RRTMG4 UDM path.
  ! Each udm2d call resets its passed surface-rain ratio row to zero.
  call udm(th=th,q=q,qc=qc,qr=qr,qi=qi,qs=qs,qg=qg,qh=qh,nn=nn,nc=nc,nr=nr, &
       den=den,pii=pii,p=p,delz=delz,delt=1.e-3,g=9.81,cpd=1004.,cpv=1850.,ccn0=1.e8, &
       rd=287.,rv=461.,t0c=273.15,ep1=0.608,ep2=0.622,qmin=1.e-12,xls=2.5e6, &
       xlv0=2.5e6,xlf0=3.34e5,den0=1.,denr=1000.,cliq=4186.,cice=2106.,psat=610., &
       xland=xland,xice=xice,rain=rain,rainncv=rainncv,snow=snow,snowncv=snowncv, &
       hail=hail,hailncv=hailncv,sr=sr,refl_10cm=refl,diagflag=.false.,do_radar_ref=0, &
       graupel=graupel,graupelncv=graupelncv,itimestep=2,has_reqc=0,has_reqi=0,has_reqs=0, &
       re_cloud=re_cloud,re_ice=re_ice,re_snow=re_snow,ids=1,ide=nx,jds=1,jde=ny,kds=1,kde=nz, &
       ims=1,ime=nx,jms=1,jme=ny,kms=1,kme=nz,its=1,ite=nx,jts=1,jte=ny,kts=1,kte=nz)

  do j=1,ny
    if (any(sr(:,j)/=0.)) then
      write(*,'(A,I0,A,2(1X,ES12.4))') 'UDM_SR_ROW_FAILURE j=',j,' observed=',sr(:,j)
      error stop 'legacy UDM path failed to reset SR row'
    end if
  end do
  write(*,'(A,4(1X,ES12.4))') 'UDM_SR_ROWS_RESET',sr(:,1),sr(:,2)
end program test_udm_sr_rows
