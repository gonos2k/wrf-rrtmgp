program test_udm_native_radii
  use module_mp_udm, only: udm, udminit, udm_mp_effective_radius, udm_funct_svp_setup, &
       udm_funct_shape_setup, udm_funct_lb2017_setup
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, parameter :: nx=3, nz=3
  real :: th(nx,nz,1), q(nx,nz,1), qc(nx,nz,1), qr(nx,nz,1)
  real :: qi(nx,nz,1), qs(nx,nz,1), qg(nx,nz,1), qh(nx,nz,1)
  real :: nn(nx,nz,1), nc(nx,nz,1), nr(nx,nz,1)
  real :: den(nx,nz,1), pii(nx,nz,1), p(nx,nz,1), delz(nx,nz,1)
  real :: xland(nx,1), xice(nx,1), rain(nx,1), rainncv(nx,1), snow(nx,1), snowncv(nx,1)
  real :: hail(nx,1), hailncv(nx,1), graupel(nx,1), graupelncv(nx,1), sr(nx,1)
  real :: refl(nx,nz,1)
  real :: re_cloud(nx,nz,1), re_ice(nx,nz,1), re_snow(nx,nz,1)
  real :: used_cf(nx,nz,1)
  integer :: used_cf_step(nx,1)
  real :: rho_case(2), radii(3,2,3), direct_radii(3,2), number_radii(2)
  real :: rt(1), rqc(1), rqi(1), rqs(1), rrho(1), rnc(1), rcloud(1), rice(1), rsnow(1)
  integer :: c,k
  rho_case=[0.8,1.15]

  call udminit(1.0,1000.0,100.0,4186.0,1004.0,1.0e8,.false.)
  call udm_funct_svp_setup
  call udm_funct_shape_setup
  call udm_funct_lb2017_setup
  do c=1,2
    th=0.; q=0.; qc=0.; qr=0.; qi=0.; qs=0.; qg=0.; qh=0.
    nn=1.e8; nc=1.e8; nr=1.e6
    den=rho_case(c); pii=0.99; p=90000.; delz=100.
    xland=1.; xice=0.
    rain=0.; rainncv=0.; snow=0.; snowncv=0.; hail=0.; hailncv=0.
    graupel=0.; graupelncv=0.; sr=0.; refl=0.
    do k=1,nz
      th(1,k,1)=250.0/pii(1,k,1)
      th(2,k,1)=250.0/pii(2,k,1)
      q(1,k,1)=0.001
      q(2,k,1)=0.001
    end do
    used_cf=-1.; used_cf_step=-1
    ! The optional output spans a larger memory tile than this call's active
    ! tile. Preserve a valid prior record outside the active bounds in one
    ! density case, and verify the sentinel is likewise preserved in the other.
    if (c==1) then
      used_cf(3,:,1)=0.25; used_cf_step(3,1)=17
    end if
    re_cloud=-99.; re_ice=-99.; re_snow=-99.
    qc(1,2,1)=1.e-3; qc(2,2,1)=1.e-3; nc(1,2,1)=1.e8; nc(2,2,1)=1.e8
    qi(1,2,1)=1.e-3; qi(2,2,1)=1.e-3; nn(1,2,1)=1.e6; nn(2,2,1)=1.e6
    qs(1,2,1)=1.e-3; qs(2,2,1)=1.e-3
    call udm(th=th,q=q,qc=qc,qr=qr,qi=qi,qs=qs,qg=qg,qh=qh,nn=nn,nc=nc,nr=nr, &
         den=den,pii=pii,p=p,delz=delz,delt=1.e-3,g=9.81,cpd=1004.,cpv=1850.,ccn0=1.e8, &
         rd=287.,rv=461.,t0c=273.15,ep1=0.608,ep2=0.622,qmin=1.e-12,xls=2.5e6, &
         xlv0=2.5e6,xlf0=3.34e5,den0=1.,denr=1000.,cliq=4186.,cice=2106.,psat=610., &
         xland=xland,xice=xice,rain=rain,rainncv=rainncv,snow=snow,snowncv=snowncv, &
         hail=hail,hailncv=hailncv,sr=sr,refl_10cm=refl,diagflag=.false.,do_radar_ref=0, &
         graupel=graupel,graupelncv=graupelncv,itimestep=1,has_reqc=1,has_reqi=1,has_reqs=1, &
         re_cloud=re_cloud,re_ice=re_ice,re_snow=re_snow,ids=1,ide=3,jds=1,jde=1,kds=1,kde=nz, &
         ims=1,ime=3,jms=1,jme=1,kms=1,kme=nz,its=1,ite=2,jts=1,jte=1,kts=1,kte=nz, &
         udm_cldfra=used_cf,udm_cf_step=used_cf_step)
    radii(:,c,1)=re_cloud(1,:,1)
    radii(:,c,2)=re_ice(1,:,1)
    radii(:,c,3)=re_snow(1,:,1)
    if (.not.all(ieee_is_finite(re_cloud(1,:,:))) .or. .not.all(ieee_is_finite(re_ice(1,:,:))) .or. &
        .not.all(ieee_is_finite(re_snow(1,:,:)))) error stop 'nonfinite effective radius'
    if (.not.all(ieee_is_finite(used_cf(1:2,:,1))) .or. any(used_cf(1:2,:,1)<0.) .or. &
        any(used_cf(1:2,:,1)>1.)) &
         error stop 'actual UDM cldf_diag output outside [0,1]'
    if (any(used_cf_step(1:2,1)/=1)) error stop 'UDM cldf_diag source step not recorded'
    if (c==1) then
      if (any(used_cf(3,:,1)/=0.25) .or. used_cf_step(3,1)/=17) &
           error stop 'out-of-tile prior UDM diagnostic must be preserved'
    else
      if (any(used_cf(3,:,1)/=-1.) .or. used_cf_step(3,1)/=-1) &
           error stop 'out-of-tile sentinel must be preserved'
    end if
    write(*,'(A,I0,9(1X,ES12.4))') 'CASE ',c,re_cloud(1,2,1),re_ice(1,2,1),re_snow(1,2,1), &
         minval(re_cloud(1:2,:,:)),maxval(re_cloud(1:2,:,:)),minval(re_ice(1:2,:,:)), &
         maxval(re_ice(1:2,:,:)),minval(re_snow(1:2,:,:)),maxval(re_snow(1:2,:,:))
    if (any(re_cloud(1:2,:,:)<2.509e-6) .or. any(re_cloud(1:2,:,:)>50.01e-6) .or. &
        any(re_ice(1:2,:,:)<5.009e-6) .or. any(re_ice(1:2,:,:)>125.01e-6) .or. &
        any(re_snow(1:2,:,:)<24.99e-6) .or. any(re_snow(1:2,:,:)>999.1e-6)) &
        error stop 'effective radius outside UDM bounds'
  end do
  if (abs(radii(2,1,1)-radii(2,2,1))<1.e-8 .or. &
      abs(radii(2,1,3)-radii(2,2,3))<1.e-8) error stop 'outer cloud/snow radii did not respond to density'
  rt=250.; rqc=1.e-3; rqi=1.e-3; rqs=1.e-3; rnc=1.e8
  do c=1,2
    rrho=rho_case(c); rcloud=2.51e-6; rice=5.01e-6; rsnow=25.e-6
    call udm_mp_effective_radius(rt,rqc,rqi,rqs,rrho,1.e-12,273.15,rnc, &
         rcloud,rice,rsnow,1,1,1,1)
    direct_radii(:,c)=[rcloud(1),rice(1),rsnow(1)]
  end do
  if (any(abs(direct_radii(:,1)-direct_radii(:,2))<1.e-9)) &
       error stop 'direct cloud/ice/snow radius equations must respond to density'
  rrho=rho_case(1); rnc=1.e8; rcloud=2.51e-6; rice=5.01e-6; rsnow=25.e-6
  call udm_mp_effective_radius(rt,rqc,rqi,rqs,rrho,1.e-12,273.15,rnc, &
       rcloud,rice,rsnow,1,1,1,1)
  number_radii(1)=rcloud(1)
  rnc=2.e8; rcloud=2.51e-6; rice=5.01e-6; rsnow=25.e-6
  call udm_mp_effective_radius(rt,rqc,rqi,rqs,rrho,1.e-12,273.15,rnc, &
       rcloud,rice,rsnow,1,1,1,1)
  number_radii(2)=rcloud(1)
  if (abs(number_radii(1)-number_radii(2))<1.e-9) &
       error stop 'direct cloud radius equation must respond to number concentration'
  ! Clear columns exit udm2d before cldf_diag; active and out-of-tile columns
  ! all retain the invalid sentinel.
  th=250./0.99; q=0.; qc=0.; qr=0.; qi=0.; qs=0.; qg=0.; qh=0.
  nn=1.e8; nc=1.e8; nr=1.e6; den=rho_case(1); pii=0.99; p=90000.; delz=100.
  rain=0.; rainncv=0.; snow=0.; snowncv=0.; hail=0.; hailncv=0.
  graupel=0.; graupelncv=0.; sr=0.; refl=0.
  call udm(th=th,q=q,qc=qc,qr=qr,qi=qi,qs=qs,qg=qg,qh=qh,nn=nn,nc=nc,nr=nr, &
       den=den,pii=pii,p=p,delz=delz,delt=1.e-3,g=9.81,cpd=1004.,cpv=1850.,ccn0=1.e8, &
       rd=287.,rv=461.,t0c=273.15,ep1=0.608,ep2=0.622,qmin=1.e-12,xls=2.5e6, &
       xlv0=2.5e6,xlf0=3.34e5,den0=1.,denr=1000.,cliq=4186.,cice=2106.,psat=610., &
       xland=xland,xice=xice,rain=rain,rainncv=rainncv,snow=snow,snowncv=snowncv, &
       hail=hail,hailncv=hailncv,sr=sr,refl_10cm=refl,diagflag=.false.,do_radar_ref=0, &
       graupel=graupel,graupelncv=graupelncv,itimestep=2,has_reqc=1,has_reqi=1,has_reqs=1, &
       re_cloud=re_cloud,re_ice=re_ice,re_snow=re_snow,ids=1,ide=3,jds=1,jde=1,kds=1,kde=nz, &
       ims=1,ime=3,jms=1,jme=1,kms=1,kme=nz,its=1,ite=2,jts=1,jte=1,kts=1,kte=nz, &
       udm_cldfra=used_cf,udm_cf_step=used_cf_step)
  if (any(used_cf(1:2,:,1)/=-1.) .or. any(used_cf_step(1:2,1)/=-1)) &
       error stop 'clear column skipped by udm2d must retain invalid sentinel'
  if (any(used_cf(3,:,1)/=-1.) .or. used_cf_step(3,1)/=-1) &
       error stop 'skipped tile column must retain invalid sentinel'
  write(*,'(A,6(1X,ES14.6))') 'UDM_NATIVE_RADII',radii(2,1,1),radii(2,2,1), &
       radii(2,1,2),radii(2,2,2),radii(2,1,3),radii(2,2,3)
  write(*,'(A,6(1X,ES14.6))') 'UDM_DIRECT_DENSITY_RESPONSE',direct_radii(:,1),direct_radii(:,2)
  write(*,'(A,2(1X,ES14.6))') 'UDM_DIRECT_NUMBER_RESPONSE',number_radii
  write(*,'(A)') 'UDM outer-call native-density test passed'
end program test_udm_native_radii
