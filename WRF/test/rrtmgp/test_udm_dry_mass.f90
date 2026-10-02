PROGRAM test_udm_dry_mass
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32, real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan, ieee_positive_inf
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_build_udm_inputs, &
       RRTMGP_INPUT_OK, RRTMGP_INPUT_CLEAR_CONDENSATE, &
       RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED, RRTMGP_INPUT_CLEAR
  IMPLICIT NONE

  INTEGER, PARAMETER :: n=2, nphase=6
  REAL :: dp(n), cf(n), qc(n), qi(n), qr(n), qs(n), qg(n), qh(n)
  REAL :: re_cloud(n), re_ice(n), re_snow(n), gravity, dry_mass(n)
  REAL :: grid(n,nphase), incloud(n,nphase), radius(n,3), omitted(n,nphase)
  REAL :: limits(nphase), clipped(n,nphase), correction(n,nphase), raw_q(n,nphase)
  REAL :: grid_saved(n,nphase), incloud_saved(n,nphase), radius_saved(n,3)
  REAL :: dry_bad(1), zero_cf(n), grid_legacy_g10(n,nphase)
  REAL :: q_before(n,nphase), dp_before(n), cf_before(n), radius_before(n,3)
  REAL :: dry_before(n), limits_before(nphase), gravity_before
  INTEGER(int32) :: q_bits(n*nphase), dp_bits(n), cf_bits(n), radius_bits(3*n)
  INTEGER(int32) :: dry_bits(n), limits_bits(nphase), gravity_bits
  INTEGER :: reason, layer_reason(n), k, p
  CHARACTER(LEN=512) :: errmsg
  CHARACTER(LEN=40) :: mode
  REAL(real64) :: mass64, raw_path64, expected64
  REAL :: expected_grid, expected_correction

  CALL get_command_argument(1, mode)
  CALL initialize_inputs()
  SELECT CASE(TRIM(mode))
  CASE('native_mixed')
    CALL set_mixed_q()
    CALL save_input_bits()
    CALL build_native()
    CALL assert_input_bits_unchanged()
    IF(reason/=RRTMGP_INPUT_OK .OR. LEN_TRIM(errmsg)/=0) ERROR STOP 'native mixed status'
    CALL assert_native_mixed_paths()

    ! A different but positive pressure thickness remains a valid input. The
    ! explicit native dry mass, rather than dp/g, controls every path output.
    grid_saved=grid; incloud_saved=incloud; radius_saved=radius
    dp=[900.,300.]
    CALL build_native()
    IF(reason/=RRTMGP_INPUT_OK) ERROR STOP 'native-mass pressure-independence status'
    IF(ANY(grid/=grid_saved) .OR. ANY(incloud/=incloud_saved) .OR. &
       ANY(radius/=radius_saved)) ERROR STOP 'native dry mass output depended on dp_hpa'

  CASE('native_clear_omission')
    qc=[0.125,0.0625]; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.
    cf=[0.,0.5]; dry_mass=[1.,2.]; re_cloud=[10.,20.]
    CALL build_native_clear()
    IF(reason/=RRTMGP_INPUT_CLEAR_CONDENSATE) ERROR STOP 'native clear-condensate reason'
    IF(layer_reason(1)/=RRTMGP_INPUT_CLEAR_CONDENSATE .OR. &
       layer_reason(2)/=RRTMGP_INPUT_OK) ERROR STOP 'native clear-condensate layer reasons'
    IF(grid(1,1)/=125. .OR. omitted(1,1)/=125.) ERROR STOP 'native omitted grid path'
    IF(ANY(incloud(1,:)/=0.)) ERROR STOP 'clear layer received in-cloud path'
    IF(ANY(grid(1,2:)/=0.) .OR. ANY(omitted(1,2:)/=0.)) ERROR STOP 'clear layer phase path pollution'
    IF(ANY(omitted(2,:)/=0.)) ERROR STOP 'cloudy layer received omitted path'
    IF(grid(2,1)/=125. .OR. incloud(2,1)/=250.) ERROR STOP 'native cloudy path in omission case'

  CASE('native_hail_tiny')
    CALL set_positive_q()
    qh(2)=NEAREST(0.,1.)
    CALL build_native()
    IF(reason/=RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED) ERROR STOP 'tiny positive hail was not refused'
    IF(TRIM(errmsg)/='RRTMGP_INPUT_UDM_HAIL_OPTICS_UNSUPPORTED') ERROR STOP 'hail refusal label mismatch'
    IF(ANY(grid/=0.) .OR. ANY(incloud/=0.) .OR. ANY(radius/=0.) .OR. &
       ANY(omitted/=0.) .OR. ANY(clipped/=0.) .OR. ANY(correction/=0.)) &
       ERROR STOP 'hail refusal did not leave atomic zero outputs'

  CASE('legacy_pressure_gravity')
    CALL set_positive_q()
    dp=[1000.,500.]; gravity=10.
    CALL build_legacy()
    IF(reason/=RRTMGP_INPUT_OK) ERROR STOP 'legacy pressure/g status'
    CALL assert_legacy_paths()
    grid_legacy_g10=grid
    gravity=5.
    CALL build_legacy()
    IF(reason/=RRTMGP_INPUT_OK) ERROR STOP 'legacy alternate-gravity status'
    IF(ANY(grid/=2.*grid_legacy_g10)) ERROR STOP 'legacy fallback did not retain inverse-gravity scaling'

  CASE('dry_shape')
    dry_bad=[1.]
    CALL build_bad_mass()
    ERROR STOP 'wrong-length native dry mass was accepted'
  CASE('dry_zero')
    dry_mass(1)=0.
    CALL build_native()
    ERROR STOP 'zero native dry mass was accepted'
  CASE('dry_negative')
    dry_mass(2)=-1.
    CALL build_native()
    ERROR STOP 'negative native dry mass was accepted'
  CASE('dry_nan')
    dry_mass(1)=ieee_value(0.,ieee_quiet_nan)
    CALL build_native()
    ERROR STOP 'NaN native dry mass was accepted'
  CASE('dry_inf')
    dry_mass(2)=ieee_value(0.,ieee_positive_inf)
    CALL build_native()
    ERROR STOP 'infinite native dry mass was accepted'
  CASE('dry_path_overflow')
    CALL set_positive_q()
    qc(1)=1.0
    dry_mass(1)=HUGE(0.)*0.75
    CALL build_native()
    ERROR STOP 'overflowing native path was accepted'
  CASE DEFAULT
    ERROR STOP 'unknown dry-mass fixture mode'
  END SELECT

  WRITE(*,'(A,A)') 'UDM_DRY_MASS_FIXTURE_PASS ',TRIM(mode)

