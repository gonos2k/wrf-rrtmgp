program test_shared_flux
 use module_advect_em,only:advect_scalar_pd
 use module_configure,only:grid_config_rec_type
 implicit none
 integer,parameter::n=20,lo=-3,hi=24,nz=4
 type(grid_config_rec_type)::cfg
 real::q(lo:hi,nz,lo:hi),t(lo:hi,nz,lo:hi),ht(lo:hi,nz,lo:hi),zt(lo:hi,nz,lo:hi)
 real::ru(lo:hi,nz,lo:hi),rv(lo:hi,nz,lo:hi),rom(lo:hi,nz,lo:hi)
 real::mu(lo:hi,lo:hi),mb(lo:hi,lo:hi),msf(lo:hi,lo:hi),c1(nz),c2(nz),fz(nz),rdz(nz),dt,qq
 real(8)::mass,div,total,minq,scale
 integer::i,j,k,order,mode,ii,jj
 cfg%polar=.false.;cfg%periodic_x=.true.;cfg%periodic_y=.true.;cfg%specified=.false.;cfg%nested=.false.
 cfg%symmetric_xs=.false.;cfg%symmetric_xe=.false.;cfg%symmetric_ys=.false.;cfg%symmetric_ye=.false.
 cfg%open_xs=.false.;cfg%open_xe=.false.;cfg%open_ys=.false.;cfg%open_ye=.false.;cfg%rk_ord=3
 mu=10.;mb=0.;msf=1.;c1=1.;c2=0.;fz=.5;rdz=-1.;dt=.8;ru=3.;rv=2.;rom=0.
 do order=5,6
 cfg%h_sca_adv_order=order;cfg%v_sca_adv_order=3
 do mode=1,3
 do j=lo,hi
 do i=lo,hi
 ii=modulo(i-1,n);jj=modulo(j-1,n)
 qq=0.
 if(mode==2)qq=.01
 if(mode==3)qq=1.e-15+(sin(6.283185307179586*real(ii)/n)*cos(6.283185307179586*real(jj)/n))**14
 q(i,:,j)=qq
 enddo
 enddo
 t=0.;ht=0.;zt=0.
 call advect_scalar_pd(q,q,t,ht,zt,ru,rv,rom,c1,c2,mu,mb,mu,3,cfg,.true.,msf,msf,msf,msf,msf,msf, &
 fz,fz,1.,1.,rdz,dt,1,n+1,1,n+1,1,nz,lo,hi,lo,hi,1,nz,1,n,1,n,1,nz)
 mass=0;div=0;minq=huge(1.d0);scale=0
 do j=1,n
 do k=1,nz-1
 do i=1,n
 mass=mass+10.d0*real(q(i,k,j),8);div=div+real(t(i,k,j),8)
 minq=min(minq,real((10.*q(i,k,j)+dt*t(i,k,j))/10.,8))
 scale=scale+abs(real(t(i,k,j),8))
 enddo
 enddo
 enddo
 total=mass+real(dt,8)*div
 call check(abs(div)<=64.d0*epsilon(1.)*max(scale,1.d-30),'periodic face divergence not conservative')
 if(mode<=2)call check(all(t(1:n,1:nz-1,1:n)==0.),'zero/constant field changed')
 call check(minq>=0.,'final native mass numerator negative')
 write(*,'(2(i0,1x),*(es25.16e3,1x))')order,mode,mass,div,total-mass,minq,scale
 enddo
 enddo
 print *,'NATIVE_SHARED_FLUX_COMPLETE'
contains
 subroutine check(ok,msg)
 logical,intent(in)::ok
 character(*),intent(in)::msg
 if(.not.ok)then
 print *,msg;error stop 1
 endif
 end subroutine
end program
