program test_source_exchange
 use module_bc_em,only:relax_bdy_scalar
 use module_configure,only:grid_config_rec_type
 implicit none
 integer,parameter::nx=11,ny=11,nz=3,bw=5
 type(grid_config_rec_type)::cfg
 real::q(nx,nz,ny),t(nx,nz,ny),raw(nx,nz,ny),prior(nx,nz,ny),mu(nx,ny),oldmu(nx,ny)
 real::bx(ny,nz,bw),by(nx,nz,bw),bn(nx,nz,bw),zx(ny,nz,bw),zy(nx,nz,bw)
 real::c1(nz),c2(nz),fcx(bw),gcx(bw),dt,available
 integer::caseid
 cfg%specified=.true.;cfg%nested=.false.;cfg%periodic_x=.false.;cfg%periodic_y=.false.
 do caseid=1,6
 q=1.e-15;t=0.;mu=1.e5;oldmu=mu;c1=.8;c2=123.;bx=0.;by=0.;bn=0.;zx=0.;zy=0.;fcx=.01;gcx=.001;dt=60.
 bn(4,:,2)=1.;bn(6,:,2)=1.
 if(caseid==2)then
 q=.01
 endif
 if(caseid==3)t=-1.
 if(caseid==4)q=-1.e-8
 if(caseid==5)then
 dt=.3;oldmu=70000.
 endif
 if(caseid==6)then
 bn=0.;by=.1;bx=.1
 endif
 prior=t
 call callrelax(.false.);raw=t;t=prior
 call callrelax(.true.)
 available=(c1(1)*oldmu(5,9)+c2(1))*q(5,1,9)
 if(caseid==1.or.caseid==5)then
 call check(available+dt*raw(5,1,9)<0.,'manufactured external overdraw missing')
 call check(available+dt*t(5,1,9)>=0.,'native source numerator still negative')
 call check(t(5,1,9)>raw(5,1,9),'negative external exchange not bounded')
 else
 call check(all(t==raw),'admissible or previously invalid source changed')
 endif
 write(*,'(i0,1x,*(es25.16e3,1x))')caseid,real(available,8),real(raw(5,1,9),8),real(t(5,1,9),8), &
 real(available+dt*raw(5,1,9),8),real(available+dt*t(5,1,9),8)
 enddo
 print *,'NATIVE_SOURCE_EXCHANGE_COMPLETE'
contains
 subroutine callrelax(enabled)
 logical,intent(in)::enabled
 real::step
 step=0.;if(enabled)step=dt
 call relax_bdy_scalar(t,q,mu,c1,c2,bx,bx,by,bn,zx,zx,zy,zy,bw,1,4,17.,fcx,gcx,cfg, &
 1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx-1,1,ny-1,1,nz, &
 positive_dt=step,positive_mu=oldmu)
 end subroutine
 subroutine check(ok,msg)
 logical,intent(in)::ok
 character(*),intent(in)::msg
 if(.not.ok)then
 print *,msg;error stop 1
 endif
 end subroutine
end program
