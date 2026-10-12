PROGRAM held_column
  USE module_ra_rrtmgp, ONLY: rrtmgp_init,rrtmgp_lw_column,rrtmgp_sw_column
  USE module_ra_rrtmgp_trace, ONLY: trace_start,trace_end
  IMPLICIT NONE
  CHARACTER(LEN=2048) :: data,input,line,magic,phase,name
  INTEGER :: u,ios,nc,nl,ov,seed,iceflag,n1,n2,n3,k,j,count,native
  REAL, ALLOCATABLE :: values(:),p(:,:),pe(:,:),t(:,:),te(:,:),ts(:),h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:)
  REAL, ALLOCATABLE :: cf(:,:),lwp(:,:),iwp(:,:),swp(:,:),rwp(:,:),rel(:,:),rei(:,:),res(:,:),md(:,:),emis(:,:)
  REAL, ALLOCATABLE :: cfc11(:,:),cfc12(:,:),cfc22(:,:),ccl4(:,:),avdir(:),avdif(:),andir(:),andif(:),mu(:)
  REAL, ALLOCATABLE :: up(:,:),dn(:,:),hr(:,:),upc(:,:),dnc(:,:),hrc(:,:),direct(:,:),diffuse(:,:),directc(:,:)
  REAL, ALLOCATABLE :: vd(:,:),vf(:,:),nd(:,:),nf(:,:),pred(:,:),predc(:,:),pv(:,:),pn(:,:)
  REAL :: gravity,cp,mw,solar
  CALL get_command_argument(1,data);CALL get_command_argument(2,input)
  OPEN(NEWUNIT=u,FILE=TRIM(input),STATUS='old')
  READ(u,*) magic;READ(u,*) phase,nc,nl,ov,seed,iceflag
  IF(nc/=1.OR.(phase/='LW'.AND.phase/='SW')) ERROR STOP 'held column shape/phase'
  native=59
  ALLOCATE(p(1,nl),pe(1,nl+1),t(1,nl),te(1,nl+1),ts(1),h2o(1,nl),co2(1,nl),o3(1,nl),n2o(1,nl),ch4(1,nl),o2(1,nl))
  ALLOCATE(cf(1,nl),lwp(1,nl),iwp(1,nl),swp(1,nl),rwp(1,nl),rel(1,nl),rei(1,nl),res(1,nl),md(1,native),emis(1,16))
  ALLOCATE(cfc11(1,nl),cfc12(1,nl),cfc22(1,nl),ccl4(1,nl),avdir(1),avdif(1),andir(1),andif(1),mu(1))
  gravity=9.81;cp=1004.5;mw=0.028964;solar=0.;emis=0.;cfc11=0.;cfc12=0.;cfc22=0.;ccl4=0.
  DO
    READ(u,'(A)',IOSTAT=ios) line
    IF(ios<0) EXIT
    IF(ios/=0) ERROR STOP 'input read'
    n3=1;READ(line,*,IOSTAT=ios) name,n1,n2,n3
    IF(ios/=0) THEN
      n3=1;READ(line,*,IOSTAT=ios) name,n1,n2
    END IF
    IF(ios/=0.OR.MIN(n1,n2,n3)<1) ERROR STOP 'record shape'
    count=n1*n2*n3;ALLOCATE(values(count))
    DO k=1,count
      READ(u,*,IOSTAT=ios) values(k)
      IF(ios/=0) ERROR STOP 'record values'
    END DO
    SELECT CASE(TRIM(name))
    CASE('PLAY');p=RESHAPE(values,SHAPE(p))
    CASE('PLEV');pe=RESHAPE(values,SHAPE(pe))
    CASE('TLAY');t=RESHAPE(values,SHAPE(t))
    CASE('TLEV');te=RESHAPE(values,SHAPE(te))
    CASE('TSFC');ts=values
    CASE('H2O');h2o=RESHAPE(values,SHAPE(h2o))
    CASE('CO2');co2=RESHAPE(values,SHAPE(co2))
    CASE('O3');o3=RESHAPE(values,SHAPE(o3))
    CASE('N2O');n2o=RESHAPE(values,SHAPE(n2o))
    CASE('CH4');ch4=RESHAPE(values,SHAPE(ch4))
    CASE('O2');o2=RESHAPE(values,SHAPE(o2))
    CASE('CF');cf=RESHAPE(values,SHAPE(cf))
    CASE('LWP');lwp=RESHAPE(values,SHAPE(lwp))
    CASE('IWP');iwp=RESHAPE(values,SHAPE(iwp))
    CASE('SWP');swp=RESHAPE(values,SHAPE(swp))
    CASE('RWP');rwp=RESHAPE(values,SHAPE(rwp))
    CASE('REL');rel=RESHAPE(values,SHAPE(rel))
    CASE('REI');rei=RESHAPE(values,SHAPE(rei))
    CASE('RES');res=RESHAPE(values,SHAPE(res))
    CASE('NATIVE_DRY_LAYER_MASS_KG_M2');md=RESHAPE(values,SHAPE(md))
    CASE('EMIS');emis=RESHAPE(values,[n1,n2])
    CASE('AVDIR');avdir=values
    CASE('AVDIF');avdif=values
    CASE('ANDIR');andir=values
    CASE('ANDIF');andif=values
    CASE('MU0');mu=values
    CASE('GRAVITY');gravity=values(1)
    CASE('CP_DRY');cp=values(1)
    CASE('MOL_WEIGHT_DRY');mw=values(1)
    CASE('SOLAR');solar=values(1)
    CASE('VMR_CFC11');cfc11=RESHAPE(values,SHAPE(cfc11))
    CASE('VMR_CFC12');cfc12=RESHAPE(values,SHAPE(cfc12))
    CASE('VMR_CFC22');cfc22=RESHAPE(values,SHAPE(cfc22))
    CASE('VMR_CCL4');ccl4=RESHAPE(values,SHAPE(ccl4))
    END SELECT
    DEALLOCATE(values)
  END DO
  CLOSE(u)
  CALL rrtmgp_init(TRIM(data),ice_roughness=1,gravity=gravity,cp_dry=cp,mol_weight_dry=mw,frozen_optics=0)
  CALL trace_start(TRIM(phase),1,1,1,2,1,2)
  ALLOCATE(up(1,nl+1),dn(1,nl+1),hr(1,nl),upc(1,nl+1),dnc(1,nl+1),hrc(1,nl))
  IF(phase=='LW') THEN
    CALL rrtmgp_lw_column(p,pe,t,te,ts,h2o,co2,o3,n2o,ch4,o2,emis,cf,lwp,iwp,swp,rel,rei,res,iceflag,ov,seed, &
         up,dn,hr,upc,dnc,hrc,rwp=rwp,native_dry_layer_mass_kg_m2=md,cfc11vmr=cfc11,cfc12vmr=cfc12,cfc22vmr=cfc22,ccl4vmr=ccl4)
  ELSE
    ALLOCATE(direct(1,nl+1),diffuse(1,nl+1),directc(1,nl+1),vd(1,nl+1),vf(1,nl+1),nd(1,nl+1),nf(1,nl+1))
    ALLOCATE(pred(1,nl+1),predc(1,nl+1),pv(1,nl+1),pn(1,nl+1))
    CALL rrtmgp_sw_column(p,pe,t,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu,solar,cf,lwp,iwp,swp,rel,rei,res, &
         iceflag,ov,seed,up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,vd,vf,nd,nf,rwp=rwp,native_dry_layer_mass_kg_m2=md, &
         direct_unscaled=pred,directc_unscaled=predc,visdir_unscaled=pv,nirdir_unscaled=pn)
  END IF
  CALL trace_end(TRIM(phase))
  PRINT *, 'SUCCESS HELD COLUMN'
END PROGRAM
