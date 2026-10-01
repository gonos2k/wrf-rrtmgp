PROGRAM test_rrtmgp_small_cf_sampling
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE mo_rte_kind, ONLY: i8
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE module_ra_rrtmgp, ONLY: rrtmgp_init, rrtmgp_lw_column, rrtmgp_sw_column, cloud_mask
  IMPLICIT NONE
  INTEGER, PARAMETER :: m=2048, nl=3, nv=nl+1, nmetric=10
  REAL, PARAMETER :: fractions(10)=[1.e-6,1.e-5,1.e-4,.001,.002,.005,.01,.02,.05,.1]
  CHARACTER(LEN=512) :: data_path, output_path
  INTEGER :: outunit, ios, ifrac, j, ngpt_lw, ngpt_sw
  INTEGER(i8) :: stream_state
  INTEGER :: seeds(m), hit_lw, hit_sw, zero_cols_lw, zero_cols_sw
  REAL :: cf(m,nl), lwp(m,nl), iwp(m,nl), swp(m,nl)
  REAL :: play(m,nl), plev(m,nv), tlay(m,nl), tlev(m,nv), tsfc(m)
  REAL :: h2o(m,nl), co2(m,nl), o3(m,nl), n2o(m,nl), ch4(m,nl), o2(m,nl)
  REAL :: emis(m,1), rel(m,nl), rei(m,nl), res(m,nl)
  REAL :: avdir(m), avdif(m), andir(m), andif(m), mu0(m), solar
  REAL :: lwup(m,nv), lwdn(m,nv), lwhr(m,nl), lwupc(m,nv), lwdnc(m,nv), lwhrc(m,nl)
  REAL :: swup(m,nv), swdn(m,nv), swhr(m,nl), swupc(m,nv), swdnc(m,nv), swhrc(m,nl)
  REAL :: direct(m,nv), diffuse(m,nv), directc(m,nv)
  REAL :: visdir(m,nv), visdif(m,nv), nirdir(m,nv), nirdif(m,nv)
  REAL :: lwup_repeat(m,nv), lwdn_repeat(m,nv), lwhr_repeat(m,nl)
  REAL :: swup_repeat(m,nv), swdn_repeat(m,nv), swhr_repeat(m,nl)
  REAL :: up_clear(m,nv), dn_clear(m,nv), hr_clear(m,nl)
  REAL :: swup_clear(m,nv), swdn_clear(m,nv), swhr_clear(m,nl)
  REAL :: up_over(m,nv), dn_over(m,nv), hr_over(m,nl)
  REAL :: swup_over(m,nv), swdn_over(m,nv), swhr_over(m,nl)
  REAL :: sample(m,nmetric)
  REAL(real64) :: exact(nmetric), means(nmetric), sdev(nmetric), se(nmetric), se_envelope(nmetric)
  LOGICAL :: mask_lw(m,nl,128), mask_sw(m,nl,112)
  REAL :: cloud_fraction, expected_lw, expected_sw, zero_frac_lw, zero_frac_sw
  REAL :: zero_col_frac_lw, zero_col_frac_sw
  REAL(real64) :: tol

  CALL get_command_argument(1,data_path)
  IF(LEN_TRIM(data_path)==0) ERROR STOP 'usage: test_small_cf_sampling DATA_DIRECTORY [CSV_OUTPUT]'
  CALL get_command_argument(2,output_path)
  outunit=6
  IF(LEN_TRIM(output_path)>0) THEN
    OPEN(NEWUNIT=outunit,FILE=TRIM(output_path),STATUS='REPLACE',ACTION='WRITE',IOSTAT=ios)
    IF(ios/=0) ERROR STOP 'could not open CSV output path'
  END IF

  CALL initialize_columns()
  CALL rrtmgp_init(TRIM(data_path))
  ngpt_lw=128; ngpt_sw=112

  ! Clear reference uses the same atmosphere and surface as every cloud case.
  cf=0.; lwp=0.; iwp=0.; swp=0.
  CALL run_lw(lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
  up_clear=lwup; dn_clear=lwdn; hr_clear=lwhr
  CALL run_sw(swup,swdn,swhr,swupc,swdnc,swhrc)
  swup_clear=swup; swdn_clear=swdn; swhr_clear=swhr

  CALL write_header()
  DO ifrac=1,SIZE(fractions)
    cloud_fraction=fractions(ifrac)
    cf=0.; lwp=0.; iwp=0.; swp=0.
    cf(:,2)=cloud_fraction
    lwp(:,2)=1./cloud_fraction

    CALL run_lw(lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
    CALL run_sw(swup,swdn,swhr,swupc,swdnc,swhrc)
    sample(:,1)=lwdn(:,1)       ! LW downward at the surface
    sample(:,2)=lwup(:,nv)      ! LW upward at TOA
    sample(:,3)=swup(:,nv)      ! SW upward at TOA
    sample(:,4)=swdn(:,1)       ! SW downward at the surface
    sample(:,5)=lwhr(:,1)
    sample(:,6)=lwhr(:,2)
    sample(:,7)=lwhr(:,3)
    sample(:,8)=swhr(:,1)
    sample(:,9)=swhr(:,2)
    sample(:,10)=swhr(:,3)

    ! Repeat exactly the same call and seed vector: the adapter is a sampled
    ! solver call, not an implicit ensemble-average operation.
    CALL run_lw(lwup_repeat,lwdn_repeat,lwhr_repeat,lwupc,lwdnc,lwhrc)
    CALL run_sw(swup_repeat,swdn_repeat,swhr_repeat,swupc,swdnc,swhrc)
    CALL require_identical('LW fixed-seed repeat',lwdn,lwdn_repeat)
    CALL require_identical('LW fixed-seed repeat',lwup,lwup_repeat)
    CALL require_identical('LW fixed-seed repeat',lwhr,lwhr_repeat)
    CALL require_identical('SW fixed-seed repeat',swdn,swdn_repeat)
    CALL require_identical('SW fixed-seed repeat',swup,swup_repeat)
    CALL require_identical('SW fixed-seed repeat',swhr,swhr_repeat)

    ! The exact independent-column ICA expectation is (1-f)*clear + f*cloudy,
    ! with the cloudy column's in-cloud path held fixed at 1/f g m-2.
    cf=0.; lwp=0.; iwp=0.; swp=0.
    cf(:,2)=1.; lwp(:,2)=1./cloud_fraction
    CALL run_lw(up_over,dn_over,hr_over,lwupc,lwdnc,lwhrc)
    CALL run_sw(swup_over,swdn_over,swhr_over,swupc,swdnc,swhrc)
    exact(1)=(1._real64-REAL(cloud_fraction,real64))*REAL(dn_clear(1,1),real64)+ &
      REAL(cloud_fraction,real64)*REAL(dn_over(1,1),real64)
    exact(2)=(1._real64-REAL(cloud_fraction,real64))*REAL(up_clear(1,nv),real64)+ &
      REAL(cloud_fraction,real64)*REAL(up_over(1,nv),real64)
    exact(3)=(1._real64-REAL(cloud_fraction,real64))*REAL(swup_clear(1,nv),real64)+ &
      REAL(cloud_fraction,real64)*REAL(swup_over(1,nv),real64)
    exact(4)=(1._real64-REAL(cloud_fraction,real64))*REAL(swdn_clear(1,1),real64)+ &
      REAL(cloud_fraction,real64)*REAL(swdn_over(1,1),real64)
    exact(5)=(1._real64-REAL(cloud_fraction,real64))*REAL(hr_clear(1,1),real64)+ &
      REAL(cloud_fraction,real64)*REAL(hr_over(1,1),real64)
    exact(6)=(1._real64-REAL(cloud_fraction,real64))*REAL(hr_clear(1,2),real64)+ &
      REAL(cloud_fraction,real64)*REAL(hr_over(1,2),real64)
    exact(7)=(1._real64-REAL(cloud_fraction,real64))*REAL(hr_clear(1,3),real64)+ &
      REAL(cloud_fraction,real64)*REAL(hr_over(1,3),real64)
    exact(8)=(1._real64-REAL(cloud_fraction,real64))*REAL(swhr_clear(1,1),real64)+ &
      REAL(cloud_fraction,real64)*REAL(swhr_over(1,1),real64)
    exact(9)=(1._real64-REAL(cloud_fraction,real64))*REAL(swhr_clear(1,2),real64)+ &
      REAL(cloud_fraction,real64)*REAL(swhr_over(1,2),real64)
    exact(10)=(1._real64-REAL(cloud_fraction,real64))*REAL(swhr_clear(1,3),real64)+ &
      REAL(cloud_fraction,real64)*REAL(swhr_over(1,3),real64)
    se_envelope(1)=bernoulli_envelope(dn_clear(1,1),dn_over(1,1),cloud_fraction)
    se_envelope(2)=bernoulli_envelope(up_clear(1,nv),up_over(1,nv),cloud_fraction)
    se_envelope(3)=bernoulli_envelope(swup_clear(1,nv),swup_over(1,nv),cloud_fraction)
    se_envelope(4)=bernoulli_envelope(swdn_clear(1,1),swdn_over(1,1),cloud_fraction)
    DO j=1,3
      se_envelope(4+j)=bernoulli_envelope(hr_clear(1,j),hr_over(1,j),cloud_fraction)
      se_envelope(7+j)=bernoulli_envelope(swhr_clear(1,j),swhr_over(1,j),cloud_fraction)
    END DO

    CALL sample_statistics(sample,means,sdev,se)
    cf=0.; cf(:,2)=cloud_fraction
    CALL cloud_mask(cf,ngpt_lw,1,173,mask_lw,column_seeds=seeds)
    CALL count_masks(mask_lw,hit_lw,zero_cols_lw)
    CALL cloud_mask(cf,ngpt_sw,1,173,mask_sw,column_seeds=seeds)
    CALL count_masks(mask_sw,hit_sw,zero_cols_sw)
    expected_lw=REAL(m*ngpt_lw)*cloud_fraction
    expected_sw=REAL(m*ngpt_sw)*cloud_fraction
    CALL check_hit_count(hit_lw,expected_lw)
    CALL check_hit_count(hit_sw,expected_sw)
    zero_frac_lw=REAL(m*ngpt_lw-hit_lw)/REAL(m*ngpt_lw)
    zero_frac_sw=REAL(m*ngpt_sw-hit_sw)/REAL(m*ngpt_sw)
    zero_col_frac_lw=REAL(zero_cols_lw)/REAL(m)
    zero_col_frac_sw=REAL(zero_cols_sw)/REAL(m)
    CALL validate_statistics(means,sdev,se)
    IF(cloud_fraction>=.001) THEN
      DO j=1,nmetric
        tol=6._real64*se(j)+4._real64*REAL(SPACING(REAL(exact(j))),real64)
        IF(ABS(means(j)-exact(j))>tol) THEN
          WRITE(*,'(A,ES12.4,A,I0,A,ES12.4,A,ES12.4)') &
            'FAIL cf ',cloud_fraction,' metric ',j,' error ',ABS(means(j)-exact(j)),' limit ',tol
          ERROR STOP 1
        END IF
      END DO
    END IF
    CALL write_row()
  END DO
  IF(outunit/=6) CLOSE(outunit)
  WRITE(*,'(A)') 'small-cloud-fraction sampling replay passed'

CONTAINS

  SUBROUTINE initialize_columns()
    INTEGER :: c, layer
    stream_state=987654321_i8
    DO c=1,m
      ! Park-Miller stream gives deterministic, dispersed positive seeds rather
      ! than consecutive seeds with strongly overlapping random sequences.
      stream_state=MODULO(48271_i8*stream_state,2147483647_i8)
      seeds(c)=INT(stream_state)
    END DO
    plev(:,1)=1000.; plev(:,2)=700.; plev(:,3)=300.; plev(:,4)=1.
    play(:,1)=850.; play(:,2)=500.; play(:,3)=150.
    tlev(:,1)=290.; tlev(:,2)=275.; tlev(:,3)=245.; tlev(:,4)=210.
    DO layer=1,nl
      tlay(:,layer)=.5*(tlev(:,layer)+tlev(:,layer+1))
    END DO
    tsfc=290.; h2o(:,1)=.01; h2o(:,2)=.003; h2o(:,3)=.0001
    co2=420.e-6; o3(:,1)=.5e-6; o3(:,2)=1.e-6; o3(:,3)=5.e-6
    n2o=330.e-9; ch4=1.8e-6; o2=.2095; emis=.98
    rel=10.; rei=30.; res=60.
    avdir=.15; avdif=.10; andir=.25; andif=.20; mu0=.65; solar=1361.
  END SUBROUTINE initialize_columns

  SUBROUTINE run_lw(up,dn,hr,upc,dnc,hrc)
    REAL, INTENT(OUT) :: up(:,:),dn(:,:),hr(:,:),upc(:,:),dnc(:,:),hrc(:,:)
    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
      cf,lwp,iwp,swp,rel,rei,res,4,1,173,up,dn,hr,upc,dnc,hrc,column_seeds=seeds)
  END SUBROUTINE run_lw

  SUBROUTINE run_sw(up,dn,hr,upc,dnc,hrc)
    REAL, INTENT(OUT) :: up(:,:),dn(:,:),hr(:,:),upc(:,:),dnc(:,:),hrc(:,:)
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif, &
      mu0,solar,cf,lwp,iwp,swp,rel,rei,res,4,1,173,up,dn,hr,upc,dnc,hrc, &
      direct,diffuse,directc,visdir,visdif,nirdir,nirdif,column_seeds=seeds)
  END SUBROUTINE run_sw

  SUBROUTINE count_masks(mask,hits,zero_columns)
    LOGICAL, INTENT(IN) :: mask(:,:,:)
    INTEGER, INTENT(OUT) :: hits,zero_columns
    INTEGER :: c
    hits=COUNT(mask(:,2,:))
    zero_columns=0
    DO c=1,SIZE(mask,1)
      IF(.NOT.ANY(mask(c,2,:))) zero_columns=zero_columns+1
    END DO
  END SUBROUTINE count_masks

  SUBROUTINE sample_statistics(values,mean_value,std_value,se_value)
    REAL, INTENT(IN) :: values(:,:)
    REAL(real64), INTENT(OUT) :: mean_value(:),std_value(:),se_value(:)
    INTEGER :: j
    DO j=1,SIZE(values,2)
      IF(.NOT.ALL(ieee_is_finite(values(:,j)))) ERROR STOP 'non-finite adapter samples'
      mean_value(j)=SUM(REAL(values(:,j),real64))/REAL(SIZE(values,1),real64)
      std_value(j)=SQRT(SUM((REAL(values(:,j),real64)-mean_value(j))**2)/REAL(SIZE(values,1)-1,real64))
      se_value(j)=std_value(j)/SQRT(REAL(SIZE(values,1),real64))
    END DO
  END SUBROUTINE sample_statistics

  REAL(real64) FUNCTION bernoulli_envelope(clear_value,cloudy_value,fraction)
    REAL, INTENT(IN) :: clear_value,cloudy_value,fraction
    ! Conservative endpoint-span SE scale treating each whole column as one
    ! Bernoulli draw. It is diagnostic only; rare-cloud cases are not required
    ! to fall inside a Gaussian confidence interval based on this estimate.
    bernoulli_envelope=ABS(REAL(cloudy_value,real64)-REAL(clear_value,real64))* &
      SQRT(REAL(fraction,real64)*(1._real64-REAL(fraction,real64))/REAL(m,real64))
  END FUNCTION bernoulli_envelope

  SUBROUTINE check_hit_count(hits,expected)
    INTEGER, INTENT(IN) :: hits
    REAL, INTENT(IN) :: expected
    ! Broad count bounds allow zero hits for very rare clouds, but catch an
    ! unintended 0.01 fraction floor and all-clear regressions once E[N]>=20.
    IF(ABS(REAL(hits)-expected)>8.*SQRT(expected)+8.) ERROR STOP 'cloud-mask hit count outside broad sampling bounds'
    IF(expected>=20..AND.hits==0) ERROR STOP 'cloud-mask sampling lost resolvable rare clouds'
  END SUBROUTINE check_hit_count

  SUBROUTINE validate_statistics(mean_value,std_value,se_value)
    REAL(real64), INTENT(IN) :: mean_value(:),std_value(:),se_value(:)
    IF(.NOT.ALL(ieee_is_finite(mean_value)).OR..NOT.ALL(ieee_is_finite(std_value)).OR. &
       .NOT.ALL(ieee_is_finite(se_value))) ERROR STOP 'non-finite statistical moments'
    IF(ANY(std_value<0.).OR.ANY(se_value<0.)) ERROR STOP 'negative statistical spread'
  END SUBROUTINE validate_statistics

  SUBROUTINE require_identical(label,a,b)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL, INTENT(IN) :: a(:,:),b(:,:)
    IF(ANY(.NOT.ieee_is_finite(a)).OR.ANY(.NOT.ieee_is_finite(b))) ERROR STOP 'non-finite repeat output'
    IF(ANY(a/=b)) THEN
      WRITE(*,'(A)') 'FAIL: '//TRIM(label)//' changed for fixed seeds'
      ERROR STOP 1
    END IF
  END SUBROUTINE require_identical

  SUBROUTINE write_header()
    INTEGER :: j
    CHARACTER(LEN=48), PARAMETER :: labels(nmetric)=[CHARACTER(LEN=48) :: &
      'lw_dn_surface','lw_up_toa','sw_up_toa','sw_dn_surface', &
      'lw_hr_layer1','lw_hr_layer2','lw_hr_layer3','sw_hr_layer1', &
      'sw_hr_layer2','sw_hr_layer3']
    WRITE(outunit,'(A)',ADVANCE='NO') &
      'cf,expected_lw_cloud_points,actual_lw_cloud_points,lw_zero_gpoint_fraction,lw_zero_column_fraction,'// &
      'expected_sw_cloud_points,actual_sw_cloud_points,sw_zero_gpoint_fraction,sw_zero_column_fraction'
    DO j=1,nmetric
      WRITE(outunit,'(A)',ADVANCE='NO') ','//TRIM(labels(j))//'_mean,'//TRIM(labels(j))//'_sd,'// &
        TRIM(labels(j))//'_se,'//TRIM(labels(j))//'_endpoint_bernoulli_se_envelope,'//TRIM(labels(j))//'_ica'
    END DO
    WRITE(outunit,'()')
  END SUBROUTINE write_header

  SUBROUTINE write_row()
    INTEGER :: j
    WRITE(outunit,'(ES14.6,",",ES14.6,",",I0,",",ES14.6,",",ES14.6,",", &
      ES14.6,",",I0,",",ES14.6,",",ES14.6)',ADVANCE='NO') cloud_fraction,expected_lw,hit_lw, &
      zero_frac_lw,zero_col_frac_lw,expected_sw,hit_sw,zero_frac_sw,zero_col_frac_sw
    DO j=1,nmetric
      WRITE(outunit,'(",",ES25.16E3,",",ES25.16E3,",",ES25.16E3,",",ES25.16E3,",",ES25.16E3)',ADVANCE='NO') &
        means(j),sdev(j),se(j),se_envelope(j),exact(j)
    END DO
    WRITE(outunit,'()')
  END SUBROUTINE write_row

END PROGRAM test_rrtmgp_small_cf_sampling
