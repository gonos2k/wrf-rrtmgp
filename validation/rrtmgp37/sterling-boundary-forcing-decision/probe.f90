module module_sterling_boundary_probe
 use iso_fortran_env,only:real64
 implicit none
 integer,save::u=0,rank_id=0,map_ids(7)=0
 real(real64),save::clock=0
 logical,save::active=.false.
contains
 logical function site(j,t)
 integer,intent(in)::j
 real(real64),intent(in)::t
 site=t>=57600._real64.and.t<61200._real64.and.j>=95.and.j<=98
 if(site.and.j/=97)site=mod(nint(t),600)==0
 end function
 integer function species(im)
 integer,intent(in)::im
 integer::n
 species=0
 do n=1,7
 if(map_ids(n)==im)species=n
 enddo
 end function
 subroutine emit(tag,t,x)
 character(*),intent(in)::tag
 real(real64),intent(in)::t,x(:)
 if(u==0)open(newunit=u,file='sterling-boundary.txt',status='replace')
 write(u,'(f12.3,1x,a,1x,*(es25.16e3,1x))')t,tag,x
 end subroutine
 subroutine begin_call(im,ids,rk,t,dt,dt_rk,s,r,alpha,fcx,gcx)
 integer,intent(in)::im,ids(7),rk,s,r
 real(real64),intent(in)::t
 real,intent(in)::dt,dt_rk,alpha,fcx(:),gcx(:)
 map_ids=ids;rank_id=species(im);clock=t;active=rank_id>0.and.rk==1.and.site(97,t)
 if(active)call emit('context',t,[real(rank_id,real64),real(rk,real64),real(dt,real64),real(dt_rk,real64),real(s,real64),real(r,real64),real(alpha,real64),real(fcx,real64),real(gcx,real64)])
 end subroutine
 subroutine core(i,j,k,b,dtbc,f,g,before,after,S,B0,BT,E)
 integer,intent(in)::i,j,k,b
 real,intent(in)::dtbc,f,g,before,after,S(5),B0(5),BT(5),E(5)
 if(.not.active)return
 if(i/=37.or..not.site(j,clock).or.k>44)return
 call emit('core',clock,[real(rank_id,real64),real(j,real64),real(k,real64),real(b,real64),real(dtbc,real64),real(f,real64),real(g,real64),real(before,real64),real(after,real64),real(S,real64),real(B0,real64),real(BT,real64),real(E,real64)])
 end subroutine
 subroutine accepted(q,tend,mu,c1,c2)
 real,intent(in)::q(:,:),tend(:,:),mu(:),c1(:),c2(:)
 integer::j,k
 real::a
 if(.not.active)return
 do j=95,98
 if(.not.site(j,clock))cycle
 do k=1,44
 a=c1(k)*mu(j-94)+c2(k)
 call emit('accepted',clock,[real(rank_id,real64),real(j,real64),real(k,real64),real(a,real64),real(q(k,j-94),real64),real(tend(k,j-94),real64)])
 enddo
 enddo
 active=.false.;flush(u)
 end subroutine
 subroutine pdpoint(label,t,im,dt,c1,c2,mu,q,tend)
 character(*),intent(in)::label
 integer,intent(in)::im
 real(real64),intent(in)::t
 real,intent(in)::dt,c1(:),c2(:),mu(:),q(:,:),tend(:,:)
 integer::j,k,sp
 real::a
 sp=species(im)
 if(sp<1.or..not.site(97,t))return
 do j=95,98
 if(.not.site(j,t))cycle
 do k=1,44
 a=c1(k)*mu(j-94)+c2(k)
 call emit(label,t,[real(sp,real64),real(j,real64),real(k,real64),real(dt,real64),real(a,real64),real(q(k,j-94),real64),real(tend(k,j-94),real64)])
 enddo
 enddo
 flush(u)
 end subroutine
end module
