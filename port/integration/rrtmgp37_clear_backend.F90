! Candidate CPU/DP clear-sky backend against pinned 41c5fcd... public interfaces.
! NOT connected to the WRF radiation driver. WRF's stage-2 runtime guards remain.
! Initialization is serialized. Per-call optical/source/flux workspaces are local.
module rrtmgp37_clear_backend
  use iso_fortran_env,only:real64
  use ieee_arithmetic,only:ieee_is_finite
  use mo_rte_kind,only:wp,wl
  use mo_gas_concentrations,only:ty_gas_concs
  use mo_gas_optics_rrtmgp,only:ty_gas_optics_rrtmgp
  use mo_optical_props,only:ty_optical_props_1scl,ty_optical_props_2str
  use mo_source_functions,only:ty_source_func_lw
  use mo_fluxes,only:ty_fluxes_broadband
  use mo_rte_sw,only:rte_sw
  use mo_rte_lw,only:rte_lw
  use rrtmgp37_core_loader,only:load_core_coefficients
  use rrtmgp37_host_bridge,only:radiation_result,check_column_state,daylight_indices,finish_fluxes
  implicit none
  private
  public :: clear_backend
  type :: clear_backend
    private
    type(ty_gas_optics_rrtmgp) :: lw,sw
    character(32),allocatable :: names(:)
    logical :: ready=.false.,attempted=.false.
  contains
    procedure :: initialize
    procedure :: band_counts
    procedure :: step
    procedure :: close
  end type
