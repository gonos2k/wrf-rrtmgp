PROGRAM test_rrtmgp_udm_inputs
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_build_udm_inputs, &
      RRTMGP_INPUT_OK, RRTMGP_INPUT_CLEAR, RRTMGP_INPUT_CLEAR_CONDENSATE, &
      RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED, &
      RRTMGP_UDM_LIQUID, RRTMGP_UDM_ICE, RRTMGP_UDM_RAIN, RRTMGP_UDM_SNOW, &
      RRTMGP_UDM_GRAUPEL, RRTMGP_UDM_HAIL, RRTMGP_UDM_CLOUD_RADIUS, &
      RRTMGP_UDM_ICE_RADIUS, RRTMGP_UDM_SNOW_RADIUS
  IMPLICIT NONE
  INTEGER, PARAMETER :: n=4
  REAL :: dp(n),cf(n),qc(n),qr(n),qi(n),qs(n),qg(n),qh(n)
  REAL :: re_cloud(n),re_ice(n),re_snow(n),gravity
  REAL :: grid(n,6),incloud(n,6),radii(n,3),omitted(n,6)
  REAL :: expected(n),tolerance
  INTEGER :: reason,layer_reason(n),k,phase
  CHARACTER(LEN=256) :: errmsg

  gravity=9.81
  dp=[100.,250.,500.,800.]
  cf=[.5,.25,0.,0.]
  qc=[1.e-4,0.,2.e-5,0.]
  qr=[3.e-5,0.,1.e-5,0.]
  qi=[2.e-5,0.,3.e-5,0.]
  qs=[4.e-5,5.e-5,4.e-5,0.]
  qg=[5.e-5,0.,5.e-5,0.]
  qh=0.
  re_cloud=[2.49,2.50,2.51,0.]
  re_ice=[4.99,5.00,5.01,0.]
  re_snow=[9.99,10.0,10.01,0.]

  CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
       grid,incloud,radii,reason,errmsg,allow_clear_condensate=.TRUE., &
       omitted_grid_path=omitted,layer_reason=layer_reason)
  CALL assert(reason==RRTMGP_INPUT_CLEAR_CONDENSATE,'zero-CF omission status')
  CALL assert(LEN_TRIM(errmsg)==0,'successful build should clear errmsg')
  CALL assert(layer_reason(1)==RRTMGP_INPUT_OK .AND. layer_reason(2)==RRTMGP_INPUT_OK, &
       'positive-CF layers should have normal reason')
  CALL assert(layer_reason(3)==RRTMGP_INPUT_CLEAR_CONDENSATE,'wet zero-CF reason')
  CALL assert(layer_reason(4)==RRTMGP_INPUT_CLEAR,'dry zero-CF reason')

  CALL check_phase(RRTMGP_UDM_LIQUID,qc)
  CALL check_phase(RRTMGP_UDM_ICE,qi)
  CALL check_phase(RRTMGP_UDM_RAIN,qr)
  CALL check_phase(RRTMGP_UDM_SNOW,qs)
  CALL check_phase(RRTMGP_UDM_GRAUPEL,qg)
  CALL assert(ALL(grid(:,RRTMGP_UDM_HAIL)==0.) .AND. ALL(incloud(:,RRTMGP_UDM_HAIL)==0.), &
       'zero hail must produce zero hail path')
  CALL assert(ALL(grid(3,1:5)>0.),'zero-CF grid-box paths must retain omitted species mass')
  CALL assert(ALL(incloud(3,:)==0.),'omitted zero-CF paths must not enter cloud optics')
  CALL assert(ALL(omitted(3,:)==grid(3,:)),'omitted diagnostic must retain each phase path')
  CALL assert(ALL(omitted(1:2,:)==0.) .AND. ALL(omitted(4,:)==0.), &
       'positive-CF and dry layers have no omitted path')
  CALL check_close('cloud radius',radii(:,RRTMGP_UDM_CLOUD_RADIUS),re_cloud,2.e-6)
  CALL check_close('ice radius',radii(:,RRTMGP_UDM_ICE_RADIUS),re_ice,2.e-6)
  CALL check_close('snow radius',radii(:,RRTMGP_UDM_SNOW_RADIUS),re_snow,2.e-6)

  ! Hail is refused regardless of amount once it is positive; no threshold is
  ! silently used and no partial paths escape in the output arrays.
  qh(2)=1.e-12
  CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
       grid,incloud,radii,reason,errmsg,allow_clear_condensate=.TRUE., &
       omitted_grid_path=omitted,layer_reason=layer_reason)
  CALL assert(reason==RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED,'positive hail status')
  CALL assert(TRIM(errmsg)=='RRTMGP_INPUT_UDM_HAIL_OPTICS_UNSUPPORTED','hail diagnostic')
  CALL assert(ALL(grid==0.) .AND. ALL(incloud==0.) .AND. ALL(radii==0.), &
       'unsupported hail must not return partial optics inputs')

  ! Clear-only baseline: no condensate paths, with exact pass-through radii.
  CALL zero_species()
  cf=0.
  CALL build_success(RRTMGP_INPUT_CLEAR,'clear-only case')
  CALL assert(ALL(grid==0.) .AND. ALL(incloud==0.),'clear-only case must have zero paths')
  CALL check_radii()

  ! Exercise each supported water/ice species alone so one phase cannot mask
  ! a missing or misrouted phase mapping.
  DO phase=RRTMGP_UDM_LIQUID,RRTMGP_UDM_GRAUPEL
    CALL zero_species()
    cf=.4
    CALL set_phase_value(phase,2,1.e-8)
    CALL build_success(RRTMGP_INPUT_OK,'single-phase case')
    CALL check_one_phase(phase)
    CALL check_radii()
  END DO

  ! Tiny but positive cloud fraction must retain exact grid-box condensate
  ! mass while the in-cloud path scales by 1/CF without overflow.
  CALL zero_species()
  cf=0.
  cf(2)=1.e-6
  qc(2)=1.e-8
  CALL build_success(RRTMGP_INPUT_OK,'tiny-CF case')
  CALL check_one_phase(RRTMGP_UDM_LIQUID)
  CALL assert(grid(2,RRTMGP_UDM_LIQUID)>0. .AND. &
       incloud(2,RRTMGP_UDM_LIQUID)>grid(2,RRTMGP_UDM_LIQUID), &
       'tiny-CF case must retain positive grid and larger in-cloud paths')
  CALL check_radii()

  ! Positive hail by itself must be rejected, independent of the other phases.
  CALL zero_species()
  cf=.4
  qh(2)=1.e-12
  CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
       grid,incloud,radii,reason,errmsg,allow_clear_condensate=.TRUE., &
       omitted_grid_path=omitted,layer_reason=layer_reason)
  CALL assert(reason==RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED,'independent hail case rejection')
  CALL assert(ALL(grid==0.) .AND. ALL(incloud==0.) .AND. ALL(radii==0.), &
       'independent unsupported hail case must return no partial paths')

  ! Fully mixed supported case with positive CF verifies combined mass closure.
  CALL zero_species()
  cf=.25
  qc(2)=1.e-8; qi(2)=2.e-8; qr(2)=3.e-8; qs(2)=4.e-8; qg(2)=5.e-8
  CALL build_success(RRTMGP_INPUT_OK,'mixed positive-CF case')
  CALL check_phase(RRTMGP_UDM_LIQUID,qc)
  CALL check_phase(RRTMGP_UDM_ICE,qi)
  CALL check_phase(RRTMGP_UDM_RAIN,qr)
  CALL check_phase(RRTMGP_UDM_SNOW,qs)
  CALL check_phase(RRTMGP_UDM_GRAUPEL,qg)
  CALL check_radii()

  WRITE(*,'(A)') 'UDM path builder tests passed: clear, independent phases, mixed/tiny-CF closure, radii, hail refusal.'

