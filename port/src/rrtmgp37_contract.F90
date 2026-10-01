! Numerical building blocks ONLY. No RTE/WRF solver is implemented here.
! Contract: columns x layers, bottom-first; fluxes W m-2; theta tendency K s-1.
module rrtmgp37_contract
  use, intrinsic :: iso_fortran_env, only: real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  private
  public :: require_paired_37, column_flux_to_theta, hydrostatic_heat_capacity
contains
  subroutine require_paired_37(lw_scheme, sw_scheme, ierr, message)
    integer, intent(in) :: lw_scheme, sw_scheme
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    ierr=0; message=''
    if ((lw_scheme==37) .neqv. (sw_scheme==37)) then
      ierr=1
      message='RRTMGP37 initial port requires LW=37 and SW=37 together.'
    end if
  end subroutine

  subroutine column_flux_to_theta(flux_up, flux_down, heat_capacity, exner, qtheta, ierr, message)
    real(real64), intent(in) :: flux_up(:,:), flux_down(:,:)
    real(real64), intent(in) :: heat_capacity(:,:), exner(:,:)
    ! INOUT deliberately preserves the caller output when validation fails.
    real(real64), intent(inout) :: qtheta(:,:)
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer :: nc, nl, i, k
    real(real64) :: delta, value
    real(real64), allocatable :: trial(:,:), net_up(:,:)
    ierr=1; message='Invalid column/layer array shapes.'
    nc=size(heat_capacity,1); nl=size(heat_capacity,2)
    if (nc<1 .or. nl<1) return
    if (any(shape(exner)/=[nc,nl])) return
    if (any(shape(qtheta)/=[nc,nl])) return
    if (any(shape(flux_up)/=[nc,nl+1])) return
    if (any(shape(flux_down)/=[nc,nl+1])) return
    message='Non-finite input; output has not been modified.'
    if (.not.all(ieee_is_finite(flux_up))) return
    if (.not.all(ieee_is_finite(flux_down))) return
    if (.not.all(ieee_is_finite(heat_capacity))) return
    if (.not.all(ieee_is_finite(exner))) return
    message='Heat capacity and Exner must be positive.'
    if (any(heat_capacity<=0.0_real64)) return
    if (any(exner<=0.0_real64)) return
    allocate(trial(nc,nl),net_up(nc,nl+1))
    message='Flux subtraction or division would overflow; output unchanged.'
    do k=1,nl+1
      do i=1,nc
        if(.not.safe_subtract(flux_up(i,k),flux_down(i,k),net_up(i,k))) return
      end do
    end do
    do k=1,nl
      do i=1,nc
        if(.not.safe_subtract(net_up(i,k),net_up(i,k+1),delta)) return
        if(.not.safe_positive_division(delta,heat_capacity(i,k),value)) return
        if(.not.safe_positive_division(value,exner(i,k),trial(i,k))) return
      end do
    end do
    message='Non-finite tendency; output has not been modified.'
    if (.not.all(ieee_is_finite(trial))) return
    qtheta=trial
    ierr=0; message=''
  end subroutine

  subroutine hydrostatic_heat_capacity(p_interface, cp, gravity, heat_capacity, ierr, message)
    ! Optional helper ONLY for a justified hydrostatic cp*dp/g mass convention.
    ! Do not use instantaneous nonhydrostatic WRF pressure blindly as layer mass.
    real(real64), intent(in) :: p_interface(:,:), cp(:,:), gravity
    real(real64), intent(inout) :: heat_capacity(:,:)
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer :: nc,nl,i,k
    real(real64), allocatable :: dp(:,:),trial(:,:)
    ierr=1; message='Invalid pressure/cp/output shape.'
    nc=size(cp,1); nl=size(cp,2)
    if (nc<1 .or. nl<1) return
    if (any(shape(p_interface)/=[nc,nl+1])) return
    if (any(shape(heat_capacity)/=[nc,nl])) return
    message='Pressure, cp, and gravity must be finite.'
    if (.not.all(ieee_is_finite(p_interface))) return
    if (.not.all(ieee_is_finite(cp))) return
    if (.not.ieee_is_finite(gravity)) return
    message='Pressure and cp must be positive; gravity must be positive.'
    if (any(p_interface<=0.0_real64) .or. any(cp<=0.0_real64)) return
    if (gravity<=0.0_real64) return
    allocate(dp(nc,nl),trial(nc,nl))
    dp=p_interface(:,1:nl)-p_interface(:,2:nl+1)
    message='Expected strictly decreasing pressure in bottom-first order.'
    if (any(dp<=0.0_real64)) return
    message='Heat-capacity arithmetic would overflow; output unchanged.'
    do k=1,nl
      do i=1,nc
        if(dp(i,k)>1.0_real64) then
          if(cp(i,k)>huge(1.0_real64)/dp(i,k)) return
        end if
        trial(i,k)=cp(i,k)*dp(i,k)
        if(gravity<1.0_real64) then
          if(trial(i,k)>huge(1.0_real64)*gravity) return
        end if
        trial(i,k)=trial(i,k)/gravity
      end do
    end do
    message='Non-finite heat capacity; output has not been modified.'
    if (.not.all(ieee_is_finite(trial))) return
    heat_capacity=trial
    ierr=0; message=''
  end subroutine
  logical function safe_subtract(a,b,c)
    real(real64),intent(in) :: a,b
    real(real64),intent(out) :: c
    safe_subtract=.false.
    if(b<0.0_real64) then
      if(a>huge(c)+b) return
    else if(b>0.0_real64) then
      if(a<(-huge(c))+b) return
    end if
    c=a-b;safe_subtract=.true.
  end function
  logical function safe_positive_division(a,b,c)
    real(real64),intent(in) :: a,b
    real(real64),intent(out) :: c
    safe_positive_division=.false.
    if(b<1.0_real64) then
      if(abs(a)>huge(c)*b) return
    end if
    c=a/b;safe_positive_division=.true.
  end function
end module
