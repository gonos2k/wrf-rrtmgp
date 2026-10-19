! Standalone diagnostic only. Never compiled into normal WRF/RRTMGP.
module endpoint_optics
  use mo_rte_kind, only: wp
  use mo_optical_props, only: ty_optical_props_1scl,ty_optical_props_2str
  use module_ra_rrtmgp_trace, only: trace_result
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  private
  public :: endpoint_load,endpoint_lw,endpoint_sw
  integer,allocatable :: selected(:)
  real(wp),allocatable :: coef(:,:,:) ! layer,band,[ext,sca,abs,sca*g], m2/g
  character(2) :: phase
contains
  subroutine endpoint_load(file)
    character(*),intent(in)::file
    integer::u,nl,nb,k,b
    open(newunit=u,file=file,status='old')
    read(u,*) phase,nl,nb
    allocate(selected(nl),coef(nl,nb,4));read(u,*)selected
    if(any(selected<0).or.any(selected>1))error stop 'INVALID_SELECTION'
    do b=1,nb
      do k=1,nl
        read(u,*)coef(k,b,:)
      enddo
    enddo
    close(u)
    if(any(.not.ieee_is_finite(coef)).or.any(coef<0))error stop 'INVALID_MOMENTS'
    if(any(abs(coef(:,:,1)-coef(:,:,2)-coef(:,:,3))>1.e-10_wp))error stop 'EXT_SCA_ABS'
    if(any(coef(:,:,4)>coef(:,:,2)))error stop 'INVALID_ASYMMETRY'
  end subroutine
  subroutine endpoint_lw(path,iwp,clouds,label)
    character(*),intent(in)::label
    real(wp),intent(in)::path(:,:),iwp(:,:)
    type(ty_optical_props_1scl),intent(inout)::clouds
    integer::k,b
    if(phase/='LW'.or.size(path,1)/=1.or.size(path,2)/=size(selected))error stop 'LW_SHAPE'
    do k=1,size(selected)
      if(selected(k)==0.or.path(1,k)==0._wp)cycle
      if(iwp(1,k)/=0._wp)error stop 'SELECTED_ICE_UNSUPPORTED'
      do b=1,size(coef,2)
        clouds%tau(1,k,b)=path(1,k)*coef(k,b,3)
      enddo
    enddo
    call trace_result('LW','ENDPOINT_'//label//'_RAW_LIQUID_ABS_TAU',clouds%tau)
  end subroutine
  subroutine endpoint_sw(path,iwp,clouds,label)
    character(*),intent(in)::label
    real(wp),intent(in)::path(:,:),iwp(:,:)
    type(ty_optical_props_2str),intent(inout)::clouds
    integer::k,b
    if(phase/='SW'.or.size(path,1)/=1.or.size(path,2)/=size(selected))error stop 'SW_SHAPE'
    do k=1,size(selected)
      if(selected(k)==0.or.path(1,k)==0._wp)cycle
      if(iwp(1,k)/=0._wp)error stop 'SELECTED_ICE_UNSUPPORTED'
      do b=1,size(coef,2)
        if(coef(k,b,1)<=0._wp.or.coef(k,b,2)<=0._wp)error stop 'INVALID_SW_COEFFICIENT'
        clouds%tau(1,k,b)=path(1,k)*coef(k,b,1)
        clouds%ssa(1,k,b)=coef(k,b,2)/coef(k,b,1)
        clouds%g(1,k,b)=coef(k,b,4)/coef(k,b,2)
      enddo
    enddo
    call trace_result('SW','ENDPOINT_'//label//'_RAW_LIQUID_EXT_TAU',clouds%tau)
    call trace_result('SW','ENDPOINT_'//label//'_RAW_LIQUID_SSA',clouds%ssa)
    call trace_result('SW','ENDPOINT_'//label//'_RAW_LIQUID_G',clouds%g)
  end subroutine
end module
