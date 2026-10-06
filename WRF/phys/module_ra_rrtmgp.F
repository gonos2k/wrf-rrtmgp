! WRF adapter for the UFS-pinned RTE+RRTMGP CPU implementation.
! The legacy WRF column preparation supplies hPa, VMR, g/m2 and micrometers.
! Results deliberately use the legacy K/day contract; WRF converts to theta/s.
MODULE module_ra_rrtmgp
  USE mo_rte_kind, ONLY: wp, i8
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE mo_gas_optics_rrtmgp, ONLY: ty_gas_optics_rrtmgp, get_col_dry
  USE mo_gas_concentrations, ONLY: ty_gas_concs
  USE mo_optical_props, ONLY: ty_optical_props_1scl, ty_optical_props_2str
  USE mo_source_functions, ONLY: ty_source_func_lw
  USE mo_fluxes, ONLY: ty_fluxes_broadband
  USE mo_fluxes_byband, ONLY: ty_fluxes_byband
  USE mo_rte_lw, ONLY: rte_lw
  USE mo_rte_sw, ONLY: rte_sw
  USE mo_heating_rates, ONLY: compute_heating_rate
  USE mo_gas_optics_constants, ONLY: init_constants, rte_grav=>grav, rte_cp_dry=>cp_dry, rte_m_dry=>m_dry, avogad
  USE mo_cloud_optics_rrtmgp, ONLY: ty_cloud_optics_rrtmgp
  USE mo_cloud_sampling, ONLY: sampled_mask_max_ran, draw_samples
  USE mo_load_coefficients, ONLY: load_and_init
  USE mo_load_cloud_coefficients, ONLY: load_cld_lutcoeff
  USE mo_simple_netcdf, ONLY: set_fatal_handler
  USE module_ra_rrtmgp_frozen, ONLY: initialize_frozen=>initialize, query_sw, query_lw, &
      frozen_table_sha256, FROZEN_GRAUPEL, FROZEN_HAIL
  USE module_ra_rrtmgp_precip, ONLY: rrtmgp_precip_lw_optics, rrtmgp_precip_sw_optics
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_validate_column_inputs, &
      rrtmgp_check_unit_interval, rrtmgp_check_positive, rrtmgp_check_nonnegative
  USE module_ra_rrtmgp_trace, ONLY: trace_configure, trace_active, trace_input_start, trace_input, trace_input_end, &
      trace_result_start, trace_result
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE
  EXTERNAL :: wrf_error_fatal3
  PUBLIC :: rrtmgp_init, rrtmgp_lw_column, rrtmgp_sw_column, cloud_mask, rrtmgp_frozen_enabled
  TYPE(ty_gas_optics_rrtmgp), SAVE :: gas_lw, gas_sw
  TYPE(ty_cloud_optics_rrtmgp), SAVE :: cloud_lw, cloud_sw
  LOGICAL, SAVE :: ready = .FALSE.
  INTEGER, SAVE :: initialized_ice_roughness = 1
  REAL(wp), SAVE :: initialized_gravity = 9.80665_wp
  REAL(wp), SAVE :: initialized_cp_dry = 1004.64_wp
  REAL(wp), SAVE :: initialized_mol_weight_dry = 0.028964_wp
  INTEGER, SAVE :: initialized_frozen_mode = 0
  CHARACTER(LEN=:), ALLOCATABLE, SAVE :: initialized_frozen_path
  CHARACTER(LEN=:), ALLOCATABLE, SAVE :: initialized_path
  CHARACTER(LEN=32), PARAMETER :: names_sw(6) = [CHARACTER(LEN=32) :: 'h2o','co2','o3','n2o','ch4','o2']
  CHARACTER(LEN=32), PARAMETER :: names_lw(10) = [CHARACTER(LEN=32) :: &
      'h2o','co2','o3','n2o','ch4','o2','cfc11','cfc12','cfc22','ccl4']
