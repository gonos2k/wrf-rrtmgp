! SPDX-License-Identifier: Apache-2.0
! Standalone regression tests for module_ra_rrtmgp_precip.
PROGRAM test_rrtmgp_precip_optics
  USE mo_rte_kind, ONLY: wp
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp_precip
  IMPLICIT NONE
  REAL(wp) :: swbands(2,RRTMGP_SW_NBAND), lwbands(2,RRTMGP_LW_NBAND)
  REAL(wp) :: rwp(1,2), swp(1,2), rsnow(1,2)
  REAL(wp) :: swtau(1,2,RRTMGP_SW_NBAND), swssa(1,2,RRTMGP_SW_NBAND)
  REAL(wp) :: swg(1,2,RRTMGP_SW_NBAND), lwtau(1,2,RRTMGP_LW_NBAND)
  REAL(wp) :: expected_tau(6), expected_ssa(6), expected_g(6)
  REAL(wp) :: wrong_shape(1,2,RRTMGP_SW_NBAND-1)
  INTEGER :: ierr, b, k
  INTEGER, PARAMETER :: selected(6)=[1,8,9,10,11,14]
  REAL(wp), PARAMETER :: tol=2.e-6_wp

  CALL rrtmgp_precip_sw_band_bounds(swbands)
  CALL rrtmgp_precip_lw_band_bounds(lwbands)
  CALL require(all(swbands(1,:) == [820._wp,2680._wp,3250._wp,4000._wp,4650._wp, &
       5150._wp,6150._wp,7700._wp,8050._wp,12850._wp,16000._wp,22650._wp, &
       29000._wp,38000._wp]), 'SW coefficient-band lower bounds/order')
  CALL require(all(swbands(2,:) == [2680._wp,3250._wp,4000._wp,4650._wp,5150._wp, &
       6150._wp,7700._wp,8050._wp,12850._wp,16000._wp,22650._wp,29000._wp, &
       38000._wp,50000._wp]), 'SW coefficient-band upper bounds/order')
  CALL require(all(lwbands(1,:) == [10._wp,250._wp,500._wp,630._wp,700._wp,820._wp, &
       980._wp,1080._wp,1180._wp,1390._wp,1480._wp,1800._wp,2080._wp,2250._wp, &
       2390._wp,2680._wp]), 'LW band limits/order')

  rwp(1,:)=[50._wp,50._wp]
  swp(1,:)=[25._wp,0._wp]
  rsnow(1,:)=[30._wp,0._wp]
  CALL rrtmgp_precip_lw_optics(rwp,swp,rsnow,lwbands,lwtau,ierr)
  CALL require(ierr==RRTMGP_PRECIP_OK, 'LW positive case status')
  CALL require(maxval(abs(lwtau(1,1,:)-1.33845_wp))<tol, 'LW rain+snow optical depth')
  CALL require(maxval(abs(lwtau(1,2,:)-0.0165_wp))<tol, 'LW rain-only optical depth')

  CALL rrtmgp_precip_sw_optics(rwp,swp,rsnow,swbands,swtau,swssa,swg,ierr)
  CALL require(ierr==RRTMGP_PRECIP_OK, 'SW positive case status')
  expected_tau=[0.729490435_wp,0.692099029_wp,0.116216606_wp,0.114742677_wp, &
                0.712616817_wp,0.712616817_wp]
  expected_ssa=[0.0620421914_wp,0.0807879755_wp,0.930898829_wp,0.978171125_wp, &
                0.999997930_wp,0.999997930_wp]
  expected_g=[0.492637610_wp,0.491382715_wp,0.490428092_wp,0.490093852_wp, &
              0.418279513_wp,0.418279513_wp]
  DO k=1,SIZE(selected)
    b=selected(k)
    CALL require(abs(swtau(1,1,b)-expected_tau(k))<tol, 'SW tau coefficient formula/order')
    CALL require(abs(swssa(1,1,b)-expected_ssa(k))<tol, 'SW ssa coefficient formula/order')
    CALL require(abs(swg(1,1,b)-expected_g(k))<tol, 'SW asymmetry/delta scaling')
  END DO
  expected_tau=[0.0791996144_wp,0.0417430798_wp,0.0367060448_wp,0.0349859460_wp, &
                0.0338178582_wp,0.0338178582_wp]
  DO k=1,SIZE(selected)
    CALL require(abs(swtau(1,2,selected(k))-expected_tau(k))<tol, 'SW rain-only band ordering')
  END DO

  ! Pinned CCPP source suppresses snow at radius <= 10 microns, without
  ! modifying either path; verify the helper preserves that optical cutoff.
  swp=25._wp
  rsnow=10._wp
  CALL rrtmgp_precip_sw_optics(rwp,swp,rsnow,swbands,swtau,swssa,swg,ierr)
  CALL require(ierr==RRTMGP_PRECIP_OK, 'snow cutoff case status')
  CALL require(maxval(abs(swtau(1,1,:)-swtau(1,2,:)))<tol, 'SW snow cutoff at 10 microns')
  CALL rrtmgp_precip_lw_optics(rwp,swp,rsnow,lwbands,lwtau,ierr)
  CALL require(maxval(abs(lwtau(1,1,:)-lwtau(1,2,:)))<tol, 'LW snow cutoff at 10 microns')

  swp=0._wp; rsnow=0._wp; rwp=1._wp
  rwp(1,2)=-1._wp
  CALL rrtmgp_precip_sw_optics(rwp,swp,rsnow,swbands,swtau,swssa,swg,ierr)
  CALL require(ierr==RRTMGP_PRECIP_BAD_PATH .AND. all(swtau==0._wp), 'negative path rejection')
  rwp=1._wp; swp(1,1)=1._wp; rsnow(1,1)=0._wp
  CALL rrtmgp_precip_lw_optics(rwp,swp,rsnow,lwbands,lwtau,ierr)
  CALL require(ierr==RRTMGP_PRECIP_BAD_SNOW_RADIUS .AND. all(lwtau==0._wp), 'nonpositive active snow radius rejection')
  swp=0._wp; rsnow=0._wp; rwp=1._wp
  rwp(1,1)=ieee_value(0._wp,ieee_quiet_nan)
  CALL rrtmgp_precip_sw_optics(rwp,swp,rsnow,swbands,swtau,swssa,swg,ierr)
  CALL require(ierr==RRTMGP_PRECIP_BAD_PATH, 'non-finite path rejection')

  CALL rrtmgp_precip_sw_optics(reshape([1._wp,1._wp],[1,2]),swp,rsnow, &
       swbands,wrong_shape,swssa,swg,ierr)
  CALL require(ierr==RRTMGP_PRECIP_BAD_SHAPE, 'bad output shape rejection')
  swbands(:,10)=swbands(:,11)
  CALL rrtmgp_precip_sw_optics(reshape([1._wp,1._wp],[1,2]),swp,rsnow, &
       swbands,swtau,swssa,swg,ierr)
  CALL require(ierr==RRTMGP_PRECIP_BAD_BANDS .AND. all(swtau==0._wp), 'misordered SW bands rejection')

  WRITE(*,'(A)') 'CCPP rain/snow optical formulas, bands and invalid inputs passed.'
CONTAINS
  SUBROUTINE require(ok, label)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(*), INTENT(IN) :: label
    IF (.NOT.ok) THEN
      WRITE(*,'(A)') 'FAIL: '//label
      ERROR STOP 1
    END IF
  END SUBROUTINE require
END PROGRAM test_rrtmgp_precip_optics