CONTAINS
  SUBROUTINE zero_species()
    qc=0.; qr=0.; qi=0.; qs=0.; qg=0.; qh=0.
  END SUBROUTINE zero_species

  SUBROUTINE set_phase_value(which,layer,value)
    INTEGER, INTENT(IN) :: which,layer
    REAL, INTENT(IN) :: value
    SELECT CASE(which)
    CASE(RRTMGP_UDM_LIQUID); qc(layer)=value
    CASE(RRTMGP_UDM_ICE); qi(layer)=value
    CASE(RRTMGP_UDM_RAIN); qr(layer)=value
    CASE(RRTMGP_UDM_SNOW); qs(layer)=value
    CASE(RRTMGP_UDM_GRAUPEL); qg(layer)=value
    CASE DEFAULT; ERROR STOP 'unsupported phase in independent test'
    END SELECT
  END SUBROUTINE set_phase_value

  SUBROUTINE build_success(expected_reason,label)
    INTEGER, INTENT(IN) :: expected_reason
    CHARACTER(LEN=*), INTENT(IN) :: label
    CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,gravity, &
         grid,incloud,radii,reason,errmsg,allow_clear_condensate=.TRUE., &
         omitted_grid_path=omitted,layer_reason=layer_reason)
    CALL assert(reason==expected_reason,label//' status')
    CALL assert(LEN_TRIM(errmsg)==0,label//' should clear errmsg')
  END SUBROUTINE build_success

  SUBROUTINE check_one_phase(which)
    INTEGER, INTENT(IN) :: which
    INTEGER :: ph,idx
    REAL :: qphase(n)
    qphase=0.
    SELECT CASE(which)
    CASE(RRTMGP_UDM_LIQUID); qphase=qc
    CASE(RRTMGP_UDM_ICE); qphase=qi
    CASE(RRTMGP_UDM_RAIN); qphase=qr
    CASE(RRTMGP_UDM_SNOW); qphase=qs
    CASE(RRTMGP_UDM_GRAUPEL); qphase=qg
    CASE DEFAULT; ERROR STOP 'unsupported phase in closure check'
    END SELECT
    DO ph=1,6
      IF(ph==which) THEN
        DO idx=1,n
          expected(idx)=qphase(idx)*(dp(idx)*100./gravity)*1000.
          CALL check_scalar('single phase grid path',grid(idx,ph),expected(idx),2.e-6)
          IF(cf(idx)>0.) THEN
            CALL check_scalar('single phase in-cloud closure',incloud(idx,ph)*cf(idx), &
                 grid(idx,ph),2.e-6)
          ELSE
            CALL assert(incloud(idx,ph)==0.,'zero-CF single-phase in-cloud path')
          END IF
        END DO
      ELSE
        CALL assert(ALL(grid(:,ph)==0.) .AND. ALL(incloud(:,ph)==0.), &
             'other phases must remain zero in an independent case')
      END IF
    END DO
  END SUBROUTINE check_one_phase

  SUBROUTINE check_radii()
    CALL check_close('cloud radius pass-through',radii(:,RRTMGP_UDM_CLOUD_RADIUS),re_cloud,2.e-6)
    CALL check_close('ice radius pass-through',radii(:,RRTMGP_UDM_ICE_RADIUS),re_ice,2.e-6)
    CALL check_close('snow radius pass-through',radii(:,RRTMGP_UDM_SNOW_RADIUS),re_snow,2.e-6)
  END SUBROUTINE check_radii

  SUBROUTINE check_phase(phase,q)
    INTEGER, INTENT(IN) :: phase
    REAL, INTENT(IN) :: q(:)
    DO k=1,n
      expected(k)=q(k)*(dp(k)*100./gravity)*1000.
      CALL assert(ieee_is_finite(grid(k,phase)),'grid path finite')
      CALL check_scalar('grid path',grid(k,phase),expected(k),2.e-6)
      IF(cf(k)>0.) THEN
        CALL check_scalar('in-cloud path',incloud(k,phase)*cf(k),grid(k,phase),2.e-6)
      ELSE
        CALL assert(incloud(k,phase)==0.,'zero-CF in-cloud path must be zero')
      END IF
    END DO
  END SUBROUTINE check_phase

  SUBROUTINE check_scalar(label,actual,wanted,tolerance)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: actual,wanted,tolerance
    IF(.NOT.ieee_is_finite(actual) .OR. ABS(actual-wanted)>MAX(1.e-12,tolerance*ABS(wanted))) THEN
      WRITE(*,'(A,2(1X,ES14.6))') TRIM(label)//' failed: actual, expected',actual,wanted
      ERROR STOP 1
    END IF
  END SUBROUTINE check_scalar

  SUBROUTINE check_close(label,actual,wanted,tolerance)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: actual(:),wanted(:),tolerance
    INTEGER :: idx
    DO idx=1,SIZE(actual)
      CALL check_scalar(label,actual(idx),wanted(idx),tolerance)
    END DO
  END SUBROUTINE check_close

  SUBROUTINE assert(condition,label)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: label
    IF(.NOT.condition) THEN
      WRITE(*,'(A)') 'FAIL: '//TRIM(label)
      ERROR STOP 1
    END IF
  END SUBROUTINE assert
END PROGRAM test_rrtmgp_udm_inputs
