program test_host_bridge
  use iso_fortran_env,only:real32,real64
  use ieee_arithmetic,only:ieee_value,ieee_quiet_nan
  use omp_lib,only:omp_get_num_threads
  use mo_rte_kind,only:wp,wl
  use rrtmgp37_sw_dispatch,only:direct_beam_checked
  use rrtmgp37_host_bridge
  implicit none
  real(real32) :: f32(-2:3,0:4,4:7),o32(-2:3,0:4,4:7)
  real(real64) :: f64(-2:3,0:4,4:7),o64(-2:3,0:4,4:7)
  real(real64),allocatable :: packed(:,:),packed2(:,:),cd(:,:),vmr(:,:)
  real(real64) :: mass(2,3),q(2,3),mu(2),pu(2,3),pl(2,4),tl(2,3),te(2,4),ts(2)
  real(real64) :: lu(2,4),ld(2,4),su(2,4),sd(2,4),di(2,4),cap(2,3),ex(2,3)
  real(real64) :: residual(128),sig,expected,nanv
  real(wp) :: tau(2,3,2),muk(2,3),inc(2,2),fb(2,4,2)
  type(radiation_result),allocatable :: result
  integer,allocatable :: day(:)
  integer :: i,j,k,c,ncheck=0,ierr,team
  character(512) :: msg
  nanv=ieee_value(0.0_real64,ieee_quiet_nan)
  do j=4,7
    do k=0,4
      do i=-2,3
        f64(i,k,j)=real(i+10*k+100*j,real64)
      end do
    end do
  end do
  f32=real(f64,real32)
  call pack_ikj(f32,-2,3,0,4,4,7,-1,2,1,3,5,6,packed,msg)
  call check(msg==''.and.all(shape(packed)==[8,3]),'real32 packing with non-unit lower bounds')
  call pack_ikj(f64,-2,3,0,4,4,7,-1,2,1,3,5,6,packed2,msg)
  call check(msg==''.and.all(packed2==packed),'real64 same column mapping')
  c=0
  do j=5,6
    do i=-1,2
      c=c+1
      do k=1,3
        call check(packed(c,k)==f64(i,k,j),'ikj to column/layer index')
      end do
    end do
  end do
  o32=-999;o64=-999
  call unpack_ikj(packed,o32,-2,3,0,4,4,7,-1,2,1,3,5,6,msg)
  call check(msg=='','unpack real32')
  call unpack_ikj(packed,o64,-2,3,0,4,4,7,-1,2,1,3,5,6,msg)
  call check(msg=='','unpack real64')
  do j=4,7
    do k=0,4
      do i=-2,3
        expected=-999.0_real64
        if(i>=-1.and.i<=2.and.k>=1.and.k<=3.and.j>=5.and.j<=6) expected=f64(i,k,j)
        call check(real(o32(i,k,j),real64)==expected.and.o64(i,k,j)==expected,'only tile changed, halo preserved')
      end do
    end do
  end do
  sig=sum(packed)
  call pack_ikj(f64,-2,3,0,4,4,7,-3,2,1,3,5,6,packed,msg)
  call check(msg/=''.and.sum(packed)==sig,'bad tile rejected atomically')
  f64(0,1,5)=nanv
  call pack_ikj(f64,-2,3,0,4,4,7,-1,2,1,3,5,6,packed,msg)
  call check(msg/=''.and.sum(packed)==sig,'NaN tile rejected atomically')
  sig=sum(o32);packed(1,1)=huge(0.0_real64)
  call unpack_ikj(packed,o32,-2,3,0,4,4,7,-1,2,1,3,5,6,msg)
  call check(msg/=''.and.sum(o32)==sig,'real32 conversion overflow refused before write')
  mass=100._real64;q=0.01_real64
  call mass_to_dry_columns(mass,0.028964_real64,cd,msg)
  expected=100._real64/0.028964_real64*6.02214076e23_real64/1.e4_real64
  call check(msg==''.and.maxval(abs(cd/expected-1))<1.e-14_real64,'dry molecule per cm2 conversion')
  call mass_mixing_to_vmr(q,0.028964_real64,0.018016_real64,vmr,msg)
  call check(msg==''.and.maxval(abs(vmr-0.01_real64*0.028964_real64/0.018016_real64))<1.e-15_real64,'dry molar ratio, not specific humidity')
  sig=sum(cd);mass(1,1)=-1
  call mass_to_dry_columns(mass,0.028964_real64,cd,msg)
  call check(msg/=''.and.sum(cd)==sig,'negative dry mass rejected atomically')
  mass=huge(1.0_real64)
  call mass_to_dry_columns(mass,0.028964_real64,cd,msg)
  call check(msg/=''.and.sum(cd)==sig,'molecule count overflow rejected')
  sig=sum(vmr);q(1,1)=-1
  call mass_mixing_to_vmr(q,0.028964_real64,0.018016_real64,vmr,msg)
  call check(msg/=''.and.sum(vmr)==sig,'negative mass mixing rejected')
  mu=[0.6_real64,0.0_real64]
  call daylight_indices(mu,day,msg)
  call check(msg==''.and.size(day)==1.and.day(1)==1,'daylight packing horizon zero')
  mu=-0.5
  call daylight_indices(mu,day,msg)
  call check(msg==''.and.size(day)==0,'all-night empty list')
  mu(1)=1.1
  call daylight_indices(mu,day,msg)
  call check(msg/=''.and.size(day)==0,'invalid cosine leaves list unchanged')
  pl(1,:)=[100000.,70000.,40000.,10000.];pl(2,:)=pl(1,:)
  pu=0.5_real64*(pl(:,1:3)+pl(:,2:4));tl=270;te=270;ts=280
  call check_column_state(pu,pl,tl,te,ts,cd,msg)
  call check(msg=='','bottom-first native levels accepted')
  call check_column_state(pu,pl(:,4:1:-1),tl,te,ts,cd,msg)
  call check(msg/='','reversed pressure rejected at host contract')
  pu(1,1)=pl(1,1)+1
  call check_column_state(pu,pl,tl,te,ts,cd,msg)
  call check(msg/='','layer pressure outside interfaces rejected')
  ! Synthetic optical depths through an actual extracted upstream direct-beam kernel.
  ! This exercises transport + host outputs, NOT gas spectroscopy or full RTE.
  tau=0.12_wp;mu=[0.6_real64,-0.2_real64]
  muk=spread(real(mu,wp),2,3);inc=500._wp;fb=-999
  call direct_beam_checked(tau,muk,inc,.false._wl,fb,ierr)
  call check(ierr==0,'extracted upstream kernel called bottom-first')
  sd=sum(real(fb,real64),dim=3);di=sd;su=0
  lu=350;ld=300;ld(:,4)=0
  cap=1.e5_real64;ex=0.9_real64
  ! Inject stale night data to prove the bridge resets it, rather than carrying it forward.
  sd(2,:)=nanv;di(2,:)=-999;su(2,:)=999
  call finish_fluxes(lu,ld,su,sd,di,mu,cap,ex,result,msg)
  if(msg/='')print *,msg
  call check(msg=='','mixed daylight/night flux finalization')
  call check(all(result%sw_dn(2,:)==0).and.all(result%qtheta_sw(2,:)==0),'night SW exactly zero')
  expected=1000._real64*mu(1)*exp(-3._real64*0.12_real64/mu(1))
  call check(abs(result%swdown(1)-expected)<1.e-11_real64,'mu0 included only once')
  call check(abs(result%swdown(1)-result%swddir(1)-result%swddif(1))<1.e-12_real64,'direct plus diffuse equals SWDOWN')
  call check(result%gsw(1)==result%swdown(1),'surface absorbed SW without albedo division')
  call check(all(result%lwdnb==ld(:,1)),'raw LW no unverified emissivity multiplication')
  do i=1,2
    expected=(lu(i,1)-ld(i,1))-(lu(i,4)-ld(i,4))
    call check(abs(sum(cap(i,:)*ex(i,:)*result%qtheta_lw(i,:))-expected)<1.e-11_real64,'LW column energy identity')
    expected=-result%sw_dn(i,1)+result%sw_dn(i,4)
    call check(abs(sum(cap(i,:)*ex(i,:)*result%qtheta_sw(i,:))-expected)<1.e-11_real64,'SW column energy identity')
  end do
  sig=sum(result%qtheta_total);di(1,:)=sd(1,:)+5
  call finish_fluxes(lu,ld,su,sd,di,mu,cap,ex,result,msg)
  call check(msg/=''.and.sum(result%qtheta_total)==sig,'unphysical direct/total preserves result')
  di(1,:)=sd(1,:);cap(1,1)=0
  call finish_fluxes(lu,ld,su,sd,di,mu,cap,ex,result,msg)
  call check(msg/=''.and.sum(result%qtheta_total)==sig,'zero heat capacity preserves result')
  ! Independent tile results: no hidden SAVE work arrays.
  team=0
  !$omp parallel default(none) shared(team,residual) private(i)
  !$omp single
  team=omp_get_num_threads()
  !$omp end single
  !$omp do
  do i=1,128
    call parallel_case(i,residual(i))
  end do
  !$omp end do
  !$omp end parallel
  call check(team==4,'actual OpenMP team size four')
  call check(maxval(abs(residual))<1.e-10_real64,'128 independent bridge evaluations conserve energy')
  print '(a,i0)','HOST_BRIDGE_ASSERTIONS_PASS=',ncheck
  print '(a,i0,a,i0)','OPENMP_THREADS=',team,' INDEPENDENT_CALLS=',size(residual)
  print '(a)','SCOPE=HOST_ADAPTERS_AND_EXTRACTED_DIRECT_BEAM_NOT_FULL_WRF_OR_RRTMGP'
contains
  subroutine check(ok,label)
    logical,intent(in)::ok
    character(*),intent(in)::label
    if(.not.ok)then
      print *, 'FAIL: ',label
      error stop 1
    end if
    ncheck=ncheck+1
  end subroutine
  subroutine parallel_case(i,res)
    integer,intent(in)::i
    real(real64),intent(out)::res
    real(real64)::u(1,4),d(1,4),z(1,4),cp(1,3),pi(1,3),mu(1)
    type(radiation_result),allocatable::r
    character(512)::m
    u=350;d(1,:)=[300.,230.,100.,0.]+real(i,real64)*0.01_real64
    z=0;cp=1.e5_real64;pi=.9_real64;mu=-.5_real64
    call finish_fluxes(u,d,z,z,z,mu,cp,pi,r,m)
    if(m/='')then
      res=huge(res);return
    end if
    res=sum(cp*pi*r%qtheta_total)-((u(1,1)-d(1,1))-(u(1,4)-d(1,4)))
  end subroutine
end program
