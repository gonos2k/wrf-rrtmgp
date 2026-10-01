! Official WRF v4.8.0 Noah interface adapter, not the Noah model or RRTMGP solver.
! The official Noah driver performs LWDN=GLW*EMISSI. Consequently GLW must
! contain incident downward LW, without a pre-applied surface emissivity.
! This file has NOT been connected to the complete WRF radiation driver.
module rrtmgp37_noah_surface
  use iso_fortran_env, only: real32, real64
  use ieee_arithmetic, only: ieee_is_finite
  implicit none
  private
  public :: map_noah_glw
  interface map_noah_glw
    module procedure map_noah_glw32, map_noah_glw64
  end interface
contains
  subroutine map_noah_glw32(lwdnb,glw,msg)
    real(real64),intent(in) :: lwdnb(:)
    real(real32),intent(inout) :: glw(:)
    character(*),intent(out) :: msg
    msg='NOAH_GLW_SHAPE'
    if(size(lwdnb)<1.or.size(lwdnb)/=size(glw)) return
    msg='NOAH_GLW_INVALID_FLUX'
    if(.not.all(ieee_is_finite(lwdnb))) return
    if(any(lwdnb<0.0_real64)) return
    if(any(lwdnb>real(huge(0.0_real32),real64))) return
    glw=real(lwdnb,real32)
    msg=''
  end subroutine
  subroutine map_noah_glw64(lwdnb,glw,msg)
    real(real64),intent(in) :: lwdnb(:)
    real(real64),intent(inout) :: glw(:)
    character(*),intent(out) :: msg
    msg='NOAH_GLW_SHAPE'
    if(size(lwdnb)<1.or.size(lwdnb)/=size(glw)) return
    msg='NOAH_GLW_INVALID_FLUX'
    if(.not.all(ieee_is_finite(lwdnb))) return
    if(any(lwdnb<0.0_real64)) return
    glw=lwdnb
    msg=''
  end subroutine
end module
