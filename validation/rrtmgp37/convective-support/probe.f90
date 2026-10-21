! Private read-only domain reductions. No prognostic argument is INOUT.
module module_real_budget_probe
 use iso_fortran_env, only: real64
 use module_model_constants, only:g,cp,r_d,r_v
 implicit none
 integer,save::unit=0,stamp=0
 real(real64),allocatable,save::area(:,:),wgt(:,:,:),radraw(:,:,:),radadded(:,:,:),pi_saved(:,:,:),gain(:,:,:),rhs_before(:,:,:)
 real(real64),save::clock=0,stepdt=0
 real(real64),save::flux(2,6)=0,fluxclock(2)=-1,fluxcheck(2)=0
 logical,save::fr_valid(2)=.false.
 real(real64),allocatable,save::cu_nca(:,:),cu_prate(:,:),cu_sh(:,:)
 logical,allocatable,save::expiry_mask(:,:)
 integer,save::cu_exp_count=0
 integer,save::fluxcount(2)=0
 real(real64),save::fr(2,10)=0
contains
 subroutine emit(tag,id,x)
 character(*),intent(in)::tag
 integer,intent(in)::id
 real(real64),intent(in)::x(:)
 if(unit==0)open(newunit=unit,file='real-budget.txt',status='replace')
 write(unit,'(f12.3,1x,a,1x,i0,1x,*(es25.16e3,1x))')clock,tag,id,x
 flush(unit)
 end subroutine
 subroutine setup(t,dt,dx,dy,mx,my,dnw)
 real(real64),intent(in)::t
 real,intent(in)::dt,dx,dy,mx(:,:),my(:,:),dnw(:)
 integer::k
 clock=t;stepdt=real(dt,real64)
 if(.not.allocated(area))then
 allocate(area(size(mx,1),size(mx,2)),wgt(size(mx,1),size(dnw),size(mx,2)))
 area=real(dx,real64)*real(dy,real64)/(real(mx,real64)*real(my,real64))
 do k=1,size(dnw)
 wgt(:,k,:)=-real(dnw(k),real64)/real(g,real64)*area
 enddo
 call emit('geometry',0,[sum(area),real(size(area),real64),real(size(dnw),real64), &
  real(g,real64),real(cp,real64),real(r_d,real64),real(r_v,real64)])
 endif
 end subroutine
 subroutine stock(tag,id,q,mu,mub,c1,c2)
 character(*),intent(in)::tag
 integer,intent(in)::id
 real,intent(in)::q(:,:,:),mu(:,:),mub(:,:),c1(:),c2(:)
 real(real64)::s,a(size(mu,1),size(mu,2))
 integer::k
 s=0
 do k=1,size(q,2)
 ! REAL32 MU+MUB is the actual native input; coefficient/product evaluation is declared double diagnostic.
 a=real(c1(k),real64)*real(mu+mub,real64)+real(c2(k),real64)
 s=s+sum(wgt(:,k,:)*a*real(q(:,k,:),real64))
 enddo
 call emit(tag,id,[s])
 end subroutine
 subroutine tend(tag,id,q,mask)
 character(*),intent(in)::tag
 integer,intent(in)::id
 real,intent(in)::q(:,:,:)
 logical,optional,intent(in)::mask
 real(real64)::s
 s=sum(wgt*real(q,real64))
 if(present(mask))s=sum(wgt(2:size(q,1)-1,:,2:size(q,3)-1)* &
 real(q(2:size(q,1)-1,:,2:size(q,3)-1),real64))
 call emit(tag,id,[s,stepdt])
 end subroutine
 subroutine adv(id,q,my,dt)
 integer,intent(in)::id
 real,intent(in)::q(:,:,:),my(:,:),dt
 real(real64)::s
 integer::k,nx,ny
 nx=size(q,1);ny=size(q,3);s=0
 do k=1,size(q,2)
 s=s+sum(wgt(2:nx-1,k,2:ny-1)*real(q(2:nx-1,k,2:ny-1),real64)*real(my(2:nx-1,2:ny-1),real64))
 enddo
 call emit('advection_rate',id,[s,real(dt,real64)])
 end subroutine
 subroutine surface(tag,p,e,qfx)
 character(*),intent(in)::tag
 real,intent(in)::p(:,:),e(:,:),qfx(:,:)
 call emit(tag,0,[sum(area*real(p,real64)),sum(area*real(e,real64))/2501000._real64, &
 sum(area*real(qfx,real64))])
 end subroutine
 subroutine radiation(tag,r,pi,mut,c1,c2,qv)
 character(*),intent(in)::tag
 real,intent(in)::r(:,:,:),pi(:,:,:),mut(:,:),c1(:),c2(:),qv(:,:,:)
 real(real64)::a(size(mut,1),size(mut,2)),s,si
 integer::k,nx,ny
 nx=size(mut,1);ny=size(mut,2);s=0;si=0
 if(tag=='rad_raw')then
 if(.not.allocated(radraw))allocate(radraw(size(r,1),size(r,2),size(r,3)))
 radraw=real(r,real64)
 if(.not.allocated(pi_saved))allocate(pi_saved(size(r,1),size(r,2),size(r,3)))
 pi_saved=real(pi,real64)
 if(.not.allocated(gain))allocate(gain(size(r,1),size(r,2),size(r,3)))
 gain=real(1.+(r_v/r_d)*qv,real64)
 do k=1,size(r,2)
 a=real(c1(k)*mut+c2(k),real64)
 s=s+sum(wgt(:,k,:)*a*real(cp,real64)*real(pi(:,k,:),real64)*radraw(:,k,:))
 si=si+sum(wgt(2:nx-1,k,2:ny-1)*a(2:nx-1,2:ny-1)*real(cp,real64)* &
 real(pi(2:nx-1,k,2:ny-1),real64)*radraw(2:nx-1,k,2:ny-1))
 enddo
 else
 ! r is coupled RTHRATEN after calculate_phy_tend. Dry theta source used by phy_ra_ten.
 do k=1,size(r,2)
 s=s+sum(wgt(:,k,:)*real(cp,real64)*real(pi(:,k,:),real64)*real(r(:,k,:),real64))
 si=si+sum(wgt(2:nx-1,k,2:ny-1)*real(cp,real64)*real(pi(2:nx-1,k,2:ny-1),real64)* &
 real(r(2:nx-1,k,2:ny-1),real64))
 enddo
 endif
 call emit(tag,0,[s,si,stepdt,fluxclock,reshape(flux,[12]),fluxcheck,real(fluxcount,real64)])
 end subroutine
 subroutine thermal(tag,x)
 character(*),intent(in)::tag
 real,intent(in)::x(:,:,:)
 if(tag=='thermal_before')then
 if(.not.allocated(radadded))allocate(radadded(size(x,1),size(x,2),size(x,3)))
 radadded=real(x,real64)
 else
 radadded=real(x,real64)-radadded
 call emit('radiation_actual_add',0,[sum(wgt*real(cp,real64)*pi_saved*radadded)])
 endif
 end subroutine
 subroutine rhs(tag,rk,x,my)
 character(*),intent(in)::tag
 integer,intent(in)::rk
 real,intent(in)::x(:,:,:),my(:,:)
 integer::k
 real(real64)::s,r
 if(tag=='before')then
 if(.not.allocated(rhs_before))allocate(rhs_before(size(x,1),size(x,2),size(x,3)))
 rhs_before=real(x,real64)
 else
 s=0;r=0
 do k=1,size(x,2)
 s=s+sum(wgt(:,k,:)*real(cp,real64)*pi_saved(:,k,:)/gain(:,k,:)*real(my,real64)* &
 (real(x(:,k,:),real64)-rhs_before(:,k,:)))
 ! The radiation-only linear component carried by the actually consumed moist-theta RHS.
 r=r+sum(wgt(:,k,:)*real(cp,real64)*pi_saved(:,k,:)*radadded(:,k,:))
 enddo
 call emit('actual_thermal_rhs',rk,[s,r,stepdt])
 endif
 end subroutine
 subroutine column(kind,i,j,n,up,dn,hr,plev,md)
 integer,intent(in)::kind,i,j,n
 real(real64),intent(in)::up(:),dn(:),hr(:),plev(:),md(:)
 real(real64)::net(6),c
 if(fluxclock(kind)/=clock)then
 flux(kind,:)=0;fluxcount(kind)=0;fluxcheck(kind)=0;fluxclock(kind)=clock
 endif
 net=[dn(1)-up(1),dn(n+1)-up(n+1),dn(size(dn))-up(size(up)), &
 sum(real(cp,real64)/real(g,real64)*100._real64*(plev(1:n)-plev(2:n+1))*hr(1:n)/86400._real64), &
 sum(real(cp,real64)*md(1:n)*hr(1:n)/86400._real64),0._real64]
 if(i>1.and.i<size(area,1).and.j>1.and.j<size(area,2))net(6)=net(2)-net(1)
 flux(kind,:)=flux(kind,:)+area(i,j)*net
 fluxcheck(kind)=max(fluxcheck(kind),abs(net(2)-net(1)-net(4)))
 fluxcount(kind)=fluxcount(kind)+1
 end subroutine
 subroutine frozen(i,j,t,p,lam,species)
 integer,intent(in)::i,j,species
 real(real64),intent(in)::t(:),p(:),lam(:)
 integer::k
 if(.not.fr_valid(species).or.fr(species,8)/=clock)then
 fr_valid(species)=.true.
 fr(species,:)=[0._real64,0._real64,huge(1._real64),0._real64,huge(1._real64),0._real64,0._real64,clock,0._real64,0._real64]
 endif
 do k=1,size(p)
 if(p(k)<=0)cycle
 fr(species,1)=fr(species,1)+area(i,j)*p(k)*.001_real64
 fr(species,2)=fr(species,2)+1
 fr(species,3)=min(fr(species,3),lam(k));fr(species,4)=max(fr(species,4),lam(k))
 fr(species,5)=min(fr(species,5),t(k));fr(species,6)=max(fr(species,6),t(k))
 if(lam(k)==20000._real64)fr(species,9)=fr(species,9)+area(i,j)*p(k)*.001_real64
 if(t(k)>273.15_real64)fr(species,10)=fr(species,10)+area(i,j)*p(k)*.001_real64
 if(lam(k)<300.or.lam(k)>20000.or.t(k)<150.or.t(k)>330)fr(species,7)=fr(species,7)+area(i,j)*p(k)*.001_real64
 enddo
 end subroutine
 subroutine frozen_end()
 integer::s
 do s=1,2
 if(fr(s,8)==clock)call emit('frozen_consumption',s,fr(s,:))
 enddo
 end subroutine
 subroutine precip(tag,rc,rnc,rsh,qfx)
 character(*),intent(in)::tag
 real,intent(in)::rc(:,:),rnc(:,:),rsh(:,:),qfx(:,:)
 real(real64)::x(12),f(size(rc,1),size(rc,2))
 integer::k,nx,ny
 nx=size(rc,1);ny=size(rc,2)
 do k=1,4
 select case(k)
 case(1);f=area*real(rc,real64)
 case(2);f=area*real(rnc,real64)
 case(3);f=area*real(rsh,real64)
 case(4);f=area*real(qfx,real64)
 end select
 x(3*k-2)=sum(f);x(3*k-1)=sum(f(2:nx-1,2:ny-1));x(3*k)=x(3*k-2)-x(3*k-1)
 enddo
 call emit(tag,0,x)
 end subroutine
 subroutine cu_context(nca,prate,sh)
 real,intent(in)::nca(:,:),prate(:,:),sh(:,:)
 if(.not.allocated(cu_nca))allocate(cu_nca(size(nca,1),size(nca,2)), &
 cu_prate(size(nca,1),size(nca,2)),cu_sh(size(nca,1),size(nca,2)))
 cu_nca=real(nca,real64);cu_prate=real(prate,real64);cu_sh=real(sh,real64)
 end subroutine
 subroutine cu_columns(qv,qc,qr,qi,qs)
 real,intent(in)::qv(:,:,:),qc(:,:,:),qr(:,:,:),qi(:,:,:),qs(:,:,:)
 real(real64)::x(4,4),water,p
 logical::active
 integer::i,j,k,c
 x=0
 do j=2,size(qv,3)-1
 do i=2,size(qv,1)-1
 water=0;active=.false.
 do k=1,size(qv,2)
 active=active.or.qv(i,k,j)/=0.or.qc(i,k,j)/=0.or.qr(i,k,j)/=0.or.qi(i,k,j)/=0.or.qs(i,k,j)/=0
 water=water+wgt(i,k,j)*(real(qv(i,k,j),real64)+real(qc(i,k,j),real64)+ &
 real(qr(i,k,j),real64)+real(qi(i,k,j),real64)+real(qs(i,k,j),real64))
 enddo
 if(cu_prate(i,j)>0)then
 c=1;if(.not.active)c=2
 else
 c=3;if(.not.active)c=4
 endif
 p=area(i,j)*cu_prate(i,j)
 x(1,c)=x(1,c)+water;x(2,c)=x(2,c)+p;x(3,c)=x(3,c)+1
 if(cu_nca(i,j)<=0)x(4,c)=x(4,c)+p
 enddo
 enddo
 do c=1,4
 call emit('cu_column_category',c,x(:,c))
 enddo
 end subroutine
 subroutine cu_expiry(tag,dt,nca,prate,qv,qc,qr,qi,qs)
 character(*),intent(in)::tag
 real,intent(in)::dt,nca(:,:),prate(:,:),qv(:,:,:),qc(:,:,:),qr(:,:,:),qi(:,:,:),qs(:,:,:)
 real(real64)::x(4),water
 logical::active,expiry
 integer::i,j,k
 x=0
 if(.not.allocated(expiry_mask))allocate(expiry_mask(size(nca,1),size(nca,2)))
 if(tag=='expiry_before')expiry_mask=nca>0.and.nint(nca/dt)<=1
 do j=2,size(qv,3)-1
 do i=2,size(qv,1)-1
 expiry=expiry_mask(i,j)
 active=.false.;water=0
 do k=1,size(qv,2)
 active=active.or.qv(i,k,j)/=0.or.qc(i,k,j)/=0.or.qr(i,k,j)/=0.or.qi(i,k,j)/=0.or.qs(i,k,j)/=0
 water=water+wgt(i,k,j)*(real(qv(i,k,j),real64)+real(qc(i,k,j),real64)+ &
 real(qr(i,k,j),real64)+real(qi(i,k,j),real64)+real(qs(i,k,j),real64))
 enddo
 if(expiry)then
 x(1)=x(1)+water;x(2)=x(2)+area(i,j)*real(prate(i,j),real64);x(3)=x(3)+1
 endif
 if(.not.active.and.prate(i,j)>0)x(4)=x(4)+area(i,j)*real(prate(i,j),real64)
 enddo
 enddo
 call emit(tag,0,x)
 end subroutine
end module
