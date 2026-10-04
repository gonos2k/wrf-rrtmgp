PROGRAM test_rrtmgp_multicolumn
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite, ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp, ONLY: rrtmgp_init, rrtmgp_lw_column, rrtmgp_sw_column
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=64, nl=3, nv=nl+1
  CHARACTER(LEN=512) :: data_path
  REAL :: play(nc,nl), plev(nc,nv), tlay(nc,nl), tlev(nc,nv), tsfc(nc)
  REAL :: h2o(nc,nl), co2(nc,nl), o3(nc,nl), n2o(nc,nl), ch4(nc,nl), o2(nc,nl)
  REAL :: emis(nc,1), cf(nc,nl), lwp(nc,nl), iwp(nc,nl), swp(nc,nl)
  REAL :: rel(nc,nl), rei(nc,nl), res(nc,nl)
  REAL :: avdir(nc), avdif(nc), andir(nc), andif(nc), mu0(nc), solar
  REAL :: lwup(nc,nv), lwdn(nc,nv), lwhr(nc,nl), lwupc(nc,nv), lwdnc(nc,nv), lwhrc(nc,nl)
  REAL :: swup(nc,nv), swdn(nc,nv), swhr(nc,nl), swupc(nc,nv), swdnc(nc,nv), swhrc(nc,nl)
  REAL :: direct(nc,nv), diffuse(nc,nv), directc(nc,nv)
  REAL :: visdir(nc,nv), visdif(nc,nv), nirdir(nc,nv), nirdif(nc,nv)
  REAL :: lwup_one(1,nv), lwdn_one(1,nv), lwhr_one(1,nl)
  REAL :: lwupc_one(1,nv), lwdnc_one(1,nv), lwhrc_one(1,nl)
  REAL :: swup_one(1,nv), swdn_one(1,nv), swhr_one(1,nl)
  REAL :: swupc_one(1,nv), swdnc_one(1,nv), swhrc_one(1,nl)
  REAL :: direct_one(1,nv), diffuse_one(1,nv), directc_one(1,nv)
  REAL :: visdir_one(1,nv), visdif_one(1,nv), nirdir_one(1,nv), nirdif_one(1,nv)
  REAL :: lwup_single(nc,nv), lwdn_single(nc,nv), lwhr_single(nc,nl)
  REAL :: lwupc_single(nc,nv), lwdnc_single(nc,nv), lwhrc_single(nc,nl)
  REAL :: swup_single(nc,nv), swdn_single(nc,nv), swhr_single(nc,nl)
  REAL :: swupc_single(nc,nv), swdnc_single(nc,nv), swhrc_single(nc,nl)
  REAL :: direct_single(nc,nv), diffuse_single(nc,nv), directc_single(nc,nv)
  REAL :: visdir_single(nc,nv), visdif_single(nc,nv), nirdir_single(nc,nv), nirdif_single(nc,nv)
  REAL :: p_play(nc,nl), p_plev(nc,nv), p_tlay(nc,nl), p_tlev(nc,nv), p_tsfc(nc)
  REAL :: p_h2o(nc,nl), p_co2(nc,nl), p_o3(nc,nl), p_n2o(nc,nl), p_ch4(nc,nl), p_o2(nc,nl)
  REAL :: p_emis(nc,1), p_cf(nc,nl), p_lwp(nc,nl), p_iwp(nc,nl), p_swp(nc,nl)
  REAL :: p_rel(nc,nl), p_rei(nc,nl), p_res(nc,nl)
  REAL :: p_avdir(nc), p_avdif(nc), p_andir(nc), p_andif(nc), p_mu0(nc)
  REAL :: solar_columns(nc)
  REAL :: direct_raw(nc,nv), directc_raw(nc,nv), visdir_raw(nc,nv), nirdir_raw(nc,nv)
  REAL :: direct_raw_one(1,nv), directc_raw_one(1,nv), visdir_raw_one(1,nv), nirdir_raw_one(1,nv)
  REAL :: direct_raw_single(nc,nv), directc_raw_single(nc,nv), visdir_raw_single(nc,nv), nirdir_raw_single(nc,nv)
  REAL :: plwup(nc,nv), plwdn(nc,nv), plwhr(nc,nl), plwupc(nc,nv), plwdnc(nc,nv), plwhrc(nc,nl)
  REAL :: pswup(nc,nv), pswdn(nc,nv), pswhr(nc,nl), pswupc(nc,nv), pswdnc(nc,nv), pswhrc(nc,nl)
  REAL :: pdirect(nc,nv), pdiffuse(nc,nv), pdirectc(nc,nv)
  REAL :: pvisdir(nc,nv), pvisdif(nc,nv), pnirdir(nc,nv), pnirdif(nc,nv)
  INTEGER :: seeds(nc), p_seeds(nc), permutation(nc), c, k, overlap
  REAL :: aggregate_max_difference=0.

  CALL get_command_argument(1,data_path)
  IF(LEN_TRIM(data_path)==0) ERROR STOP 'usage: test_rrtmgp_multicolumn DATA_DIRECTORY'
  CALL initialize_columns()
  CALL rrtmgp_init(TRIM(data_path))
  BLOCK
    CHARACTER(LEN=64) :: invalid_case
    CALL get_command_argument(2,invalid_case)
    IF(LEN_TRIM(invalid_case)>0) THEN
      CALL reject_solar_input(TRIM(invalid_case))
      ERROR STOP 'invalid solar test unexpectedly returned'
    END IF
  END BLOCK

  ! Keep all daylight columns together. The adapter intentionally rejects mixed
  ! day/night batches; packing and unpacking those batches is a WRF-side concern.
  IF(ANY(mu0<=0.)) CALL fail('daylight batch unexpectedly contains a night column')
  DO overlap=0,3
    CALL compare_batch_to_single(overlap)
    CALL compare_reordered_batch(overlap)
  END DO
  CALL compare_column_solar_to_single()
  CALL check_all_night_batch()
  WRITE(*,'(A,ES12.4)') 'RRTMGP multicolumn checks passed; aggregate max difference ', &
    aggregate_max_difference

