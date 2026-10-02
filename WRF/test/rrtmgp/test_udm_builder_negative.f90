PROGRAM test_udm_builder_negative
  USE module_ra_rrtmgp_input, ONLY: rrtmgp_build_udm_inputs
  IMPLICIT NONE
  REAL :: dp(2),cf(2),qc(2),qr(2),qi(2),qs(2),qg(2),qh(2)
  REAL :: re_cloud(2),re_ice(2),re_snow(2),grid(2,6),incloud(2,6),radius(2,3),omitted(2,6)
  INTEGER :: reason,layers(2)
  CHARACTER(LEN=512) :: errmsg
  dp=1000.;cf=0.5;qc=0.;qr=0.;qi=0.;qs=0.;qg=0.;qh=0.
  re_cloud=10.;re_ice=30.;re_snow=30.;qg(2)=-0.125
  CALL rrtmgp_build_udm_inputs(dp,cf,qc,qr,qi,qs,qg,qh,re_cloud,re_ice,re_snow,9.81, &
       grid,incloud,radius,reason,errmsg,'column=d01:i=19:j=8', &
       omitted_grid_path=omitted,layer_reason=layers)
  ERROR STOP 'negative graupel unexpectedly passed builder'
END PROGRAM test_udm_builder_negative
