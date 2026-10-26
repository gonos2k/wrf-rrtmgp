! Private, read-only serial observer. No numerical state arguments are modified.
module module_cloud_loss_probe
 implicit none
 private
 public :: cl_setup,cl_context,cl_row,cl_stock,cl_tend
 real(8),save :: source=-1
 integer,save :: step=0,sp=0,u=0
 logical,save :: active=.false.
contains
 subroutine cl_setup(t)
 real(8),intent(in)::t
 source=t
 active=t>=60600d0.and.t<65400d0
 if(active.and.u==0)then
  open(newunit=u,file='cloud_operations.txt',status='new',action='write')
 endif
 end subroutine
 subroutine cl_context(r,s)
 integer,intent(in)::r,s
 step=r
 sp=s
 end subroutine
 subroutine cl_row(tag,s,k,v)
 character(*),intent(in)::tag
 integer,intent(in)::s,k
 real,intent(in)::v(:)
 if(.not.active)return
 if(s<0.and.sp==0)return
 write(u,'(F10.1,1X,A,3I5,1X,*(ES25.16E3,1X))') source,tag,step,merge(sp,s,s<0),k,real(v,8)
 end subroutine
 subroutine cl_stock(tag,s,q,mu,mub,c1,c2,dnw)
 character(*),intent(in)::tag
 integer,intent(in)::s
 real,intent(in)::q(:),mu,mub,c1(:),c2(:),dnw(:)
 integer::k
 real::a
 if(.not.active)return
 do k=1,size(q)
  a=c1(k)*(mu+mub)+c2(k)
  call cl_row(tag,s,k,[q(k),a,dnw(k)])
 enddo
 end subroutine
 subroutine cl_tend(tag,s,t)
 character(*),intent(in)::tag
 integer,intent(in)::s
 real,intent(in)::t(:)
 integer::k
 if(.not.active)return
 do k=1,size(t)
  call cl_row(tag,s,k,[t(k)])
 enddo
 end subroutine
end module
