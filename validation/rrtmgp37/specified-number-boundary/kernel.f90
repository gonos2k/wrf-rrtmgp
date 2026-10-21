program native_boundary_kernels
 use module_configure,only:grid_config_rec_type
 use module_bc,only:flow_dep_bdy_qnn,spec_bdy_final
 use module_bc_em,only:relax_bdy_scalar,spec_bdy_scalar
 use module_em,only:rk_update_scalar
 implicit none
 integer,parameter::nx=11,ny=11,nz=3,bw=5
 type(grid_config_rec_type)::cfg
 real::field(nx,nz,ny),u(nx,nz,ny),v(nx,nz,ny),alt(nx,nz,ny)
 real::tend(nx,nz,ny),bxs(ny,nz,bw),bxe(ny,nz,bw),bys(nx,nz,bw),bye(nx,nz,bw)
 real::txs(ny,nz,bw),txe(ny,nz,bw),tys(nx,nz,bw),tye(nx,nz,bw)
 real::c1(nz),c2(nz),mut(nx,ny),fcx(bw),gcx(bw),msf(nx,ny),mold(nx,ny),mnew(nx,ny),base(nx,ny)
 real::old(nx,nz,ny,1),new(nx,nz,ny,1),st(nx,nz,ny,1),zero(nx,nz,ny)
 real::s0,ds,eta0,a0,a1,dt,amid,desired,relax_expected,bg,points(5)
 integer::f
 character(32)::arg
 cfg%periodic_x=.false.;cfg%periodic_y=.false.;cfg%specified=.true.;cfg%nested=.false.
 cfg%udm_number_policy=1;cfg%scalar_adv_opt=0;cfg%rk_ord=3
 call get_command_argument(1,arg)
 alt=1.25;field=5.e7;field(5,1,5)=7.e7;u=1.;v=1.;bg=5.e7
 if(arg=='bad_density')alt=0.
 if(arg=='missing_density')then
 call flow_dep_bdy_qnn(field,u,v,cfg,1,bg,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx-1,1,ny-1,1,nz)
 else
 call flow_dep_bdy_qnn(field,u,v,cfg,1,bg,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx-1,1,ny-1,1,nz, &
 dry_inverse_density=alt)
 endif
 points=[field(1,1,5),field(nx-1,1,5),field(5,1,1),field(5,1,ny-1),field(5,1,5)]
 call check(abs(points(1)-6.25e7)<16.,'dry inflow')
 call check(points(2)==5.e7.and.points(4)==5.e7,'eta outflow')
 call check(points(3)==6.25e7.and.points(5)==7.e7,'Y inflow or interior overwritten')
 open(newunit=f,file='kernel.txt',status='new');write(f,'(*(ES25.17E3,1X))')points
 ! Legacy raw volume path is unchanged when the density optional is absent.
 cfg%udm_number_policy=0;field=5.e7
 call flow_dep_bdy_qnn(field,u,v,cfg,1,bg,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx-1,1,ny-1,1,nz)
 call check(field(1,1,5)==bg,'legacy inflow changed');write(f,*)field(1,1,5)
 cfg%udm_number_policy=1
 ! Reversed winds exercise the opposite inflow/outflow branches on all sides.
 field=5.e7;u=-1.;v=-1.
 call flow_dep_bdy_qnn(field,u,v,cfg,1,bg,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx-1,1,ny-1,1,nz, &
 dry_inverse_density=alt)
 points=[field(1,1,5),field(nx-1,1,5),field(5,1,1),field(5,1,ny-1),field(5,1,5)]
 call check(points(1)==5.e7.and.points(3)==5.e7.and.points(2)==6.25e7.and.points(4)==6.25e7,'reverse winds')
 write(f,'(*(ES25.17E3,1X))')points
 open(unit=23,file='endpoints.txt',status='old');read(23,*)s0,ds,eta0,a0,a1,dt;close(23)
 amid=(a0+a1)*.5;c1=.8;c2=200.;mut=(amid-c2(1))/c1(1);msf=1.;fcx=1./600.;gcx=0.
 bxs=s0;bxe=s0;bys=s0;bye=s0;txs=ds;txe=ds;tys=ds;tye=ds
 field=eta0;tend=0.
 call relax_bdy_scalar(tend,field,mut,c1,c2,bxs,bxe,bys,bye,txs,txe,tys,tye,bw,1,4,dt*.5,fcx,gcx,cfg, &
 1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx-1,1,ny-1,1,nz)
 relax_expected=(s0+dt*.5*ds-amid*eta0)/600.
 call check(abs(tend(2,1,5)-relax_expected)<=4.e-6*abs(relax_expected),'relaxation mass convention')
 call check(tend(5,1,5)==0.,'relaxation changed interior')
 call spec_bdy_scalar(tend,bxs,bxe,bys,bye,txs,txe,tys,tye,bw,1,cfg, &
 1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx-1,1,ny-1,1,nz)
 call check(tend(1,1,5)==ds,'specified source differs from coupled tendency')
 write(f,'(*(ES25.17E3,1X))')tend(1,1,5),tend(2,1,5),tend(5,1,5)
 call spec_bdy_final(field,mut,c1,c2,msf,bxs,bxe,bys,bye,txs,txe,tys,tye,'t',cfg,bw,1,dt*.5, &
 1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx,1,ny,1,nz,1,nx-1,1,ny-1,1,nz)
 desired=(s0+dt*.5*ds)/amid
 call check(abs(field(1,1,5)-desired)<=4.e-6*desired,'specified value interpolation')
 call check(field(5,1,5)==eta0,'specified value overwrote interior')
 write(f,'(*(ES25.17E3,1X))')field(1,1,5),field(5,1,5)
 old=eta0;new=eta0;st=0.;st(1,1,5,1)=ds;zero=0.;base=0.;mold=(a0-c2(1))/c1(1);mnew=(a1-c2(1))/c1(1)
 call rk_update_scalar(scs=1,sce=1,scalar_1=old,scalar_2=new,sc_tend=st,advect_tend=zero,h_tendency=zero,z_tendency=zero, &
 msftx=msf,msfty=msf,c1=c1,c2=c2,mu_old=mold,mu_new=mnew,mu_base=base,rk_step=1,dt=dt,spec_zone=1,config_flags=cfg, &
 tenddec=.false.,ids=1,ide=nx,jds=1,jde=ny,kds=1,kde=nz,ims=1,ime=nx,jms=1,jme=ny,kms=1,kme=nz, &
 its=1,ite=nx-1,jts=1,jte=ny-1,kts=1,kte=nz)
 desired=(s0+dt*ds)/a1
 call check(abs(new(1,1,5,1)-desired)<=4.e-6*desired,'actual RK mass uncoupling')
 write(f,'(*(ES25.17E3,1X))')new(1,1,5,1);close(f)
 print *,'NATIVE_BOUNDARY_KERNELS_COMPLETE'
contains
 subroutine check(ok,message)
 logical,intent(in)::ok
 character(*),intent(in)::message
 if(.not.ok)then
 print *,message;error stop 1
 endif
 end subroutine
end program
