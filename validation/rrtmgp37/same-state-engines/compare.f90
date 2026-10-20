! Diagnostic only. Link unchanged native RRTMG4 and public RRTMGP37.
program same_state_engines
 use iso_fortran_env,only:real64
 use module_ra_rrtmgp,only:rrtmgp_init,rrtmgp_lw_column,rrtmgp_sw_column
 use module_ra_rrtmgp_trace,only:trace_start,trace_end
 use module_rrtmg4_optics_export,only:rrtmg4_export_begin,rrtmg4_export_end
 use module_ra_rrtmg_lw,only:rrtmg_lwlookuptable
 use module_ra_rrtmg_sw,only:rrtmg_swlookuptable
 use rrtmg_lw_init,only:rrtmg_lw_ini
 use rrtmg_sw_init,only:rrtmg_sw_ini
 use rrtmg_lw_rad,only:rrtmg_lw
 use rrtmg_sw_rad,only:rrtmg_sw
 use parrrtm,only:ngptlw
 use parrrsw,only:ngptsw
 use rrlw_con,only:g4=>grav,a4=>avogad,hfaclw=>heatfac
 use rrsw_con,only:hfacsw=>heatfac
 use mo_gas_optics_constants,only:avogad
 use mo_rte_kind,only:wp
 implicit none
 character(1024)::data,input
 character(2)::phase
 integer::u,nl,nn,seed,k,icld,ng
 real::grav,cp,mol,solar,heatfac4,z1,z2,z3
 real,allocatable::p(:,:),pe(:,:),t(:,:),te(:,:),ts(:),emis(:,:),ev(:,:)
 real,allocatable::v(:,:,:),cf(:,:),lwp(:,:),rel(:,:),zero(:,:),md(:,:),mgas(:,:),coldry4(:,:)
 real,allocatable::cfm(:,:,:),lwm(:,:,:),zm(:,:,:),tm(:,:,:),sm(:,:,:),gm(:,:,:),fm(:,:,:)
 real,allocatable::ta(:,:,:),sa(:,:,:),ga(:,:,:),ea(:,:,:),extra(:,:)
 real,allocatable::up4(:,:),dn4(:,:),hr4(:,:),uc4(:,:),dc4(:,:),hc4(:,:),clean1(:,:),clean2(:,:)
 real,allocatable::up37(:,:),dn37(:,:),hr37(:,:),uc37(:,:),dc37(:,:),hc37(:,:)
 real,allocatable::avd(:),avf(:),and(:),anf(:),mu(:),direct(:,:),diffuse(:,:),directc(:,:),vd(:,:),vf(:,:),nd(:,:),nf(:,:)
 real(wp),allocatable::capacity(:,:)
 call get_command_argument(1,data);call get_command_argument(2,input)
 open(newunit=u,file=trim(input),status='old');read(u,*)phase,nl,nn,seed;read(u,*)grav,cp,mol,solar
 allocate(p(1,nl),pe(1,nl+1),t(1,nl),te(1,nl+1),ts(1),emis(1,1),ev(1,16),v(1,nl,6))
 allocate(cf(1,nl),lwp(1,nl),rel(1,nl),zero(1,nl),md(1,nn),mgas(1,nl),coldry4(1,nl),capacity(1,nn))
 allocate(avd(1),avf(1),and(1),anf(1),mu(1))
 read(u,*)p;read(u,*)pe;read(u,*)t;read(u,*)te;read(u,*)ts;read(u,*)emis
 do k=1,6;read(u,*)v(:,:,k);enddo
 read(u,*)cf;read(u,*)lwp;read(u,*)rel;read(u,*)md;read(u,*)capacity
 read(u,*)avd;read(u,*)avf;read(u,*)and;read(u,*)anf;read(u,*)mu;close(u)
 if(nl/=121.or.nn/=59)error stop 'unexpected comparison extent'
 if(any(cf/=0..and.cf/=1.))error stop 'deterministic CF0/1 required'
 if(any(lwp<0.).or.any(rel<2.5).or.any(rel>21.5))error stop 'unsupported liquid diagnostic'
 if(any(lwp>0..and.cf/=1.))error stop 'ambiguous cloud path'
 zero=0.;ev=emis(1,1)
 call rrtmg_lwlookuptable();call rrtmg_lw_ini(cp)
 call rrtmg_swlookuptable();call rrtmg_sw_ini(cp)
 call rrtmgp_init(trim(data),gravity=grav,cp_dry=cp,mol_weight_dry=mol)
 ! Same molecule count in the two gas routines; never overwrite host md.
 do k=1,nl
  coldry4(1,k)=(pe(1,k)-pe(1,k+1))*1.e3*a4/(1.e2*g4*((1.-v(1,k,1))*28.966+v(1,k,1)*18.016)*(1.+v(1,k,1)))
 enddo
 mgas=real(real(coldry4,wp)*(real(mol,wp)*10000._wp)/avogad)
 allocate(up4(1,nl+1),dn4(1,nl+1),hr4(1,nl),uc4(1,nl+1),dc4(1,nl+1),hc4(1,nl),clean1(1,nl+1),clean2(1,nl+1))
 allocate(up37(1,nl+1),dn37(1,nl+1),hr37(1,nl),uc37(1,nl+1),dc37(1,nl+1),hc37(1,nl))
 allocate(direct(1,nl+1),diffuse(1,nl+1),directc(1,nl+1),vd(1,nl+1),vf(1,nl+1),nd(1,nl+1),nf(1,nl+1))
 ng=ngptlw;if(phase=='SW')ng=ngptsw
 allocate(cfm(ng,1,nl),lwm(ng,1,nl),zm(ng,1,nl),tm(ng,1,nl),sm(ng,1,nl),gm(ng,1,nl),fm(ng,1,nl))
 do k=1,nl;cfm(:,1,k)=cf(1,k);lwm(:,1,k)=lwp(1,k);enddo
 zm=0.;tm=0.;sm=0.;gm=0.;fm=0.;icld=3
 call snapshot('before.bin')
 if(phase=='LW')then
  allocate(ta(1,nl,16));ta=0.
  call rrtmg4_export_begin('lw',1,6511,65100.,1,2)
  call rrtmg_lw(1,nl,icld,p,pe,t,te,ts,v(:,:,1),v(:,:,3),v(:,:,2),v(:,:,5),v(:,:,4),v(:,:,6), &
    zero,zero,zero,zero,ev,2,3,1,cfm,tm,zm,lwm,zm,rel,rel,rel,ta,up4,dn4,hr4,uc4,dc4,hc4,clean1,clean2,0)
  call rrtmg4_export_end();heatfac4=hfaclw
 else
  allocate(ta(1,nl,14),sa(1,nl,14),ga(1,nl,14),ea(1,nl,6),extra(1,nl+1));ta=0.;sa=0.;ga=0.;ea=0.
  call rrtmg4_export_begin('sw',1,6511,65100.,1,2,mu(1))
  call rrtmg_sw(1,nl,icld,p,pe,t,te,ts,v(:,:,1),v(:,:,3),v(:,:,2),v(:,:,5),v(:,:,4),v(:,:,6), &
    avd,avf,and,anf,mu,1.,0,solar,2,3,1,cfm,tm,sm,gm,fm,zm,lwm,zm,rel,rel,rel, &
    ta,sa,ga,ea,up4,dn4,hr4,uc4,dc4,hc4,clean1,clean2,0,vd,vf,nd,nf,direct,diffuse,directc,0,z1,z2,z3)
  call rrtmg4_export_end();heatfac4=hfacsw
 endif
 call snapshot('after4.bin')
 call trace_start(phase,1,1)
 if(phase=='LW')then
  call rrtmgp_lw_column(p,pe,t,te,ts,v(:,:,1),v(:,:,2),v(:,:,3),v(:,:,4),v(:,:,5),v(:,:,6),emis, &
    cf,lwp,zero,zero,rel,rel,rel,3,3,seed,up37,dn37,hr37,uc37,dc37,hc37,native_dry_layer_mass_kg_m2=mgas)
 else
  call rrtmgp_sw_column(p,pe,t,v(:,:,1),v(:,:,2),v(:,:,3),v(:,:,4),v(:,:,5),v(:,:,6), &
    avd,avf,and,anf,mu,solar,cf,lwp,zero,zero,rel,rel,rel,3,3,seed,up37,dn37,hr37,uc37,dc37,hc37, &
    direct,diffuse,directc,vd,vf,nd,nf,native_dry_layer_mass_kg_m2=mgas)
 endif
 call trace_end(phase);call snapshot('after37.bin')
 open(newunit=u,file='native4.txt',status='new')
 write(u,'(A)')'SAME_STATE_RRTMG4_V1';write(u,*)nl,nn;write(u,'(3ES25.17E3)')real(heatfac4,wp),real(g4,wp),real(cp,wp)
 call row(up4(1,:));call row(dn4(1,:));call row(hr4(1,:));call row(uc4(1,:));call row(dc4(1,:));call row(hc4(1,:))
 call row(coldry4(1,:));call row(mgas(1,:));write(u,'(*(ES25.17E3,1X))')capacity(1,:)
 close(u)
 print *,'SAME_STATE_BOTH_ENGINES_COMPLETE'
contains
 subroutine row(a)
 real,intent(in)::a(:)
 write(u,'(*(ES25.17E3,1X))')real(a,wp)
 end subroutine
 subroutine snapshot(name)
 character(*),intent(in)::name
 integer::f
 open(newunit=f,file=name,status='new',access='stream',form='unformatted')
 write(f)p,pe,t,te,ts,emis,v,cf,lwp,rel,md,mgas,capacity,avd,avf,and,anf,mu,solar,grav,cp,mol
 close(f)
 end subroutine
end program