CONTAINS
  SUBROUTINE require(msg)
    CHARACTER(LEN=*), INTENT(IN) :: msg
    IF (LEN_TRIM(msg)>0) CALL wrf_error_fatal3('module_ra_rrtmgp.F',0,'RRTMGP: '//TRIM(msg))
  END SUBROUTINE

  SUBROUTINE rrtmgp_coeff_fatal(message)
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL wrf_error_fatal3('module_ra_rrtmgp.F',0,'RRTMGP: '//TRIM(message))
  END SUBROUTINE

  SUBROUTINE rrtmgp_init(data_path,ice_roughness,gravity,cp_dry,mol_weight_dry,frozen_optics,frozen_table)
    CHARACTER(LEN=*), INTENT(IN) :: data_path
    INTEGER, OPTIONAL, INTENT(IN) :: ice_roughness
    REAL, OPTIONAL, INTENT(IN) :: gravity,cp_dry,mol_weight_dry
    INTEGER, OPTIONAL, INTENT(IN) :: frozen_optics
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: frozen_table
    INTEGER :: selected_mode,frozen_status
    CHARACTER(LEN=:), ALLOCATABLE :: selected_table
    CHARACTER(LEN=1024) :: frozen_message
    INTEGER :: selected_roughness
    REAL(wp) :: selected_gravity,selected_cp,selected_mol_weight
    TYPE(ty_gas_concs) :: gases
    selected_mode=0; selected_table=""
    IF(PRESENT(frozen_optics)) selected_mode=frozen_optics
    IF(PRESENT(frozen_table)) selected_table=TRIM(frozen_table)
    IF(selected_mode<0.OR.selected_mode>1) CALL require("rrtmgp_udm_frozen_optics must be 0 or 1")
    IF(selected_mode==1.AND.LEN_TRIM(selected_table)==0) &
      CALL require("experimental UDM frozen optics requires rrtmgp_udm_frozen_table")
    selected_roughness=1
    IF(PRESENT(ice_roughness)) selected_roughness=ice_roughness
    selected_gravity=rte_grav; selected_cp=rte_cp_dry; selected_mol_weight=rte_m_dry
    IF(PRESENT(gravity)) selected_gravity=REAL(gravity,wp)
    IF(PRESENT(cp_dry)) selected_cp=REAL(cp_dry,wp)
    IF(PRESENT(mol_weight_dry)) selected_mol_weight=REAL(mol_weight_dry,wp)
    IF(selected_roughness<1.OR.selected_roughness>3) &
      CALL require('rrtmgp_ice_roughness must be 1 (smooth), 2 (medium), or 3 (high)')
    IF(.NOT.ieee_is_finite(selected_gravity).OR.selected_gravity<=0.) CALL require('RRTMGP gravity must be finite and positive')
    IF(.NOT.ieee_is_finite(selected_cp).OR.selected_cp<=0.) CALL require('RRTMGP cp_dry must be finite and positive')
    IF(.NOT.ieee_is_finite(selected_mol_weight).OR.selected_mol_weight<=0.) &
      CALL require('RRTMGP mol_weight_dry must be finite and positive in kg/mol')
    CALL trace_configure()
    IF (ready) THEN
      IF(selected_mode/=initialized_frozen_mode.OR.selected_table/=initialized_frozen_path) &
        CALL require("UDM frozen optics mode and table path must be global and unchanged")
      IF(TRIM(data_path)/=initialized_path) CALL require('rrtmgp_data_path must be global and unchanged after initialization')
      IF(selected_roughness/=initialized_ice_roughness) &
        CALL require('rrtmgp_ice_roughness must be global and unchanged after initialization')
      IF(selected_gravity/=initialized_gravity.OR.selected_cp/=initialized_cp_dry.OR. &
         selected_mol_weight/=initialized_mol_weight_dry) &
        CALL require('RRTMGP gravity, cp_dry, and mol_weight_dry must be global and unchanged after initialization')
      RETURN
    END IF
    CALL init_constants(selected_gravity,selected_mol_weight,selected_cp)
    CALL set_fatal_handler(rrtmgp_coeff_fatal)
    CALL require(gases%init(names_lw))
    CALL load_and_init(gas_lw,TRIM(data_path)//'/rrtmgp-gas-lw-g128.nc',gases)
    CALL require(gases%init(names_sw))
    CALL load_and_init(gas_sw,TRIM(data_path)//'/rrtmgp-gas-sw-g112.nc',gases)
    CALL load_cld_lutcoeff(cloud_lw,TRIM(data_path)//'/rrtmgp-clouds-lw-bnd.nc')
    CALL load_cld_lutcoeff(cloud_sw,TRIM(data_path)//'/rrtmgp-clouds-sw-bnd.nc')
    CALL require(cloud_lw%set_ice_roughness(selected_roughness))
    CALL require(cloud_sw%set_ice_roughness(selected_roughness))
    IF (.NOT.cloud_lw%bands_are_equal(gas_lw)) CALL require('LW cloud/gas spectral bands differ')
    IF (.NOT.cloud_sw%bands_are_equal(gas_sw)) CALL require('SW cloud/gas spectral bands differ')
    IF(selected_mode==1) THEN
      CALL initialize_frozen(selected_table,frozen_status,frozen_message)
      IF(frozen_status/=0) CALL require("RRTMGP_FROZEN_TABLE: "//TRIM(frozen_message))
    END IF
    initialized_frozen_mode=selected_mode
    initialized_frozen_path=selected_table
    initialized_ice_roughness=selected_roughness
    initialized_gravity=selected_gravity
    initialized_cp_dry=selected_cp
    initialized_mol_weight_dry=selected_mol_weight
    initialized_path=TRIM(data_path)
    ready = .TRUE.
  END SUBROUTINE

  PURE LOGICAL FUNCTION rrtmgp_frozen_enabled()
    rrtmgp_frozen_enabled=initialized_frozen_mode==1
  END FUNCTION

  SUBROUTINE validate_frozen_inputs(expected_shape,gwp,hwp,lambda_g,lambda_h,frozen_context)
    INTEGER, INTENT(IN) :: expected_shape(2)
    REAL, OPTIONAL, INTENT(IN) :: gwp(:,:),hwp(:,:),lambda_g(:,:),lambda_h(:,:)
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: frozen_context
    LOGICAL :: any_input,all_input
    any_input=PRESENT(gwp).OR.PRESENT(hwp).OR.PRESENT(lambda_g).OR.PRESENT(lambda_h)
    all_input=PRESENT(gwp).AND.PRESENT(hwp).AND.PRESENT(lambda_g).AND.PRESENT(lambda_h)
    IF(rrtmgp_frozen_enabled()) THEN
      IF(.NOT.all_input) CALL require('RRTMGP_FROZEN_INPUTS_REQUIRED_IN_MODE_1')
      IF(ANY(SHAPE(gwp)/=expected_shape).OR.ANY(SHAPE(hwp)/=expected_shape).OR. &
         ANY(SHAPE(lambda_g)/=expected_shape).OR.ANY(SHAPE(lambda_h)/=expected_shape)) &
        CALL require('RRTMGP_FROZEN_INPUT_SHAPE_MISMATCH')
      CALL rrtmgp_check_nonnegative('gwp',gwp)
      CALL rrtmgp_check_nonnegative('hwp',hwp)
      CALL rrtmgp_check_positive('lambda_g',lambda_g)
      CALL rrtmgp_check_positive('lambda_h',lambda_h)
    ELSE IF(any_input) THEN
      CALL require('RRTMGP_FROZEN_INPUTS_REQUIRE_MODE_1')
    END IF
  END SUBROUTINE

  FUNCTION frozen_error(label,message,context) RESULT(error_message)
    CHARACTER(LEN=*), INTENT(IN) :: label,message
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: context
    CHARACTER(LEN=:), ALLOCATABLE :: error_message
    error_message=TRIM(label)//': '//TRIM(message)
    IF(PRESENT(context)) error_message=TRIM(context)//' '//error_message
  END FUNCTION

  SUBROUTINE add_frozen_lw(atmos,tlay,gwp,hwp,lambda_g,lambda_h,frozen_context)
    TYPE(ty_optical_props_1scl), INTENT(INOUT) :: atmos
    REAL, INTENT(IN) :: tlay(:,:),gwp(:,:),hwp(:,:),lambda_g(:,:),lambda_h(:,:)
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: frozen_context
    TYPE(ty_optical_props_1scl) :: frozen
    REAL(real64) :: gt(SIZE(tlay,1),SIZE(tlay,2),16),ht(SIZE(tlay,1),SIZE(tlay,2),16)
    INTEGER :: status
    CHARACTER(LEN=1024) :: message
    CALL query_lw(FROZEN_GRAUPEL,REAL(lambda_g,real64),REAL(tlay,real64),REAL(gwp,real64),gt,status,message)
    IF(status/=0) CALL require(frozen_error('RRTMGP_FROZEN_LW_GRAUPEL',message,frozen_context))
    CALL query_lw(FROZEN_HAIL,REAL(lambda_h,real64),REAL(tlay,real64),REAL(hwp,real64),ht,status,message)
    IF(status/=0) CALL require(frozen_error('RRTMGP_FROZEN_LW_HAIL',message,frozen_context))
    CALL require(frozen%alloc_1scl(SIZE(tlay,1),SIZE(tlay,2),cloud_lw))
    frozen%tau=REAL(gt+ht,wp)
    IF(trace_active('LW')) THEN
      CALL trace_result('LW','GRAUPEL_TAU_ABS',gt)
      CALL trace_result('LW','HAIL_TAU_ABS',ht)
      CALL trace_result('LW','FROZEN_TAU',frozen%tau)
    END IF
    ! Uniform grid-mean precipitation is independent of cloud McICA sampling.
    ! Increment only after the gas-only clear-sky calculation.
    CALL require(frozen%increment(atmos))
  END SUBROUTINE

  SUBROUTINE add_frozen_sw(atmos,gwp,hwp,lambda_g,lambda_h,frozen_context)
    TYPE(ty_optical_props_2str), INTENT(INOUT) :: atmos
    REAL, INTENT(IN) :: gwp(:,:),hwp(:,:),lambda_g(:,:),lambda_h(:,:)
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: frozen_context
    TYPE(ty_optical_props_2str) :: frozen
    REAL(real64) :: gt(SIZE(gwp,1),SIZE(gwp,2),14),gw(SIZE(gwp,1),SIZE(gwp,2),14), &
                    gmg(SIZE(gwp,1),SIZE(gwp,2),14),ht(SIZE(gwp,1),SIZE(gwp,2),14), &
                    hw(SIZE(gwp,1),SIZE(gwp,2),14),hmg(SIZE(gwp,1),SIZE(gwp,2),14)
    INTEGER :: status
    CHARACTER(LEN=1024) :: message
    CALL query_sw(FROZEN_GRAUPEL,REAL(lambda_g,real64),REAL(gwp,real64),gt,gw,gmg,status,message)
    IF(status/=0) CALL require(frozen_error('RRTMGP_FROZEN_SW_GRAUPEL',message,frozen_context))
    CALL query_sw(FROZEN_HAIL,REAL(lambda_h,real64),REAL(hwp,real64),ht,hw,hmg,status,message)
    IF(status/=0) CALL require(frozen_error('RRTMGP_FROZEN_SW_HAIL',message,frozen_context))
    CALL require(frozen%alloc_2str(SIZE(gwp,1),SIZE(gwp,2),cloud_sw))
    frozen%tau=REAL(gt+ht,wp)
    frozen%ssa=REAL((gw+hw)/MAX(gt+ht,TINY(1._real64)),wp)
    frozen%g=REAL((gmg+hmg)/MAX(gw+hw,TINY(1._real64)),wp)
    IF(trace_active('SW')) THEN
      CALL trace_result('SW','GRAUPEL_TAU_EXT',gt)
      CALL trace_result('SW','GRAUPEL_TAU_SCA',gw)
      CALL trace_result('SW','GRAUPEL_TAU_SCA_G',gmg)
      CALL trace_result('SW','HAIL_TAU_EXT',ht)
      CALL trace_result('SW','HAIL_TAU_SCA',hw)
      CALL trace_result('SW','HAIL_TAU_SCA_G',hmg)
    END IF
    ! Raw band moments are combined in tau/tau*ssa/tau*ssa*g space,
    ! then delta scaled exactly once, separately from cloud/rain/snow.
    CALL require(frozen%delta_scale())
    IF(trace_active('SW')) THEN
      CALL trace_result('SW','FROZEN_TAU',frozen%tau)
      CALL trace_result('SW','FROZEN_SSA',frozen%ssa)
      CALL trace_result('SW','FROZEN_G',frozen%g)
    END IF
    CALL require(frozen%increment(atmos))
  END SUBROUTINE

  SUBROUTINE set_gases_sw(gases,h2o,co2,o3,n2o,ch4,o2)
    TYPE(ty_gas_concs), INTENT(INOUT) :: gases
    REAL, INTENT(IN) :: h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:)
    IF(ANY(SHAPE(co2)/=SHAPE(h2o)).OR.ANY(SHAPE(o3)/=SHAPE(h2o)).OR. &
       ANY(SHAPE(n2o)/=SHAPE(h2o)).OR.ANY(SHAPE(ch4)/=SHAPE(h2o)).OR. &
       ANY(SHAPE(o2)/=SHAPE(h2o))) CALL require('gas shapes must match column layers')
    CALL rrtmgp_check_nonnegative('h2o',h2o)
    CALL rrtmgp_check_nonnegative('co2',co2)
    CALL rrtmgp_check_nonnegative('o3',o3)
    CALL rrtmgp_check_nonnegative('n2o',n2o)
    CALL rrtmgp_check_nonnegative('ch4',ch4)
    CALL rrtmgp_check_nonnegative('o2',o2)
    CALL require(gases%init(names_sw))
    CALL require(gases%set_vmr('h2o',REAL(h2o,wp)))
    CALL require(gases%set_vmr('co2',REAL(co2,wp)))
    CALL require(gases%set_vmr('o3',REAL(o3,wp)))
    CALL require(gases%set_vmr('n2o',REAL(n2o,wp)))
    CALL require(gases%set_vmr('ch4',REAL(ch4,wp)))
    CALL require(gases%set_vmr('o2',REAL(o2,wp)))
  END SUBROUTINE

  SUBROUTINE set_gases_lw(gases,h2o,co2,o3,n2o,ch4,o2,cfc11,cfc12,cfc22,ccl4)
    TYPE(ty_gas_concs), INTENT(INOUT) :: gases
    REAL, INTENT(IN) :: h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:)
    REAL, OPTIONAL, INTENT(IN) :: cfc11(:,:),cfc12(:,:),cfc22(:,:),ccl4(:,:)
    REAL(wp) :: zero_vmr(SIZE(h2o,1),SIZE(h2o,2))
    LOGICAL :: any_cfc,all_cfc
    zero_vmr=0._wp
    any_cfc=PRESENT(cfc11).OR.PRESENT(cfc12).OR.PRESENT(cfc22).OR.PRESENT(ccl4)
    all_cfc=PRESENT(cfc11).AND.PRESENT(cfc12).AND.PRESENT(cfc22).AND.PRESENT(ccl4)
    IF(any_cfc.AND..NOT.all_cfc) THEN
      CALL require('RRTMGP_LW_TRACE_GAS_PARTIAL_INPUTS')
      RETURN
    END IF
    IF(ANY(SHAPE(co2)/=SHAPE(h2o)).OR.ANY(SHAPE(o3)/=SHAPE(h2o)).OR. &
       ANY(SHAPE(n2o)/=SHAPE(h2o)).OR.ANY(SHAPE(ch4)/=SHAPE(h2o)).OR. &
       ANY(SHAPE(o2)/=SHAPE(h2o))) CALL require('gas shapes must match column layers')
    CALL rrtmgp_check_nonnegative('h2o',h2o)
    CALL rrtmgp_check_nonnegative('co2',co2)
    CALL rrtmgp_check_nonnegative('o3',o3)
    CALL rrtmgp_check_nonnegative('n2o',n2o)
    CALL rrtmgp_check_nonnegative('ch4',ch4)
    CALL rrtmgp_check_nonnegative('o2',o2)
    CALL require(gases%init(names_lw))
    CALL require(gases%set_vmr('h2o',REAL(h2o,wp)))
    CALL require(gases%set_vmr('co2',REAL(co2,wp)))
    CALL require(gases%set_vmr('o3',REAL(o3,wp)))
    CALL require(gases%set_vmr('n2o',REAL(n2o,wp)))
    CALL require(gases%set_vmr('ch4',REAL(ch4,wp)))
    CALL require(gases%set_vmr('o2',REAL(o2,wp)))
    IF(all_cfc) THEN
      IF(ANY(SHAPE(cfc11)/=SHAPE(h2o)).OR.ANY(SHAPE(cfc12)/=SHAPE(h2o)).OR. &
         ANY(SHAPE(cfc22)/=SHAPE(h2o)).OR.ANY(SHAPE(ccl4)/=SHAPE(h2o))) THEN
        CALL require('RRTMGP_LW_TRACE_GAS_SHAPE_MISMATCH')
        RETURN
      END IF
      IF(.NOT.ALL(ieee_is_finite(cfc11)).OR..NOT.ALL(ieee_is_finite(cfc12)).OR. &
         .NOT.ALL(ieee_is_finite(cfc22)).OR..NOT.ALL(ieee_is_finite(ccl4))) THEN
        CALL require('RRTMGP_LW_TRACE_GAS_NOT_FINITE_NONNEGATIVE')
        RETURN
      END IF
      IF(ANY(cfc11<0.).OR.ANY(cfc12<0.).OR.ANY(cfc22<0.).OR.ANY(ccl4<0.)) &
        CALL require('RRTMGP_LW_TRACE_GAS_NOT_FINITE_NONNEGATIVE')
      CALL require(gases%set_vmr('cfc11',REAL(cfc11,wp)))
      CALL require(gases%set_vmr('cfc12',REAL(cfc12,wp)))
      CALL require(gases%set_vmr('cfc22',REAL(cfc22,wp)))
      CALL require(gases%set_vmr('ccl4',REAL(ccl4,wp)))
    ELSE
      CALL require(gases%set_vmr('cfc11',zero_vmr))
      CALL require(gases%set_vmr('cfc12',zero_vmr))
      CALL require(gases%set_vmr('cfc22',zero_vmr))
      CALL require(gases%set_vmr('ccl4',zero_vmr))
    END IF
  END SUBROUTINE

  SUBROUTINE cloud_mask(cf,ngpt,overlap,seed,mask,column_seeds)
    REAL, INTENT(IN) :: cf(:,:)
    INTEGER, INTENT(IN) :: ngpt,overlap,seed
    LOGICAL, INTENT(OUT) :: mask(SIZE(cf,1),SIZE(cf,2),ngpt)
    INTEGER, OPTIONAL, INTENT(IN) :: column_seeds(:)
    REAL(wp) :: randoms(ngpt,SIZE(cf,2),SIZE(cf,1))
    INTEGER(i8) :: state
    INTEGER :: c,k,g
    IF (overlap<0.OR.overlap>3) CALL require('cloud overlap supported: 0, 1, 2, 3')
    IF(PRESENT(column_seeds)) THEN
      IF(SIZE(column_seeds)/=SIZE(cf,1)) CALL require('column_seeds shape must match columns')
    END IF
    state=MODULO(INT(seed,i8),2147483646_i8)+1_i8
    DO c=1,SIZE(cf,1)
      IF(PRESENT(column_seeds)) state=MODULO(INT(column_seeds(c),i8),2147483646_i8)+1_i8
      DO k=1,SIZE(cf,2)
        DO g=1,ngpt
          state=MODULO(48271_i8*state,2147483647_i8)
          randoms(g,k,c)=REAL(state,wp)/2147483647._wp
        END DO
      END DO
    END DO
    SELECT CASE(overlap)
    CASE(0)
      mask=.FALSE.
    CASE(2)
      CALL require(sampled_mask_max_ran(randoms,REAL(cf,wp),mask))
    CASE DEFAULT
      DO c=1,SIZE(cf,1)
        DO k=1,SIZE(cf,2)
          DO g=1,ngpt
            IF(overlap==3) THEN
              mask(c,k,g)=randoms(g,1,c)>1._wp-REAL(cf(c,k),wp)
            ELSE
              mask(c,k,g)=randoms(g,k,c)>1._wp-REAL(cf(c,k),wp)
            END IF
          END DO
        END DO
      END DO
    END SELECT
  END SUBROUTINE

  ! The public ice LUT uses effective diameter. WRF's Fu dge=1.0315*r_ec;
  ! Thompson supplies effective radius directly. Convert both to diameter.
  FUNCTION ice_diameter(re,iceflag) RESULT(d)
    REAL, INTENT(IN) :: re(:,:)
    INTEGER, INTENT(IN) :: iceflag
    REAL(wp) :: d(SIZE(re,1),SIZE(re,2))
    d=2._wp*REAL(re,wp)
    IF(iceflag==3) d=d/1.0315_wp
  END FUNCTION

  FUNCTION gas_dry_column(h2o,plev,native_mass) RESULT(col_dry)
    ! Bottom-first WRF layers: kg dry air m-2 to dry molecules cm-2.
    ! Above the native model top, retain the pressure/VMR extension policy.
    ! The optional prefix leaves historical standalone callers unchanged.
    REAL, INTENT(IN) :: h2o(:,:),plev(:,:)
    REAL, OPTIONAL, INTENT(IN) :: native_mass(:,:)
    REAL(wp) :: col_dry(SIZE(h2o,1),SIZE(h2o,2))
    col_dry=get_col_dry(REAL(h2o,wp),REAL(plev,wp)*100._wp)
    IF(PRESENT(native_mass)) THEN
      col_dry(:,1:SIZE(native_mass,2))=REAL(native_mass,wp)* &
        (avogad/(initialized_mol_weight_dry*10000._wp))
    END IF
  END FUNCTION gas_dry_column

  SUBROUTINE rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
                             cf,lwp,iwp,swp,rel,rei,res,iceflag,overlap,seed, &
                             up,dn,hr,upc,dnc,hrc,column_seeds,rwp,native_dry_layer_mass_kg_m2,gwp,hwp,lambda_g,lambda_h, &
                             frozen_context,cfc11vmr,cfc12vmr,cfc22vmr,ccl4vmr)
    REAL, INTENT(IN) :: play(:,:),plev(:,:),tlay(:,:),tlev(:,:),tsfc(:),emis(:,:)
    REAL, INTENT(IN) :: h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:)
    REAL, INTENT(IN) :: cf(:,:),lwp(:,:),iwp(:,:),swp(:,:),rel(:,:),rei(:,:),res(:,:)
    INTEGER, INTENT(IN) :: iceflag,overlap,seed
    INTEGER, OPTIONAL, INTENT(IN) :: column_seeds(:)
    REAL, OPTIONAL, INTENT(IN) :: rwp(:,:),native_dry_layer_mass_kg_m2(:,:)
    REAL, OPTIONAL, INTENT(IN) :: gwp(:,:),hwp(:,:),lambda_g(:,:),lambda_h(:,:)
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: frozen_context
    REAL, OPTIONAL, INTENT(IN) :: cfc11vmr(:,:),cfc12vmr(:,:),cfc22vmr(:,:),ccl4vmr(:,:)
    REAL, INTENT(OUT) :: up(:,:),dn(:,:),hr(:,:),upc(:,:),dnc(:,:),hrc(:,:)
    TYPE(ty_gas_concs) :: gases
    TYPE(ty_optical_props_1scl) :: atmos,clouds,snow,sampled
    TYPE(ty_source_func_lw) :: source
    TYPE(ty_fluxes_broadband) :: flux
    REAL(wp), TARGET :: fu(SIZE(plev,1),SIZE(plev,2)),fd(SIZE(plev,1),SIZE(plev,2))
    REAL(wp) :: col_dry(SIZE(play,1),SIZE(play,2))
    REAL(wp) :: heat(SIZE(play,1),SIZE(play,2)),zero(SIZE(play,1),SIZE(play,2))
    REAL(wp) :: emissivity(gas_lw%get_nband(),SIZE(play,1))
    REAL(wp) :: rl(SIZE(play,1),SIZE(play,2)),di(SIZE(play,1),SIZE(play,2)),ds(SIZE(play,1),SIZE(play,2))
    LOGICAL :: mask(SIZE(play,1),SIZE(play,2),gas_lw%get_ngpt())
    INTEGER :: nc,nl,precip_status
    LOGICAL :: trace_gases
    IF(.NOT.ready) CALL require('initialization must precede parallel column calls')
    CALL validate_frozen_inputs(SHAPE(play),gwp,hwp,lambda_g,lambda_h,frozen_context)
    CALL rrtmgp_validate_column_inputs(play,plev,tlay,cf,lwp,iwp,swp,rel,rei,res)
    IF(PRESENT(native_dry_layer_mass_kg_m2)) THEN
      IF(SIZE(native_dry_layer_mass_kg_m2,1)/=SIZE(play,1).OR. &
         SIZE(native_dry_layer_mass_kg_m2,2)<1.OR.SIZE(native_dry_layer_mass_kg_m2,2)>SIZE(play,2)) &
        CALL require('RRTMGP_INPUT_NATIVE_DRY_MASS_SHAPE')
      IF(.NOT.ALL(ieee_is_finite(native_dry_layer_mass_kg_m2))) &
        CALL require('RRTMGP_INPUT_NATIVE_DRY_MASS_NOT_POSITIVE_FINITE')
      IF(ANY(native_dry_layer_mass_kg_m2<=0.)) &
        CALL require('RRTMGP_INPUT_NATIVE_DRY_MASS_NOT_POSITIVE_FINITE')
    END IF
    IF(PRESENT(rwp)) THEN
      IF(ANY(SHAPE(rwp)/=SHAPE(play))) CALL require('RRTMGP_INPUT_RWP_SHAPE_MISMATCH')
      CALL rrtmgp_check_nonnegative('rwp',rwp)
      IF(ANY(cf==0..AND.rwp>0.)) CALL require('RRTMGP_INPUT_ZERO_CLOUD_FRACTION_WITH_RAIN_PATH')
    END IF
    IF(ANY(SHAPE(h2o)/=SHAPE(play))) CALL require('gas shapes must match column layers')
    IF(overlap<0.OR.overlap>3) CALL require('cloud overlap supported: 0, 1, 2, 3')
    IF(PRESENT(column_seeds)) THEN
      IF(SIZE(column_seeds)/=SIZE(play,1)) CALL require('column_seeds shape must match columns')
    END IF
    IF(ANY(SHAPE(up)/=SHAPE(plev)).OR.ANY(SHAPE(dn)/=SHAPE(plev)).OR. &
       ANY(SHAPE(upc)/=SHAPE(plev)).OR.ANY(SHAPE(dnc)/=SHAPE(plev)).OR. &
       ANY(SHAPE(hr)/=SHAPE(play)).OR.ANY(SHAPE(hrc)/=SHAPE(play))) &
       CALL require('output shapes must match columns and interfaces/layers')
    nc=SIZE(play,1); nl=SIZE(play,2); zero=0._wp
    trace_gases=PRESENT(cfc11vmr).AND.PRESENT(cfc12vmr).AND.PRESENT(cfc22vmr).AND.PRESENT(ccl4vmr)
    IF((PRESENT(cfc11vmr).OR.PRESENT(cfc12vmr).OR.PRESENT(cfc22vmr).OR.PRESENT(ccl4vmr)).AND..NOT.trace_gases) THEN
      CALL require('RRTMGP_LW_TRACE_GAS_PARTIAL_INPUTS')
      RETURN
    END IF
    IF(trace_gases) THEN
      IF(ANY(SHAPE(cfc11vmr)/=SHAPE(play)).OR.ANY(SHAPE(cfc12vmr)/=SHAPE(play)).OR. &
         ANY(SHAPE(cfc22vmr)/=SHAPE(play)).OR.ANY(SHAPE(ccl4vmr)/=SHAPE(play))) THEN
        CALL require('RRTMGP_LW_TRACE_GAS_SHAPE_MISMATCH')
        RETURN
      END IF
      IF(.NOT.ALL(ieee_is_finite(cfc11vmr)).OR..NOT.ALL(ieee_is_finite(cfc12vmr)).OR. &
         .NOT.ALL(ieee_is_finite(cfc22vmr)).OR..NOT.ALL(ieee_is_finite(ccl4vmr))) THEN
        CALL require('RRTMGP_LW_TRACE_GAS_NOT_FINITE_NONNEGATIVE')
        RETURN
      END IF
      IF(ANY(cfc11vmr<0.).OR.ANY(cfc12vmr<0.).OR.ANY(cfc22vmr<0.).OR.ANY(ccl4vmr<0.)) THEN
        CALL require('RRTMGP_LW_TRACE_GAS_NOT_FINITE_NONNEGATIVE')
        RETURN
      END IF
    END IF
    IF(SIZE(tsfc)/=nc.OR.ANY(SHAPE(tlev)/=SHAPE(plev)).OR.SIZE(emis,1)/=nc) &
      CALL require('LW surface/interface shapes must match columns')
    CALL rrtmgp_check_positive('tsfc',RESHAPE(tsfc,[nc,1]))
    CALL rrtmgp_check_positive('tlev',tlev)
    CALL rrtmgp_check_unit_interval('emis',emis)
    IF(SIZE(emis,2)==1) THEN
      emissivity=SPREAD(REAL(emis(:,1),wp),1,gas_lw%get_nband())
    ELSE IF(SIZE(emis,2)==gas_lw%get_nband()) THEN
      emissivity=TRANSPOSE(REAL(emis,wp))
    ELSE
      CALL require('surface emissivity must be grey or match LW bands')
    END IF
    IF(trace_active('LW')) THEN
      CALL trace_input_start('LW',nc,nl,overlap,seed,iceflag,udm_precip=PRESENT(rwp), &
           gravity=REAL(initialized_gravity,real64),cp_dry=REAL(initialized_cp_dry,real64), &
           mol_weight_dry=REAL(initialized_mol_weight_dry,real64), &
           native_dry_mass=PRESENT(native_dry_layer_mass_kg_m2), &
           frozen_mode=initialized_frozen_mode,frozen_table_sha256=frozen_table_sha256(), &
           trace_gases_present=trace_gases)
      CALL trace_input('LW','SOLAR',RESHAPE([0.],[1,1]))
      CALL trace_input('LW','PLAY',play)
      CALL trace_input('LW','PLEV',plev)
      CALL trace_input('LW','TLAY',tlay)
      CALL trace_input('LW','TLEV',tlev)
      CALL trace_input('LW','TSFC',RESHAPE(tsfc,[nc,1]))
      CALL trace_input('LW','H2O',h2o)
      CALL trace_input('LW','CO2',co2)
      CALL trace_input('LW','O3',o3)
      CALL trace_input('LW','N2O',n2o)
      CALL trace_input('LW','CH4',ch4)
      CALL trace_input('LW','O2',o2)
      IF(trace_gases) THEN
        CALL trace_input('LW','VMR_CFC11',cfc11vmr)
        CALL trace_input('LW','VMR_CFC12',cfc12vmr)
        CALL trace_input('LW','VMR_CFC22',cfc22vmr)
        CALL trace_input('LW','VMR_CCL4',ccl4vmr)
      END IF
      CALL trace_input('LW','EMIS',emis)
      CALL trace_input('LW','AVDIR',RESHAPE(0.*tsfc,[nc,1]))
      CALL trace_input('LW','AVDIF',RESHAPE(0.*tsfc,[nc,1]))
      CALL trace_input('LW','ANDIR',RESHAPE(0.*tsfc,[nc,1]))
      CALL trace_input('LW','ANDIF',RESHAPE(0.*tsfc,[nc,1]))
      CALL trace_input('LW','MU0',RESHAPE(0.*tsfc,[nc,1]))
      CALL trace_input('LW','CF',cf)
      CALL trace_input('LW','LWP',lwp)
      CALL trace_input('LW','IWP',iwp)
      CALL trace_input('LW','SWP',swp)
      CALL trace_input('LW','REL',rel)
      CALL trace_input('LW','REI',rei)
      CALL trace_input('LW','RES',res)
      CALL trace_input('LW','ICE_ROUGHNESS',RESHAPE([REAL(initialized_ice_roughness)],[1,1]))
      IF(PRESENT(rwp)) THEN
        CALL trace_input('LW','PRECIPITATION_OPTICS',RESHAPE([1.],[1,1]))
        CALL trace_input('LW','RWP',rwp)
      END IF
      IF(PRESENT(native_dry_layer_mass_kg_m2)) &
        CALL trace_input('LW','NATIVE_DRY_LAYER_MASS_KG_M2',native_dry_layer_mass_kg_m2)
      IF(rrtmgp_frozen_enabled()) THEN
        CALL trace_input('LW','GWP',gwp)
        CALL trace_input('LW','HWP',hwp)
        CALL trace_input('LW','LAMBDA_G',lambda_g)
        CALL trace_input('LW','LAMBDA_H',lambda_h)
      END IF
      CALL trace_input_end('LW')
      CALL trace_result_start('LW',nc,nl)
    END IF
    CALL set_gases_lw(gases,h2o,co2,o3,n2o,ch4,o2,cfc11vmr,cfc12vmr,cfc22vmr,ccl4vmr)
    col_dry=gas_dry_column(h2o,plev,native_dry_layer_mass_kg_m2)
    CALL require(atmos%alloc_1scl(nc,nl,gas_lw))
    CALL require(source%alloc(nc,nl,gas_lw))
    CALL require(gas_lw%gas_optics(REAL(play,wp)*100._wp,REAL(plev,wp)*100._wp, &
                 REAL(tlay,wp),REAL(tsfc,wp),gases,atmos,source,col_dry=col_dry,tlev=REAL(tlev,wp)))
    IF(trace_active('LW')) THEN
      CALL trace_result('LW','GAS_COL_DRY',col_dry)
      CALL trace_result('LW','GAS_TAU',atmos%tau)
      IF(trace_gases) CALL trace_result('LW','GAS_TAU_RAW',atmos%tau)
    END IF
    flux%flux_up=>fu; flux%flux_dn=>fd
    CALL require(rte_lw(atmos,.FALSE.,source,emissivity,flux))
    upc=REAL(fu); dnc=REAL(fd)
    CALL require(compute_heating_rate(fu,fd,REAL(plev,wp)*100._wp,heat))
    hrc=REAL(heat*86400._wp)
    ! A selected replay also records prepared optics for clear/overlap-zero controls.
    IF((ANY(cf>0.).AND.overlap/=0).OR.trace_active('LW')) THEN
      CALL require(clouds%alloc_1scl(nc,nl,cloud_lw))
      CALL require(snow%alloc_1scl(nc,nl,cloud_lw))
      CALL require(sampled%alloc_1scl(nc,nl,gas_lw))
      rl=MAX(cloud_lw%get_min_radius_liq(),MIN(cloud_lw%get_max_radius_liq(),REAL(rel,wp)))
      di=MAX(cloud_lw%get_min_radius_ice(),MIN(cloud_lw%get_max_radius_ice(),ice_diameter(rei,iceflag)))
      ds=MAX(cloud_lw%get_min_radius_ice(),MIN(cloud_lw%get_max_radius_ice(),2._wp*REAL(res,wp)))
      CALL require(cloud_lw%cloud_optics(REAL(lwp,wp),REAL(iwp,wp),rl,di,clouds))
      IF(PRESENT(rwp)) THEN
        ds=REAL(res,wp) ! Native UDM snow radius, never ice diameter/LUT clipping.
        CALL rrtmgp_precip_lw_optics(REAL(rwp,wp),REAL(swp,wp),ds, &
             gas_lw%get_band_lims_wavenumber(),snow%tau,precip_status)
        IF(precip_status/=0) CALL require('RRTMGP_UDM_PRECIP_LW_INVALID_INPUT_OR_BANDS')
        IF(trace_active('LW')) CALL trace_result('LW','PRECIP_TAU',snow%tau)
      ELSE
        CALL require(cloud_lw%cloud_optics(zero,REAL(swp,wp),rl,ds,snow))
      END IF
      CALL require(snow%increment(clouds))
    IF(trace_active('LW')) THEN
      CALL trace_result('LW','CLOUD_TAU',clouds%tau)
    END IF
    IF(trace_active('LW')) THEN
      CALL trace_result('LW','PREPARED_TAU',clouds%tau)
      CALL trace_result('LW','RL_USED',rl)
      CALL trace_result('LW','DI_USED',di)
      CALL trace_result('LW','DS_USED',ds)
    END IF
      CALL cloud_mask(cf,gas_lw%get_ngpt(),overlap,seed,mask,column_seeds)
    IF(trace_active('LW')) THEN
      CALL trace_result('LW','MASK',MERGE(1._wp,0._wp,mask))
    END IF
      CALL require(draw_samples(mask,clouds,sampled))
      IF(ANY(cf>0.).AND.overlap/=0) CALL require(sampled%increment(atmos))
    END IF
    IF(rrtmgp_frozen_enabled()) CALL add_frozen_lw(atmos,tlay,gwp,hwp,lambda_g,lambda_h,frozen_context)
    IF(trace_active('LW')) THEN
      CALL trace_result('LW','TOTAL_TAU',atmos%tau)
    END IF
    CALL require(rte_lw(atmos,.FALSE.,source,emissivity,flux))
    up=REAL(fu); dn=REAL(fd)
    CALL require(compute_heating_rate(fu,fd,REAL(plev,wp)*100._wp,heat))
    hr=REAL(heat*86400._wp)
    IF(trace_active('LW')) THEN
      CALL trace_result('LW','UP',up)
      CALL trace_result('LW','DN',dn)
      CALL trace_result('LW','HR',hr)
      CALL trace_result('LW','UPC',upc)
      CALL trace_result('LW','DNC',dnc)
      CALL trace_result('LW','HRC',hrc)
    END IF
  END SUBROUTINE

  SUBROUTINE rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2, &
                             avdir,avdif,andir,andif,mu0,solar, &
                             cf,lwp,iwp,swp,rel,rei,res,iceflag,overlap,seed, &
                             up,dn,hr,upc,dnc,hrc,direct,diffuse,directc,visdir,visdif,nirdir,nirdif,column_seeds,rwp,native_dry_layer_mass_kg_m2,gwp,hwp,lambda_g,lambda_h,frozen_context)
    REAL, INTENT(IN) :: play(:,:),plev(:,:),tlay(:,:)
    REAL, INTENT(IN) :: h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:)
    REAL, INTENT(IN) :: avdir(:),avdif(:),andir(:),andif(:),mu0(:),solar
    REAL, INTENT(IN) :: cf(:,:),lwp(:,:),iwp(:,:),swp(:,:),rel(:,:),rei(:,:),res(:,:)
    INTEGER, INTENT(IN) :: iceflag,overlap,seed
    INTEGER, OPTIONAL, INTENT(IN) :: column_seeds(:)
    REAL, OPTIONAL, INTENT(IN) :: rwp(:,:),native_dry_layer_mass_kg_m2(:,:)
    REAL, OPTIONAL, INTENT(IN) :: gwp(:,:),hwp(:,:),lambda_g(:,:),lambda_h(:,:)
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: frozen_context
    REAL, INTENT(OUT) :: up(:,:),dn(:,:),hr(:,:),upc(:,:),dnc(:,:),hrc(:,:)
    REAL, INTENT(OUT) :: direct(:,:),diffuse(:,:),directc(:,:)
    REAL, INTENT(OUT) :: visdir(:,:),visdif(:,:),nirdir(:,:),nirdif(:,:)
    TYPE(ty_gas_concs) :: gases
    TYPE(ty_optical_props_2str) :: atmos,clouds,snow,sampled
    TYPE(ty_fluxes_byband) :: flux
    REAL(wp), TARGET :: fu(SIZE(plev,1),SIZE(plev,2)),fd(SIZE(plev,1),SIZE(plev,2)), &
                        fdir(SIZE(plev,1),SIZE(plev,2)), &
                        bd(SIZE(plev,1),SIZE(plev,2),gas_sw%get_nband()), &
                        bdir(SIZE(plev,1),SIZE(plev,2),gas_sw%get_nband())
    REAL(wp) :: col_dry(SIZE(play,1),SIZE(play,2))
    REAL(wp) :: heat(SIZE(play,1),SIZE(play,2)),zero(SIZE(play,1),SIZE(play,2)), &
                rl(SIZE(play,1),SIZE(play,2)),di(SIZE(play,1),SIZE(play,2)),ds(SIZE(play,1),SIZE(play,2))
    REAL(wp) :: toa(SIZE(play,1),gas_sw%get_ngpt()),albdir(gas_sw%get_nband(),SIZE(play,1)), &
                albdif(gas_sw%get_nband(),SIZE(play,1)),bands(2,gas_sw%get_nband()), &
                visible_weight(gas_sw%get_nband())
    LOGICAL :: mask(SIZE(play,1),SIZE(play,2),gas_sw%get_ngpt())
    INTEGER :: nc,nl,b,c,precip_status
    IF(.NOT.ready) CALL require('initialization must precede parallel column calls')
    CALL validate_frozen_inputs(SHAPE(play),gwp,hwp,lambda_g,lambda_h,frozen_context)
    CALL rrtmgp_validate_column_inputs(play,plev,tlay,cf,lwp,iwp,swp,rel,rei,res)
    IF(PRESENT(native_dry_layer_mass_kg_m2)) THEN
      IF(SIZE(native_dry_layer_mass_kg_m2,1)/=SIZE(play,1).OR. &
         SIZE(native_dry_layer_mass_kg_m2,2)<1.OR.SIZE(native_dry_layer_mass_kg_m2,2)>SIZE(play,2)) &
        CALL require('RRTMGP_INPUT_NATIVE_DRY_MASS_SHAPE')
      IF(.NOT.ALL(ieee_is_finite(native_dry_layer_mass_kg_m2))) &
        CALL require('RRTMGP_INPUT_NATIVE_DRY_MASS_NOT_POSITIVE_FINITE')
      IF(ANY(native_dry_layer_mass_kg_m2<=0.)) &
        CALL require('RRTMGP_INPUT_NATIVE_DRY_MASS_NOT_POSITIVE_FINITE')
    END IF
    IF(PRESENT(rwp)) THEN
      IF(ANY(SHAPE(rwp)/=SHAPE(play))) CALL require('RRTMGP_INPUT_RWP_SHAPE_MISMATCH')
      CALL rrtmgp_check_nonnegative('rwp',rwp)
      IF(ANY(cf==0..AND.rwp>0.)) CALL require('RRTMGP_INPUT_ZERO_CLOUD_FRACTION_WITH_RAIN_PATH')
    END IF
    IF(ANY(SHAPE(h2o)/=SHAPE(play))) CALL require('gas shapes must match column layers')
    IF(overlap<0.OR.overlap>3) CALL require('cloud overlap supported: 0, 1, 2, 3')
    IF(PRESENT(column_seeds)) THEN
      IF(SIZE(column_seeds)/=SIZE(play,1)) CALL require('column_seeds shape must match columns')
    END IF
    IF(ANY(SHAPE(up)/=SHAPE(plev)).OR.ANY(SHAPE(dn)/=SHAPE(plev)).OR. &
       ANY(SHAPE(upc)/=SHAPE(plev)).OR.ANY(SHAPE(dnc)/=SHAPE(plev)).OR. &
       ANY(SHAPE(hr)/=SHAPE(play)).OR.ANY(SHAPE(hrc)/=SHAPE(play))) &
       CALL require('output shapes must match columns and interfaces/layers')
    nc=SIZE(play,1); nl=SIZE(play,2); zero=0._wp
    up=0.; dn=0.; hr=0.; upc=0.; dnc=0.; hrc=0.; direct=0.; diffuse=0.; directc=0.
    visdir=0.; visdif=0.; nirdir=0.; nirdif=0.
    IF(SIZE(mu0)/=nc.OR.SIZE(avdir)/=nc.OR.SIZE(avdif)/=nc.OR.SIZE(andir)/=nc.OR.SIZE(andif)/=nc) &
      CALL require('SW surface shapes must match columns')
    CALL rrtmgp_check_unit_interval('avdir',RESHAPE(avdir,[nc,1]))
    CALL rrtmgp_check_unit_interval('avdif',RESHAPE(avdif,[nc,1]))
    CALL rrtmgp_check_unit_interval('andir',RESHAPE(andir,[nc,1]))
    CALL rrtmgp_check_unit_interval('andif',RESHAPE(andif,[nc,1]))
    IF(.NOT.ALL(ieee_is_finite(mu0))) CALL require('mu0 must be finite')
    IF(ANY(ABS(mu0)>1.)) CALL require('mu0 must be in [-1,1]')
    CALL rrtmgp_check_nonnegative('solar',RESHAPE([solar],[1,1]))
    IF(ANY(SHAPE(direct)/=SHAPE(plev)).OR.ANY(SHAPE(diffuse)/=SHAPE(plev)).OR. &
       ANY(SHAPE(directc)/=SHAPE(plev)).OR.ANY(SHAPE(visdir)/=SHAPE(plev)).OR. &
       ANY(SHAPE(visdif)/=SHAPE(plev)).OR.ANY(SHAPE(nirdir)/=SHAPE(plev)).OR. &
       ANY(SHAPE(nirdif)/=SHAPE(plev))) CALL require('SW diagnostic shapes must match interfaces')
    CALL set_gases_sw(gases,h2o,co2,o3,n2o,ch4,o2)
    col_dry=gas_dry_column(h2o,plev,native_dry_layer_mass_kg_m2)
    IF(ALL(mu0<=0.)) RETURN
    IF(ANY(mu0<=0.)) CALL require('daylight columns must be packed separately')
    IF(trace_active('SW')) THEN
      CALL trace_input_start('SW',nc,nl,overlap,seed,iceflag,udm_precip=PRESENT(rwp), &
           gravity=REAL(initialized_gravity,real64),cp_dry=REAL(initialized_cp_dry,real64), &
           mol_weight_dry=REAL(initialized_mol_weight_dry,real64), &
           native_dry_mass=PRESENT(native_dry_layer_mass_kg_m2), &
           frozen_mode=initialized_frozen_mode,frozen_table_sha256=frozen_table_sha256())
      CALL trace_input('SW','SOLAR',RESHAPE([solar],[1,1]))
      CALL trace_input('SW','PLAY',play)
      CALL trace_input('SW','PLEV',plev)
      CALL trace_input('SW','TLAY',tlay)
      CALL trace_input('SW','TLEV',0.*plev)
      CALL trace_input('SW','TSFC',RESHAPE(0.*mu0,[nc,1]))
      CALL trace_input('SW','H2O',h2o)
      CALL trace_input('SW','CO2',co2)
      CALL trace_input('SW','O3',o3)
      CALL trace_input('SW','N2O',n2o)
      CALL trace_input('SW','CH4',ch4)
      CALL trace_input('SW','O2',o2)
      CALL trace_input('SW','EMIS',RESHAPE(0.*mu0,[nc,1]))
      CALL trace_input('SW','AVDIR',RESHAPE(avdir,[nc,1]))
      CALL trace_input('SW','AVDIF',RESHAPE(avdif,[nc,1]))
      CALL trace_input('SW','ANDIR',RESHAPE(andir,[nc,1]))
      CALL trace_input('SW','ANDIF',RESHAPE(andif,[nc,1]))
      CALL trace_input('SW','MU0',RESHAPE(mu0,[nc,1]))
      CALL trace_input('SW','CF',cf)
      CALL trace_input('SW','LWP',lwp)
      CALL trace_input('SW','IWP',iwp)
      CALL trace_input('SW','SWP',swp)
      CALL trace_input('SW','REL',rel)
      CALL trace_input('SW','REI',rei)
      CALL trace_input('SW','RES',res)
      CALL trace_input('SW','ICE_ROUGHNESS',RESHAPE([REAL(initialized_ice_roughness)],[1,1]))
      CALL trace_input('SW','SW_BAND_PARTITION',RESHAPE([1.],[1,1]))
      IF(PRESENT(rwp)) THEN
        CALL trace_input('SW','PRECIPITATION_OPTICS',RESHAPE([1.],[1,1]))
        CALL trace_input('SW','RWP',rwp)
      END IF
      IF(PRESENT(native_dry_layer_mass_kg_m2)) &
        CALL trace_input('SW','NATIVE_DRY_LAYER_MASS_KG_M2',native_dry_layer_mass_kg_m2)
      IF(rrtmgp_frozen_enabled()) THEN
        CALL trace_input('SW','GWP',gwp)
        CALL trace_input('SW','HWP',hwp)
        CALL trace_input('SW','LAMBDA_G',lambda_g)
        CALL trace_input('SW','LAMBDA_H',lambda_h)
      END IF
      CALL trace_input_end('SW')
      CALL trace_result_start('SW',nc,nl)
    END IF
    CALL require(atmos%alloc_2str(nc,nl,gas_sw))
    CALL require(gas_sw%gas_optics(REAL(play,wp)*100._wp,REAL(plev,wp)*100._wp, &
                                 REAL(tlay,wp),gases,atmos,toa,col_dry=col_dry))
    IF(trace_active('SW')) THEN
      CALL trace_result('SW','GAS_COL_DRY',col_dry)
      CALL trace_result('SW','GAS_TAU',atmos%tau)
      CALL trace_result('SW','GAS_SSA',atmos%ssa)
      CALL trace_result('SW','GAS_G',atmos%g)
    END IF
    DO c=1,nc
      IF(SUM(toa(c,:))<=0._wp) CALL require('TOA solar spectrum must have positive integral')
      toa(c,:)=toa(c,:)*(REAL(solar,wp)/SUM(toa(c,:)))
    END DO
    bands=gas_sw%get_band_lims_wavenumber()
    DO b=1,gas_sw%get_nband()
      ! Pinned UFS/CCPP convention: the 12850--16000 cm-1 band is half VIS/NIR.
      ! This is a band convention, not an exact integration at 0.7 micrometers.
      IF(bands(2,b)<=12850._wp) THEN
        visible_weight(b)=0._wp
      ELSE IF(bands(1,b)>=16000._wp) THEN
        visible_weight(b)=1._wp
      ELSE IF(bands(1,b)==12850._wp.AND.bands(2,b)==16000._wp) THEN
        visible_weight(b)=0.5_wp
      ELSE
        CALL require('SW VIS/NIR partition requires the 12850--16000 cm-1 transition band')
      END IF
      albdir(b,:)=(1._wp-visible_weight(b))*REAL(andir,wp)+visible_weight(b)*REAL(avdir,wp)
      albdif(b,:)=(1._wp-visible_weight(b))*REAL(andif,wp)+visible_weight(b)*REAL(avdif,wp)
    END DO
    flux%flux_up=>fu; flux%flux_dn=>fd; flux%flux_dn_dir=>fdir
    flux%bnd_flux_dn=>bd; flux%bnd_flux_dn_dir=>bdir
    CALL require(rte_sw(atmos,.FALSE.,REAL(mu0,wp),toa,albdir,albdif,flux))
    upc=REAL(fu); dnc=REAL(fd); directc=REAL(fdir)
    CALL require(compute_heating_rate(fu,fd,REAL(plev,wp)*100._wp,heat)); hrc=REAL(heat*86400._wp)
    ! A selected replay also records prepared optics for clear/overlap-zero controls.
    IF((ANY(cf>0.).AND.overlap/=0).OR.trace_active('SW')) THEN
      CALL require(clouds%alloc_2str(nc,nl,cloud_sw))
      CALL require(snow%alloc_2str(nc,nl,cloud_sw))
      CALL require(sampled%alloc_2str(nc,nl,gas_sw))
      rl=MAX(cloud_sw%get_min_radius_liq(),MIN(cloud_sw%get_max_radius_liq(),REAL(rel,wp)))
      di=MAX(cloud_sw%get_min_radius_ice(),MIN(cloud_sw%get_max_radius_ice(),ice_diameter(rei,iceflag)))
      ds=MAX(cloud_sw%get_min_radius_ice(),MIN(cloud_sw%get_max_radius_ice(),2._wp*REAL(res,wp)))
      CALL require(cloud_sw%cloud_optics(REAL(lwp,wp),REAL(iwp,wp),rl,di,clouds))
      IF(PRESENT(rwp)) THEN
        ds=REAL(res,wp) ! Native UDM snow radius in micrometers.
        CALL rrtmgp_precip_sw_optics(REAL(rwp,wp),REAL(swp,wp),ds,bands, &
             snow%tau,snow%ssa,snow%g,precip_status)
        IF(precip_status/=0) CALL require('RRTMGP_UDM_PRECIP_SW_INVALID_INPUT_OR_BANDS')
        ! CCPP precipitation is already delta scaled: scale cloud exactly once.
        CALL require(clouds%delta_scale())
        DO b=1,gas_sw%get_nband()
          WHERE(cf==0.)
            snow%tau(:,:,b)=0._wp
            snow%ssa(:,:,b)=0._wp
            snow%g(:,:,b)=0._wp
          END WHERE
        END DO
        IF(trace_active('SW')) THEN
          CALL trace_result('SW','PRECIP_TAU',snow%tau)
          CALL trace_result('SW','PRECIP_SSA',snow%ssa)
          CALL trace_result('SW','PRECIP_G',snow%g)
        END IF
      ELSE
        CALL require(cloud_sw%cloud_optics(zero,REAL(swp,wp),rl,ds,snow))
      END IF
      CALL require(snow%increment(clouds))
    IF(trace_active('SW')) THEN
      CALL trace_result('SW','CLOUD_TAU',clouds%tau)
      CALL trace_result('SW','CLOUD_SSA',clouds%ssa)
      CALL trace_result('SW','CLOUD_G',clouds%g)
    END IF
      IF(.NOT.PRESENT(rwp)) CALL require(clouds%delta_scale())
    IF(trace_active('SW')) THEN
      CALL trace_result('SW','PREPARED_TAU',clouds%tau)
      CALL trace_result('SW','PREPARED_SSA',clouds%ssa)
      CALL trace_result('SW','PREPARED_G',clouds%g)
      CALL trace_result('SW','RL_USED',rl)
      CALL trace_result('SW','DI_USED',di)
      CALL trace_result('SW','DS_USED',ds)
    END IF
      CALL cloud_mask(cf,gas_sw%get_ngpt(),overlap,seed,mask,column_seeds)
    IF(trace_active('SW')) THEN
      CALL trace_result('SW','MASK',MERGE(1._wp,0._wp,mask))
    END IF
      CALL require(draw_samples(mask,clouds,sampled))
      IF(ANY(cf>0.).AND.overlap/=0) CALL require(sampled%increment(atmos))
    END IF
    IF(rrtmgp_frozen_enabled()) CALL add_frozen_sw(atmos,gwp,hwp,lambda_g,lambda_h,frozen_context)
    IF(trace_active('SW')) THEN
      CALL trace_result('SW','TOTAL_TAU',atmos%tau)
      CALL trace_result('SW','TOTAL_SSA',atmos%ssa)
      CALL trace_result('SW','TOTAL_G',atmos%g)
    END IF
    CALL require(rte_sw(atmos,.FALSE.,REAL(mu0,wp),toa,albdir,albdif,flux))
    up=REAL(fu); dn=REAL(fd); direct=REAL(fdir); diffuse=REAL(fd-fdir)
    CALL require(compute_heating_rate(fu,fd,REAL(plev,wp)*100._wp,heat)); hr=REAL(heat*86400._wp)
    DO b=1,gas_sw%get_nband()
      visdir=visdir+REAL(visible_weight(b)*bdir(:,:,b))
      visdif=visdif+REAL(visible_weight(b)*(bd(:,:,b)-bdir(:,:,b)))
      nirdir=nirdir+REAL((1._wp-visible_weight(b))*bdir(:,:,b))
      nirdif=nirdif+REAL((1._wp-visible_weight(b))*(bd(:,:,b)-bdir(:,:,b)))
    END DO
    IF(trace_active('SW')) THEN
      CALL trace_result('SW','UP',up)
      CALL trace_result('SW','DN',dn)
      CALL trace_result('SW','HR',hr)
      CALL trace_result('SW','UPC',upc)
      CALL trace_result('SW','DNC',dnc)
      CALL trace_result('SW','HRC',hrc)
      CALL trace_result('SW','DIRECT',direct)
      CALL trace_result('SW','DIFFUSE',diffuse)
      CALL trace_result('SW','DIRECTC',directc)
      CALL trace_result('SW','VISDIR',visdir)
      CALL trace_result('SW','VISDIF',visdif)
      CALL trace_result('SW','NIRDIR',nirdir)
      CALL trace_result('SW','NIRDIF',nirdif)
    END IF
  END SUBROUTINE
END MODULE module_ra_rrtmgp
