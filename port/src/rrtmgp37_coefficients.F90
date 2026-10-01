! Non-fatal reader for the pinned legacy-Make-layout RRTMGP coefficient schema.
! This is file IO + schema validation, not a gas-optics calculation.
! Source schema: NCAR/rte-rrtmgp@41c5fcd... examples/mo_load_coefficients.F90.
module rrtmgp37_coefficients
  use iso_fortran_env, only: real64,int64
  use rrtmgp37_netcdf, only: nc_info,nc_read,nc_names
  implicit none
  private
  public :: coefficient_table, read_coefficients
  type :: coefficient_table
    logical :: is_lw=.false.
    real(real64),allocatable :: band_lims(:,:)
    real(real64),allocatable :: press_ref(:)
    real(real64),allocatable :: temp_ref(:)
    real(real64),allocatable :: vmr_ref(:,:,:)
    real(real64),allocatable :: kmajor(:,:,:,:)
    real(real64),allocatable :: kminor_lower(:,:,:)
    real(real64),allocatable :: kminor_upper(:,:,:)
    real(real64),allocatable :: totplnk(:,:)
    real(real64),allocatable :: planck_frac(:,:,:,:)
    real(real64),allocatable :: optimal_angle_fit(:,:)
    real(real64),allocatable :: solar_quiet(:)
    real(real64),allocatable :: solar_facular(:)
    real(real64),allocatable :: solar_sunspot(:)
    real(real64),allocatable :: rayl_lower(:,:,:)
    real(real64),allocatable :: rayl_upper(:,:,:)
    integer,allocatable :: key_species(:,:,:)
    integer,allocatable :: band2gpt(:,:)
    integer,allocatable :: minor_limits_gpt_lower(:,:)
    integer,allocatable :: minor_limits_gpt_upper(:,:)
    integer,allocatable :: kminor_start_lower(:)
    integer,allocatable :: kminor_start_upper(:)
    integer,allocatable :: density_lower(:)
    integer,allocatable :: density_upper(:)
    integer,allocatable :: complement_lower(:)
    integer,allocatable :: complement_upper(:)
    character(32),allocatable :: gas_names(:)
    character(32),allocatable :: gas_minor(:)
    character(32),allocatable :: identifier_minor(:)
    character(32),allocatable :: minor_gases_lower(:)
    character(32),allocatable :: minor_gases_upper(:)
    character(32),allocatable :: scaling_gas_lower(:)
    character(32),allocatable :: scaling_gas_upper(:)
    real(real64) :: press_ref_trop=0.0_real64
    real(real64) :: ref_p=0.0_real64
    real(real64) :: ref_t=0.0_real64
    real(real64) :: tsi_default=0.0_real64
    real(real64) :: mg_default=0.0_real64
    real(real64) :: sb_default=0.0_real64
  end type
