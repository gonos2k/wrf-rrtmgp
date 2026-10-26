! Read-only serial observer; every numerical input is INTENT(IN).
module module_transport_probe
 implicit none
 private
 public::ts_setup,ts_context,ts_mode,ts_row
 real(8),save::source=-1
 integer,save::rk=0,mode=0,u=0
 logical,save::active=.false.
contains
 subroutine ts_setup(t)
 real(8),intent(in)::t
 source=t
 active=t>=43200d0.and.t<61200d0
 if(active.and.u==0)open(newunit=u,file='transport_faces.txt',status='new',action='write')
 end subroutine
 subroutine ts_context(r)
 integer,intent(in)::r
 rk=r
 end subroutine
 subroutine ts_mode(m)
 integer,intent(in)::m
 mode=m
 end subroutine
 subroutine ts_row(tag,s,k,v)
 character(*),intent(in)::tag
 integer,intent(in)::s,k
 real,intent(in)::v(:)
 if(.not.active.or.rk/=3)return
 if(s<0.and.mode==0)return
 write(u,'(F10.1,1X,A,3I5,1X,*(ES25.16E3,1X))')source,tag,rk,merge(mode,s,s<0),k,real(v,8)
 end subroutine
end module
