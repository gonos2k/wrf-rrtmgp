! Candidate binding to the exact pinned RRTMGP public load() signatures.
! Requires the REAL DP core modules. No mock solver is linked by the real build script.
! Real coefficient/core execution was unavailable in the authoring environment.
module rrtmgp37_core_loader
  use mo_rte_kind,only:wp,wl
  use mo_gas_concentrations,only:ty_gas_concs
  use mo_gas_optics_rrtmgp,only:ty_gas_optics_rrtmgp
  use rrtmgp37_coefficients,only:coefficient_table,read_coefficients
  implicit none
  private
  public :: load_core_coefficients
contains
  subroutine load_core_coefficients(path,available,kdist,want_lw,msg)
    character(*),intent(in) :: path
    type(ty_gas_concs),intent(in) :: available
    type(ty_gas_optics_rrtmgp),intent(inout) :: kdist
    logical,intent(in) :: want_lw
    character(*),intent(out) :: msg
    type(coefficient_table),allocatable :: t
    logical(wl),allocatable :: dl(:),du(:),cl(:),cu(:)
    call read_coefficients(path,t,msg)
    if(msg/='') return
    if(t%is_lw.neqv.want_lw) then
      msg='CORE_COEFFICIENT_SOURCE_KIND_MISMATCH';return
    end if
    dl=logical(t%density_lower==1,wl);du=logical(t%density_upper==1,wl)
    cl=logical(t%complement_lower==1,wl);cu=logical(t%complement_upper==1,wl)
    ! DP-only bridge by design. Build -DRTE_USE_DP; all table arrays are REAL64.
    ! Optional unallocated Rayleigh arrays are forwarded as in the upstream loader.
    if(want_lw) then
      msg=kdist%load(available,t%gas_names,t%key_species,t%band2gpt,t%band_lims, &
        t%press_ref,t%press_ref_trop,t%temp_ref,t%ref_p,t%ref_t,t%vmr_ref,t%kmajor, &
        t%kminor_lower,t%kminor_upper,t%gas_minor,t%identifier_minor, &
        t%minor_gases_lower,t%minor_gases_upper,t%minor_limits_gpt_lower,t%minor_limits_gpt_upper, &
        dl,du,t%scaling_gas_lower,t%scaling_gas_upper,cl,cu,t%kminor_start_lower,t%kminor_start_upper, &
        t%totplnk,t%planck_frac,t%rayl_lower,t%rayl_upper,t%optimal_angle_fit)
    else
      msg=kdist%load(available,t%gas_names,t%key_species,t%band2gpt,t%band_lims, &
        t%press_ref,t%press_ref_trop,t%temp_ref,t%ref_p,t%ref_t,t%vmr_ref,t%kmajor, &
        t%kminor_lower,t%kminor_upper,t%gas_minor,t%identifier_minor, &
        t%minor_gases_lower,t%minor_gases_upper,t%minor_limits_gpt_lower,t%minor_limits_gpt_upper, &
        dl,du,t%scaling_gas_lower,t%scaling_gas_upper,cl,cu,t%kminor_start_lower,t%kminor_start_upper, &
        t%solar_quiet,t%solar_facular,t%solar_sunspot,t%tsi_default,t%mg_default,t%sb_default, &
        t%rayl_lower,t%rayl_upper)
    end if
  end subroutine
end module