contains
  subroutine read_coefficients(path,table,msg)
    character(*),intent(in) :: path
    type(coefficient_table),allocatable,intent(inout) :: table
    character(*),intent(out) :: msg
    type(coefficient_table),allocatable :: tmp
    integer :: rank,xtype,astat
    integer(int64) :: dims(4),total
    real(real64),allocatable :: r1(:),r2(:,:),r3(:,:,:)
    logical :: has_lower,has_upper
    allocate(tmp,stat=astat)
    msg=''
    if(astat/=0) then
      msg='COEFFICIENT_ALLOCATION_FAILED';return
    end if
    total=0
    call field_shape('bnd_limits_wavenumber',2)
    if(msg/='') return
    call nc_read(path,'bnd_limits_wavenumber',int(dims(1:2)),tmp%band_lims,msg)
    if(msg/='') return
    call field_shape('press_ref',1)
    if(msg/='') return
    call nc_read(path,'press_ref',int(dims(1:1)),tmp%press_ref,msg)
    if(msg/='') return
    call field_shape('temp_ref',1)
    if(msg/='') return
    call nc_read(path,'temp_ref',int(dims(1:1)),tmp%temp_ref,msg)
    if(msg/='') return
    call field_shape('vmr_ref',3)
    if(msg/='') return
    call nc_read(path,'vmr_ref',int(dims(1:3)),tmp%vmr_ref,msg)
    if(msg/='') return
    call field_shape('kmajor',4)
    if(msg/='') return
    call nc_read(path,'kmajor',int(dims(1:4)),tmp%kmajor,msg)
    if(msg/='') return
    call field_shape('kminor_lower',3)
    if(msg/='') return
    call nc_read(path,'kminor_lower',int(dims(1:3)),tmp%kminor_lower,msg)
    if(msg/='') return
    call field_shape('kminor_upper',3)
    if(msg/='') return
    call nc_read(path,'kminor_upper',int(dims(1:3)),tmp%kminor_upper,msg)
    if(msg/='') return
    call field_shape('key_species',3)
    if(msg/='') return
    call nc_read(path,'key_species',int(dims(1:3)),r3,msg)
    if(msg/='') return
    if(any(abs(r3)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: key_species';return
    end if
    if(any(r3/=anint(r3))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: key_species';return
    end if
    tmp%key_species=int(r3)
    call field_shape('bnd_limits_gpt',2)
    if(msg/='') return
    call nc_read(path,'bnd_limits_gpt',int(dims(1:2)),r2,msg)
    if(msg/='') return
    if(any(abs(r2)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: bnd_limits_gpt';return
    end if
    if(any(r2/=anint(r2))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: bnd_limits_gpt';return
    end if
    tmp%band2gpt=int(r2)
    call field_shape('minor_limits_gpt_lower',2)
    if(msg/='') return
    call nc_read(path,'minor_limits_gpt_lower',int(dims(1:2)),r2,msg)
    if(msg/='') return
    if(any(abs(r2)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: minor_limits_gpt_lower';return
    end if
    if(any(r2/=anint(r2))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: minor_limits_gpt_lower';return
    end if
    tmp%minor_limits_gpt_lower=int(r2)
    call field_shape('minor_limits_gpt_upper',2)
    if(msg/='') return
    call nc_read(path,'minor_limits_gpt_upper',int(dims(1:2)),r2,msg)
    if(msg/='') return
    if(any(abs(r2)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: minor_limits_gpt_upper';return
    end if
    if(any(r2/=anint(r2))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: minor_limits_gpt_upper';return
    end if
    tmp%minor_limits_gpt_upper=int(r2)
    call field_shape('kminor_start_lower',1)
    if(msg/='') return
    call nc_read(path,'kminor_start_lower',int(dims(1:1)),r1,msg)
    if(msg/='') return
    if(any(abs(r1)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: kminor_start_lower';return
    end if
    if(any(r1/=anint(r1))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: kminor_start_lower';return
    end if
    tmp%kminor_start_lower=int(r1)
    call field_shape('kminor_start_upper',1)
    if(msg/='') return
    call nc_read(path,'kminor_start_upper',int(dims(1:1)),r1,msg)
    if(msg/='') return
    if(any(abs(r1)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: kminor_start_upper';return
    end if
    if(any(r1/=anint(r1))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: kminor_start_upper';return
    end if
    tmp%kminor_start_upper=int(r1)
    call field_shape('minor_scales_with_density_lower',1)
    if(msg/='') return
    call nc_read(path,'minor_scales_with_density_lower',int(dims(1:1)),r1,msg)
    if(msg/='') return
    if(any(abs(r1)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: minor_scales_with_density_lower';return
    end if
    if(any(r1/=anint(r1))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: minor_scales_with_density_lower';return
    end if
    tmp%density_lower=int(r1)
    call field_shape('minor_scales_with_density_upper',1)
    if(msg/='') return
    call nc_read(path,'minor_scales_with_density_upper',int(dims(1:1)),r1,msg)
    if(msg/='') return
    if(any(abs(r1)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: minor_scales_with_density_upper';return
    end if
    if(any(r1/=anint(r1))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: minor_scales_with_density_upper';return
    end if
    tmp%density_upper=int(r1)
    call field_shape('scale_by_complement_lower',1)
    if(msg/='') return
    call nc_read(path,'scale_by_complement_lower',int(dims(1:1)),r1,msg)
    if(msg/='') return
    if(any(abs(r1)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: scale_by_complement_lower';return
    end if
    if(any(r1/=anint(r1))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: scale_by_complement_lower';return
    end if
    tmp%complement_lower=int(r1)
    call field_shape('scale_by_complement_upper',1)
    if(msg/='') return
    call nc_read(path,'scale_by_complement_upper',int(dims(1:1)),r1,msg)
    if(msg/='') return
    if(any(abs(r1)>real(huge(1)-1,real64))) then
      msg='COEFFICIENT_INTEGER_RANGE: scale_by_complement_upper';return
    end if
    if(any(r1/=anint(r1))) then
      msg='COEFFICIENT_NONINTEGER_INDEX: scale_by_complement_upper';return
    end if
    tmp%complement_upper=int(r1)
    call field_shape('gas_names',2)
    if(msg/='') return
    call nc_names(path,'gas_names',int(dims(2)),tmp%gas_names,msg)
    if(msg/='') return
    call field_shape('gas_minor',2)
    if(msg/='') return
    call nc_names(path,'gas_minor',int(dims(2)),tmp%gas_minor,msg)
    if(msg/='') return
    call field_shape('identifier_minor',2)
    if(msg/='') return
    call nc_names(path,'identifier_minor',int(dims(2)),tmp%identifier_minor,msg)
    if(msg/='') return
    call field_shape('minor_gases_lower',2)
    if(msg/='') return
    call nc_names(path,'minor_gases_lower',int(dims(2)),tmp%minor_gases_lower,msg)
    if(msg/='') return
    call field_shape('minor_gases_upper',2)
    if(msg/='') return
    call nc_names(path,'minor_gases_upper',int(dims(2)),tmp%minor_gases_upper,msg)
    if(msg/='') return
    call field_shape('scaling_gas_lower',2)
    if(msg/='') return
    call nc_names(path,'scaling_gas_lower',int(dims(2)),tmp%scaling_gas_lower,msg)
    if(msg/='') return
    call field_shape('scaling_gas_upper',2)
    if(msg/='') return
    call nc_names(path,'scaling_gas_upper',int(dims(2)),tmp%scaling_gas_upper,msg)
    if(msg/='') return
    call nc_read(path,'press_ref_trop',tmp%press_ref_trop,msg)
    if(msg/='') return
    call nc_read(path,'absorption_coefficient_ref_P',tmp%ref_p,msg)
    if(msg/='') return
    call nc_read(path,'absorption_coefficient_ref_T',tmp%ref_t,msg)
    if(msg/='') return
    call nc_info(path,'totplnk',rank,dims,xtype,msg)
    tmp%is_lw=(msg=='')
    msg=''
    if(tmp%is_lw) then
    call field_shape('totplnk',2)
    if(msg/='') return
    call nc_read(path,'totplnk',int(dims(1:2)),tmp%totplnk,msg)
    if(msg/='') return
    call field_shape('plank_fraction',4)
    if(msg/='') return
    call nc_read(path,'plank_fraction',int(dims(1:4)),tmp%planck_frac,msg)
    if(msg/='') return
    call field_shape('optimal_angle_fit',2)
    if(msg/='') return
    call nc_read(path,'optimal_angle_fit',int(dims(1:2)),tmp%optimal_angle_fit,msg)
    if(msg/='') return
    else
    call field_shape('solar_source_quiet',1)
    if(msg/='') return
    call nc_read(path,'solar_source_quiet',int(dims(1:1)),tmp%solar_quiet,msg)
    if(msg/='') return
    call field_shape('solar_source_facular',1)
    if(msg/='') return
    call nc_read(path,'solar_source_facular',int(dims(1:1)),tmp%solar_facular,msg)
    if(msg/='') return
    call field_shape('solar_source_sunspot',1)
    if(msg/='') return
    call nc_read(path,'solar_source_sunspot',int(dims(1:1)),tmp%solar_sunspot,msg)
    if(msg/='') return
    call nc_read(path,'tsi_default',tmp%tsi_default,msg)
    if(msg/='') return
    call nc_read(path,'mg_default',tmp%mg_default,msg)
    if(msg/='') return
    call nc_read(path,'sb_default',tmp%sb_default,msg)
    if(msg/='') return
    end if
    call nc_info(path,'rayl_lower',rank,dims,xtype,msg)
    has_lower=(msg=='')
    call nc_info(path,'rayl_upper',rank,dims,xtype,msg)
    has_upper=(msg=='')
    msg=''
    if(has_lower.neqv.has_upper) then
      msg='COEFFICIENT_INCOMPLETE_RAYLEIGH_PAIR';return
    end if
    if(has_lower) then
    call field_shape('rayl_lower',3)
    if(msg/='') return
    call nc_read(path,'rayl_lower',int(dims(1:3)),tmp%rayl_lower,msg)
    if(msg/='') return
    call field_shape('rayl_upper',3)
    if(msg/='') return
    call nc_read(path,'rayl_upper',int(dims(1:3)),tmp%rayl_upper,msg)
    if(msg/='') return
    end if
    call validate_coefficients(tmp,msg)
    if(msg/='') return
    call move_alloc(tmp,table)
  contains
    subroutine field_shape(name,wanted_rank)
      character(*),intent(in) :: name
      integer,intent(in) :: wanted_rank
      integer :: i
      integer(int64) :: n
      call nc_info(path,name,rank,dims,xtype,msg)
      if(msg/='') return
      if(rank/=wanted_rank) then
        msg='COEFFICIENT_RANK: '//name;return
      end if
      n=1
      do i=1,rank
        if(dims(i)<0.or.dims(i)>huge(1)) then
          msg='COEFFICIENT_EXTENT: '//name;return
        end if
        if(dims(i)>0) then
          if(n>33554432_int64/dims(i)) then
            msg='COEFFICIENT_ARRAY_MEMORY_LIMIT';return
          end if
        end if
        n=n*dims(i)
      end do
      if(total>33554432_int64-n) then
        msg='COEFFICIENT_TOTAL_MEMORY_LIMIT';return
      end if
      total=total+n
    end subroutine
  end subroutine
  subroutine validate_coefficients(t,msg)
    type(coefficient_table),intent(in) :: t
    character(*),intent(out) :: msg
    integer :: ng,nb,nt,np,nm,na,nlo,nhi,j,k
    real(real64) :: dp,dt,tol
    msg='COEFFICIENT_MISSING_CORE_ARRAY'
    if(.not.allocated(t%kmajor).or..not.allocated(t%temp_ref).or..not.allocated(t%press_ref))return
    if(.not.allocated(t%band2gpt).or..not.allocated(t%band_lims).or..not.allocated(t%gas_names))return
    ng=size(t%kmajor,1);nm=size(t%kmajor,2);nt=size(t%temp_ref);np=size(t%press_ref)
    nb=size(t%band2gpt,2);na=size(t%gas_names)
    msg='COEFFICIENT_EMPTY_CORE_DIMENSION'
    if(ng<1.or.nb<1.or.nt<2.or.np<2.or.nm<2.or.na<1)return
    msg='COEFFICIENT_KMAJOR_SHAPE'
    if(any(shape(t%kmajor)/=[ng,nm,np+1,nt]))return
    msg='COEFFICIENT_BAND_SHAPE'
    if(any(shape(t%band2gpt)/=[2,nb]).or.any(shape(t%band_lims)/=[2,nb]))return
    if(any(t%band_lims(1,:)>=t%band_lims(2,:)))return
    msg='COEFFICIENT_GPOINT_COVERAGE'
    if(any(t%band2gpt<1).or.any(t%band2gpt>ng))return
    if(t%band2gpt(1,1)/=1.or.t%band2gpt(2,nb)/=ng)return
    do j=1,nb
      if(t%band2gpt(1,j)>t%band2gpt(2,j))return
      if(j>1)then
        if(t%band2gpt(1,j)/=t%band2gpt(2,j-1)+1)return
      end if
    end do
    msg='COEFFICIENT_REFERENCE_GRID'
    if(any(t%press_ref<=0).or.any(t%temp_ref<=0))return
    if(any(t%press_ref(1:np-1)<=t%press_ref(2:np)))return
    if(any(t%temp_ref(1:nt-1)>=t%temp_ref(2:nt)))return
    if(t%ref_p<=0.or.t%ref_t<=0.or.t%press_ref_trop<=0)return
    dp=(log(t%press_ref(np))-log(t%press_ref(1)))/(np-1)
    dt=(t%temp_ref(nt)-t%temp_ref(1))/(nt-1)
    tol=1.e-5_real64
    if(any(abs(log(t%press_ref(2:np))-log(t%press_ref(1:np-1))-dp)>tol*max(1.0_real64,abs(dp))))return
    if(any(abs(t%temp_ref(2:nt)-t%temp_ref(1:nt-1)-dt)>tol*max(1.0_real64,abs(dt))))return
    msg='COEFFICIENT_GAS_NAMES'
    if(any(len_trim(t%gas_names)==0))return
    do j=1,na
      do k=j+1,na
        if(t%gas_names(j)==t%gas_names(k))return
      end do
    end do
    msg='COEFFICIENT_KEY_SPECIES'
    if(any(shape(t%key_species)/=[2,2,nb]))return
    if(any(t%key_species<0).or.any(t%key_species>na))return
    msg='COEFFICIENT_VMR_REFERENCE'
    if(any(shape(t%vmr_ref)/=[2,na+1,nt]))return
    if(any(t%vmr_ref<0).or.any(t%kmajor<0))return
    nlo=size(t%minor_gases_lower);nhi=size(t%minor_gases_upper)
    msg='COEFFICIENT_MINOR_SHAPE'
    if(any(shape(t%minor_limits_gpt_lower)/=[2,nlo]))return
    if(any(shape(t%minor_limits_gpt_upper)/=[2,nhi]))return
    if(any(shape(t%kminor_lower)/=[size(t%kminor_lower,1),nm,nt]))return
    if(any(shape(t%kminor_upper)/=[size(t%kminor_upper,1),nm,nt]))return
    if(size(t%density_lower)/=nlo.or.size(t%density_upper)/=nhi)return
    if(size(t%complement_lower)/=nlo.or.size(t%complement_upper)/=nhi)return
    if(size(t%scaling_gas_lower)/=nlo.or.size(t%scaling_gas_upper)/=nhi)return
    if(size(t%kminor_start_lower)/=nlo.or.size(t%kminor_start_upper)/=nhi)return
    if(size(t%gas_minor)/=size(t%identifier_minor))return
    msg='COEFFICIENT_MINOR_VALUES'
    if(any(t%kminor_lower<0).or.any(t%kminor_upper<0))return
    if(any(t%density_lower<0).or.any(t%density_lower>1))return
    if(any(t%density_upper<0).or.any(t%density_upper>1))return
    if(any(t%complement_lower<0).or.any(t%complement_lower>1))return
    if(any(t%complement_upper<0).or.any(t%complement_upper>1))return
    do j=1,nlo
      if(t%minor_limits_gpt_lower(1,j)<1.or.t%minor_limits_gpt_lower(2,j)>ng)return
      if(t%minor_limits_gpt_lower(2,j)<t%minor_limits_gpt_lower(1,j))return
      if(t%kminor_start_lower(j)<1)return
      if(int(t%kminor_start_lower(j),int64)+int(t%minor_limits_gpt_lower(2,j),int64)- &
         int(t%minor_limits_gpt_lower(1,j),int64)>size(t%kminor_lower,1))return
    end do
    do j=1,nhi
      if(t%minor_limits_gpt_upper(1,j)<1.or.t%minor_limits_gpt_upper(2,j)>ng)return
      if(t%minor_limits_gpt_upper(2,j)<t%minor_limits_gpt_upper(1,j))return
      if(t%kminor_start_upper(j)<1)return
      if(int(t%kminor_start_upper(j),int64)+int(t%minor_limits_gpt_upper(2,j),int64)- &
         int(t%minor_limits_gpt_upper(1,j),int64)>size(t%kminor_upper,1))return
    end do
    if(allocated(t%rayl_lower))then
      msg='COEFFICIENT_RAYLEIGH_SHAPE'
      if(.not.allocated(t%rayl_upper))return
      if(any(shape(t%rayl_lower)/=[ng,nm,nt]).or.any(shape(t%rayl_upper)/=[ng,nm,nt]))return
      if(any(t%rayl_lower<0).or.any(t%rayl_upper<0))return
    end if
    if(t%is_lw)then
      msg='COEFFICIENT_PLANCK_SHAPE'
      if(.not.allocated(t%totplnk).or..not.allocated(t%planck_frac).or..not.allocated(t%optimal_angle_fit))return
      if(size(t%totplnk,1)<2.or.size(t%totplnk,2)/=nb)return
      if(any(shape(t%planck_frac)/=[ng,nm,np+1,nt]))return
      if(size(t%optimal_angle_fit,2)/=nb)return
      if(any(t%totplnk<0).or.any(t%planck_frac<0))return
    else
      msg='COEFFICIENT_SOLAR_SOURCE'
      if(.not.allocated(t%solar_quiet).or..not.allocated(t%solar_facular).or..not.allocated(t%solar_sunspot))return
      if(size(t%solar_quiet)/=ng.or.size(t%solar_facular)/=ng.or.size(t%solar_sunspot)/=ng)return
      if(t%tsi_default<=0)return
    end if
    msg=''
  end subroutine
end module
