program test_cu_population_optics
  use, intrinsic :: iso_fortran_env, only: int8
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite,ieee_value,ieee_quiet_nan
  use mo_rte_kind, only: wp
  use mo_cloud_optics_rrtmgp, only: ty_cloud_optics_rrtmgp
  use mo_optical_props, only: ty_optical_props_1scl,ty_optical_props_2str
  use mo_load_cloud_coefficients, only: load_cld_lutcoeff
  use module_ra_rrtmgp, only: rrtmgp_init,rrtmgp_lw_column,rrtmgp_sw_column, &
       ty_rrtmgp_lw_workspace,ty_rrtmgp_sw_workspace,rrtmgp_release_workspace
  use module_ra_rrtmgp_trace, only: trace_start,trace_end
  implicit none
  integer,parameter :: nc=2,nl=3,nv=4
  character(1024) :: data,mode,table,arg
  integer :: frozen=0,overlap=1,c,ncols=nc,nlayers=nl
  logical :: precip=.true.,bundle=.true.
  real :: p(nc,nl),pe(nc,nv),t(nc,nl),te(nc,nv),ts(nc),h2o(nc,nl),co2(nc,nl),o3(nc,nl)
  real :: n2o(nc,nl),ch4(nc,nl),o2(nc,nl),emis(nc,1),cf(nc,nl),lwp(nc,nl),iwp(nc,nl)
  real :: swp(nc,nl),rwp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl)
  real :: cu_l(nc,nl),cu_i(nc,nl),cu_rl(nc,nl),cu_ri(nc,nl),lg(nc,nl),lh(nc,nl),zero(nc,nl)
  real :: a(nc),mu(nc),up(nc,nv),dn(nc,nv),hr(nc,nl),upc(nc,nv),dnc(nc,nv),hrc(nc,nl)
  real :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv),visd(nc,nv),visf(nc,nv),nird(nc,nv),nirf(nc,nv)
  real :: du(nc,nv),dcu(nc,nv),vdu(nc,nv),ndu(nc,nv),before_lw(44),before_sw(132),after_lw(44),after_sw(132),last_lw(44)
  real :: saved_l(nc,nl),saved_i(nc,nl),saved_rl(nc,nl),saved_ri(nc,nl)
  real,allocatable :: frozen_g(:,:),frozen_h(:,:),frozen_lg(:,:),frozen_lh(:,:)
  type(ty_rrtmgp_lw_workspace) :: lw_work
  type(ty_rrtmgp_sw_workspace) :: sw_work
  call get_command_argument(1,data);call get_command_argument(2,mode)
  call get_command_argument(3,table);call get_command_argument(4,arg)
  if(len_trim(arg)>0) read(arg,*) frozen
  do c=1,nc
    pe(c,:)=[1000.,700.,300.,1.];p(c,:)=[850.,500.,150.]
    t(c,:)=[285.,260.,230.];te(c,:)=[290.,275.,245.,210.]
    h2o(c,:)=[.01,.003,.0001];o3(c,:)=[.5e-6,1.e-6,5.e-6]
  end do
  ts=290.;co2=420.e-6;n2o=330.e-9;ch4=1.8e-6;o2=.2095;emis=.98
  cf=1.;lwp=0.;iwp=0.;swp=0.;rwp=0.;rel=10.;rei=30.;res=100.
  cu_l=0.;cu_i=0.;cu_rl=14.;cu_ri=55.;zero=0.;lg=20000.;lh=20000.;a=.1;mu=.65
  call rrtmgp_init(trim(data),frozen_optics=frozen,frozen_table=trim(table))
  if(frozen==1) then
    frozen_g=zero;frozen_h=zero;frozen_lg=lg;frozen_lh=lh
  end if
  select case(trim(mode))
  case('partial','radius','radius_nan','shape','path_negative','cf_zero')
    cu_l(:,2)=40.;cu_i(:,3)=30.
    if(mode=='radius') cu_ri=0.
    if(mode=='radius_nan') cu_ri=ieee_value(0.,ieee_quiet_nan)
    if(mode=='path_negative') cu_i=-1.
    if(mode=='cf_zero') cf=0.
    if(mode=='partial') then
      call rrtmgp_lw_column(p,pe,t,te,ts,h2o,co2,o3,n2o,ch4,o2,emis, &
           cf,lwp,iwp,swp,rel,rei,res,4,overlap,771,up,dn,hr,upc,dnc,hrc, &
           gwp=frozen_g,hwp=frozen_h,lambda_g=frozen_lg,lambda_h=frozen_lh,cu_lwp=cu_l)
    else if(mode=='shape') then
      call rrtmgp_lw_column(p,pe,t,te,ts,h2o,co2,o3,n2o,ch4,o2,emis, &
           cf,lwp,iwp,swp,rel,rei,res,4,overlap,771,up,dn,hr,upc,dnc,hrc, &
           gwp=frozen_g,hwp=frozen_h,lambda_g=frozen_lg,lambda_h=frozen_lh,cu_lwp=cu_l(:,:2),cu_iwp=cu_i,cu_rel=cu_rl,cu_rei=cu_ri)
    else
      call run_lw()
    end if
    error stop 'invalid CU backend bundle accepted'
  end select
  call optical_moment_and_allocation_proof()
  lwp(:,2)=40.;iwp(:,3)=30.;rwp(:,2)=4.;swp(:,3)=3.
  bundle=.false.;call both();before_lw=last_lw;before_sw=pack_sw()
  bundle=.true.;call both();after_lw=last_lw;after_sw=pack_sw()
  if(.not.bits_equal(after_lw,before_lw).or..not.bits_equal(after_sw,before_sw)) error stop 'zero-CU bundle changed original bits'
  ! Same particle sizes provide an independent linear-mass decomposition check.
  cu_rl=rel;cu_ri=rei;cu_l(:,2)=15.;cu_i(:,3)=12.
  call both();before_lw=last_lw;before_sw=pack_sw()
  saved_l=lwp;saved_i=iwp;lwp=lwp+cu_l;iwp=iwp+cu_i
  bundle=.false.;call both();after_lw=last_lw;after_sw=pack_sw()
  call close_outputs(before_lw,after_lw,'LW equal-size split mass')
  call close_outputs(before_sw,after_sw,'SW equal-size split mass')
  lwp=saved_l;iwp=saved_i
  ! A CU-only population must use its own sizes, including with native-min rei.
  lwp=0.;iwp=0.;rwp=0.;swp=0.;rel=2.51;rei=5.01;cu_rl=14.;cu_ri=55.
  bundle=.true.;call both();before_lw=last_lw;before_sw=pack_sw()
  lwp=cu_l;iwp=cu_i;saved_rl=rel;saved_ri=rei;rel=cu_rl;rei=cu_ri
  bundle=.false.;call both();after_lw=last_lw;after_sw=pack_sw()
  call close_outputs(before_lw,after_lw,'LW CU-only radius identity')
  call close_outputs(before_sw,after_sw,'SW CU-only radius identity')
  rel=saved_rl;rei=saved_ri;call both()
  if(maxval(abs(pack_sw()-before_sw))<.01) error stop 'fixture cannot distinguish wrong native-min CU radius'
  lwp=0.;iwp=0.;bundle=.true.
  ! Reuse one tile-owned workspace through different tails and active -> zero -> absent.
  ncols=1;nlayers=2;call both();ncols=nc;nlayers=nl;call both()
  cu_l=0.;cu_i=0.;call both();before_lw=last_lw;before_sw=pack_sw()
  bundle=.false.;call both();after_lw=last_lw;after_sw=pack_sw()
  if(.not.bits_equal(after_lw,before_lw).or..not.bits_equal(after_sw,before_sw)) error stop 'stale CU optics after zero/absent transition'
  if(mode=='capture'.or.mode=='overlap_zero'.or.mode=='no_precip'.or. &
     mode=='capture_zero'.or.mode=='capture_absent') then
    cf(:,1)=0.;cf(:,2:)=.6
    lwp(:,2)=40.;iwp(:,3)=30.;rwp(:,2)=4.;swp(:,3)=3.
    if(mode=='overlap_zero') overlap=0
    if(mode=='no_precip') then
      precip=.false.;swp(:,3)=8.
    end if
    cu_l(:,2)=35.;cu_i(:,3)=20.;bundle=.true.
    if(mode=='capture_zero'.or.mode=='capture_absent') then
      cu_l=0.;cu_i=0.
      if(mode=='capture_absent') bundle=.false.
    end if
    if(frozen==1) then
      frozen_g(:,3)=.5;frozen_h(:,3)=.2
    end if
    call trace_start('LW',1,1);call run_lw();call trace_end('LW')
    call trace_start('SW',1,1);call run_sw();call trace_end('SW')
    if(overlap==0) then
      before_sw=pack_sw();bundle=.false.;call run_sw();after_sw=pack_sw()
      if(.not.bits_equal(before_sw,after_sw)) error stop 'overlap-zero CU changed radiation outputs'
      if(frozen==0.and.any(du/=dcu)) error stop 'overlap-zero CU attenuated unscaled direct'
      bundle=.true.
    end if
  end if
  if(mode=='night') then
    mu=0.;cu_l=10.;bundle=.true.;call run_sw()
    if(any(pack_sw()/=0.)) error stop 'night CU left nonzero/stale outputs'
  end if
  call rrtmgp_release_workspace(lw_work);call rrtmgp_release_workspace(sw_work)
  print *, 'CU optical separation PASS: ',trim(mode),' frozen=',frozen
