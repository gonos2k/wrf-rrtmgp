program test_phase_path_stats
  use, intrinsic :: iso_fortran_env, only: int64, real64
  use mo_rte_kind, only: wp
  use module_ra_rrtmgp, only: rrtmgp_init, rrtmgp_cloud_lut_bounds, rrtmgp_ice_lut_coordinate
  use module_ra_rrtmgp_input, only: rrtmgp_summarize_path_clipping, rrtmgp_build_udm_inputs, rrtmgp_build_cu_inputs, &
       RRTMGP_INPUT_CLEAR_CONDENSATE
  implicit none
  character(len=1024) :: data_dir
  real(wp) :: lmin_lw,lmax_lw,imin_lw,imax_lw,lmin_sw,lmax_sw,imin_sw,imax_sw
  real(real64) :: coord(6),nlow_sum,nlow_max,nhigh_sum,nhigh_max,total,eps,native_total(4),native_omitted(4)
  real :: path(6),path_before(6),cf(6),cf_before(6)
  real :: dp(2),cf_build(2),qc(2),qi(2),qr(2),qs(2),qg(2),qh(2),re_cloud(2),re_ice(2),re_snow(2)
  real :: grid(2,6),incloud(2,6),sizes(2,3),omitted(2,6),dry_mass(2)
  real :: cu_cf(2),cu_dp(2),cu_sh(2),cu_qc(2),cu_qi(2)
  real :: cu_grid(2,2),cu_incloud(2,2),cu_rejected(2,2),cu_omitted(2,2),negative_limits(6),negative_correction(2,6)
  integer :: build_reason,layer_reason(2)
  character(len=256) :: errmsg
  integer(int64) :: nlow,nhigh
  real(wp) :: ice4,ice3

  call get_command_argument(1,data_dir)
  if(len_trim(data_dir)==0) error stop 'coefficient directory argument required'
  call rrtmgp_init(trim(data_dir))
  call rrtmgp_cloud_lut_bounds('LW',lmin_lw,lmax_lw,imin_lw,imax_lw)
  call rrtmgp_cloud_lut_bounds('SW',lmin_sw,lmax_sw,imin_sw,imax_sw)
  if(.not.(lmin_lw>0._wp .and. lmax_lw>lmin_lw .and. imin_lw>0._wp .and. imax_lw>imin_lw)) &
    error stop 'invalid LW LUT clipping bounds'
  if(.not.(lmin_sw>0._wp .and. lmax_sw>lmin_sw .and. imin_sw>0._wp .and. imax_sw>imin_sw)) &
    error stop 'invalid SW LUT clipping bounds'

  ! Verify that diagnostic coordinate mapping is the same adapter operation:
  ! iceflag 4 is 2*re; flag 3 retains the Fu conversion before diameter.
  ice4=rrtmgp_ice_lut_coordinate(8.0,4)
  ice3=rrtmgp_ice_lut_coordinate(8.0,3)
  if(abs(ice4-16._wp)>1.e-12_wp) error stop 'iceflag 4 coordinate mapping changed'
  if(abs(ice3-16._wp/1.0315_wp)>1.e-12_wp) error stop 'iceflag 3 coordinate mapping changed'

  ! Strictly outside values clip; exact lower/upper boundaries do not.
  ! A CF=0 positive path is excluded from both the numerator and denominator.
  eps=max(1.e-9_real64,abs(real(lmin_lw,real64))*1.e-12_real64)
  coord=[real(lmin_lw,real64)-eps,real(lmin_lw,real64), &
         (real(lmin_lw,real64)+real(lmax_lw,real64))/2._real64, &
         real(lmax_lw,real64),real(lmax_lw,real64)+eps,real(lmax_lw,real64)+2._real64*eps]
  path=[1.,2.,9.,3.,4.,5.]
  cf=[1.,1.,0.,1.,1.,1.]
  path_before=path; cf_before=cf
  call rrtmgp_summarize_path_clipping(path,cf,coord,real(lmin_lw,real64),real(lmax_lw,real64), &
       nlow,nlow_sum,nlow_max,nhigh,nhigh_sum,nhigh_max,total)
  if(nlow/=1_int64 .or. nhigh/=2_int64) error stop 'clip boundary/count contract failed'
  if(abs(nlow_sum-1._real64)>1.e-12_real64 .or. abs(nlow_max-1._real64)>1.e-12_real64) &
    error stop 'low-clipped water-path summary failed'
  if(abs(nhigh_sum-9._real64)>1.e-12_real64 .or. abs(nhigh_max-5._real64)>1.e-12_real64) &
    error stop 'high-clipped water-path summary failed'
  if(abs(total-15._real64)>1.e-12_real64) error stop 'eligible grid water path total failed'
  if(any(path/=path_before) .or. any(cf/=cf_before)) error stop 'diagnostic summary modified inputs'

  ! All-zero mass contributes neither clipping counts nor a denominator.
  path=0.; cf=1.; coord=real(lmin_lw,real64)-eps
  call rrtmgp_summarize_path_clipping(path,cf,coord,real(lmin_lw,real64),real(lmax_lw,real64), &
       nlow,nlow_sum,nlow_max,nhigh,nhigh_sum,nhigh_max,total)
  if(nlow/=0_int64 .or. nhigh/=0_int64 .or. total/=0._real64) &
    error stop 'zero-path column changed clipping statistics'

  ! Builder contract fixture: CF=0 paths are retained as per-phase omitted
  ! grid paths, and cloudy-layer paths keep the existing grid/in-cloud split.
  dp=100.; cf_build=[0.,0.5]; qc=[1.e-3,1.e-3]; qi=[2.e-3,0.]; qr=[3.e-3,0.]; qs=[4.e-3,0.]
  qg=0.; qh=0.; re_cloud=10.; re_ice=20.; re_snow=30.; dry_mass=100.
  call rrtmgp_build_udm_inputs(dp,cf_build,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,9.81, &
       grid,incloud,sizes,build_reason,errmsg,allow_clear_condensate=.true., &
       omitted_grid_path=omitted,layer_reason=layer_reason,dry_layer_mass_kg_m2=dry_mass)
  if(build_reason/=RRTMGP_INPUT_CLEAR_CONDENSATE .or. layer_reason(1)/=RRTMGP_INPUT_CLEAR_CONDENSATE) &
    error stop 'clear-condensate builder status not reported'
  if(any(abs(omitted(1,1:4)-[100.,200.,300.,400.])>1.e-4) .or. any(omitted(2,:)/=0.)) then
    write(*,'(A,6(1X,ES14.6))') 'omitted row 1:',omitted(1,:)
    write(*,'(A,6(1X,ES14.6))') 'omitted row 2:',omitted(2,:)
    error stop 'phase-resolved CF0 omitted paths changed'
  end if
  if(abs(grid(2,1)-100.)>1.e-4 .or. abs(incloud(2,1)-200.)>1.e-4) &
    error stop 'cloudy grid/in-cloud path contract changed'

  ! The CF0 denominator includes all native grid paths, including CF0;
  ! it differs from the positive-CF LUT eligible denominator above.
  native_total=sum(real(grid(:,1:4),real64),dim=1)
  native_omitted=sum(real(omitted(:,1:4),real64),dim=1)
  if(any(abs(native_total-[200._real64,200._real64,300._real64,400._real64])>1.e-4_real64)) &
    error stop 'native phase grid denominator changed'
  if(native_omitted(1)/native_total(1)/=0.5_real64 .or. &
     any(native_omitted(2:4)/native_total(2:4)/=1._real64)) &
    error stop 'native CF0 phase fraction changed'

  ! Positive uniform frozen G/H never enter the four native denominators.
  qc=0.; qi=0.; qr=0.; qs=0.; qg=1.e-3; qh=2.e-3
  call rrtmgp_build_udm_inputs(dp,cf_build,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,9.81, &
       grid,incloud,sizes,build_reason,errmsg,allow_clear_condensate=.true., &
       omitted_grid_path=omitted,dry_layer_mass_kg_m2=dry_mass,frozen_uniform=.true.)
  if(any(grid(:,5:6)<=0.) .or. any(grid(:,1:4)/=0.) .or. any(omitted(:,1:4)/=0.)) &
    error stop 'G/H leaked into native four-phase denominator'

  ! Positive diagnosed CU does not become native condensate or denominator.
  cu_cf=[0.,0.2];cu_dp=cu_cf;cu_sh=0.;cu_qc=1.e-3;cu_qi=2.e-3
  call rrtmgp_build_cu_inputs(cf_build,cu_cf,cu_dp,cu_sh,cu_qc,cu_qi,dry_mass, &
       cu_grid,cu_incloud,cu_rejected,cu_omitted,build_reason)
  if(cu_grid(2,1)<=0. .or. cu_grid(2,2)<=0. .or. any(grid(:,1:4)/=0.)) &
    error stop 'CU participation contaminated native denominator'

  ! Existing native correction is applied before grid-path accounting.
  qg=0.;qh=0.;qc=[-1.e-10,1.e-3];negative_limits=1.e-9
  call rrtmgp_build_udm_inputs(dp,cf_build,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,9.81, &
       grid,incloud,sizes,build_reason,errmsg,allow_clear_condensate=.true., &
       omitted_grid_path=omitted,dry_layer_mass_kg_m2=dry_mass,negative_q_limits=negative_limits, &
       negative_grid_correction=negative_correction)
  if(negative_correction(1,1)<=0. .or. grid(1,1)/=0. .or. any(omitted/=0.) .or. &
     abs(sum(real(grid(:,1),real64))-100._real64)>1.e-4_real64) &
    error stop 'native corrected path denominator changed'

  write(*,'(A)') 'phase path and LUT clipping statistics contract passed'
end program test_phase_path_stats
