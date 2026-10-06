PROGRAM wp_probe_driver
  USE module_ra_rrtmgp, ONLY: rrtmgp_init,rrtmgp_lw_column,rrtmgp_release_workspace,ty_rrtmgp_lw_workspace,rrtmgp_lw_batch_size
  IMPLICIT NONE
  INTEGER,PARAMETER:: nc=32,nl=47,nm=39
  REAL::play(nc,nl),plev(nc,nl+1),tlay(nc,nl),tlev(nc,nl+1),tsfc(nc)
  REAL::h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl),emis(nc,16)
  REAL::cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl),rwp(nc,nl)
  REAL::native_mass(nc,nm),gwp(nc,nl),hwp(nc,nl),lambda_g(nc,nl),lambda_h(nc,nl)
  REAL::cfc11(nc,nl),cfc12(nc,nl),cfc22(nc,nl),ccl4(nc,nl)
  REAL::up(nc,nl+1),dn(nc,nl+1),hr(nc,nl),upc(nc,nl+1),dnc(nc,nl+1),hrc(nc,nl)
  INTEGER::seeds(nc),day,overlap,iceflag,u,ios,i,mode,nc_read,nl_read
  REAL::gravity,cp_dry,mol_weight_dry,seconds
  CHARACTER(1024)::fixture,datadir,table,modearg,outfile
  REAL::sp_play(1,nl),sp_plev(1,nl+1),sp_tlay(1,nl),sp_tlev(1,nl+1),sp_tsfc(1)
  REAL::sp_h2o(1,nl),sp_co2(1,nl),sp_o3(1,nl),sp_n2o(1,nl),sp_ch4(1,nl),sp_o2(1,nl),sp_emis(1,16)
  REAL::sp_cf(1,nl),sp_lwp(1,nl),sp_iwp(1,nl),sp_swp(1,nl),sp_rel(1,nl),sp_rei(1,nl),sp_res(1,nl),sp_rwp(1,nl)
  REAL::sp_native(1,nm),sp_gwp(1,nl),sp_hwp(1,nl),sp_lg(1,nl),sp_lh(1,nl)
  REAL::sp_cfc11(1,nl),sp_cfc12(1,nl),sp_cfc22(1,nl),sp_ccl4(1,nl)
  REAL::sp_up(1,nl+1),sp_dn(1,nl+1),sp_hr(1,nl),sp_upc(1,nl+1),sp_dnc(1,nl+1),sp_hrc(1,nl)
  TYPE(ty_rrtmgp_lw_workspace)::workspace
  CALL GET_COMMAND_ARGUMENT(1,fixture); CALL GET_COMMAND_ARGUMENT(2,datadir)
  CALL GET_COMMAND_ARGUMENT(3,table); CALL GET_COMMAND_ARGUMENT(4,modearg)
  CALL GET_COMMAND_ARGUMENT(5,outfile)
  IF(TRIM(modearg)=='batch32') THEN; mode=1; ELSE IF(TRIM(modearg)=='scalar32') THEN; mode=0; ELSE; ERROR STOP 'mode'; END IF
  OPEN(NEWUNIT=u,FILE=TRIM(fixture),ACCESS='STREAM',FORM='UNFORMATTED',STATUS='OLD',CONVERT='BIG_ENDIAN')
  READ(u) nc_read,nl_read,gravity,cp_dry,mol_weight_dry,seconds,overlap,iceflag,day,seeds
  IF(nc_read/=nc.OR.nl_read/=nl) ERROR STOP 'fixture shape mismatch'
  READ(u) play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis,cf,lwp,iwp,swp,rel,rei,res,rwp,native_mass,gwp,hwp,lambda_g,lambda_h,cfc11,cfc12,cfc22,ccl4
  CLOSE(u)
  CALL rrtmgp_init(TRIM(datadir),ice_roughness=1,gravity=gravity,cp_dry=cp_dry,mol_weight_dry=mol_weight_dry, &
       frozen_optics=1,frozen_table=TRIM(table))
  IF((mode==1.AND.rrtmgp_lw_batch_size()/=32).OR.(mode==0.AND.rrtmgp_lw_batch_size()/=1)) ERROR STOP 'batch mode selection mismatch'
  IF(mode==1) THEN
    CALL rrtmgp_lw_column(play=play,plev=plev,tlay=tlay,tlev=tlev,tsfc=tsfc,h2o=h2o,co2=co2,o3=o3,n2o=n2o,ch4=ch4,o2=o2,emis=emis, &
      cf=cf,lwp=lwp,iwp=iwp,swp=swp,rel=rel,rei=rei,res=res,iceflag=iceflag,overlap=overlap,seed=seeds(1), &
      column_seeds=seeds,up=up,dn=dn,hr=hr,upc=upc,dnc=dnc,hrc=hrc,rwp=rwp, &
      native_dry_layer_mass_kg_m2=native_mass,gwp=gwp,hwp=hwp,lambda_g=lambda_g,lambda_h=lambda_h, &
      cfc11vmr=cfc11,cfc12vmr=cfc12,cfc22vmr=cfc22,ccl4vmr=ccl4,frozen_context='UDM27',workspace=workspace)
  ELSE
    DO i=1,nc
      sp_play=play(i:i,:); sp_plev=plev(i:i,:); sp_tlay=tlay(i:i,:); sp_tlev=tlev(i:i,:); sp_tsfc=tsfc(i:i)
      sp_h2o=h2o(i:i,:); sp_co2=co2(i:i,:); sp_o3=o3(i:i,:); sp_n2o=n2o(i:i,:); sp_ch4=ch4(i:i,:); sp_o2=o2(i:i,:)
      sp_emis=emis(i:i,:); sp_cf=cf(i:i,:); sp_lwp=lwp(i:i,:); sp_iwp=iwp(i:i,:); sp_swp=swp(i:i,:)
      sp_rel=rel(i:i,:); sp_rei=rei(i:i,:); sp_res=res(i:i,:); sp_rwp=rwp(i:i,:); sp_native=native_mass(i:i,:)
      sp_gwp=gwp(i:i,:); sp_hwp=hwp(i:i,:); sp_lg=lambda_g(i:i,:); sp_lh=lambda_h(i:i,:)
      sp_cfc11=cfc11(i:i,:); sp_cfc12=cfc12(i:i,:); sp_cfc22=cfc22(i:i,:); sp_ccl4=ccl4(i:i,:)
      CALL rrtmgp_lw_column(play=sp_play,plev=sp_plev,tlay=sp_tlay,tlev=sp_tlev,tsfc=sp_tsfc,h2o=sp_h2o,co2=sp_co2, &
       o3=sp_o3,n2o=sp_n2o,ch4=sp_ch4,o2=sp_o2,emis=sp_emis,cf=sp_cf,lwp=sp_lwp,iwp=sp_iwp,swp=sp_swp, &
       rel=sp_rel,rei=sp_rei,res=sp_res,iceflag=iceflag,overlap=overlap,seed=seeds(i),up=sp_up,dn=sp_dn,hr=sp_hr, &
       upc=sp_upc,dnc=sp_dnc,hrc=sp_hrc,rwp=sp_rwp,native_dry_layer_mass_kg_m2=sp_native,gwp=sp_gwp,hwp=sp_hwp, &
       lambda_g=sp_lg,lambda_h=sp_lh,cfc11vmr=sp_cfc11,cfc12vmr=sp_cfc12,cfc22vmr=sp_cfc22,ccl4vmr=sp_ccl4, &
       frozen_context='UDM27',workspace=workspace)
      up(i,:)=sp_up(1,:); dn(i,:)=sp_dn(1,:); hr(i,:)=sp_hr(1,:)
      upc(i,:)=sp_upc(1,:); dnc(i,:)=sp_dnc(1,:); hrc(i,:)=sp_hrc(1,:)
    END DO
  END IF
  OPEN(NEWUNIT=u,FILE=TRIM(outfile),ACCESS='STREAM',FORM='UNFORMATTED',STATUS='NEW',CONVERT='BIG_ENDIAN')
  WRITE(u) up,dn,hr,upc,dnc,hrc
  CLOSE(u)
  CALL rrtmgp_release_workspace(workspace)
END PROGRAM
SUBROUTINE wrf_error_fatal3(file,line,message)
  CHARACTER(*),INTENT(IN)::file,message
  INTEGER,INTENT(IN)::line
  WRITE(*,*) 'FATAL ',TRIM(file),line,TRIM(message)
  ERROR STOP 2
END SUBROUTINE