CONTAINS

  SUBROUTINE initialize_inputs()
    dp=[300.,900.]; cf=[0.5,0.25]; gravity=9.8
    dry_mass=[1.5,2.5]
    qc=0.; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.
    re_cloud=[10.,20.]; re_ice=[30.,40.]; re_snow=[50.,60.]
    limits=[0.125,0.0625,0.25,0.25,0.5,0.0625]
    grid=-11.; incloud=-12.; radius=-13.; omitted=-14.
    clipped=-15.; correction=-16.; dry_bad=-17.
    layer_reason=-18
  END SUBROUTINE initialize_inputs

  SUBROUTINE set_mixed_q()
    qc=[-0.0625,0.125]
    qi=[0.03125,-0.03125]
    qr=[-0.125,0.25]
    qs=[0.125,-0.0625]
    qg=[-0.25,0.125]
    qh=[-0.03125,-0.015625]
  END SUBROUTINE set_mixed_q

  SUBROUTINE set_positive_q()
    qc=[0.125,0.0625]; qi=[0.03125,0.125]
    qr=[0.25,0.125]; qs=[0.125,0.0625]
    qg=[0.0625,0.125]; qh=0.
  END SUBROUTINE set_positive_q

  SUBROUTINE save_input_bits()
    q_before(:,1)=qc; q_before(:,2)=qi; q_before(:,3)=qr
    q_before(:,4)=qs; q_before(:,5)=qg; q_before(:,6)=qh
    dp_before=dp; cf_before=cf
    radius_before(:,1)=re_cloud; radius_before(:,2)=re_ice; radius_before(:,3)=re_snow
    dry_before=dry_mass; limits_before=limits; gravity_before=gravity
    q_bits=TRANSFER(q_before,q_bits); dp_bits=TRANSFER(dp_before,dp_bits)
    cf_bits=TRANSFER(cf_before,cf_bits); radius_bits=TRANSFER(radius_before,radius_bits)
    dry_bits=TRANSFER(dry_before,dry_bits); limits_bits=TRANSFER(limits_before,limits_bits)
    gravity_bits=TRANSFER(gravity_before,gravity_bits)
  END SUBROUTINE save_input_bits

  SUBROUTINE assert_input_bits_unchanged()
    IF(ANY(TRANSFER(reshape_q(),q_bits)/=q_bits)) ERROR STOP 'native builder changed source q bits'
    IF(ANY(TRANSFER(dp,dp_bits)/=dp_bits)) ERROR STOP 'native builder changed dp bits'
    IF(ANY(TRANSFER(cf,cf_bits)/=cf_bits)) ERROR STOP 'native builder changed cloud-fraction bits'
    IF(ANY(TRANSFER(reshape_radius(),radius_bits)/=radius_bits)) ERROR STOP 'native builder changed radius bits'
    IF(ANY(TRANSFER(dry_mass,dry_bits)/=dry_bits)) ERROR STOP 'native builder changed native dry-mass bits'
    IF(ANY(TRANSFER(limits,limits_bits)/=limits_bits)) ERROR STOP 'native builder changed q-limit bits'
    IF(TRANSFER(gravity,gravity_bits)/=gravity_bits) ERROR STOP 'native builder changed gravity bits'
  END SUBROUTINE assert_input_bits_unchanged

  FUNCTION reshape_q() RESULT(result)
    REAL :: result(n,nphase)
    result(:,1)=qc; result(:,2)=qi; result(:,3)=qr
    result(:,4)=qs; result(:,5)=qg; result(:,6)=qh
  END FUNCTION reshape_q

  FUNCTION reshape_radius() RESULT(result)
    REAL :: result(n,3)
    result(:,1)=re_cloud; result(:,2)=re_ice; result(:,3)=re_snow
  END FUNCTION reshape_radius

  SUBROUTINE build_native()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='dry-mass-fixture', &
         omitted_grid_path=omitted,layer_reason=layer_reason,negative_q_limits=limits, &
         clipped_negative_q=clipped,negative_grid_correction=correction, &
         dry_layer_mass_kg_m2=dry_mass)
  END SUBROUTINE build_native

  SUBROUTINE build_native_clear()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='dry-mass-clear-fixture', &
         allow_clear_condensate=.TRUE.,omitted_grid_path=omitted,layer_reason=layer_reason, &
         dry_layer_mass_kg_m2=dry_mass)
  END SUBROUTINE build_native_clear

  SUBROUTINE build_legacy()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='dry-mass-legacy-fixture', &
         omitted_grid_path=omitted,layer_reason=layer_reason)
  END SUBROUTINE build_legacy

  SUBROUTINE build_bad_mass()
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radius,reason,errmsg,column_context='dry-mass-shape-fixture', &
         dry_layer_mass_kg_m2=dry_bad)
  END SUBROUTINE build_bad_mass

  SUBROUTINE assert_native_mixed_paths()
    raw_q(:,1)=qc; raw_q(:,2)=qi; raw_q(:,3)=qr
    raw_q(:,4)=qs; raw_q(:,5)=qg; raw_q(:,6)=qh
    DO k=1,n
      mass64=REAL(dry_mass(k),real64)*1000.0_real64
      DO p=1,nphase
        raw_path64=REAL(raw_q(k,p),real64)*mass64
        expected_correction=0.
        IF(raw_q(k,p)<0.) expected_correction=REAL(-raw_path64)
        expected_grid=0.
        IF(raw_q(k,p)>0.) expected_grid=REAL(raw_path64)
        IF(grid(k,p)/=expected_grid) ERROR STOP 'native dry mass grid path mismatch'
        IF(clipped(k,p)/=MIN(raw_q(k,p),0.)) ERROR STOP 'native negative clipped-q value mismatch'
        IF(correction(k,p)/=expected_correction) ERROR STOP 'native negative-path correction mismatch'
        IF(REAL(raw_path64)+correction(k,p)/=grid(k,p)) &
          ERROR STOP 'raw signed path plus correction differs from sanitized path'
        IF(incloud(k,p)/=grid(k,p)/cf(k)) ERROR STOP 'native dry mass in-cloud path mismatch'
      END DO
    END DO
    IF(ANY(radius(:,1)/=re_cloud) .OR. ANY(radius(:,2)/=re_ice) .OR. &
       ANY(radius(:,3)/=re_snow)) ERROR STOP 'native dry mass changed radii'
    IF(ANY(omitted/=0.)) ERROR STOP 'native mixed case unexpectedly omitted path'
    IF(ANY(layer_reason/=RRTMGP_INPUT_OK)) ERROR STOP 'native mixed layer reason mismatch'
  END SUBROUTINE assert_native_mixed_paths

  SUBROUTINE assert_legacy_paths()
    raw_q(:,1)=qc; raw_q(:,2)=qi; raw_q(:,3)=qr
    raw_q(:,4)=qs; raw_q(:,5)=qg; raw_q(:,6)=qh
    DO k=1,n
      mass64=REAL(dp(k),real64)*100.0_real64/REAL(gravity,real64)*1000.0_real64
      DO p=1,nphase
        expected64=REAL(raw_q(k,p),real64)*mass64
        IF(grid(k,p)/=REAL(expected64)) ERROR STOP 'legacy pressure/g grid path mismatch'
        IF(incloud(k,p)/=grid(k,p)/cf(k)) ERROR STOP 'legacy pressure/g in-cloud path mismatch'
      END DO
    END DO
  END SUBROUTINE assert_legacy_paths

END PROGRAM test_udm_dry_mass
