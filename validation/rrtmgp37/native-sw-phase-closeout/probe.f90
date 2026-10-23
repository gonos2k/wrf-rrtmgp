! Serial, one-tile read-only observations of actual SW branches and returned fields.
module module_sw_phase_probe
 use iso_fortran_env,only:real64
 use ieee_arithmetic,only:ieee_is_finite
 use module_model_constants,only:g,cp
 implicit none
 integer,save::u=0,phase_count=0,audit_n=-1
 real(real64),save::clock=0,phase=-1,dt_saved=0
 real(real64),allocatable,save::area(:,:),dnw_saved(:),mom(:,:,:)
 integer,allocatable,save::branch(:,:),seen(:,:)
 real(real64),save::phase_net(2)=0,phase_pressure(2)=0,phase_dry(2)=0
contains
 subroutine emit(tag,x)
 character(*),intent(in)::tag
 real(real64),intent(in)::x(:)
 if(u==0)open(newunit=u,file='sw-phase.txt',status='replace')
 write(u,'(f12.3,1x,a,1x,*(es25.16e3,1x))')clock,tag,x
 flush(u)
 end subroutine
 subroutine sw_setup(t,dt,dx,dy,mx,my,dnw)
 real(real64),intent(in)::t
 real,intent(in)::dt,dx,dy,mx(:,:),my(:,:),dnw(:)
 clock=t;dt_saved=real(dt,real64)
 if(.not.allocated(area))then
 allocate(area(size(mx,1),size(mx,2)),dnw_saved(size(dnw)))
 allocate(branch(size(mx,1),size(mx,2)),seen(size(mx,1),size(mx,2)),mom(size(mx,1),size(mx,2),4))
 area=real(dx,real64)*real(dy,real64)/(real(mx,real64)*real(my,real64));dnw_saved=real(dnw,real64)
 call emit('geometry',[sum(area),real(size(mx,1),real64),real(size(mx,2),real64),real(size(dnw),real64), &
 real(g,real64),real(cp,real64)])
 endif
 end subroutine
 subroutine sw_begin(audit_step,audit_time,its,ite,jts,jte)
 integer,intent(in)::audit_step,its,ite,jts,jte
 real,intent(in)::audit_time
 if(its/=1.or.jts/=1.or.ite/=size(area,1).or.jte/=size(area,2))error stop 'SW observer requires full serial tile'
 if(real(audit_time,real64)/=clock)error stop 'SW audit time differs from actual step source'
 if(phase==clock)error stop 'duplicate SW call in phase'
 phase=clock;audit_n=audit_step;phase_count=phase_count+1
 branch=0;seen=0;mom=0
 call emit('call_begin',[phase,real(audit_n,real64),real(phase_count,real64)])
 end subroutine
 subroutine sw_day(i,j,n,up,dn,hr,plev,md)
 integer,intent(in)::i,j,n
 real(real64),intent(in)::up(:),dn(:),hr(:),plev(:),md(:)
 if(branch(i,j)/=0)error stop 'duplicate day/night branch'
 branch(i,j)=1
 mom(i,j,1)=sum(real(cp,real64)/real(g,real64)*100._real64* &
 (plev(1:n)-plev(2:n+1))*hr(1:n)/86400._real64)
 mom(i,j,2)=sum(real(cp,real64)*md(1:n)*hr(1:n)/86400._real64)
 ! Replay the actual assignment to native REAL32 layer flux arrays.
 mom(i,j,3)=real(real(dn(n+1)),real64)-real(real(up(n+1)),real64)- &
 real(real(dn(1)),real64)+real(real(up(1)),real64)
 mom(i,j,4)=dn(n+1)-up(n+1)-dn(1)+up(1)
 if(.not.all(ieee_is_finite(mom(i,j,:))))error stop 'invalid SW day moments'
 end subroutine
 subroutine sw_night(i,j)
 integer,intent(in)::i,j
 if(branch(i,j)/=0)error stop 'duplicate day/night branch'
 branch(i,j)=2
 end subroutine
 subroutine sw_end(up,dn,theta,pi,md,mu0,gsw,upb,dnb,upt,dnt)
 real,intent(in)::up(:,:,:),dn(:,:,:),theta(:,:,:),pi(:,:,:),md(:,:,:),mu0(:,:),gsw(:,:), &
 upb(:,:),dnb(:,:),upt(:,:),dnt(:,:)
 real(real64)::s(2,12),nightmax,err,return_err,vals(12),w,boundmax,mu_min,mu_max
 integer::i,j,k,n,nx,ny,zone
 logical::interior
 nx=size(area,1);ny=size(area,2);n=size(theta,2)
 s=0;nightmax=0;err=0;return_err=0;boundmax=0;mu_min=huge(1._real64);mu_max=-huge(1._real64)
 do j=1,ny
 do i=1,nx
 if(branch(i,j)==0)error stop 'missing SW branch'
 if(seen(i,j)/=0)error stop 'duplicate returned SW column'
 seen(i,j)=1
 if(.not.all(ieee_is_finite(up(i,:,j))).or..not.all(ieee_is_finite(dn(i,:,j))).or. &
 .not.all(ieee_is_finite(theta(i,:,j))))error stop 'nonfinite returned SW'
 mu_min=min(mu_min,real(mu0(i,j),real64));mu_max=max(mu_max,real(mu0(i,j),real64))
 vals=0
 vals(1:6)=[real(up(i,1,j),real64),real(dn(i,1,j),real64), &
 real(up(i,n+1,j),real64),real(dn(i,n+1,j),real64), &
 real(up(i,n+2,j),real64),real(dn(i,n+2,j),real64)]
 vals(7:9)=mom(i,j,1:3)
 vals(10)=sum(real(cp,real64)*real(md(i,:,j),real64)*real(pi(i,:,j),real64)*real(theta(i,:,j),real64))
 vals(11)=vals(4)-vals(3)-vals(2)+vals(1)
 vals(12)=mom(i,j,4)-vals(7)
 err=max(err,abs(vals(12)))
 return_err=max(return_err,abs(vals(11)-vals(9)))
 boundmax=max(boundmax,abs(real(gsw(i,j),real64)-(vals(2)-vals(1))), &
 abs(real(upb(i,j),real64)-vals(1)),abs(real(dnb(i,j),real64)-vals(2)), &
 abs(real(upt(i,j),real64)-vals(5)),abs(real(dnt(i,j),real64)-vals(6)))
 if(branch(i,j)==2)then
 ! Confirm actual zero arrays from the native return path, not a solar-angle fill.
 nightmax=max(nightmax,maxval(abs(real(up(i,:,j),real64))),maxval(abs(real(dn(i,:,j),real64))), &
 maxval(abs(real(theta(i,:,j),real64))),abs(real(gsw(i,j),real64)), &
 abs(real(upb(i,j),real64)),abs(real(dnb(i,j),real64)),abs(real(upt(i,j),real64)),abs(real(dnt(i,j),real64)))
 if(mu0(i,j)>0)error stop 'night branch inconsistent with consumed solar angle'
 else
 if(mu0(i,j)<=0)error stop 'day branch inconsistent with consumed solar angle'
 endif
 w=area(i,j);s(1,:)=s(1,:)+w*vals
 interior=i>1.and.i<nx.and.j>1.and.j<ny
 if(interior)s(2,:)=s(2,:)+w*vals
 enddo
 enddo
 if(nightmax/=0)error stop 'nonzero actual native night return'
 if(return_err/=0)error stop 'day raw/returned native boundary differs'
 call emit('coverage',[phase,real(audit_n,real64),real(count(branch==1),real64),real(count(branch==2),real64), &
 real(count(seen==1),real64),real(count(branch(2:nx-1,2:ny-1)==1),real64), &
 real(count(branch(2:nx-1,2:ny-1)==2),real64),nightmax,err,return_err,boundmax,mu_min,mu_max])
 do zone=1,2
 call emit('phase_flux',[real(zone,real64),s(zone,:)/sum(area)])
 enddo
 phase_net=s(:,11)/sum(area);phase_pressure=s(:,7)/sum(area);phase_dry=s(:,10)/sum(area)
 end subroutine
 subroutine sw_held(r,pi,mut,c1,c2)
 real,intent(in)::r(:,:,:),pi(:,:,:),mut(:,:),c1(:),c2(:)
 real(real64)::s(2),sc(2),v(size(r,1),size(r,3)),vc(size(r,1),size(r,3))
 integer::k,nx,ny
 nx=size(r,1);ny=size(r,3);s=0;sc=0
 do k=1,size(r,2)
 ! Match native REAL32 coupling before diagnostic double mass integration.
 v=-dnw_saved(k)/real(g,real64)*real(c1(k)*mut+c2(k),real64)* &
 real(cp,real64)*real(pi(:,k,:),real64)*real(r(:,k,:),real64)
 vc=-dnw_saved(k)/real(g,real64)*real(cp,real64)*real(pi(:,k,:),real64)* &
 real((c1(k)*mut+c2(k))*r(:,k,:),real64)
 s(1)=s(1)+sum(area*v);s(2)=s(2)+sum(area(2:nx-1,2:ny-1)*v(2:nx-1,2:ny-1))
 sc(1)=sc(1)+sum(area*vc);sc(2)=sc(2)+sum(area(2:nx-1,2:ny-1)*vc(2:nx-1,2:ny-1))
 enddo
 call emit('held',[phase,real(phase_count,real64),dt_saved,merge(1._real64,0._real64,phase==clock), &
 s/sum(area),sc/sum(area),phase_net,phase_pressure,phase_dry])
 end subroutine
end module
