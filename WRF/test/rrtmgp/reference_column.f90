PROGRAM rrtmgp_reference_column
  USE mo_rte_kind, ONLY: wp,i8
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE mo_gas_concentrations, ONLY: ty_gas_concs
  USE mo_gas_optics_rrtmgp, ONLY: ty_gas_optics_rrtmgp
  USE mo_cloud_optics_rrtmgp, ONLY: ty_cloud_optics_rrtmgp
  USE mo_optical_props, ONLY: ty_optical_props_1scl,ty_optical_props_2str
  USE mo_source_functions, ONLY: ty_source_func_lw
  USE mo_fluxes, ONLY: ty_fluxes_broadband
  USE mo_fluxes_byband, ONLY: ty_fluxes_byband
  USE mo_rte_lw, ONLY: rte_lw
  USE mo_rte_sw, ONLY: rte_sw
  USE mo_heating_rates, ONLY: compute_heating_rate
  USE mo_cloud_sampling, ONLY: draw_samples
  USE mo_load_coefficients, ONLY: load_and_init
  USE mo_load_cloud_coefficients, ONLY: load_cld_lutcoeff
  IMPLICIT NONE

  CHARACTER(LEN=512) :: data_dir,input_path,output_path
  CHARACTER(LEN=32) :: magic,phase
  INTEGER :: nc,nl,overlap,seed,iceflag,u_in,u_out,ios,nemis
  INTEGER :: c,k,g,b,ngpt,nbnd
  REAL(wp) :: solar,roughness_value,partition_value,visible_weight
  INTEGER :: ice_roughness
  REAL(wp), ALLOCATABLE :: play(:,:),plev(:,:),tlay(:,:),tlev(:,:),tsfc(:,:)
  REAL(wp), ALLOCATABLE :: h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:)
  REAL(wp), ALLOCATABLE :: emis_in(:,:),cf(:,:),lwp(:,:),iwp(:,:),swp(:,:)
  REAL(wp), ALLOCATABLE :: rel(:,:),rei(:,:),res(:,:),avdir_in(:,:),avdif_in(:,:)
  REAL(wp), ALLOCATABLE :: andir_in(:,:),andif_in(:,:),mu0_in(:,:)
  REAL(wp), ALLOCATABLE :: emissivity(:,:),avdir(:),avdif(:),andir(:),andif(:),mu0(:),albdir(:,:),albdif(:,:)
  REAL(wp), ALLOCATABLE :: zero(:,:),rl(:,:),di(:,:),ds(:,:),toa(:,:)
  REAL(wp), ALLOCATABLE :: gas_tau(:,:,:),gas_ssa(:,:,:),gas_g(:,:,:)
  REAL(wp), ALLOCATABLE :: mask_values(:,:,:)
  REAL(wp), ALLOCATABLE :: cloud_tau(:,:,:),cloud_ssa(:,:,:),cloud_g(:,:,:)
  REAL(wp), ALLOCATABLE :: prepared_tau(:,:,:),prepared_ssa(:,:,:),prepared_g(:,:,:)
  LOGICAL, ALLOCATABLE :: mask(:,:,:)
  REAL(wp), ALLOCATABLE :: randoms(:,:,:),local_random(:)
  REAL(wp), ALLOCATABLE, TARGET :: fu(:,:),fd(:,:),fdir(:,:)
  REAL(wp), ALLOCATABLE :: heat(:,:)
  REAL(wp), ALLOCATABLE :: up_all(:,:),dn_all(:,:),hr_all(:,:)
  REAL(wp), ALLOCATABLE :: up_clear(:,:),dn_clear(:,:),hr_clear(:,:)
  REAL(wp), ALLOCATABLE :: direct_all(:,:),diffuse_all(:,:),direct_clear(:,:)
  REAL(wp), ALLOCATABLE :: visdir(:,:),visdif(:,:),nirdir(:,:),nirdif(:,:)
  REAL(wp), ALLOCATABLE :: bands(:,:)
  REAL(wp), ALLOCATABLE, TARGET :: flux_band_dn(:,:,:),flux_band_dir(:,:,:)
  INTEGER(i8) :: rng_state
  TYPE(ty_gas_concs) :: gases
  TYPE(ty_gas_optics_rrtmgp) :: gas_lw,gas_sw
  TYPE(ty_cloud_optics_rrtmgp) :: cloud_lw,cloud_sw
  TYPE(ty_optical_props_1scl) :: lw_atmos,lw_cloud,lw_snow,lw_sampled
  TYPE(ty_optical_props_2str) :: sw_atmos,sw_cloud,sw_snow,sw_sampled
  TYPE(ty_source_func_lw) :: lw_source
  TYPE(ty_fluxes_broadband) :: lw_flux
  TYPE(ty_fluxes_byband) :: sw_flux
  CHARACTER(LEN=128) :: err
  CHARACTER(LEN=3), PARAMETER :: gas_names(6)=['h2o','co2','o3 ','n2o','ch4','o2 ']

  CALL get_command_argument(1,data_dir)
  CALL get_command_argument(2,input_path)
  CALL get_command_argument(3,output_path)
  IF(LEN_TRIM(data_dir)==0 .OR. LEN_TRIM(input_path)==0 .OR. LEN_TRIM(output_path)==0) &
    ERROR STOP 'usage: reference_column DATA_DIR INPUT_FILE OUTPUT_FILE'
  OPEN(NEWUNIT=u_in,FILE=TRIM(input_path),STATUS='OLD',ACTION='READ',IOSTAT=ios)
  IF(ios/=0) ERROR STOP 'could not open reference input file'
  READ(u_in,*,IOSTAT=ios) magic
  IF(ios/=0) ERROR STOP 'invalid replay input magic'
  IF(TRIM(magic)/='RRTMGP_REPLAY_V1'.AND.TRIM(magic)/='RRTMGP_REPLAY_V2'.AND. &
     TRIM(magic)/='RRTMGP_REPLAY_V3') &
    ERROR STOP 'invalid replay input magic'
  READ(u_in,*,IOSTAT=ios) phase,nc,nl,overlap,seed,iceflag
  IF(ios/=0 .OR. (TRIM(phase)/='LW' .AND. TRIM(phase)/='SW')) ERROR STOP 'invalid replay header'
  IF(nc<1 .OR. nl<1) ERROR STOP 'replay dimensions must be positive'

  ALLOCATE(play(nc,nl),plev(nc,nl+1),tlay(nc,nl),tlev(nc,nl+1),tsfc(nc,1))
  ALLOCATE(h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl))
  ALLOCATE(emis_in(nc,16),cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl))
  ALLOCATE(rel(nc,nl),rei(nc,nl),res(nc,nl),avdir_in(nc,1),avdif_in(nc,1))
  ALLOCATE(andir_in(nc,1),andif_in(nc,1),mu0_in(nc,1))
  CALL read_scalar_section(u_in,'SOLAR',solar)
  CALL read_section(u_in,'PLAY',play)
  CALL read_section(u_in,'PLEV',plev)
  CALL read_section(u_in,'TLAY',tlay)
  CALL read_section(u_in,'TLEV',tlev)
  CALL read_section(u_in,'TSFC',tsfc)
  CALL read_section(u_in,'H2O',h2o)
  CALL read_section(u_in,'CO2',co2)
  CALL read_section(u_in,'O3',o3)
  CALL read_section(u_in,'N2O',n2o)
  CALL read_section(u_in,'CH4',ch4)
  CALL read_section(u_in,'O2',o2)
  CALL read_section_flexible(u_in,'EMIS',emis_in,nemis)
  CALL read_section(u_in,'AVDIR',avdir_in)
  CALL read_section(u_in,'AVDIF',avdif_in)
  CALL read_section(u_in,'ANDIR',andir_in)
  CALL read_section(u_in,'ANDIF',andif_in)
  CALL read_section(u_in,'MU0',mu0_in)
  CALL read_section(u_in,'CF',cf)
  CALL read_section(u_in,'LWP',lwp)
  CALL read_section(u_in,'IWP',iwp)
  CALL read_section(u_in,'SWP',swp)
  CALL read_section(u_in,'REL',rel)
  CALL read_section(u_in,'REI',rei)
  CALL read_section(u_in,'RES',res)
  ice_roughness=1
  IF(TRIM(magic)/='RRTMGP_REPLAY_V1') THEN
    CALL read_scalar_section(u_in,'ICE_ROUGHNESS',roughness_value)
    IF(.NOT.ieee_is_finite(roughness_value)) ERROR STOP 'non-finite ice roughness'
    IF(roughness_value<1._wp.OR.roughness_value>3._wp) ERROR STOP 'invalid ice roughness'
    ice_roughness=INT(roughness_value)
    IF(REAL(ice_roughness,wp)/=roughness_value) ERROR STOP 'ice roughness must be integer'
  END IF
  IF(TRIM(magic)=='RRTMGP_REPLAY_V3'.AND.TRIM(phase)=='SW') THEN
    CALL read_scalar_section(u_in,'SW_BAND_PARTITION',partition_value)
    IF(.NOT.ieee_is_finite(partition_value)) ERROR STOP 'non-finite SW band partition'
    IF(partition_value/=1._wp) ERROR STOP 'V3 requires SW_BAND_PARTITION=1 (CCPP transition)'
  END IF
  CLOSE(u_in)

  ALLOCATE(emissivity(16,nc),avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc))
  ALLOCATE(zero(nc,nl),rl(nc,nl),di(nc,nl),ds(nc,nl))
  zero=0._wp
  IF(nemis==1) THEN
    emissivity=SPREAD(emis_in(:,1),1,16)
  ELSE IF(nemis==16) THEN
    emissivity=TRANSPOSE(emis_in)
  ELSE
    ERROR STOP 'EMIS section must be grey or have 16 bands'
  END IF
  avdir=avdir_in(:,1); avdif=avdif_in(:,1); andir=andir_in(:,1); andif=andif_in(:,1)
  mu0=mu0_in(:,1)
  CALL check_error(gases%init(gas_names))
  CALL load_and_init(gas_lw,TRIM(data_dir)//'/rrtmgp-gas-lw-g128.nc',gases)
  CALL load_and_init(gas_sw,TRIM(data_dir)//'/rrtmgp-gas-sw-g112.nc',gases)
  CALL load_cld_lutcoeff(cloud_lw,TRIM(data_dir)//'/rrtmgp-clouds-lw-bnd.nc')
  CALL load_cld_lutcoeff(cloud_sw,TRIM(data_dir)//'/rrtmgp-clouds-sw-bnd.nc')
  CALL check_error(cloud_lw%set_ice_roughness(ice_roughness))
  CALL check_error(cloud_sw%set_ice_roughness(ice_roughness))
  CALL check_error(gases%init(gas_names))
  CALL check_error(gases%set_vmr('h2o',h2o))
  CALL check_error(gases%set_vmr('co2',co2))
  CALL check_error(gases%set_vmr('o3',o3))
  CALL check_error(gases%set_vmr('n2o',n2o))
  CALL check_error(gases%set_vmr('ch4',ch4))
  CALL check_error(gases%set_vmr('o2',o2))

  ALLOCATE(up_all(nc,nl+1),dn_all(nc,nl+1),hr_all(nc,nl))
  ALLOCATE(up_clear(nc,nl+1),dn_clear(nc,nl+1),hr_clear(nc,nl))
  ALLOCATE(fu(nc,nl+1),fd(nc,nl+1),heat(nc,nl))
  IF(TRIM(phase)=='LW') THEN
    ALLOCATE(gas_tau(nc,nl,gas_lw%get_ngpt()),cloud_tau(nc,nl,cloud_lw%get_nband()))
    ALLOCATE(mask(nc,nl,gas_lw%get_ngpt()),randoms(gas_lw%get_ngpt(),nl,nc))
    ALLOCATE(local_random(gas_lw%get_ngpt()))
    CALL check_error(lw_atmos%alloc_1scl(nc,nl,gas_lw))
    CALL check_error(lw_cloud%alloc_1scl(nc,nl,cloud_lw))
    CALL check_error(lw_snow%alloc_1scl(nc,nl,cloud_lw))
    CALL check_error(lw_sampled%alloc_1scl(nc,nl,gas_lw))
    CALL check_error(lw_source%alloc(nc,nl,gas_lw))
    CALL check_error(gas_lw%gas_optics(play*100._wp,plev*100._wp,tlay,tsfc(:,1),gases, &
                                      lw_atmos,lw_source,tlev=tlev))
    gas_tau=lw_atmos%tau
    emissivity=MAX(0._wp,MIN(1._wp,emissivity))
    lw_flux%flux_up=>fu; lw_flux%flux_dn=>fd
    CALL check_error(rte_lw(lw_atmos,.FALSE.,lw_source,emissivity,lw_flux))
    up_clear=fu; dn_clear=fd
    CALL check_error(compute_heating_rate(fu,fd,plev*100._wp,heat))
    hr_clear=heat*86400._wp
    rl=MAX(cloud_lw%get_min_radius_liq(),MIN(cloud_lw%get_max_radius_liq(),rel))
    di=MAX(cloud_lw%get_min_radius_ice(),MIN(cloud_lw%get_max_radius_ice(),ice_diameter(rei,iceflag)))
    ds=MAX(cloud_lw%get_min_radius_ice(),MIN(cloud_lw%get_max_radius_ice(),2._wp*res))
    CALL check_error(cloud_lw%cloud_optics(lwp,iwp,rl,di,lw_cloud))
    CALL check_error(cloud_lw%cloud_optics(zero,swp,rl,ds,lw_snow))
    CALL check_error(lw_snow%increment(lw_cloud))
    cloud_tau=lw_cloud%tau
    ALLOCATE(prepared_tau(nc,nl,cloud_lw%get_nband()))
    prepared_tau=lw_cloud%tau
    CALL make_mask(cf,gas_lw%get_ngpt(),overlap,seed,mask,randoms,local_random)
    IF(ANY(cf>0._wp) .AND. overlap/=0) THEN
      CALL check_error(draw_samples(mask,lw_cloud,lw_sampled))
      CALL check_error(lw_sampled%increment(lw_atmos))
    END IF
    CALL check_error(rte_lw(lw_atmos,.FALSE.,lw_source,emissivity,lw_flux))
    up_all=fu; dn_all=fd
    CALL check_error(compute_heating_rate(fu,fd,plev*100._wp,heat))
    hr_all=heat*86400._wp
  ELSE
    ALLOCATE(gas_tau(nc,nl,gas_sw%get_ngpt()),gas_ssa(nc,nl,gas_sw%get_ngpt()),gas_g(nc,nl,gas_sw%get_ngpt()))
    ALLOCATE(cloud_tau(nc,nl,cloud_sw%get_nband()),cloud_ssa(nc,nl,cloud_sw%get_nband()), &
             cloud_g(nc,nl,cloud_sw%get_nband()))
    ALLOCATE(prepared_tau(nc,nl,cloud_sw%get_nband()),prepared_ssa(nc,nl,cloud_sw%get_nband()), &
             prepared_g(nc,nl,cloud_sw%get_nband()))
    ALLOCATE(mask(nc,nl,gas_sw%get_ngpt()),randoms(gas_sw%get_ngpt(),nl,nc))
    ALLOCATE(local_random(gas_sw%get_ngpt()),toa(nc,gas_sw%get_ngpt()))
    ALLOCATE(direct_all(nc,nl+1),diffuse_all(nc,nl+1),direct_clear(nc,nl+1))
    ALLOCATE(fdir(nc,nl+1))
    ALLOCATE(visdir(nc,nl+1),visdif(nc,nl+1),nirdir(nc,nl+1),nirdif(nc,nl+1))
    ALLOCATE(bands(2,gas_sw%get_nband()),flux_band_dn(nc,nl+1,gas_sw%get_nband()), &
             flux_band_dir(nc,nl+1,gas_sw%get_nband()))
    ALLOCATE(albdir(gas_sw%get_nband(),nc),albdif(gas_sw%get_nband(),nc))
    CALL check_error(sw_atmos%alloc_2str(nc,nl,gas_sw))
    CALL check_error(sw_cloud%alloc_2str(nc,nl,cloud_sw))
    CALL check_error(sw_snow%alloc_2str(nc,nl,cloud_sw))
    CALL check_error(sw_sampled%alloc_2str(nc,nl,gas_sw))
    CALL check_error(gas_sw%gas_optics(play*100._wp,plev*100._wp,tlay,gases,sw_atmos,toa))
    gas_tau=sw_atmos%tau; gas_ssa=sw_atmos%ssa; gas_g=sw_atmos%g
    DO c=1,nc
      IF(SUM(toa(c,:))<=0._wp) ERROR STOP 'TOA solar spectrum integral must be positive'
      toa(c,:)=toa(c,:)*(REAL(solar,wp)/SUM(toa(c,:)))
    END DO
    bands=gas_sw%get_band_lims_wavenumber()
    DO b=1,gas_sw%get_nband()
      IF(TRIM(magic)=='RRTMGP_REPLAY_V3'.AND.bands(1,b)==12850._wp) THEN
        IF(bands(2,b)/=16000._wp) ERROR STOP 'unexpected transition-band upper limit'
        albdir(b,:)=0.5_wp*(andir+avdir); albdif(b,:)=0.5_wp*(andif+avdif)
      ELSE IF(bands(1,b)>=12850._wp) THEN
        albdir(b,:)=avdir; albdif(b,:)=avdif
      ELSE
        albdir(b,:)=andir; albdif(b,:)=andif
      END IF
    END DO
    sw_flux%flux_up=>fu; sw_flux%flux_dn=>fd; sw_flux%flux_dn_dir=>fdir
    sw_flux%bnd_flux_dn=>flux_band_dn; sw_flux%bnd_flux_dn_dir=>flux_band_dir
    CALL check_error(rte_sw(sw_atmos,.FALSE.,mu0,toa,albdir,albdif,sw_flux))
    up_clear=fu; dn_clear=fd; direct_clear=fdir
    CALL check_error(compute_heating_rate(fu,fd,plev*100._wp,heat))
    hr_clear=heat*86400._wp
    rl=MAX(cloud_sw%get_min_radius_liq(),MIN(cloud_sw%get_max_radius_liq(),rel))
    di=MAX(cloud_sw%get_min_radius_ice(),MIN(cloud_sw%get_max_radius_ice(),ice_diameter(rei,iceflag)))
    ds=MAX(cloud_sw%get_min_radius_ice(),MIN(cloud_sw%get_max_radius_ice(),2._wp*res))
    CALL check_error(cloud_sw%cloud_optics(lwp,iwp,rl,di,sw_cloud))
    CALL check_error(cloud_sw%cloud_optics(zero,swp,rl,ds,sw_snow))
    CALL check_error(sw_snow%increment(sw_cloud))
    cloud_tau=sw_cloud%tau; cloud_ssa=sw_cloud%ssa; cloud_g=sw_cloud%g
    CALL check_error(sw_cloud%delta_scale())
    prepared_tau=sw_cloud%tau; prepared_ssa=sw_cloud%ssa; prepared_g=sw_cloud%g
    CALL make_mask(cf,gas_sw%get_ngpt(),overlap,seed,mask,randoms,local_random)
    IF(ANY(cf>0._wp) .AND. overlap/=0) THEN
      CALL check_error(draw_samples(mask,sw_cloud,sw_sampled))
      CALL check_error(sw_sampled%increment(sw_atmos))
    END IF
    CALL check_error(rte_sw(sw_atmos,.FALSE.,mu0,toa,albdir,albdif,sw_flux))
    up_all=fu; dn_all=fd; direct_all=fdir; diffuse_all=fd-fdir
    CALL check_error(compute_heating_rate(fu,fd,plev*100._wp,heat))
    hr_all=heat*86400._wp
    visdir=0._wp; visdif=0._wp; nirdir=0._wp; nirdif=0._wp
    DO b=1,gas_sw%get_nband()
      visible_weight=MERGE(1._wp,0._wp,bands(1,b)>=12850._wp)
      IF(TRIM(magic)=='RRTMGP_REPLAY_V3'.AND.bands(1,b)==12850._wp) visible_weight=0.5_wp
      visdir=visdir+visible_weight*flux_band_dir(:,:,b)
      visdif=visdif+visible_weight*(flux_band_dn(:,:,b)-flux_band_dir(:,:,b))
      nirdir=nirdir+(1._wp-visible_weight)*flux_band_dir(:,:,b)
      nirdif=nirdif+(1._wp-visible_weight)*(flux_band_dn(:,:,b)-flux_band_dir(:,:,b))
    END DO
  END IF

  ALLOCATE(mask_values(nc,nl,SIZE(mask,3)))
  WHERE(mask)
    mask_values=1._wp
  ELSEWHERE
    mask_values=0._wp
  END WHERE

  OPEN(NEWUNIT=u_out,FILE=TRIM(output_path),STATUS='REPLACE',ACTION='WRITE',IOSTAT=ios)
  IF(ios/=0) ERROR STOP 'could not open reference output file'
  WRITE(u_out,'(A)') 'RRTMGP_RESULT_V1'
  WRITE(u_out,'(A,1X,I0,1X,I0)') TRIM(phase),nc,nl
  CALL write3(u_out,'GAS_TAU',gas_tau)
  IF(TRIM(phase)=='SW') THEN
    CALL write3(u_out,'GAS_SSA',gas_ssa); CALL write3(u_out,'GAS_G',gas_g)
  END IF
  CALL write3(u_out,'CLOUD_TAU',cloud_tau)
  IF(TRIM(phase)=='SW') THEN
    CALL write3(u_out,'CLOUD_SSA',cloud_ssa); CALL write3(u_out,'CLOUD_G',cloud_g)
  END IF
  CALL write3(u_out,'PREPARED_TAU',prepared_tau)
  IF(TRIM(phase)=='SW') THEN
    CALL write3(u_out,'PREPARED_SSA',prepared_ssa); CALL write3(u_out,'PREPARED_G',prepared_g)
  END IF
  CALL write3(u_out,'MASK',mask_values)
  IF(TRIM(phase)=='LW') THEN
    CALL write3(u_out,'TOTAL_TAU',lw_atmos%tau)
  ELSE
    CALL write3(u_out,'TOTAL_TAU',sw_atmos%tau); CALL write3(u_out,'TOTAL_SSA',sw_atmos%ssa)
    CALL write3(u_out,'TOTAL_G',sw_atmos%g)
  END IF
  CALL write3(u_out,'RL_USED',RESHAPE(rl,[nc,nl,1]))
  CALL write3(u_out,'DI_USED',RESHAPE(di,[nc,nl,1]))
  CALL write3(u_out,'DS_USED',RESHAPE(ds,[nc,nl,1]))
  CALL write3(u_out,'UP',RESHAPE(up_all,[nc,nl+1,1]))
  CALL write3(u_out,'DN',RESHAPE(dn_all,[nc,nl+1,1]))
  CALL write3(u_out,'HR',RESHAPE(hr_all,[nc,nl,1]))
  CALL write3(u_out,'UPC',RESHAPE(up_clear,[nc,nl+1,1]))
  CALL write3(u_out,'DNC',RESHAPE(dn_clear,[nc,nl+1,1]))
  CALL write3(u_out,'HRC',RESHAPE(hr_clear,[nc,nl,1]))
  IF(TRIM(phase)=='SW') THEN
    CALL write3(u_out,'DIRECT',RESHAPE(direct_all,[nc,nl+1,1]))
    CALL write3(u_out,'DIFFUSE',RESHAPE(diffuse_all,[nc,nl+1,1]))
    CALL write3(u_out,'DIRECTC',RESHAPE(direct_clear,[nc,nl+1,1]))
    CALL write3(u_out,'VISDIR',RESHAPE(visdir,[nc,nl+1,1]))
    CALL write3(u_out,'VISDIF',RESHAPE(visdif,[nc,nl+1,1]))
    CALL write3(u_out,'NIRDIR',RESHAPE(nirdir,[nc,nl+1,1]))
    CALL write3(u_out,'NIRDIF',RESHAPE(nirdif,[nc,nl+1,1]))
  END IF
  CLOSE(u_out)

CONTAINS
  SUBROUTINE read_section(unit,wanted,array)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(LEN=*), INTENT(IN) :: wanted
    REAL(wp), INTENT(OUT) :: array(:,:)
    CHARACTER(LEN=32) :: got
    INTEGER :: rows,cols,stat
    READ(unit,*,IOSTAT=stat) got,rows,cols
    IF(stat/=0) ERROR STOP 'failed to read replay section header'
    IF(TRIM(got)/=TRIM(wanted) .OR. rows/=SIZE(array,1) .OR. cols/=SIZE(array,2)) &
      ERROR STOP 'replay section name or shape mismatch'
    READ(unit,*,IOSTAT=stat) array
    IF(stat/=0) ERROR STOP 'failed to read replay section values'
  END SUBROUTINE

  SUBROUTINE read_section_flexible(unit,wanted,array,ncols_read)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(LEN=*), INTENT(IN) :: wanted
    REAL(wp), INTENT(INOUT) :: array(:,:)
    INTEGER, INTENT(OUT) :: ncols_read
    CHARACTER(LEN=32) :: got
    INTEGER :: rows,cols,stat
    READ(unit,*,IOSTAT=stat) got,rows,cols
    IF(stat/=0) ERROR STOP 'failed to read replay section header'
    IF(TRIM(got)/=TRIM(wanted) .OR. rows/=SIZE(array,1) .OR. cols<1 .OR. cols>SIZE(array,2)) &
      ERROR STOP 'replay section name or shape mismatch'
    ncols_read=cols
    array=0._wp
    READ(unit,*,IOSTAT=stat) array(:,1:cols)
    IF(stat/=0) ERROR STOP 'failed to read replay section values'
  END SUBROUTINE

  SUBROUTINE read_scalar_section(unit,wanted,value)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(LEN=*), INTENT(IN) :: wanted
    REAL(wp), INTENT(OUT) :: value
    CHARACTER(LEN=32) :: got
    INTEGER :: rows,cols,stat
    READ(unit,*,IOSTAT=stat) got,rows,cols
    IF(stat/=0) ERROR STOP 'failed to read scalar section header'
    IF(TRIM(got)/=TRIM(wanted) .OR. rows/=1 .OR. cols/=1) ERROR STOP 'scalar section shape mismatch'
    READ(unit,*,IOSTAT=stat) value
    IF(stat/=0) ERROR STOP 'failed to read scalar section value'
  END SUBROUTINE

  SUBROUTINE write3(unit,name,array)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(wp), INTENT(IN) :: array(:,:,:)
    INTEGER :: stat
    WRITE(unit,'(A,1X,I0,1X,I0,1X,I0)') TRIM(name),SIZE(array,1),SIZE(array,2),SIZE(array,3)
    WRITE(unit,'(*(ES25.16E3,1X))',IOSTAT=stat) array
    IF(stat/=0) ERROR STOP 'failed to write result array'
  END SUBROUTINE

  SUBROUTINE check_error(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF(LEN_TRIM(message)>0) THEN
      WRITE(*,'(A)') TRIM(message)
      ERROR STOP 'reference RRTMGP/RTE call failed'
    END IF
  END SUBROUTINE

  FUNCTION ice_diameter(radius,flag) RESULT(diameter)
    REAL(wp), INTENT(IN) :: radius(:,:)
    INTEGER, INTENT(IN) :: flag
    REAL(wp) :: diameter(SIZE(radius,1),SIZE(radius,2))
    diameter=2._wp*radius
    IF(flag==3) diameter=diameter/1.0315_wp
  END FUNCTION

  SUBROUTINE make_mask(frac,npoint,mode,base_seed,cloud_mask,rand,local)
    REAL(wp), INTENT(IN) :: frac(:,:)
    INTEGER, INTENT(IN) :: npoint,mode,base_seed
    LOGICAL, INTENT(OUT) :: cloud_mask(SIZE(frac,1),SIZE(frac,2),npoint)
    REAL(wp), INTENT(OUT) :: rand(npoint,SIZE(frac,2),SIZE(frac,1))
    REAL(wp), INTENT(OUT) :: local(:)
    INTEGER :: col,lev,point,first,last
    LOGICAL :: is_cloud(SIZE(frac,2))
    INTEGER(i8) :: state
    state=MODULO(INT(base_seed,i8),2147483646_i8)+1_i8
    DO col=1,SIZE(frac,1)
      DO lev=1,SIZE(frac,2)
        DO point=1,npoint
          state=MODULO(48271_i8*state,2147483647_i8)
          rand(point,lev,col)=REAL(state,wp)/2147483647._wp
        END DO
      END DO
    END DO
    SELECT CASE(mode)
    CASE(0)
      cloud_mask=.FALSE.
    CASE(2)
      DO col=1,SIZE(frac,1)
        is_cloud=frac(col,:)>0._wp
        IF(.NOT.ANY(is_cloud)) THEN
          cloud_mask(col,:,:)=.FALSE.
          CYCLE
        END IF
        first=FINDLOC(is_cloud,.TRUE.,DIM=1)
        last=FINDLOC(is_cloud,.TRUE.,DIM=1,BACK=.TRUE.)
        cloud_mask(col,1:first-1,:)=.FALSE.
        local=rand(:,first,col)
        cloud_mask(col,first,:)=local>1._wp-frac(col,first)
        DO lev=first+1,last
          IF(is_cloud(lev)) THEN
            IF(.NOT.is_cloud(lev-1)) local=rand(:,lev,col)
            cloud_mask(col,lev,:)=local>1._wp-frac(col,lev)
          ELSE
            cloud_mask(col,lev,:)=.FALSE.
          END IF
        END DO
        cloud_mask(col,last+1:SIZE(frac,2),:)=.FALSE.
      END DO
    CASE(1,3)
      DO col=1,SIZE(frac,1)
        DO lev=1,SIZE(frac,2)
          DO point=1,npoint
            IF(mode==3) THEN
              cloud_mask(col,lev,point)=rand(point,1,col)>1._wp-frac(col,lev)
            ELSE
              cloud_mask(col,lev,point)=rand(point,lev,col)>1._wp-frac(col,lev)
            END IF
          END DO
        END DO
      END DO
    CASE DEFAULT
      ERROR STOP 'overlap must be one of 0,1,2,3'
    END SELECT
  END SUBROUTINE
END PROGRAM rrtmgp_reference_column