contains
  subroutine run_lw()
    if(precip) then
      call lw(rwp(:ncols,:nlayers))
    else
      call lw()
    end if
  end subroutine
  subroutine lw(rain)
    real,optional,intent(in)::rain(:,:)
    real,allocatable::c_l(:,:),c_i(:,:),c_rl(:,:),c_ri(:,:),fg(:,:),fh(:,:),flg(:,:),flh(:,:)
    if(frozen==1) then
      fg=frozen_g(:ncols,:nlayers);fh=frozen_h(:ncols,:nlayers)
      flg=lg(:ncols,:nlayers);flh=lh(:ncols,:nlayers)
    end if
    if(bundle) then
      c_l=cu_l(:ncols,:nlayers);c_i=cu_i(:ncols,:nlayers)
      c_rl=cu_rl(:ncols,:nlayers);c_ri=cu_ri(:ncols,:nlayers)
    end if
    call rrtmgp_lw_column(p(:ncols,:nlayers),pe(:ncols,:nlayers+1),t(:ncols,:nlayers), &
         te(:ncols,:nlayers+1),ts(:ncols),h2o(:ncols,:nlayers),co2(:ncols,:nlayers),o3(:ncols,:nlayers), &
         n2o(:ncols,:nlayers),ch4(:ncols,:nlayers),o2(:ncols,:nlayers),emis(:ncols,:), &
         cf(:ncols,:nlayers),lwp(:ncols,:nlayers),iwp(:ncols,:nlayers),swp(:ncols,:nlayers), &
         rel(:ncols,:nlayers),rei(:ncols,:nlayers),res(:ncols,:nlayers),4,overlap,771, &
         up(:ncols,:nlayers+1),dn(:ncols,:nlayers+1),hr(:ncols,:nlayers), &
         upc(:ncols,:nlayers+1),dnc(:ncols,:nlayers+1),hrc(:ncols,:nlayers), &
         gwp=fg,hwp=fh,lambda_g=flg,lambda_h=flh, &
         rwp=rain,workspace=lw_work,cu_lwp=c_l,cu_iwp=c_i,cu_rel=c_rl,cu_rei=c_ri, &
         cfc11vmr=zero(:ncols,:nlayers),cfc12vmr=zero(:ncols,:nlayers), &
         cfc22vmr=zero(:ncols,:nlayers),ccl4vmr=zero(:ncols,:nlayers))
    ! Unallocated actual arrays represent the absent optional legacy bundle.
  end subroutine
  subroutine run_sw()
    if(precip) then
      call sw(rwp(:ncols,:nlayers))
    else
      call sw()
    end if
  end subroutine
  subroutine sw(rain)
    real,optional,intent(in)::rain(:,:)
    real,allocatable::c_l(:,:),c_i(:,:),c_rl(:,:),c_ri(:,:),fg(:,:),fh(:,:),flg(:,:),flh(:,:)
    if(frozen==1) then
      fg=frozen_g(:ncols,:nlayers);fh=frozen_h(:ncols,:nlayers)
      flg=lg(:ncols,:nlayers);flh=lh(:ncols,:nlayers)
    end if
    if(bundle) then
      c_l=cu_l(:ncols,:nlayers);c_i=cu_i(:ncols,:nlayers)
      c_rl=cu_rl(:ncols,:nlayers);c_ri=cu_ri(:ncols,:nlayers)
    end if
    call rrtmgp_sw_column(p(:ncols,:nlayers),pe(:ncols,:nlayers+1),t(:ncols,:nlayers), &
         h2o(:ncols,:nlayers),co2(:ncols,:nlayers),o3(:ncols,:nlayers),n2o(:ncols,:nlayers),ch4(:ncols,:nlayers),o2(:ncols,:nlayers), &
         a(:ncols),a(:ncols),a(:ncols),a(:ncols),mu(:ncols),1361.,cf(:ncols,:nlayers), &
         lwp(:ncols,:nlayers),iwp(:ncols,:nlayers),swp(:ncols,:nlayers),rel(:ncols,:nlayers),rei(:ncols,:nlayers),res(:ncols,:nlayers), &
         4,overlap,771,up(:ncols,:nlayers+1),dn(:ncols,:nlayers+1),hr(:ncols,:nlayers), &
         upc(:ncols,:nlayers+1),dnc(:ncols,:nlayers+1),hrc(:ncols,:nlayers),direct(:ncols,:nlayers+1),diffuse(:ncols,:nlayers+1), &
         directc(:ncols,:nlayers+1),visd(:ncols,:nlayers+1),visf(:ncols,:nlayers+1),nird(:ncols,:nlayers+1),nirf(:ncols,:nlayers+1), &
         rwp=rain,gwp=fg,hwp=fh,lambda_g=flg,lambda_h=flh, &
         direct_unscaled=du(:ncols,:nlayers+1),directc_unscaled=dcu(:ncols,:nlayers+1), &
         visdir_unscaled=vdu(:ncols,:nlayers+1),nirdir_unscaled=ndu(:ncols,:nlayers+1),workspace=sw_work, &
         cu_lwp=c_l,cu_iwp=c_i,cu_rel=c_rl,cu_rei=c_ri)
  end subroutine
  subroutine both()
    call run_lw();last_lw=pack_lw();call run_sw()
    if(any(.not.ieee_is_finite(pack_sw()))) error stop 'nonfinite CU SW'
  end subroutine
  function pack_lw() result(out)
    real::out(44)
    out=[reshape(up,[8]),reshape(dn,[8]),reshape(hr,[6]),reshape(upc,[8]),reshape(dnc,[8]),reshape(hrc,[6])]
  end function
  function pack_sw() result(out)
    real::out(132)
    out=[pack_lw(),reshape(direct,[8]),reshape(diffuse,[8]),reshape(directc,[8]),reshape(visd,[8]),reshape(visf,[8]), &
         reshape(nird,[8]),reshape(nirf,[8]),reshape(du,[8]),reshape(dcu,[8]),reshape(vdu,[8]),reshape(ndu,[8])]
  end function
  function bits_equal(a,b) result(equal)
    real,intent(in)::a(:),b(:)
    logical::equal
    equal=.false.
    if(size(a)/=size(b)) return
    equal=all(transfer(a,[0_int8],size(a)*storage_size(a)/8)== &
              transfer(b,[0_int8],size(b)*storage_size(b)/8))
  end function
  subroutine close_outputs(expected,actual,label)
    real,intent(in)::expected(:),actual(:)
    character(*),intent(in)::label
    if(any(abs(actual-expected)>3.e-6*max(1.,abs(expected)))) then
      print *, label,maxval(abs(actual-expected));error stop 'optical population equivalence'
    end if
  end subroutine
  subroutine optical_moment_and_allocation_proof()
    type(ty_cloud_optics_rrtmgp)::clw,csw
    type(ty_optical_props_1scl)::lw1,lw2,lwm
    type(ty_optical_props_2str)::sw1,sw2,swm,wrong
    real(wp)::ql(1,1),qi(1,1),rl(1,1),di(1,1)
    real(wp),allocatable::tau(:,:,:),scatter(:,:,:),moment(:,:,:)
    call load_cld_lutcoeff(clw,trim(data)//'/rrtmgp-clouds-lw-bnd.nc')
    call load_cld_lutcoeff(csw,trim(data)//'/rrtmgp-clouds-sw-bnd.nc')
    if(clw%get_ngpt()/=clw%get_nband().or.csw%get_ngpt()/=csw%get_nband()) error stop 'cloud descriptor not band based'
    call check(lw1%init(clw));call check(lw2%init(clw));call check(lwm%init(clw))
    call check(lw1%alloc_1scl(1,1));call check(lw2%alloc_1scl(1,1));call check(lwm%alloc_1scl(1,1))
    call check(sw1%init(csw));call check(sw2%init(csw));call check(swm%init(csw));call check(wrong%init(csw))
    call check(sw1%alloc_2str(1,1));call check(sw2%alloc_2str(1,1));call check(swm%alloc_2str(1,1));call check(wrong%alloc_2str(1,1))
    ql=50.;qi=0.;rl=8.;di=20.
    call check(clw%cloud_optics(ql,qi,rl,di,lw1));call check(csw%cloud_optics(ql,qi,rl,di,sw1))
    ql=0.;qi=80.;rl=14.;di=110.
    call check(clw%cloud_optics(ql,qi,rl,di,lw2));call check(csw%cloud_optics(ql,qi,rl,di,sw2))
    lwm%tau=lw1%tau;tau=lw1%tau+lw2%tau;call check(lw2%increment(lwm))
    call moment_close(lwm%tau,tau,'LW absorption sum')
    tau=sw1%tau+sw2%tau;scatter=sw1%tau*sw1%ssa+sw2%tau*sw2%ssa
    moment=sw1%tau*sw1%ssa*sw1%g+sw2%tau*sw2%ssa*sw2%g
    swm%tau=sw1%tau;swm%ssa=sw1%ssa;swm%g=sw1%g;call check(sw2%increment(swm))
    call moment_close(swm%tau,tau,'SW extinction')
    call moment_close(swm%tau*swm%ssa,scatter,'SW scattering')
    call moment_close(swm%tau*swm%ssa*swm%g,moment,'SW asymmetry moment')
    call check(swm%delta_scale());call check(sw1%delta_scale());call check(sw2%delta_scale())
    wrong%tau=sw1%tau;wrong%ssa=sw1%ssa;wrong%g=sw1%g;call check(sw2%increment(wrong))
    if(maxval(abs(wrong%tau-swm%tau))<=100*epsilon(1._wp)) error stop 'fixture cannot detect separate-before-mix delta scaling'
    print *, 'actual cloud optical allocation extents LW/SW=',shape(lwm%tau),shape(swm%tau)
  end subroutine
  subroutine moment_close(actual,expected,label)
    real(wp),intent(in)::actual(:,:,:),expected(:,:,:)
    character(*),intent(in)::label
    if(any(abs(actual-expected)>100*epsilon(1._wp)*max(1._wp,abs(expected)))) then
      print *, label;error stop 'optical conserved moment mismatch'
    end if
  end subroutine
  subroutine check(message)
    character(*),intent(in)::message
    if(len_trim(message)>0) then
      print *,message;error stop 'vendor optical call failure'
    end if
  end subroutine
end program
