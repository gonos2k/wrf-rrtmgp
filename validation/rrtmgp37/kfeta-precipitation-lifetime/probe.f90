module module_kfeta_lifetime_probe
 implicit none
 real(8),save::clock=0
 real,allocatable,save::rate(:,:),cv0(:,:),rc0(:,:),pp0(:,:),lastcv(:,:)
 logical,allocatable,save::expires(:,:)
 integer,save::u=0
 real,save::dt0
contains
 subroutine trace(tag,t,dt,rc,cv,pr,nca,pp)
 character(*),intent(in)::tag
 real(8),intent(in)::t
 real,intent(in)::dt,rc(:,:),cv(:,:),pr(:,:),nca(:,:),pp(:,:)
 real(8)::x(14)
 real,allocatable::expected(:,:)
 clock=t;x=0;dt0=dt
 if(u==0)open(newunit=u,file='kfeta-lifetime.txt',status='replace')
 if(tag=='ppt_before')then
 rate=pr;cv0=cv;rc0=rc;pp0=pp;expires=nca>0.and.nint(nca/dt)<=1
 endif
 x(1)=sum(real(rc,8));x(2)=sum(real(cv,8));x(3)=sum(real(pr,8));x(4)=sum(real(pp,8))
 if(tag=='physics_before'.and.allocated(lastcv))x(5)=count(cv/=lastcv)
 if(tag=='physics_after'.and.allocated(rate))x(6)=count(pr>0.and.rate==0)
 if(tag=='ppt_after')then
 expected=rc0+rate*dt;x(7)=count(rc/=expected)
 expected=rate*dt;x(8)=count(cv/=expected)
 expected=pp0+(rate+0.)*dt/1000.;x(9)=count(pp/=expected)
 x(10)=count(expires);x(11)=sum(real(rate,8),mask=expires)
 x(12)=sum(real(pr,8),mask=expires);x(13)=sum(real(cv,8),mask=expires)
 x(14)=count(pr/=rate.and..not.expires)
 lastcv=cv
 endif
 write(u,'(f12.3,1x,a,1x,*(es25.16e3,1x))')clock,tag,x
 flush(u)
 end subroutine
end module
