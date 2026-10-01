! Standalone smoke test using REAL pinned gas coefficients and SYNTHETIC columns.
! The build runner first rejects all files not matching the pinned Git blob hashes.
! This test has NOT run in the authoring environment (real core/data unavailable).
program test_real_clear_backend
  use iso_fortran_env,only:real64
  use rrtmgp37_clear_backend,only:clear_backend
  use rrtmgp37_host_bridge,only:radiation_result,mass_to_dry_columns,mass_mixing_to_vmr
  implicit none
  integer,parameter :: nc=3,nl=24,ng=8
  character(3),parameter :: names(ng)=['h2o','co2','o3 ','n2o','co ','ch4','o2 ','n2 ']
  type(clear_backend) :: backend
  type(radiation_result),allocatable :: result
  real(real64) :: pl(nc,nl+1),p(nc,nl),tl(nc,nl),te(nc,nl+1),ts(nc),q(nc,nl),mass(nc,nl)
  real(real64) :: vmr(nc,nl,ng),mu(nc),scale(nc),capacity(nc,nl),exner(nc,nl)
  real(real64),allocatable :: dry(:,:),h2o(:,:),ad(:,:),af(:,:),emis(:,:),old_up(:)
  real(real64) :: f,energy_error,sig
  integer :: k,j,nlw,nsw,ncheck=0
  character(1024) :: lwfile,swfile,msg
  if(command_argument_count()/=2)error stop 'Usage: test_real_clear_backend LW.nc SW.nc'
  call get_command_argument(1,lwfile);call get_command_argument(2,swfile)
  call backend%initialize(trim(lwfile),trim(swfile),names,msg);call good('initialize actual core')
  call backend%band_counts(nlw,nsw,msg);call good('band counts')
  call check(nlw==16.and.nsw==14,'expected band counts')
  allocate(ad(nsw,nc),af(nsw,nc),emis(nlw,nc));ad=.12_real64;af=.14_real64;emis=.98_real64
  do k=1,nl+1
    f=real(k-1,real64)/real(nl,real64)
    pl(:,k)=100000.0_real64*exp(log(0.0001_real64)*f)
    te(:,k)=288.0_real64-60.0_real64*min(1.0_real64,2.0_real64*f)
  end do
  p=0.5_real64*(pl(:,:nl)+pl(:,2:));tl=0.5_real64*(te(:,:nl)+te(:,2:));ts=290.0_real64
  q=0.01_real64*(p/100000.0_real64)**2
  mass=(pl(:,:nl)-pl(:,2:))/(9.80665_real64*(1.0_real64+q))
  call mass_to_dry_columns(mass,0.028964_real64,dry,msg);call good('explicit dry columns')
  call mass_mixing_to_vmr(q,0.028964_real64,0.018016_real64,h2o,msg);call good('dry VMR')
  vmr(:,:,1)=h2o;vmr(:,:,2)=400.e-6_real64
  vmr(:,:,3)=5.e-8_real64+6.e-6_real64*exp(-(log(p/5000.0_real64))**2)
  vmr(:,:,4)=320.e-9_real64;vmr(:,:,5)=100.e-9_real64;vmr(:,:,6)=1800.e-9_real64
  vmr(:,:,7)=.2095_real64;vmr(:,:,8)=.7808_real64
  capacity=mass*(1004.64_real64+q*1850.0_real64)
  exner=(p/100000.0_real64)**(287.0_real64/1004.64_real64)
  mu=[.65_real64,0.0_real64,-.2_real64];scale=1.0_real64
  call run_column(.true.,.true.,.true.);call good('actual clear-sky LW+SW')
  call check(result%swdown(1)>0.0_real64,'daylight flux positive')
  call check(all(result%sw_dn(2:,:)==0.0_real64),'night/horizon shortwave exactly zero')
  call check(all(result%swdown==result%swddir+result%swddif),'SW direct plus diffuse')
  energy_error=0
  do j=1,nc
    f=result%lw_up(j,1)-result%lw_dn(j,1)-result%lw_up(j,nl+1)+result%lw_dn(j,nl+1)
    energy_error=max(energy_error,abs(sum(capacity(j,:)*exner(j,:)*result%qtheta_lw(j,:))-f))
    f=result%sw_up(j,1)-result%sw_dn(j,1)-result%sw_up(j,nl+1)+result%sw_dn(j,nl+1)
    energy_error=max(energy_error,abs(sum(capacity(j,:)*exner(j,:)*result%qtheta_sw(j,:))-f))
  end do
  call check(energy_error<1.e-8_real64,'column energy identity')
  print '(a,es24.15)','COLUMN_ENERGY_RESIDUAL_W_M2=',energy_error
  print '(a,3es24.15)','BASELINE_SWDOWN=',result%swdown
  print '(a,3es24.15)','BASELINE_LWDNB=',result%lwdnb
  old_up=result%lw_up(:,nl+1);vmr(:,:,2)=800.e-6_real64
  call run_column(.true.,.true.,.true.);call good('CO2 perturbation')
  call check(maxval(abs(result%lw_up(:,nl+1)-old_up))>1.e-6_real64,'CO2 sensitivity is nonzero')
  scale=0.0_real64
  call run_column(.true.,.true.,.true.);call good('zero source')
  call check(maxval(abs(result%sw_dn))<1.e-10_real64,'zero source removes SW')
  sig=sum(result%qtheta_total)
  call run_column(.false.,.true.,.true.)
  call check(msg/=''.and.sum(result%qtheta_total)==sig,'unsupported cloud state rejected atomically')
  call run_column(.true.,.false.,.true.)
  call check(msg/=''.and.sum(result%qtheta_total)==sig,'unsupported aerosol rejected atomically')
  call run_column(.true.,.true.,.false.)
  call check(msg/=''.and.sum(result%qtheta_total)==sig,'truncated/unaudited top boundary rejected')
  call backend%close()
  print '(a,i0)','REAL_CORE_SYNTHETIC_COLUMN_ASSERTIONS_PASS=',ncheck
  print '(a)','SCOPE=REAL_COEFFICIENT_CLEAR_SKY_SMOKE_NOT_WRF_INTEGRATION_OR_FORECAST_VALIDATION'
contains
  subroutine run_column(cld,aer,toa)
    logical,intent(in)::cld,aer,toa
    call backend%step(p,pl,tl,te,ts,dry,vmr,mu,scale,ad,af,emis,capacity,exner,cld,aer,toa,result,msg)
  end subroutine
  subroutine good(label)
    character(*),intent(in)::label
    if(msg/='')then
      print *,trim(label),': ',trim(msg)
      error stop 1
    end if
    ncheck=ncheck+1
  end subroutine
  subroutine check(ok,label)
    logical,intent(in)::ok
    character(*),intent(in)::label
    if(.not.ok)then
      print *, 'FAIL: ',label
      error stop 1
    end if
    ncheck=ncheck+1
  end subroutine
end program
