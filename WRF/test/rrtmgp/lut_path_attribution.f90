! Diagnostic caller of the unchanged public adapter. No optical extrapolation.
program lut_path_attribution
  use module_ra_rrtmgp, only: rrtmgp_init,rrtmgp_lw_column,rrtmgp_sw_column
  use module_ra_rrtmgp_trace, only: trace_start,trace_end
  use mo_rte_kind, only: wp
  implicit none
  character(1024) :: data,input
  character(2) :: phase
  integer :: u,nl,nn,seed,overlap,iceflag,rough
  real :: grav,cp,mol,solar
  real,allocatable :: play(:,:),plev(:,:),tlay(:,:),tlev(:,:),tsfc(:),emis(:,:)
  real,allocatable :: h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:),cfc11(:,:),cfc12(:,:),cfc22(:,:),ccl4(:,:)
  real,allocatable :: cf(:,:),lwp(:,:),iwp(:,:),swp(:,:),rwp(:,:),rel(:,:),rei(:,:),res(:,:),md(:,:),ul(:,:),ur(:,:)
  real,allocatable :: avdir(:),avdif(:),andir(:),andif(:),mu0(:)
  real,allocatable :: up(:,:),dn(:,:),hr(:,:),upc(:,:),dnc(:,:),hrc(:,:)
  real,allocatable :: direct(:,:),diffuse(:,:),directc(:,:),vd(:,:),vf(:,:),nd(:,:),nf(:,:),du(:,:),dcu(:,:),vu(:,:),nu(:,:)
  real(wp),allocatable :: capacity(:,:)
  call get_command_argument(1,data);call get_command_argument(2,input)
  open(newunit=u,file=trim(input),status='old')
  read(u,*) phase,nl,nn,seed,overlap,iceflag,rough
  read(u,*) grav,cp,mol,solar
  allocate(play(1,nl),plev(1,nl+1),tlay(1,nl),tlev(1,nl+1),tsfc(1),emis(1,1))
  allocate(h2o(1,nl),co2(1,nl),o3(1,nl),n2o(1,nl),ch4(1,nl),o2(1,nl))
  allocate(cfc11(1,nl),cfc12(1,nl),cfc22(1,nl),ccl4(1,nl))
  allocate(cf(1,nl),lwp(1,nl),iwp(1,nl),swp(1,nl),rwp(1,nl),rel(1,nl),rei(1,nl),res(1,nl))
  allocate(md(1,nn),ul(1,nl),ur(1,nl),capacity(1,nn))
  allocate(avdir(1),avdif(1),andir(1),andif(1),mu0(1))
  allocate(up(1,nl+1),dn(1,nl+1),hr(1,nl),upc(1,nl+1),dnc(1,nl+1),hrc(1,nl))
  allocate(direct(1,nl+1),diffuse(1,nl+1),directc(1,nl+1),vd(1,nl+1),vf(1,nl+1),nd(1,nl+1),nf(1,nl+1))
  allocate(du(1,nl+1),dcu(1,nl+1),vu(1,nl+1),nu(1,nl+1))
  read(u,*) play;read(u,*) plev;read(u,*) tlay;read(u,*) tlev;read(u,*) tsfc;read(u,*) emis
  read(u,*) h2o;read(u,*) co2;read(u,*) o3;read(u,*) n2o;read(u,*) ch4;read(u,*) o2
  read(u,*) cfc11;read(u,*) cfc12;read(u,*) cfc22;read(u,*) ccl4
  read(u,*) cf;read(u,*) lwp;read(u,*) iwp;read(u,*) swp;read(u,*) rwp
  read(u,*) rel;read(u,*) rei;read(u,*) res
  read(u,*) md;read(u,*) ul;read(u,*) ur;read(u,*) capacity
  read(u,*) avdir;read(u,*) avdif;read(u,*) andir;read(u,*) andif;read(u,*) mu0
  close(u)
  call rrtmgp_init(trim(data),ice_roughness=rough,gravity=grav,cp_dry=cp,mol_weight_dry=mol,uniform_clear_warm=.true.)
  call trace_start(phase,1,1)
  if(phase=='LW') then
    call rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis,cf,lwp,iwp,swp,rel,rei,res, &
      iceflag,overlap,seed,up,dn,hr,upc,dnc,hrc,rwp=rwp,native_dry_layer_mass_kg_m2=md, &
      cfc11vmr=cfc11,cfc12vmr=cfc12,cfc22vmr=cfc22,ccl4vmr=ccl4,uniform_lwp=ul,uniform_rwp=ur,native_heat_capacity=capacity)
  else
    call rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
      cf,lwp,iwp,swp,rel,rei,res,iceflag,overlap,seed,up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,vd,vf,nd,nf, &
      rwp=rwp,native_dry_layer_mass_kg_m2=md,direct_unscaled=du,directc_unscaled=dcu,visdir_unscaled=vu,nirdir_unscaled=nu, &
      uniform_lwp=ul,uniform_rwp=ur,native_heat_capacity=capacity)
  endif
  call trace_end(phase)
  print *, 'LUT_PATH_ATTRIBUTION_COMPLETE'
end program
