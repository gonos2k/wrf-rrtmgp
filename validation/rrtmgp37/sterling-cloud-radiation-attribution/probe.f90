module module_sterling_cloud_probe
 use iso_fortran_env,only:real64
 implicit none
 integer,save::u=0
 real(real64),save::mu(89:99)=0,phase(89:99)=-1,directu(89:99)=0,directcu(89:99)=0
contains
 logical function selected(i,j,t)
 integer,intent(in)::i,j
 real,intent(in)::t
 selected=i==37.and.j>=89.and.j<=99.and.t>=57600..and.t<61200.
 end function
 subroutine emit(tag,t,values)
 character(*),intent(in)::tag
 real,intent(in)::t
 real(real64),intent(in)::values(:)
 if(u==0)open(newunit=u,file='sterling-cloud.txt',status='replace')
 write(u,'(f12.3,1x,a,1x,*(es25.16e3,1x))')t,tag,values
 end subroutine
 subroutine inputs(i,j,t,temp,p,md,qv,qc,qi,qr,qs,qg,qh,cf,radcf,udmcf,grid,rad,sizes,cugrid,cul, cui,cur,cui_r)
 integer,intent(in)::i,j
 real,intent(in)::t,temp(:),p(:),md(:),qv(:),qc(:),qi(:),qr(:),qs(:),qg(:),qh(:),cf(:),radcf(:),udmcf(:),grid(:,:),rad(:,:),sizes(:,:),cugrid(:,:),cul(:),cui(:),cur(:),cui_r(:)
 integer::k
 if(.not.selected(i,j,t))return
 do k=1,size(cf)
 call emit('input',t,[real(i,real64),real(j,real64),real(k,real64),real(temp(k),real64),real(p(k),real64),real(md(k),real64), &
 real(qv(k),real64),real(qc(k),real64),real(qi(k),real64),real(qr(k),real64),real(qs(k),real64),real(qg(k),real64),real(qh(k),real64), &
 real(cf(k),real64),real(radcf(k),real64),real(udmcf(k),real64),real(grid(k,:),real64),real(rad(k,:),real64),real(sizes(k,:),real64), &
 real(cugrid(k,:),real64),real(cul(k),real64),real(cui(k),real64),real(cur(k),real64),real(cui_r(k),real64)])
 enddo
 flush(u)
 end subroutine
 subroutine returns(i,j,t,cosine,dn,dnc,diru,dircu,dir_scaled,dirc_scaled)
 integer,intent(in)::i,j
 real,intent(in)::t,cosine,dn,dnc,diru,dircu,dir_scaled,dirc_scaled
 if(.not.selected(i,j,t))return
 phase(j)=real(t,real64);mu(j)=real(cosine,real64);directu(j)=real(diru,real64);directcu(j)=real(dircu,real64)
 call emit('return',t,real([i*1.,j*1.,cosine,dn,dnc,diru,dircu,dir_scaled,dirc_scaled],real64));flush(u)
 end subroutine
 subroutine held(t,dt,all,clear,direct,diffuse,ac,acc)
 real,intent(in)::t,dt,all(:),clear(:),direct(:),diffuse(:),ac(:),acc(:)
 integer::j,k
 if(t<57600..or.t>=61200.)return
 do j=89,99
 k=j-88
 if(phase(j)<57600.)error stop 'held sample has no actual call in target hour'
 call emit('held',t,[real(j,real64),real(dt,real64),phase(j),mu(j),real(all(k),real64),real(clear(k),real64), &
 real(direct(k),real64),real(diffuse(k),real64),directu(j),directcu(j),real(ac(k),real64),real(acc(k),real64)])
 enddo
 flush(u)
 end subroutine
end module