contains
  subroutine initialize(self,lw_file,sw_file,names,msg)
    class(clear_backend),intent(inout) :: self
    character(*),intent(in) :: lw_file,sw_file,names(:)
    character(*),intent(out) :: msg
    type(ty_gas_concs) :: available
    msg='CORE_BACKEND_INITIALIZE_ONCE'
    ! No unsafe partial reinitialization or shallow copies of owning core objects.
    if(self%attempted) return
    self%attempted=.true.;self%ready=.false.
    if(wp/=real64) then
      msg='CORE_BACKEND_REQUIRES_DP';return
    end if
    if(any(len_trim(names)>32).or.size(names)<1) then
      msg='CORE_BACKEND_GAS_NAMES';return
    end if
    msg=available%init(names)
    if(msg/='') return
    self%names=names
    call load_core_coefficients(lw_file,available,self%lw,.true.,msg)
    if(msg/='') return
    call load_core_coefficients(sw_file,available,self%sw,.false.,msg)
    if(msg/='') return
    self%ready=.true.
  end subroutine
  subroutine band_counts(self,nlw,nsw,msg)
    class(clear_backend),intent(in) :: self
    integer,intent(out) :: nlw,nsw
    character(*),intent(out) :: msg
    nlw=0;nsw=0;msg='CORE_BACKEND_NOT_READY'
    if(.not.self%ready) return
    nlw=self%lw%get_nband();nsw=self%sw%get_nband();msg=''
  end subroutine
  subroutine step(self,play,plev,tlay,tlev,tsfc,col_dry,vmr,mu0,solar_scale, &
                  alb_dir,alb_dif,emis,capacity,exner,cloud_free,aerosol_free,toa_boundary_confirmed,result,msg)
    class(clear_backend),intent(in) :: self
    real(real64),intent(in) :: play(:,:),plev(:,:),tlay(:,:),tlev(:,:),tsfc(:),col_dry(:,:)
    real(real64),intent(in) :: vmr(:,:,:),mu0(:),solar_scale(:)
    real(real64),intent(in) :: alb_dir(:,:),alb_dif(:,:),emis(:,:),capacity(:,:),exner(:,:)
    logical,intent(in) :: cloud_free,aerosol_free,toa_boundary_confirmed
    type(radiation_result),allocatable,intent(inout) :: result
    character(*),intent(out) :: msg
    type(ty_gas_concs) :: allgas,daygas
    type(ty_optical_props_1scl) :: olw
    type(ty_optical_props_2str) :: osw
    type(ty_source_func_lw) :: sources
    type(ty_fluxes_broadband) :: flux
    real(wp),allocatable,target :: lu(:,:),ld(:,:),su(:,:),sd(:,:),di(:,:)
    real(wp),allocatable,target :: su_day(:,:),sd_day(:,:),di_day(:,:)
    real(wp),allocatable :: toa(:,:)
    integer,allocatable :: day(:)
    integer :: nc,nl,ngas,nd,j
    msg='CORE_BACKEND_NOT_READY'
    if(.not.self%ready) return
    msg='CORE_BACKEND_CLEAR_SKY_NO_AEROSOL_ONLY'
    if(.not.cloud_free.or..not.aerosol_free) return
    msg='CORE_BACKEND_TOA_BOUNDARY_NOT_CONFIRMED'
    ! A truncated WRF model top is not automatically a top-of-atmosphere boundary.
    if(.not.toa_boundary_confirmed) return
    call check_column_state(play,plev,tlay,tlev,tsfc,col_dry,msg)
    if(msg/='') return
    nc=size(play,1);nl=size(play,2);ngas=size(self%names)
    msg='CORE_BACKEND_EXTENTS'
    if(any(shape(vmr)/=[nc,nl,ngas])) return
    if(size(mu0)/=nc.or.size(solar_scale)/=nc) return
    if(any(shape(alb_dir)/=[self%sw%get_nband(),nc])) return
    if(any(shape(alb_dif)/=shape(alb_dir)).or.any(shape(emis)/=[self%lw%get_nband(),nc])) return
    if(any(shape(capacity)/=[nc,nl]).or.any(shape(exner)/=[nc,nl])) return
    msg='CORE_BACKEND_NONFINITE_OR_RANGE'
    if(.not.all(ieee_is_finite(vmr))) return
    if(any(vmr<0.0_real64)) return
    if(.not.all(ieee_is_finite(solar_scale))) return
    if(any(solar_scale<0.0_real64)) return
    if(.not.all(ieee_is_finite(alb_dir)).or..not.all(ieee_is_finite(alb_dif))) return
    if(.not.all(ieee_is_finite(emis))) return
    if(any(alb_dir<0.0_real64).or.any(alb_dir>1.0_real64)) return
    if(any(alb_dif<0.0_real64).or.any(alb_dif>1.0_real64)) return
    if(any(emis<0.0_real64).or.any(emis>1.0_real64)) return
    call daylight_indices(mu0,day,msg)
    if(msg/='') return
    msg=allgas%init(self%names)
    if(msg/='') return
    do j=1,ngas
      msg=allgas%set_vmr(self%names(j),vmr(:,:,j))
      if(msg/='') return
    end do
    allocate(lu(nc,nl+1),ld(nc,nl+1),su(nc,nl+1),sd(nc,nl+1),di(nc,nl+1))
    su=0;sd=0;di=0
    msg=olw%alloc_1scl(nc,nl,self%lw)
    if(msg/='') return
    msg=sources%alloc(nc,nl,self%lw)
    if(msg/='') return
    msg=self%lw%gas_optics(play,plev,tlay,tsfc,allgas,olw,sources,col_dry=col_dry,tlev=tlev)
    if(msg/='') return
    flux%flux_up=>lu;flux%flux_dn=>ld
    msg=rte_lw(olw,.false._wl,sources,emis,flux)
    if(msg/='') return
    nd=size(day)
    if(nd>0) then
      msg=daygas%init(self%names)
      if(msg/='') return
      do j=1,ngas
        msg=daygas%set_vmr(self%names(j),vmr(day,:,j))
        if(msg/='') return
      end do
      msg=osw%alloc_2str(nd,nl,self%sw)
      if(msg/='') return
      allocate(toa(nd,self%sw%get_ngpt()))
      allocate(su_day(nd,nl+1),sd_day(nd,nl+1),di_day(nd,nl+1))
      msg=self%sw%gas_optics(play(day,:),plev(day,:),tlay(day,:),daygas,osw,toa,col_dry=col_dry(day,:))
      if(msg/='') return
      do j=1,nd
        if(solar_scale(day(j))>1.0_real64) then
          if(any(abs(toa(j,:))>huge(1.0_wp)/solar_scale(day(j)))) then
            msg='CORE_SOLAR_SCALE_OVERFLOW';return
          end if
        end if
        toa(j,:)=toa(j,:)*solar_scale(day(j)) ! no extra mu0 or quadrature weight
      end do
      flux%flux_up=>su_day;flux%flux_dn=>sd_day;flux%flux_dn_dir=>di_day
      msg=rte_sw(osw,.false._wl,mu0(day),toa,alb_dir(:,day),alb_dif(:,day),flux)
      if(msg/='') return
      su(day,:)=su_day;sd(day,:)=sd_day;di(day,:)=di_day
    end if
    nullify(flux%flux_up,flux%flux_dn,flux%flux_dn_dir)
    call finish_fluxes(lu,ld,su,sd,di,mu0,capacity,exner,result,msg)
  end subroutine
  subroutine close(self)
    class(clear_backend),intent(inout) :: self
    ! Must be called only when no tile evaluation is in progress.
    ! Core finalize follows the upstream object's explicit lifetime convention.
    call self%lw%finalize()
    call self%sw%finalize()
    if(allocated(self%names)) deallocate(self%names)
    self%ready=.false.
    ! attempted deliberately remains true: create a new object for reinitialization.
  end subroutine
end module
