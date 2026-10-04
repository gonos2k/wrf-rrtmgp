! CPU scalar-libm boundary for repeatable scalar and batched RRTMGP calls.
!
! Keep this module in a separate translation unit.  Its public elemental
! procedures deliberately call the scalar Fortran intrinsics; CPU callers
! must not be LTO/IPO-inlined across this boundary, so a caller's array shape
! cannot select a vector libm entry point for these operations.
module mo_rte_scalar_math
  use mo_rte_kind, only: wp
  implicit none
  private
  public :: rte_scalar_exp, rte_scalar_log, rte_scalar_cos
contains
  pure elemental function rte_scalar_exp(x) result(y)
    real(wp), intent(in) :: x
    real(wp) :: y
    y = exp(x)
  end function rte_scalar_exp

  pure elemental function rte_scalar_log(x) result(y)
    real(wp), intent(in) :: x
    real(wp) :: y
    y = log(x)
  end function rte_scalar_log

  pure elemental function rte_scalar_cos(x) result(y)
    real(wp), intent(in) :: x
    real(wp) :: y
    y = cos(x)
  end function rte_scalar_cos
end module mo_rte_scalar_math
