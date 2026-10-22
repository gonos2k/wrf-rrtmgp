module module_vapor_first_probe
 implicit none
 real(8),save::clock=0
 integer,save::u=0
 real,allocatable,save::before(:,:,:),base(:,:,:),src(:,:,:),ad(:,:,:),oldmu(:,:),newmu(:,:),bmu(:,:),cc1(:),cc2(:),mapy(:,:)
 real,save::saved_dt
 integer,save::saved_rk
 character(32),save::name
contains
 subroutine begin_step(t)
 real(8),intent(in)::t
 clock=t
 end subroutine
 subroutine capture(tag,rk,dt,q,qbase,tend,adv,m0,m1,mb,c1,c2,my)
 character(*),intent(in)::tag
 integer,intent(in)::rk
 real,intent(in)::dt,q(:,:,:),qbase(:,:,:),tend(:,:,:),adv(:,:,:),m0(:,:),m1(:,:),mb(:,:),c1(:),c2(:),my(:,:)
 before=q;base=qbase;src=tend;ad=adv;oldmu=m0;newmu=m1;bmu=mb;cc1=c1;cc2=c2;mapy=my
 name=tag;saved_rk=rk;saved_dt=dt
 if(tag=='rk'.and.rk==1)base=q
 end subroutine
 subroutine examine(q)
 real,intent(in)::q(:,:,:)
 integer::i,j,k,n
 real::mu0,mu1,a0,a1,tendency,used_adv,expected
 if(u==0)open(newunit=u,file='vapor-first.txt',status='replace')
 n=0
 do j=1,size(q,3)
 do k=1,size(q,2)
 do i=1,size(q,1)
 if(q(i,k,j)>=0.or.before(i,k,j)<0)cycle
 n=n+1
 used_adv=0
 if(name=='rk'.and.i>1.and.i<size(q,1).and.j>1.and.j<size(q,3))used_adv=ad(i,k,j)*mapy(i,j)
 tendency=used_adv+src(i,k,j)
 mu0=oldmu(i,j)+bmu(i,j);mu1=newmu(i,j)+bmu(i,j)
 a0=cc1(k)*mu0+cc2(k);a1=cc1(k)*mu1+cc2(k)
 expected=(a0*base(i,k,j)+saved_dt*tendency)/a1
 write(u,'(f12.3,1x,a,1x,4(i0,1x),*(es25.16e3,1x))')clock,trim(name),saved_rk,i,j,k, &
 real(before(i,k,j),8),real(q(i,k,j),8),real(base(i,k,j),8),real(src(i,k,j),8),real(ad(i,k,j),8), &
 real(mapy(i,j),8),real(a0,8),real(a1,8),real(saved_dt,8),real(expected,8)
 enddo
 enddo
 enddo
 write(u,'(f12.3,1x,a,1x,i0,1x,i0,1x,es25.16e3)')clock,'summary_'//trim(name),saved_rk,n,real(minval(q),8)
 flush(u)
 end subroutine
end module
