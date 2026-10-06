PROGRAM test_rrtmgp_adapter_invalid
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE module_ra_rrtmgp, ONLY: rrtmgp_init, rrtmgp_lw_column, rrtmgp_sw_column
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=1,nl=3,nv=nl+1
  CHARACTER(LEN=512) :: data_path,case_name
  REAL :: play(nc,nl),plev(nc,nv),tlay(nc,nl),tlev(nc,nv),tsfc(nc)
  REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl)
  REAL :: emis(nc,1),cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl)
  REAL :: rel(nc,nl),rei(nc,nl),res(nc,nl)
  REAL :: lwup(nc,nv),lwdn(nc,nv),lwhr(nc,nl),lwupc(nc,nv),lwdnc(nc,nv),lwhrc(nc,nl)
  REAL :: swup(nc,nv),swdn(nc,nv),swhr(nc,nl),swupc(nc,nv),swdnc(nc,nv),swhrc(nc,nl)
  REAL :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv)
  REAL :: visdir(nc,nv),visdif(nc,nv),nirdir(nc,nv),nirdif(nc,nv)
  REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  INTEGER :: arg_status

  CALL get_command_argument(1,data_path,status=arg_status)
  IF(arg_status/=0.OR.LEN_TRIM(data_path)==0) ERROR STOP 'usage: test_adapter_invalid DATA_PATH CASE'
  CALL get_command_argument(2,case_name,status=arg_status)
  IF(arg_status/=0.OR.LEN_TRIM(case_name)==0) ERROR STOP 'usage: test_adapter_invalid DATA_PATH CASE'
  CALL initialize_inputs()
  IF(TRIM(case_name)=='coefficient_load_missing') THEN
    CALL rrtmgp_init(TRIM(data_path)//'/missing-coefficient-directory')
    WRITE(*,'(A)') 'INVALID_ADAPTER_INPUT_ACCEPTED='//TRIM(case_name)
    ERROR STOP 2
  END IF
  CALL rrtmgp_init(TRIM(data_path))

  SELECT CASE(TRIM(case_name))
  CASE('cf_overlap1')
    cf(1,2)=1.01
    CALL run_lw(1)
  CASE('cf_overlap3')
    cf(1,2)=1.01
    CALL run_sw(3)
  CASE('gas_nan')
    h2o(1,2)=ieee_value(0.,ieee_quiet_nan)
    CALL run_sw(2)
  CASE('albedo_above_one')
    avdir=1.01
    CALL run_sw(2)
  CASE('emissivity_nan')
    emis(1,1)=ieee_value(0.,ieee_quiet_nan)
    CALL run_lw(2)
  CASE('mu0_nan_night')
    mu0=ieee_value(0.,ieee_quiet_nan)
    CALL run_sw(2)
  CASE('solar_negative')
    solar=-1.
    CALL run_sw(2)
  CASE('roughness_low')
    CALL rrtmgp_init(TRIM(data_path),0)
  CASE('roughness_high')
    CALL rrtmgp_init(TRIM(data_path),4)
  CASE('changed_init_roughness')
    CALL rrtmgp_init(TRIM(data_path),2)
  CASE('changed_init_path')
    CALL rrtmgp_init(TRIM(data_path)//'/different-global-path')
  CASE('changed_init_constants')
    CALL rrtmgp_init(TRIM(data_path),gravity=9.81,cp_dry=1004.5,mol_weight_dry=28.966e-3)
  CASE DEFAULT
    WRITE(*,'(A)') 'UNKNOWN_ADAPTER_INVALID_CASE='//TRIM(case_name)
    ERROR STOP 2
  END SELECT
  WRITE(*,'(A)') 'INVALID_ADAPTER_INPUT_ACCEPTED='//TRIM(case_name)
  ERROR STOP 2
CONTAINS
  SUBROUTINE initialize_inputs()
    plev(1,:)=[1000.,700.,300.,1.]
    play(1,:)=[850.,500.,150.]
    tlay(1,:)=[285.,260.,230.]
    tlev(1,:)=[290.,275.,245.,210.]
    tsfc=290.
    h2o(1,:)=[.01,.003,.0001]
    co2=420.e-6; o3(1,:)=[.5e-6,1.e-6,5.e-6]
    n2o=330.e-9; ch4=1.8e-6; o2=.2095
    emis=.98; cf=0.; lwp=0.; iwp=0.; swp=0.
    rel=10.; rei=30.; res=30.
    avdir=.15; avdif=.10; andir=.25; andif=.20
    mu0=.65; solar=1361.
  END SUBROUTINE initialize_inputs

  SUBROUTINE run_lw(overlap_mode)
    INTEGER, INTENT(IN) :: overlap_mode
    CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
         cf,lwp,iwp,swp,rel,rei,res,4,overlap_mode,117,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
  END SUBROUTINE run_lw

  SUBROUTINE run_sw(overlap_mode)
    INTEGER, INTENT(IN) :: overlap_mode
    CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
         cf,lwp,iwp,swp,rel,rei,res,4,overlap_mode,117,swup,swdn,swhr,swupc,swdnc,swhrc, &
         direct,diffuse,directc,visdir,visdif,nirdir,nirdif)
  END SUBROUTINE run_sw
END PROGRAM test_rrtmgp_adapter_invalid
