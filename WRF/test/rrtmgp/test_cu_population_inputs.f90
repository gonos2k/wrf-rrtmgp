program test_cu_population_inputs
  use, intrinsic :: iso_fortran_env, only: int64, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan
  use module_ra_rrtmgp_input, only: rrtmgp_build_cu_inputs,rrtmgp_summarize_cu_filter,rrtmgp_build_udm_inputs
  implicit none
  integer, parameter :: n=3
  real :: cf(n),cu_cf(n),cu_dp(n),cu_sh(n),qc(n),qi(n),mass(n)
  real :: grid(n,2),radiation(n,2),rejected(n,2),omitted(n,2),wrong(n,1),before(n,2)
  real :: native_qc(n),native_qi(n),zero(n),dp(n),radius(n),native_grid(n,6),native_rad(n,6),sizes(n,3)
  real :: limits(6),clipped(n,6),correction(n,6)
  real(real64) :: rejected_sum(2),rejected_max(2),accepted_sum(2)
  integer(int64) :: source_count(2),active_count(2)
  integer :: reason
  character(40) :: mode
  character(256) :: errmsg
  call get_command_argument(1,mode)
  cf=[.5,.5,0.];cu_dp=[.25,0.,0.];cu_sh=[0.,.25,0.];cu_cf=cu_dp+cu_sh
  qc=[.001,-.002,-.003];qi=[-.004,.005,-.006];mass=[2.,4.,1.]
  zero=0.;dp=10.;radius=30.;native_qc=0.;native_qi=[0.,.002,0.]
  limits=1.e-12
  select case(trim(mode))
  case('cf_below_cu');cf(1)=.125
  case('cf_zero');cf(1)=0.
  case('cf_sum');cu_cf(1)=.5
  case('negative_fraction');cu_dp(1)=-.25;cu_cf=cu_dp+cu_sh
  case('cf_nan');cu_sh(1)=ieee_value(0.,ieee_quiet_nan)
  case('q_nan');qi(1)=ieee_value(0.,ieee_quiet_nan)
  case('mass_zero');mass(1)=0.
  case('overflow');qi(1)=huge(0.);mass(1)=huge(0.)
  case('native_masked');native_qi(1)=-.001;qi(1)=.01
  case('native_tiny');native_qi(1)=-.5e-12
  case('shape')
    call rrtmgp_build_cu_inputs(cf,cu_cf,cu_dp,cu_sh,qc,qi,mass,wrong,radiation,rejected,omitted,reason)
    error stop 'invalid output shape accepted'
  case('','success')
  case default;error stop 'unknown CU input test'
  end select
  ! Exercise the existing native contract before diagnosed CU can conceal it.
  if(trim(mode)=='success'.or.trim(mode)==''.or.index(trim(mode),'native_')==1) then
  call rrtmgp_build_udm_inputs(dp,cf,native_qc,zero,native_qi,zero,zero,zero, &
       radius,radius,radius,9.80665,native_grid,native_rad,sizes,reason,errmsg, &
       negative_q_limits=limits,clipped_negative_q=clipped,negative_grid_correction=correction, &
       dry_layer_mass_kg_m2=mass,allow_clear_condensate=.true.)
  end if
  if(trim(mode)=='native_masked') error stop 'positive CU concealed invalid native ice'
  if(trim(mode)=='native_tiny') then
    if(clipped(1,2)/=native_qi(1).or.native_grid(1,2)/=0.) error stop 'native correction contract changed'
    if(correction(1,2)/=real(-real(native_qi(1),real64)*real(mass(1),real64)*1000._real64)) &
      error stop 'native correction mass accounting changed'
  end if
  before(:,1)=qc;before(:,2)=qi
  call rrtmgp_build_cu_inputs(cf,cu_cf,cu_dp,cu_sh,qc,qi,mass,grid,radiation,rejected,omitted,reason)
  if(trim(mode)/='success'.and.trim(mode)/=''.and.trim(mode)/='native_tiny') error stop 'invalid CU input accepted'
  if(reason/=0) error stop 'valid CU builder status'
  if(any(qc/=before(:,1)).or.any(qi/=before(:,2))) error stop 'stored diagnosed condensate modified'
  if(grid(1,2)/=0..or.grid(2,1)/=0..or.any(grid(3,:)/=0.)) error stop 'negative diagnosed mass entered accepted paths'
  if(grid(1,1)/=real(real(qc(1),real64)*500._real64)) error stop 'liquid dry-grid path wrong'
  if(grid(2,2)/=real(real(qi(2),real64)*1000._real64)) error stop 'ice dry-grid path wrong'
  if(rejected(1,2)/=real(-real(qi(1),real64)*500._real64)) error stop 'ice rejected path wrong'
  if(rejected(2,1)/=real(-real(qc(2),real64)*1000._real64)) error stop 'liquid rejected path wrong'
  if(any(rejected(3,:)/=0.).or.any(omitted/=0.)) error stop 'inactive CU introduced grid path'
  if(any(radiation(1:2,:)/=grid(1:2,:)/.5)) error stop 'combined-CF conversion changed'
  if(native_grid(2,2)/=real(real(native_qi(2),real64)*4000._real64)) error stop 'native ice removed by diagnosed CU'
  call rrtmgp_summarize_cu_filter(qc,qi,cu_cf,grid,rejected,source_count,active_count, &
                                 rejected_sum,rejected_max,accepted_sum)
  if(any(source_count/=[2_int64,2_int64]).or.any(active_count/=[1_int64,1_int64])) error stop 'CU negative counts wrong'
  if(any(rejected_sum/=sum(real(rejected,real64),dim=1))) error stop 'CU rejected sum wrong'
  if(any(rejected_max/=maxval(real(rejected,real64),dim=1))) error stop 'CU rejected maximum wrong'
  if(any(accepted_sum/=sum(real(grid,real64),dim=1))) error stop 'CU accepted sum wrong'
  print *, 'CU population input policy PASS: ',trim(mode)
end program
