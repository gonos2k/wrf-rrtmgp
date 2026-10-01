! WRF-facing numerical adapters, not the WRF driver or a radiation solver.
! All columns are bottom-first. Native WRF ikj arrays are packed, not regridded.
! No mutable module state. NetCDF initialization is separate from tile evaluation.
module rrtmgp37_host_bridge
  use iso_fortran_env, only: real32,real64,int64
  use ieee_arithmetic, only: ieee_is_finite
  use rrtmgp37_contract, only: column_flux_to_theta
  implicit none
  private
  public :: pack_ikj,unpack_ikj,mass_to_dry_columns,mass_mixing_to_vmr
  public :: daylight_indices,finish_fluxes,radiation_result,check_column_state
  type :: radiation_result
    real(real64),allocatable :: qtheta_lw(:,:),qtheta_sw(:,:),qtheta_total(:,:)
    real(real64),allocatable :: swdown(:),swddir(:),swddif(:),gsw(:),lwdnb(:),lwupb(:)
    real(real64),allocatable :: sw_up(:,:),sw_dn(:,:),sw_dir(:,:),lw_up(:,:),lw_dn(:,:)
  end type
  interface pack_ikj
    module procedure pack_ikj_r32,pack_ikj_r64
  end interface
  interface unpack_ikj
    module procedure unpack_ikj_r32,unpack_ikj_r64
  end interface
