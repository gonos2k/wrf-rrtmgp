! Private serial observer. Native numerical state arguments are input only.
module module_thermodynamic_probe
 implicit none
 private
 public::td_setup,td_context,td_mode,td_row,td_col,td_state
 real(8),save::source=-1
 integer,save::rk=0,mode=0,u=0
 logical,save::active=.false.
contains
 subroutine td_setup(t)
 real(8),intent(in)::t
 source=t
 active=t>=43200d0.and.t<61200d0
 if(active.and.u==0)open(newunit=u,file='thermodynamic_operations.txt',status='new',action='write')
 end subroutine
 subroutine td_context(r)
 integer,intent(in)::r
 rk=r
 end subroutine
 subroutine td_mode(m)
 integer,intent(in)::m
 mode=m
 end subroutine
 subroutine td_row(tag,s,k,v)
 character(*),intent(in)::tag
 integer,intent(in)::s,k
 real,intent(in)::v(:)
 if(.not.active)return
 if(s<0.and.mode==0)return
 write(u,'(F10.1,1X,A,3I5,1X,*(ES25.16E3,1X))')source,tag,rk,merge(mode,s,s<0),k,real(v,8)
 end subroutine
 subroutine td_col(tag,s,v)
 character(*),intent(in)::tag
 integer,intent(in)::s
 real,intent(in)::v(:)
 integer::k
 if(.not.active)return
 do k=1,size(v)
 call td_row(tag,s,k+4,[v(k)])
 enddo
 end subroutine
 subroutine td_state(tag,t,q,mu,mub,c1,c2,dnw,p,pb)
 character(*),intent(in)::tag
 real,intent(in)::t(:),q(:),mu,mub,c1(:),c2(:),dnw(:),p(:),pb(:)
 integer::k
 real::a
 if(.not.active)return
 do k=1,size(t)
 a=c1(k)*(mu+mub)+c2(k)
 call td_row(tag,0,k+4,[t(k),q(k),a,dnw(k),p(k),pb(k)])
 enddo
 end subroutine
end module
