program optional_array_probe
  implicit none
  real, allocatable :: aa(:,:,:)
  integer, allocatable :: ab(:,:), ac(:,:)
  real, pointer :: pa(:,:,:)
  integer, pointer :: pb(:,:), pc(:,:)
  integer :: i,j,k

  allocate(aa(-3:0,2:4,-2:1), ab(-3:0,-2:1), ac(-3:0,-2:1))
  aa=0.; ab=0; ac=0
  call touch(-3,2,-2, aa,ab,ac)
  if (any(aa/=-1.) .or. any(ab/=-1) .or. any(ac/=-1)) error stop 'allocatable writeback failed'
  if (lbound(aa,1)/=-3 .or. lbound(aa,2)/=2 .or. lbound(aa,3)/=-2) error stop 'allocatable bounds changed'

  allocate(pa(-3:0,2:4,-2:1), pb(-3:0,-2:1), pc(-3:0,-2:1))
  pa=0.; pb=0; pc=0
  call touch(-3,2,-2, pa,pb,pc)
  if (any(pa/=-1.) .or. any(pb/=-1) .or. any(pc/=-1)) error stop 'pointer writeback failed'
  if (lbound(pa,1)/=-3 .or. lbound(pa,2)/=2 .or. lbound(pa,3)/=-2) error stop 'pointer bounds changed'

  deallocate(aa,ab,ac)
  deallocate(pa,pb,pc)
  nullify(pa,pb,pc)
  call touch(-3,2,-2, aa,ab,ac)
  call touch(-3,2,-2, pa,pb,pc)
  call touch(-3,2,-2)
  print *, 'OPTIONAL_ARRAY_PROBE_PASS'
contains
  subroutine touch(ims,kms,jms, a,b,c)
    integer,intent(in)::ims,kms,jms
    real, optional,intent(inout)::a(ims:,kms:,jms:)
    integer, optional,intent(inout)::b(ims:,jms:),c(ims:,jms:)
    if (present(a)) a=-1.
    if (present(b)) b=-1
    if (present(c)) c=-1
  end subroutine touch
end program optional_array_probe