contains
  logical function tile_ok(ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
    integer,intent(in) :: ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
    integer(int64) :: ni,nj,nk
    tile_ok=.false.
    if(ime<ims.or.kme<kms.or.jme<jms) return
    if(ite<its.or.kte<kts.or.jte<jts) return
    if(its<ims.or.ite>ime.or.kts<kms.or.kte>kme.or.jts<jms.or.jte>jme) return
    ni=int(ite,int64)-int(its,int64)+1; nj=int(jte,int64)-int(jts,int64)+1
    nk=int(kte,int64)-int(kts,int64)+1
    ! Bound intermediate integer products and per-field working memory.
    if(ni>67108864_int64.or.nj>67108864_int64.or.nk>67108864_int64) return
    if(ni*nj>67108864_int64) return
    if(ni*nj*nk>67108864_int64) return
    tile_ok=.true.
  end function
  subroutine pack_ikj_r32(field,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte,columns,msg)
    integer,intent(in) :: ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
    real(real32),intent(in) :: field(ims:ime,kms:kme,jms:jme)
    real(real64),allocatable,intent(inout) :: columns(:,:)
    character(*),intent(out) :: msg
    real(real64),allocatable :: tmp(:,:)
    integer :: i,j,k,c,st
    msg='HOST_TILE_EXTENTS'
    if(.not.tile_ok(ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)) return
    allocate(tmp((ite-its+1)*(jte-jts+1),kte-kts+1),stat=st)
    if(st/=0) then
      msg='HOST_ALLOCATION';return
    end if
    c=0
    do j=jts,jte
      do i=its,ite
        c=c+1
        do k=kts,kte
          tmp(c,k-kts+1)=real(field(i,k,j),real64)
        end do
      end do
    end do
    if(.not.all(ieee_is_finite(tmp))) then
      msg='HOST_NONFINITE_TILE';return
    end if
    call move_alloc(tmp,columns)
    msg=''
  end subroutine
  subroutine unpack_ikj_r32(columns,field,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte,msg)
    integer,intent(in) :: ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
    real(real64),intent(in) :: columns(:,:)
    real(real32),intent(inout) :: field(ims:ime,kms:kme,jms:jme)
    character(*),intent(out) :: msg
    integer :: i,j,k,c
    msg='HOST_TILE_EXTENTS'
    if(.not.tile_ok(ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)) return
    if(any(shape(columns)/=[(ite-its+1)*(jte-jts+1),kte-kts+1])) return
    msg='HOST_NONFINITE_OR_UNREPRESENTABLE'
    if(.not.all(ieee_is_finite(columns))) return
    if(any(abs(columns)>real(huge(0.0_real32),real64))) return
    c=0
    do j=jts,jte
      do i=its,ite
        c=c+1
        do k=kts,kte
          field(i,k,j)=real(columns(c,k-kts+1),real32)
        end do
      end do
    end do
    msg=''
  end subroutine
  subroutine pack_ikj_r64(field,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte,columns,msg)
    integer,intent(in) :: ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
    real(real64),intent(in) :: field(ims:ime,kms:kme,jms:jme)
    real(real64),allocatable,intent(inout) :: columns(:,:)
    character(*),intent(out) :: msg
    real(real64),allocatable :: tmp(:,:)
    integer :: i,j,k,c,st
    msg='HOST_TILE_EXTENTS'
    if(.not.tile_ok(ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)) return
    allocate(tmp((ite-its+1)*(jte-jts+1),kte-kts+1),stat=st)
    if(st/=0) then
      msg='HOST_ALLOCATION';return
    end if
    c=0
    do j=jts,jte
      do i=its,ite
        c=c+1
        do k=kts,kte
          tmp(c,k-kts+1)=real(field(i,k,j),real64)
        end do
      end do
    end do
    if(.not.all(ieee_is_finite(tmp))) then
      msg='HOST_NONFINITE_TILE';return
    end if
    call move_alloc(tmp,columns)
    msg=''
  end subroutine
  subroutine unpack_ikj_r64(columns,field,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte,msg)
    integer,intent(in) :: ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
    real(real64),intent(in) :: columns(:,:)
    real(real64),intent(inout) :: field(ims:ime,kms:kme,jms:jme)
    character(*),intent(out) :: msg
    integer :: i,j,k,c
    msg='HOST_TILE_EXTENTS'
    if(.not.tile_ok(ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)) return
    if(any(shape(columns)/=[(ite-its+1)*(jte-jts+1),kte-kts+1])) return
    msg='HOST_NONFINITE_OR_UNREPRESENTABLE'
    if(.not.all(ieee_is_finite(columns))) return
    if(any(abs(columns)>real(huge(0.0_real64),real64))) return
    c=0
    do j=jts,jte
      do i=its,ite
        c=c+1
        do k=kts,kte
          field(i,k,j)=real(columns(c,k-kts+1),real64)
        end do
      end do
    end do
    msg=''
  end subroutine
  subroutine mass_to_dry_columns(dry_mass,molar_mass_dry,col_dry,msg)
    ! dry_mass: kg dry air / m2. col_dry: molecules / cm2.
    ! Supply WRF's audited dry layer mass, not nonhydrostatic dp/g by default.
    real(real64),intent(in) :: dry_mass(:,:),molar_mass_dry ! kg/mol
    real(real64),allocatable,intent(inout) :: col_dry(:,:)
    character(*),intent(out) :: msg
    real(real64),parameter :: avogadro=6.02214076e23_real64
    real(real64),allocatable :: tmp(:,:)
    real(real64) :: factor
    msg='HOST_DRY_MASS_OR_MOLAR_MASS'
    if(any(shape(dry_mass)<1)) return
    if(.not.all(ieee_is_finite(dry_mass)).or..not.ieee_is_finite(molar_mass_dry)) return
    if(any(dry_mass<=0.0_real64).or.molar_mass_dry<=0.0_real64) return
    if(molar_mass_dry<avogadro/1.e4_real64/huge(factor)) return
    factor=(avogadro/1.e4_real64)/molar_mass_dry
    if(factor>1.0_real64) then
      if(any(dry_mass>huge(factor)/factor)) return
    end if
    tmp=dry_mass*factor
    if(.not.all(ieee_is_finite(tmp)).or.any(tmp<=0.0_real64)) return
    call move_alloc(tmp,col_dry);msg=''
  end subroutine
  subroutine mass_mixing_to_vmr(qmass,molar_mass_dry,molar_mass_species,vmr,msg)
    ! qmass is kg species / kg DRY air; not specific humidity.
    ! Output is mol species / mol dry air, consistent with gas*col_dry.
    real(real64),intent(in) :: qmass(:,:),molar_mass_dry,molar_mass_species
    real(real64),allocatable,intent(inout) :: vmr(:,:)
    character(*),intent(out) :: msg
    real(real64),allocatable :: tmp(:,:)
    real(real64) :: factor
    msg='HOST_MIXING_RATIO_OR_MOLAR_MASS'
    if(any(shape(qmass)<1)) return
    if(.not.all(ieee_is_finite(qmass))) return
    if(.not.ieee_is_finite(molar_mass_dry).or..not.ieee_is_finite(molar_mass_species)) return
    if(any(qmass<0.0_real64).or.molar_mass_dry<=0.0_real64.or.molar_mass_species<=0.0_real64) return
    if(molar_mass_species<1.0_real64) then
      if(molar_mass_dry>huge(factor)*molar_mass_species) return
    end if
    factor=molar_mass_dry/molar_mass_species
    if(factor>1.0_real64) then
      if(any(qmass>huge(factor)/factor)) return
    end if
    tmp=qmass*factor
    if(.not.all(ieee_is_finite(tmp))) return
    call move_alloc(tmp,vmr);msg=''
  end subroutine
  subroutine daylight_indices(mu0,indices,msg)
    real(real64),intent(in) :: mu0(:)
    integer,allocatable,intent(inout) :: indices(:)
    character(*),intent(out) :: msg
    integer,allocatable :: tmp(:)
    integer :: i,k
    msg='HOST_SOLAR_COSINE'
    if(size(mu0)<1.or..not.all(ieee_is_finite(mu0))) return
    if(any(abs(mu0)>1.0_real64)) return
    allocate(tmp(count(mu0>0.0_real64)));k=0
    do i=1,size(mu0)
      if(mu0(i)>0.0_real64) then
        k=k+1;tmp(k)=i
      end if
    end do
    call move_alloc(tmp,indices);msg=''
  end subroutine
  subroutine check_column_state(play,plev,tlay,tlev,tsfc,col_dry,msg)
    real(real64),intent(in) :: play(:,:),plev(:,:),tlay(:,:),tlev(:,:),tsfc(:),col_dry(:,:)
    character(*),intent(out) :: msg
    integer :: nc,nl
    nc=size(play,1);nl=size(play,2);msg='HOST_COLUMN_EXTENTS'
    if(nc<1.or.nl<1) return
    if(any(shape(plev)/=[nc,nl+1]).or.any(shape(tlay)/=[nc,nl])) return
    if(any(shape(tlev)/=[nc,nl+1]).or.any(shape(col_dry)/=[nc,nl]).or.size(tsfc)/=nc) return
    msg='HOST_COLUMN_NONFINITE'
    if(.not.all(ieee_is_finite(play)).or..not.all(ieee_is_finite(plev))) return
    if(.not.all(ieee_is_finite(tlay)).or..not.all(ieee_is_finite(tlev))) return
    if(.not.all(ieee_is_finite(tsfc)).or..not.all(ieee_is_finite(col_dry))) return
    msg='HOST_COLUMN_POSITIVE'
    if(any(play<=0.0_real64).or.any(plev<0.0_real64)) return
    if(any(tlay<=0.0_real64).or.any(tlev<=0.0_real64).or.any(tsfc<=0.0_real64)) return
    if(any(col_dry<=0.0_real64)) return
    msg='HOST_PRESSURE_BOTTOM_FIRST_BRACKETING'
    if(any(plev(:,1:nl)<=plev(:,2:nl+1))) return
    if(any(play>=plev(:,1:nl)).or.any(play<=plev(:,2:nl+1))) return
    msg=''
  end subroutine
  subroutine finish_fluxes(lw_up,lw_dn,sw_up,sw_dn,sw_dir,mu0,capacity,exner,result,msg)
    ! Atomic result; nighttime shortwave is zeroed even if input buffers are stale.
    ! lw_dn is RAW incident LW. LWDNB is returned; GLW is deliberately NOT assigned.
    ! Validate the exact WRF/Noah consumer before adding emissivity factors.
    real(real64),intent(in) :: lw_up(:,:),lw_dn(:,:),sw_up(:,:),sw_dn(:,:),sw_dir(:,:)
    real(real64),intent(in) :: mu0(:),capacity(:,:),exner(:,:)
    type(radiation_result),allocatable,intent(inout) :: result
    character(*),intent(out) :: msg
    type(radiation_result),allocatable :: tmp
    integer,allocatable :: day(:)
    integer :: nc,nl,ic,j,k,ierr
    real(real64) :: tol
    nc=size(capacity,1);nl=size(capacity,2);msg='HOST_FLUX_EXTENTS'
    if(nc<1.or.nl<1.or.size(mu0)/=nc) return
    if(any(shape(exner)/=[nc,nl])) return
    if(any(shape(lw_up)/=[nc,nl+1]).or.any(shape(lw_dn)/=[nc,nl+1])) return
    if(any(shape(sw_up)/=[nc,nl+1]).or.any(shape(sw_dn)/=[nc,nl+1])) return
    if(any(shape(sw_dir)/=[nc,nl+1])) return
    call daylight_indices(mu0,day,msg)
    if(msg/='') return
    msg='HOST_LW_NONFINITE_OR_NEGATIVE'
    if(.not.all(ieee_is_finite(lw_up)).or..not.all(ieee_is_finite(lw_dn))) return
    if(any(lw_up<0.0_real64).or.any(lw_dn<0.0_real64)) return
    allocate(tmp)
    allocate(tmp%sw_up(nc,nl+1),tmp%sw_dn(nc,nl+1),tmp%sw_dir(nc,nl+1))
    tmp%sw_up=0;tmp%sw_dn=0;tmp%sw_dir=0
    do j=1,size(day)
      ic=day(j);msg='HOST_SW_NONFINITE_OR_NEGATIVE'
      if(.not.all(ieee_is_finite(sw_up(ic,:))).or..not.all(ieee_is_finite(sw_dn(ic,:)))) return
      if(.not.all(ieee_is_finite(sw_dir(ic,:)))) return
      if(any(sw_up(ic,:)<0.0_real64).or.any(sw_dn(ic,:)<0.0_real64).or.any(sw_dir(ic,:)<0.0_real64)) return
      tol=1.e-9_real64*max(1.0_real64,maxval(sw_dn(ic,:)))
      msg='HOST_SW_DIRECT_EXCEEDS_TOTAL'
      if(any(sw_dir(ic,:)-sw_dn(ic,:)>tol)) return
      msg='HOST_SW_SURFACE_UP_EXCEEDS_DOWN'
      if(sw_up(ic,1)-sw_dn(ic,1)>tol) return
      tmp%sw_up(ic,:)=sw_up(ic,:);tmp%sw_dn(ic,:)=sw_dn(ic,:)
      tmp%sw_dir(ic,:)=min(sw_dir(ic,:),sw_dn(ic,:)) ! roundoff-only correction
    end do
    tmp%lw_up=lw_up;tmp%lw_dn=lw_dn
    allocate(tmp%qtheta_lw(nc,nl),tmp%qtheta_sw(nc,nl))
    call column_flux_to_theta(tmp%lw_up,tmp%lw_dn,capacity,exner,tmp%qtheta_lw,ierr,msg)
    if(ierr/=0) return
    call column_flux_to_theta(tmp%sw_up,tmp%sw_dn,capacity,exner,tmp%qtheta_sw,ierr,msg)
    if(ierr/=0) return
    allocate(tmp%qtheta_total(nc,nl))
    msg='HOST_TENDENCY_SUM_OVERFLOW'
    do k=1,nl
      do ic=1,nc
        if(tmp%qtheta_sw(ic,k)>0.0_real64) then
          if(tmp%qtheta_lw(ic,k)>huge(1.0_real64)-tmp%qtheta_sw(ic,k)) return
        else if(tmp%qtheta_sw(ic,k)<0.0_real64) then
          if(tmp%qtheta_lw(ic,k)<(-huge(1.0_real64))-tmp%qtheta_sw(ic,k)) return
        end if
        tmp%qtheta_total(ic,k)=tmp%qtheta_lw(ic,k)+tmp%qtheta_sw(ic,k)
      end do
    end do
    if(.not.all(ieee_is_finite(tmp%qtheta_total))) then
      msg='HOST_TENDENCY_OVERFLOW';return
    end if
    tmp%swdown=tmp%sw_dn(:,1)
    tmp%swddir=tmp%sw_dir(:,1)
    tmp%swddif=tmp%swdown-tmp%swddir
    tmp%gsw=tmp%sw_dn(:,1)-tmp%sw_up(:,1)
    tmp%lwdnb=lw_dn(:,1);tmp%lwupb=lw_up(:,1)
    call move_alloc(tmp,result);msg=''
  end subroutine
end module