CONTAINS

  SUBROUTINE initialize_columns()
    INTEGER :: layer
    REAL :: fraction
    solar=1361.
    DO c=1,nc
      fraction=REAL(c-1)/REAL(nc-1)
      seeds(c)=1009*c+173
      permutation(c)=nc+1-c
      plev(c,1)=990.+10.*fraction
      plev(c,2)=700.+8.*fraction
      plev(c,3)=300.+5.*fraction
      IF(MOD(c,2)==0) THEN
        plev(c,4)=0.
      ELSE
        plev(c,4)=1.
      END IF
      play(c,1)=0.5*(plev(c,1)+plev(c,2))
      play(c,2)=0.5*(plev(c,2)+plev(c,3))
      play(c,3)=0.5*(plev(c,3)+plev(c,4))
      tlev(c,1)=286.+3.*fraction
      tlev(c,2)=276.+2.*fraction
      tlev(c,3)=244.+4.*fraction
      tlev(c,4)=210.+8.*fraction
      DO layer=1,nl
        tlay(c,layer)=0.5*(tlev(c,layer)+tlev(c,layer+1))
      END DO
      tsfc(c)=tlev(c,1)
      h2o(c,:)=[0.009+0.002*fraction,0.0025+0.0005*fraction,0.00008+0.00004*fraction]
      co2(c,:)=410.e-6+20.e-6*fraction
      o3(c,:)=[0.4e-6+0.2e-6*fraction,1.0e-6+0.2e-6*fraction,4.0e-6+1.0e-6*fraction]
      n2o(c,:)=320.e-9+20.e-9*fraction
      ch4(c,:)=1.7e-6+0.2e-6*fraction
      o2(c,:)=0.209+0.001*fraction
      emis(c,1)=0.96+0.03*fraction
      cf(c,:)=[0.2+0.2*fraction,0.45+0.2*fraction,0.3+0.3*fraction]
      lwp(c,:)=[10.+10.*fraction,60.+35.*fraction,20.+20.*fraction]
      iwp(c,:)=[5.+10.*fraction,30.+30.*fraction,45.+20.*fraction]
      swp(c,:)=[2.+5.*fraction,18.+20.*fraction,8.+10.*fraction]
      rel(c,:)=8.+8.*fraction
      rei(c,:)=25.+30.*fraction
      res(c,:)=20.+35.*fraction
      avdir(c)=0.1+0.2*fraction
      avdif(c)=0.12+0.18*fraction
      andir(c)=0.18+0.22*fraction
      andif(c)=0.2+0.2*fraction
      mu0(c)=0.3+0.5*fraction
    END DO
  END SUBROUTINE initialize_columns

  SUBROUTINE compare_batch_to_single(overlap_mode)
    INTEGER, INTENT(IN) :: overlap_mode
    CHARACTER(LEN=48) :: label
    WRITE(label,'("overlap ",I0," batch versus single")') overlap_mode
    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
      cf,lwp,iwp,swp,rel,rei,res,4,overlap_mode,173,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc, &
      column_seeds=seeds)
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
      cf,lwp,iwp,swp,rel,rei,res,4,overlap_mode,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
      direct,diffuse,directc,visdir,visdif,nirdir,nirdif,column_seeds=seeds)
    DO c=1,nc
      CALL rrtmgp_lw_column(play(c:c,:),plev(c:c,:),tlay(c:c,:),tlev(c:c,:),tsfc(c:c), &
        h2o(c:c,:),co2(c:c,:),o3(c:c,:),n2o(c:c,:),ch4(c:c,:),o2(c:c,:),emis(c:c,:), &
        cf(c:c,:),lwp(c:c,:),iwp(c:c,:),swp(c:c,:),rel(c:c,:),rei(c:c,:),res(c:c,:), &
        4,overlap_mode,173,lwup_one,lwdn_one,lwhr_one,lwupc_one,lwdnc_one,lwhrc_one, &
        column_seeds=seeds(c:c))
      lwup_single(c,:)=lwup_one(1,:); lwdn_single(c,:)=lwdn_one(1,:); lwhr_single(c,:)=lwhr_one(1,:)
      lwupc_single(c,:)=lwupc_one(1,:); lwdnc_single(c,:)=lwdnc_one(1,:); lwhrc_single(c,:)=lwhrc_one(1,:)
      CALL rrtmgp_sw_column(play(c:c,:),plev(c:c,:),tlay(c:c,:),h2o(c:c,:),co2(c:c,:), &
        o3(c:c,:),n2o(c:c,:),ch4(c:c,:),o2(c:c,:),avdir(c:c),avdif(c:c),andir(c:c),andif(c:c), &
        mu0(c:c),solar,cf(c:c,:),lwp(c:c,:),iwp(c:c,:),swp(c:c,:),rel(c:c,:),rei(c:c,:),res(c:c,:), &
        4,overlap_mode,173,swup_one,swdn_one,swhr_one,swupc_one,swdnc_one,swhrc_one, &
        direct_one,diffuse_one,directc_one,visdir_one,visdif_one,nirdir_one,nirdif_one, &
        column_seeds=seeds(c:c))
      swup_single(c,:)=swup_one(1,:); swdn_single(c,:)=swdn_one(1,:); swhr_single(c,:)=swhr_one(1,:)
      swupc_single(c,:)=swupc_one(1,:); swdnc_single(c,:)=swdnc_one(1,:); swhrc_single(c,:)=swhrc_one(1,:)
      direct_single(c,:)=direct_one(1,:); diffuse_single(c,:)=diffuse_one(1,:)
      directc_single(c,:)=directc_one(1,:); visdir_single(c,:)=visdir_one(1,:)
      visdif_single(c,:)=visdif_one(1,:); nirdir_single(c,:)=nirdir_one(1,:); nirdif_single(c,:)=nirdif_one(1,:)
    END DO
    CALL check_close(TRIM(label)//' LW up',lwup,lwup_single)
    CALL check_close(TRIM(label)//' LW down',lwdn,lwdn_single)
    CALL check_close(TRIM(label)//' LW heating',lwhr,lwhr_single)
    CALL check_close(TRIM(label)//' LW clear up',lwupc,lwupc_single)
    CALL check_close(TRIM(label)//' LW clear down',lwdnc,lwdnc_single)
    CALL check_close(TRIM(label)//' LW clear heating',lwhrc,lwhrc_single)
    CALL check_close(TRIM(label)//' SW up',swup,swup_single)
    CALL check_close(TRIM(label)//' SW down',swdn,swdn_single)
    CALL check_close(TRIM(label)//' SW heating',swhr,swhr_single)
    CALL check_close(TRIM(label)//' SW clear up',swupc,swupc_single)
    CALL check_close(TRIM(label)//' SW clear down',swdnc,swdnc_single)
    CALL check_close(TRIM(label)//' SW clear heating',swhrc,swhrc_single)
    CALL check_close(TRIM(label)//' SW direct',direct,direct_single)
    CALL check_close(TRIM(label)//' SW diffuse',diffuse,diffuse_single)
    CALL check_close(TRIM(label)//' SW clear direct',directc,directc_single)
    CALL check_close(TRIM(label)//' SW visible direct',visdir,visdir_single)
    CALL check_close(TRIM(label)//' SW visible diffuse',visdif,visdif_single)
    CALL check_close(TRIM(label)//' SW near-IR direct',nirdir,nirdir_single)
    CALL check_close(TRIM(label)//' SW near-IR diffuse',nirdif,nirdif_single)
  END SUBROUTINE compare_batch_to_single

  SUBROUTINE compare_reordered_batch(overlap_mode)
    INTEGER, INTENT(IN) :: overlap_mode
    CHARACTER(LEN=48) :: label
    DO c=1,nc
      p_seeds(c)=seeds(permutation(c))
      p_play(c,:)=play(permutation(c),:); p_plev(c,:)=plev(permutation(c),:)
      p_tlay(c,:)=tlay(permutation(c),:); p_tlev(c,:)=tlev(permutation(c),:)
      p_tsfc(c)=tsfc(permutation(c)); p_h2o(c,:)=h2o(permutation(c),:)
      p_co2(c,:)=co2(permutation(c),:); p_o3(c,:)=o3(permutation(c),:)
      p_n2o(c,:)=n2o(permutation(c),:); p_ch4(c,:)=ch4(permutation(c),:)
      p_o2(c,:)=o2(permutation(c),:); p_emis(c,:)=emis(permutation(c),:)
      p_cf(c,:)=cf(permutation(c),:); p_lwp(c,:)=lwp(permutation(c),:)
      p_iwp(c,:)=iwp(permutation(c),:); p_swp(c,:)=swp(permutation(c),:)
      p_rel(c,:)=rel(permutation(c),:); p_rei(c,:)=rei(permutation(c),:)
      p_res(c,:)=res(permutation(c),:); p_avdir(c)=avdir(permutation(c))
      p_avdif(c)=avdif(permutation(c)); p_andir(c)=andir(permutation(c))
      p_andif(c)=andif(permutation(c)); p_mu0(c)=mu0(permutation(c))
    END DO
    WRITE(label,'("overlap ",I0," reordered batch")') overlap_mode
    CALL rrtmgp_lw_column(p_play,p_plev,p_tlay,p_tlev,p_tsfc,p_h2o,p_co2,p_o3,p_n2o,p_ch4,p_o2,p_emis, &
      p_cf,p_lwp,p_iwp,p_swp,p_rel,p_rei,p_res,4,overlap_mode,173,plwup,plwdn,plwhr,plwupc,plwdnc,plwhrc, &
      column_seeds=p_seeds)
    CALL rrtmgp_sw_column(p_play,p_plev,p_tlay,p_h2o,p_co2,p_o3,p_n2o,p_ch4,p_o2, &
      p_avdir,p_avdif,p_andir,p_andif,p_mu0,solar,p_cf,p_lwp,p_iwp,p_swp,p_rel,p_rei,p_res, &
      4,overlap_mode,173,pswup,pswdn,pswhr,pswupc,pswdnc,pswhrc, &
      pdirect,pdiffuse,pdirectc,pvisdir,pvisdif,pnirdir,pnirdif,column_seeds=p_seeds)
    DO c=1,nc
      k=permutation(c)
      CALL check_close(TRIM(label)//' LW up',plwup(c:c,:),lwup(k:k,:))
      CALL check_close(TRIM(label)//' LW down',plwdn(c:c,:),lwdn(k:k,:))
      CALL check_close(TRIM(label)//' LW heating',plwhr(c:c,:),lwhr(k:k,:))
      CALL check_close(TRIM(label)//' LW clear up',plwupc(c:c,:),lwupc(k:k,:))
      CALL check_close(TRIM(label)//' LW clear down',plwdnc(c:c,:),lwdnc(k:k,:))
      CALL check_close(TRIM(label)//' LW clear heating',plwhrc(c:c,:),lwhrc(k:k,:))
      CALL check_close(TRIM(label)//' SW up',pswup(c:c,:),swup(k:k,:))
      CALL check_close(TRIM(label)//' SW down',pswdn(c:c,:),swdn(k:k,:))
      CALL check_close(TRIM(label)//' SW heating',pswhr(c:c,:),swhr(k:k,:))
      CALL check_close(TRIM(label)//' SW clear up',pswupc(c:c,:),swupc(k:k,:))
      CALL check_close(TRIM(label)//' SW clear down',pswdnc(c:c,:),swdnc(k:k,:))
      CALL check_close(TRIM(label)//' SW clear heating',pswhrc(c:c,:),swhrc(k:k,:))
      CALL check_close(TRIM(label)//' SW direct',pdirect(c:c,:),direct(k:k,:))
      CALL check_close(TRIM(label)//' SW diffuse',pdiffuse(c:c,:),diffuse(k:k,:))
      CALL check_close(TRIM(label)//' SW clear direct',pdirectc(c:c,:),directc(k:k,:))
      CALL check_close(TRIM(label)//' SW visible direct',pvisdir(c:c,:),visdir(k:k,:))
      CALL check_close(TRIM(label)//' SW visible diffuse',pvisdif(c:c,:),visdif(k:k,:))
      CALL check_close(TRIM(label)//' SW near-IR direct',pnirdir(c:c,:),nirdir(k:k,:))
      CALL check_close(TRIM(label)//' SW near-IR diffuse',pnirdif(c:c,:),nirdif(k:k,:))
    END DO
  END SUBROUTINE compare_reordered_batch

  SUBROUTINE compare_column_solar_to_single()
    ! WRF's eclipse factor can vary by grid point. A batch must use each
    ! column's solar irradiance, not the first column's scalar value.
    CHARACTER(LEN=48) :: label
    DO c=1,nc
      solar_columns(c)=solar*(1.-REAL(c-1)/REAL(nc-1))
    END DO
    WRITE(label,'(A)') 'column-varying solar batch versus single'
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
      cf,lwp,iwp,swp,rel,rei,res,4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
      direct,diffuse,directc,visdir,visdif,nirdir,nirdif,column_seeds=seeds, &
      direct_unscaled=direct_raw,directc_unscaled=directc_raw,visdir_unscaled=visdir_raw, &
      nirdir_unscaled=nirdir_raw,solar_by_column=solar_columns)
    DO c=1,nc
      CALL rrtmgp_sw_column(play(c:c,:),plev(c:c,:),tlay(c:c,:),h2o(c:c,:),co2(c:c,:), &
        o3(c:c,:),n2o(c:c,:),ch4(c:c,:),o2(c:c,:),avdir(c:c),avdif(c:c),andir(c:c),andif(c:c), &
        mu0(c:c),solar_columns(c),cf(c:c,:),lwp(c:c,:),iwp(c:c,:),swp(c:c,:),rel(c:c,:),rei(c:c,:),res(c:c,:), &
        4,2,173,swup_one,swdn_one,swhr_one,swupc_one,swdnc_one,swhrc_one, &
        direct_one,diffuse_one,directc_one,visdir_one,visdif_one,nirdir_one,nirdif_one,column_seeds=seeds(c:c), &
        direct_unscaled=direct_raw_one,directc_unscaled=directc_raw_one, &
        visdir_unscaled=visdir_raw_one,nirdir_unscaled=nirdir_raw_one)
      swup_single(c,:)=swup_one(1,:); swdn_single(c,:)=swdn_one(1,:); swhr_single(c,:)=swhr_one(1,:)
      swupc_single(c,:)=swupc_one(1,:); swdnc_single(c,:)=swdnc_one(1,:); swhrc_single(c,:)=swhrc_one(1,:)
      direct_single(c,:)=direct_one(1,:); diffuse_single(c,:)=diffuse_one(1,:)
      directc_single(c,:)=directc_one(1,:); visdir_single(c,:)=visdir_one(1,:)
      visdif_single(c,:)=visdif_one(1,:); nirdir_single(c,:)=nirdir_one(1,:); nirdif_single(c,:)=nirdif_one(1,:)
      direct_raw_single(c,:)=direct_raw_one(1,:); directc_raw_single(c,:)=directc_raw_one(1,:)
      visdir_raw_single(c,:)=visdir_raw_one(1,:); nirdir_raw_single(c,:)=nirdir_raw_one(1,:)
    END DO
    CALL check_close(TRIM(label)//' up',swup,swup_single)
    CALL check_close(TRIM(label)//' down',swdn,swdn_single)
    CALL check_close(TRIM(label)//' heating',swhr,swhr_single)
    CALL check_close(TRIM(label)//' clear up',swupc,swupc_single)
    CALL check_close(TRIM(label)//' clear down',swdnc,swdnc_single)
    CALL check_close(TRIM(label)//' clear heating',swhrc,swhrc_single)
    CALL check_close(TRIM(label)//' direct',direct,direct_single)
    CALL check_close(TRIM(label)//' diffuse',diffuse,diffuse_single)
    CALL check_close(TRIM(label)//' clear direct',directc,directc_single)
    CALL check_close(TRIM(label)//' visible direct',visdir,visdir_single)
    CALL check_close(TRIM(label)//' visible diffuse',visdif,visdif_single)
    CALL check_close(TRIM(label)//' near-IR direct',nirdir,nirdir_single)
    CALL check_close(TRIM(label)//' near-IR diffuse',nirdif,nirdif_single)
    CALL check_close(TRIM(label)//' unscaled broadband direct',direct_raw,direct_raw_single)
    CALL check_close(TRIM(label)//' unscaled clear direct',directc_raw,directc_raw_single)
    CALL check_close(TRIM(label)//' unscaled visible direct',visdir_raw,visdir_raw_single)
    CALL check_close(TRIM(label)//' unscaled near-IR direct',nirdir_raw,nirdir_raw_single)
    IF(ANY(.NOT.ieee_is_finite(direct_raw)).OR.ANY(.NOT.ieee_is_finite(directc_raw)).OR. &
       ANY(.NOT.ieee_is_finite(visdir_raw)).OR.ANY(.NOT.ieee_is_finite(nirdir_raw))) &
      CALL fail('column-varying solar produced non-finite pre-delta direct output')
    IF(ANY(direct_raw(nc,:)/=0.).OR.ANY(directc_raw(nc,:)/=0.).OR. &
       ANY(visdir_raw(nc,:)/=0.).OR.ANY(nirdir_raw(nc,:)/=0.)) &
      CALL fail('zero-solar column has nonzero pre-delta direct output')
  END SUBROUTINE compare_column_solar_to_single

  SUBROUTINE reject_solar_input(case_name)
    CHARACTER(LEN=*), INTENT(IN) :: case_name
    REAL :: bad_solar(nc), wrong_solar(nc-1)
    SELECT CASE(case_name)
    CASE('solar_shape')
      wrong_solar=solar
      CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
        cf,lwp,iwp,swp,rel,rei,res,4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
        direct,diffuse,directc,visdir,visdif,nirdir,nirdif,solar_by_column=wrong_solar)
    CASE('solar_negative')
      bad_solar=solar
      bad_solar(3)=-1.
      CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
        cf,lwp,iwp,swp,rel,rei,res,4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
        direct,diffuse,directc,visdir,visdif,nirdir,nirdif,solar_by_column=bad_solar)
    CASE('solar_nan')
      bad_solar=solar
      bad_solar(3)=ieee_value(0.,ieee_quiet_nan)
      CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
        cf,lwp,iwp,swp,rel,rei,res,4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
        direct,diffuse,directc,visdir,visdif,nirdir,nirdif,solar_by_column=bad_solar)
    CASE DEFAULT
      ERROR STOP 'unknown invalid solar case'
    END SELECT
  END SUBROUTINE reject_solar_input

  SUBROUTINE check_all_night_batch()
    mu0=0.
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
      cf,lwp,iwp,swp,rel,rei,res,4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
      direct,diffuse,directc,visdir,visdif,nirdir,nirdif,column_seeds=seeds)
    CALL check_zero('all-night SW up',swup)
    CALL check_zero('all-night SW down',swdn)
    CALL check_zero('all-night SW heating',swhr)
    CALL check_zero('all-night SW clear up',swupc)
    CALL check_zero('all-night SW clear down',swdnc)
    CALL check_zero('all-night SW clear heating',swhrc)
    CALL check_zero('all-night SW direct',direct)
    CALL check_zero('all-night SW diffuse',diffuse)
    CALL check_zero('all-night SW clear direct',directc)
    CALL check_zero('all-night SW visible direct',visdir)
    CALL check_zero('all-night SW visible diffuse',visdif)
    CALL check_zero('all-night SW near-IR direct',nirdir)
    CALL check_zero('all-night SW near-IR diffuse',nirdif)
  END SUBROUTINE check_all_night_batch

  SUBROUTINE check_close(label,a,b)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: a(:,:),b(:,:)
    REAL :: difference, allowed
    IF(ANY(SHAPE(a)/=SHAPE(b))) CALL fail(TRIM(label)//' has mismatched extents')
    IF(.NOT.ALL(ieee_is_finite(a)).OR..NOT.ALL(ieee_is_finite(b))) &
      CALL fail(TRIM(label)//' contains non-finite values')
    difference=MAXVAL(ABS(a-b))
    aggregate_max_difference=MAX(aggregate_max_difference,difference)
    allowed=1.e-3+1.e-5*MAX(1.,MAXVAL(ABS(a)),MAXVAL(ABS(b)))
    IF(difference>allowed) THEN
      WRITE(*,'(A,ES12.4,A,ES12.4)') TRIM(label)//' max diff ',difference,' allowed ',allowed
      CALL fail(TRIM(label)//' differs between batch and reference')
    END IF
  END SUBROUTINE check_close

  SUBROUTINE check_zero(label,a)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: a(:,:)
    IF(.NOT.ALL(ieee_is_finite(a))) CALL fail(TRIM(label)//' contains non-finite values')
    IF(ANY(a/=0.)) CALL fail(TRIM(label)//' is not zero')
  END SUBROUTINE check_zero

  SUBROUTINE fail(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    WRITE(*,'(A)') 'FAIL: '//TRIM(message)
    ERROR STOP 1
  END SUBROUTINE fail

END PROGRAM test_rrtmgp_multicolumn
