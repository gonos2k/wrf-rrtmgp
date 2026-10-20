! Standalone client linked only with pinned upstream RTE+RRTMGP, not WRF/vendor modules.
program direct
 use mo_rte_kind,only:wp
 use mo_gas_optics_constants,only:init_constants,avogad
 use mo_optical_props,only:ty_optical_props_1scl,ty_optical_props_2str
 use mo_gas_optics_rrtmgp,only:ty_gas_optics_rrtmgp
 use mo_gas_concentrations,only:ty_gas_concs
 use mo_source_functions,only:ty_source_func_lw
 use mo_rte_lw,only:rte_lw
 use mo_rte_sw,only:rte_sw
 use mo_fluxes,only:ty_fluxes_broadband
 use mo_load_coefficients,only:load_and_init
 implicit none
 type(ty_gas_optics_rrtmgp)::gas
 type(ty_gas_concs)::gases
 type(ty_optical_props_1scl)::lw
 type(ty_optical_props_2str)::sw
 type(ty_source_func_lw)::source
 type(ty_fluxes_broadband)::flux
 character(32),parameter::names(11)=[character(32)::'h2o','co2','o3','n2o','ch4','o2','cfc11','cfc12','cfc22','ccl4','n2']
 character(1024)::data,input,bridge
 character(2)::phase
 character(100)::magic
 integer::u,nl,nn,seed,k,nb,ng
 real::grav,cp,mol,solar
 real,allocatable::p(:,:),pe(:,:),t(:,:),te(:,:),ts(:),em(:,:),v(:,:,:),cf(:,:),path(:,:),rel(:,:),md(:,:),mgas(:,:)
 real::avd,avf,andir,anf,mu
 real(wp),allocatable::cap(:,:),col(:,:),toa(:,:),ed(:,:),ef(:,:),band(:,:),vis(:)
 real(wp),target,allocatable::up(:,:),dn(:,:),dir(:,:)
 call get_command_argument(1,data);call get_command_argument(2,input);call get_command_argument(3,bridge)
 open(newunit=u,file=trim(input),status='old');read(u,*)phase,nl,nn,seed;read(u,*)grav,cp,mol,solar
 if(nl/=121.or.nn/=59)error stop 'extent'
 allocate(p(1,nl),pe(1,nl+1),t(1,nl),te(1,nl+1),ts(1),em(1,1),v(1,nl,6),cf(1,nl),path(1,nl),rel(1,nl))
 allocate(md(1,nn),mgas(1,nl),cap(1,nn),col(1,nl),up(1,nl+1),dn(1,nl+1),dir(1,nl+1))
 read(u,*)p;read(u,*)pe;read(u,*)t;read(u,*)te;read(u,*)ts;read(u,*)em
 do k=1,6;read(u,*)v(:,:,k);enddo
 read(u,*)cf;read(u,*)path;read(u,*)rel;read(u,*)md;read(u,*)cap
 read(u,*)avd;read(u,*)avf;read(u,*)andir;read(u,*)anf;read(u,*)mu;close(u)
 if(any(cf/=0.).or.any(path/=0.))error stop 'clear only'
 open(newunit=u,file=trim(bridge),status='old');read(u,'(A)')magic
 do k=1,9;read(u,*);enddo
 read(u,*)mgas;close(u)
 if(phase=="LW")then
  call check(gases%init(names))
 else
  call check(gases%init(names(:6)))
 endif
 do k=1,6;call check(gases%set_vmr(trim(names(k)),real(v(:,:,k),wp)));enddo
 if(phase=='LW')then
 do k=7,10;call check(gases%set_vmr(trim(names(k)),0._wp));enddo
 call check(gases%set_vmr('n2',0.7808_wp))
 endif
 call init_constants(real(grav,wp),real(mol,wp),real(cp,wp))
 col=real(mgas,wp)*(avogad/(real(mol,wp)*10000._wp))
 if(phase=='LW')then
  call load_and_init(gas,trim(data)//'/rrtmgp-gas-lw-g128.nc',gases)
  call check(lw%alloc_1scl(1,nl,gas));call check(source%alloc(1,nl,gas))
  call check(gas%gas_optics(real(p,wp)*100._wp,real(pe,wp)*100._wp,real(t,wp),real(ts,wp),gases,lw,source,col_dry=col,tlev=real(te,wp)))
  nb=gas%get_nband();allocate(ed(nb,1));ed=real(em(1,1),wp)
  flux%flux_up=>up;flux%flux_dn=>dn
  call check(rte_lw(lw,.false.,source,ed,flux))
  open(newunit=u,file='source.dat',status='new')
  write(u,*)nl,gas%get_ngpt()
  write(u,'(*(ES25.17E3,1X))')lw%tau
  write(u,'(*(ES25.17E3,1X))')source%lay_source
  write(u,'(*(ES25.17E3,1X))')source%lev_source
  write(u,'(*(ES25.17E3,1X))')source%sfc_source
  write(u,'(*(ES25.17E3,1X))')gas%get_band_lims_wavenumber()
  close(u)
 else
  call load_and_init(gas,trim(data)//'/rrtmgp-gas-sw-g112.nc',gases)
  call check(sw%alloc_2str(1,nl,gas));ng=gas%get_ngpt();nb=gas%get_nband()
  allocate(toa(1,ng),ed(nb,1),ef(nb,1),band(2,nb),vis(nb))
  call check(gas%gas_optics(real(p,wp)*100._wp,real(pe,wp)*100._wp,real(t,wp),gases,sw,toa,col_dry=col))
  open(newunit=u,file='optics.dat',status='new')
  write(u,'(*(ES25.17E3,1X))')sw%tau
  write(u,'(*(ES25.17E3,1X))')sw%ssa
  write(u,'(*(ES25.17E3,1X))')sw%g
  close(u)
  toa=toa*(real(solar,wp)/sum(toa))
  band=gas%get_band_lims_wavenumber()
  do k=1,nb
   if(band(2,k)<=12850._wp)then
    vis(k)=0
   else if(band(1,k)>=16000._wp)then
    vis(k)=1
   else if(band(1,k)==12850._wp.and.band(2,k)==16000._wp)then
    vis(k)=0.5_wp
   else
    error stop "partition"
   endif
  enddo
  ed(:,1)=(1-vis)*real(andir,wp)+vis*real(avd,wp)
  ef(:,1)=(1-vis)*real(anf,wp)+vis*real(avf,wp)
  flux%flux_up=>up;flux%flux_dn=>dn;flux%flux_dn_dir=>dir
  call check(rte_sw(sw,.false.,[real(mu,wp)],toa,ed,ef,flux))
 endif
 open(newunit=u,file='flux.dat',status='new');write(u,'(*(ES25.17E3,1X))')up
 write(u,'(*(ES25.17E3,1X))')dn;write(u,'(*(ES25.17E3,1X))')col;close(u)
 print *,'DIRECT_UPSTREAM_COMPLETE'
contains
 subroutine check(err)
 character(*),intent(in)::err
 if(len_trim(err)>0)then
 print *,trim(err);error stop 1
 endif
 end subroutine
end program
