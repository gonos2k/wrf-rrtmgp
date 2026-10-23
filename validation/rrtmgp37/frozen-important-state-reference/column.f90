program frozen_state_column
 use module_ra_rrtmgp,only:rrtmgp_init,rrtmgp_lw_column
 use module_ra_rrtmgp_trace,only:trace_start,trace_end
 use reference_hail_hook,only:load_reference
 implicit none
 character(1024)::data,input,table,coefficients
 integer::u,nl,nn,seed,overlap,iceflag,rough
 real::grav,cp,mol
 real,allocatable::play(:,:),plev(:,:),tlay(:,:),tlev(:,:),tsfc(:),emis(:,:)
 real,allocatable::h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:),cfc11(:,:),cfc12(:,:),cfc22(:,:),ccl4(:,:)
 real,allocatable::cf(:,:),lwp(:,:),iwp(:,:),swp(:,:),rwp(:,:),rel(:,:),rei(:,:),res(:,:),md(:,:)
 real,allocatable::gwp(:,:),hwp(:,:),lg(:,:),lh(:,:),cl(:,:),ci(:,:),cr(:,:),cs(:,:),up(:,:),dn(:,:),hr(:,:),upc(:,:),dnc(:,:),hrc(:,:)
 call get_command_argument(1,data);call get_command_argument(2,input);call get_command_argument(3,table);call get_command_argument(4,coefficients)
 open(newunit=u,file=trim(input),status='old')
 read(u,*)nl,nn,seed,overlap,iceflag,rough
 read(u,*)grav,cp,mol
 allocate(play(1,nl),plev(1,nl+1),tlay(1,nl),tlev(1,nl+1),tsfc(1),emis(1,16))
 allocate(h2o(1,nl),co2(1,nl),o3(1,nl),n2o(1,nl),ch4(1,nl),o2(1,nl))
 allocate(cfc11(1,nl),cfc12(1,nl),cfc22(1,nl),ccl4(1,nl))
 allocate(cf(1,nl),lwp(1,nl),iwp(1,nl),swp(1,nl),rwp(1,nl),rel(1,nl),rei(1,nl),res(1,nl),md(1,nn))
 allocate(gwp(1,nl),hwp(1,nl),lg(1,nl),lh(1,nl),cl(1,nl),ci(1,nl),cr(1,nl),cs(1,nl))
 allocate(up(1,nl+1),dn(1,nl+1),hr(1,nl),upc(1,nl+1),dnc(1,nl+1),hrc(1,nl))
 read(u,*)play;read(u,*)plev;read(u,*)tlay;read(u,*)tlev;read(u,*)tsfc;read(u,*)emis
 read(u,*)h2o;read(u,*)co2;read(u,*)o3;read(u,*)n2o;read(u,*)ch4;read(u,*)o2
 read(u,*)cfc11;read(u,*)cfc12;read(u,*)cfc22;read(u,*)ccl4
 read(u,*)cf;read(u,*)lwp;read(u,*)iwp;read(u,*)swp;read(u,*)rwp
 read(u,*)rel;read(u,*)rei;read(u,*)res;read(u,*)md
 read(u,*)gwp;read(u,*)hwp;read(u,*)lg;read(u,*)lh
 read(u,*)cl;read(u,*)ci;read(u,*)cr;read(u,*)cs
 close(u)
 call rrtmgp_init(trim(data),ice_roughness=rough,gravity=grav,cp_dry=cp,mol_weight_dry=mol, &
 frozen_optics=1,frozen_table=trim(table),uniform_clear_warm=.false.)
 call load_reference(trim(coefficients));call trace_start('LW',1,1)
 call rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis,cf,lwp,iwp,swp,rel,rei,res, &
 iceflag,overlap,seed,up,dn,hr,upc,dnc,hrc,rwp=rwp,native_dry_layer_mass_kg_m2=md, &
 cfc11vmr=cfc11,cfc12vmr=cfc12,cfc22vmr=cfc22,ccl4vmr=ccl4, &
 gwp=gwp,hwp=hwp,lambda_g=lg,lambda_h=lh,frozen_context='actual selected hail source3000', &
 cu_lwp=cl,cu_iwp=ci,cu_rel=cr,cu_rei=cs)
 call trace_end('LW')
 print *,'ACTUAL_FROZEN_STATE_COLUMN_COMPLETE'
end program
