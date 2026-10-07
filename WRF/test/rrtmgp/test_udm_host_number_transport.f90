! Selected native scalar procedures with a type/shape adapter, not a WRF run.
program host_number_transport
 use host_scalar_procedures
 implicit none
 integer,parameter::nx=4,ny=3,nz=2
 type(grid_config_rec_type)::cfg
 real::old(0:nx+1,0:nz+1,0:ny+1,2),s1(0:nx+1,0:nz+1,0:ny+1,2)
 real::s2(0:nx+1,0:nz+1,0:ny+1,2),src(0:nx+1,0:nz+1,0:ny+1,2),pd(0:nx+1,0:nz+1,0:ny+1,2)
 real::adv(0:nx+1,0:nz+1,0:ny+1),ru(0:nx+1,0:nz+1,0:ny+1),rv(0:nx+1,0:nz+1,0:ny+1)
 real::rom(0:nx+1,0:nz+1,0:ny+1),ah(0:nx+1,0:nz+1,0:ny+1),az(0:nx+1,0:nz+1,0:ny+1)
 real::zero3(0:nx+1,0:nz+1,0:ny+1),saved(0:nx+1,0:nz+1,0:ny+1,2)
 real::mx(0:nx+1,0:ny+1),my(0:nx+1,0:ny+1),mu0(0:nx+1,0:ny+1),mu1(0:nx+1,0:ny+1),mub(0:nx+1,0:ny+1)
 real::c1(0:nz+1),c2(0:nz+1),fz(0:nz+1),rdzw(0:nz+1),gf(nx+1),dt,mnew,values(23)
 integer::case_id,arm,pattern,geometry,stage,im,i,j,k,ii,jj,nadv=0,nrk=0,npd=0,nbdy=0,mode,periodic
 real::boundary(0:nx+1,0:nz+1,0:ny+1),bvalues(6)
 cfg%periodic_x=.true.; cfg%periodic_y=.true.
 dt=.25; gf=[1024.,2304.,768.,1536.,1024.]
 zero3=0.;rv=0.;rom=0.;fz=.5;rdzw=1.;mu0=0.
 case_id=0
 do arm=1,2
 do pattern=0,1
 do geometry=0,1
 case_id=case_id+1
 c1=1.; c2=0.
 if(geometry==1)then
   c1(2)=.5; c2(2)=4096.
 endif
 do j=0,ny+1
 do i=0,nx+1
   ii=modulo(i-1,nx)+1; jj=modulo(j-1,ny)+1
   mx(i,j)=1.; my(i,j)=1.
   if(geometry==1)then
     mx(i,j)=1.+.125*real(ii-1); my(i,j)=.75+.0625*real(jj)
   endif
   mub(i,j)=65536.+32768.*real(arm-1)
   mu1(i,j)=-dt*mx(i,j)*my(i,j)*(gf(ii+1)-gf(ii))
   do k=0,nz+1
     ru(i,k,j)=c1(k)*gf(ii)+c2(k)*.125
     do im=1,2
       old(i,k,j,im)=1.e8/real(im)
       if(pattern==1)old(i,k,j,im)=old(i,k,j,im)*(1.+.125*real(ii)+.0625*real(jj)+.03125*real(k))
     enddo
   enddo
 enddo
 enddo
 saved=old
 do stage=1,3,2
   s1=old; s2=old
   ! Later-stage update must use the time-t buffer, not current scalar_2.
   if(stage==3)s2=-777.
   src=0.;pd=0.
   do im=1,2
     adv=0.;ah=0.;az=0.
     call advect_scalar(old(:,:,:,im),old(:,:,:,im),adv,ru,rv,rom,c1,c2,mub,1,cfg, &
       mx,my,mx,my,mx,my,fz,fz,1.,1.,rdzw, &
       1,nx+1,1,ny+1,1,nz+1,0,nx+1,0,ny+1,0,nz+1,1,nx,1,ny,1,nz+1)
     nadv=nadv+1
     call rk_update_scalar(im,im,s1(:,:,:,im:im),s2(:,:,:,im:im),src(:,:,:,im:im),ah,az, &
       adv,adv,zero3,mx,my,c1,c2,mu0,mu1,mub,stage,dt,1,cfg,.true., &
       1,nx+1,1,ny+1,1,nz+1,0,nx+1,0,ny+1,0,nz+1,1,nx,1,ny,1,nz+1)
     nrk=nrk+1
     pd(:,:,:,im)=s2(:,:,:,im)
     do j=1,ny
     do k=1,nz
     do i=1,nx
       mnew=c1(k)*(mu1(i,j)+mub(i,j))+c2(k)
       src(i,k,j,im)=.01*mnew*old(i,k,j,im)
     enddo
     enddo
     enddo
     call rk_update_scalar_pd(im,im,pd(:,:,:,im:im),src(:,:,:,im:im),c1,c2,mu1,mu1,mub,stage,dt,1,cfg, &
       1,nx+1,1,ny+1,1,nz+1,0,nx+1,0,ny+1,0,nz+1,1,nx,1,ny,1,nz+1)
     npd=npd+1
     do j=1,ny
     do k=1,nz
     do i=1,nx
       mnew=c1(k)*(mu1(i,j)+mub(i,j))+c2(k)
       values=[dt,-.5,9.81,c1(k),c2(k),mx(i,j),my(i,j),mu0(i,j),mub(i,j),mu1(i,j), &
         ru(i,k,j),ru(i+1,k,j),old(i-1,k,j,im),old(i,k,j,im),old(i+1,k,j,im), &
         adv(i,k,j),s2(i,k,j,im),s1(i,k,j,im),ah(i,k,j),az(i,k,j), &
         .01*mnew*old(i,k,j,im),pd(i,k,j,im),src(i,k,j,im)]
       write(*,'(a,6(1x,i0))')'CELL',case_id,stage,im,i,k,j
       write(*,'(*(z8.8,1x))')transfer(values,[0],size(values))
     enddo
     enddo
     enddo
   enddo
 enddo
 if(any(transfer(old,[0],size(old))/=transfer(saved,[0],size(saved))))error stop 'input changed'
 enddo
 enddo
 enddo
 do periodic=0,1
 do mode=-1,1
   cfg%periodic_x=periodic==1
   ru=real(mode);rv=real(mode)
   do j=0,ny+1
   do k=0,nz+1
   do i=0,nx+1
     boundary(i,k,j)=1.e6*real(i+8*k+32*j)
   enddo
   enddo
   enddo
   call flow_dep_bdy_qnn(boundary,ru,rv,cfg,1,1.e8, &
       1,nx+1,1,ny+1,1,nz+1,0,nx+1,0,ny+1,0,nz+1, &
       1,nx,1,ny,1,nz,1,nx,1,ny,1,nz)
   nbdy=nbdy+1
   do j=0,ny+1
   do k=0,nz+1
   do i=0,nx+1
     bvalues=[1.e6*real(i+8*k+32*j),real(mode),real(mode),1.e8,boundary(i,k,j),real(periodic)]
     write(*,'(a,4(1x,i0))')'BOUNDARY',nbdy,i,k,j
     write(*,'(*(z8.8,1x))')transfer(bvalues,[0],size(bvalues))
   enddo
   enddo
   enddo
 enddo
 enddo
 write(*,'(a,4(1x,i0))')'CALLS',nadv,nrk,npd,nbdy
end program
