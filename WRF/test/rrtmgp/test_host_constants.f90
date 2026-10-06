PROGRAM test_rrtmgp_host_constants
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE mo_rte_kind, ONLY: wp
  USE mo_gas_optics_constants, ONLY: grav,cp_dry,m_dry
  USE mo_gas_optics_rrtmgp, ONLY: get_col_dry
  USE mo_gas_optics_constants, ONLY: avogad,m_h2o
  USE module_ra_rrtmgp, ONLY: rrtmgp_init,rrtmgp_lw_column,rrtmgp_sw_column
  USE module_ra_rrtmgp_trace, ONLY: trace_start,trace_end
  IMPLICIT NONE
  INTEGER, PARAMETER :: nc=1,nl=3,nv=nl+1
  REAL, PARAMETER :: host_g=9.81,host_cp=1004.5,host_mwdry=28.966e-3
  CHARACTER(LEN=512) :: data_path
  REAL :: play(nc,nl),plev(nc,nv),tlay(nc,nl),tlev(nc,nv),tsfc(nc)
  REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl)
  REAL :: emis(nc,1),cf(nc,nl),path(nc,nl),radius(nc,nl)
  REAL :: lwup(nc,nv),lwdn(nc,nv),lwhr(nc,nl),lwupc(nc,nv),lwdnc(nc,nv),lwhrc(nc,nl)
  REAL :: swup(nc,nv),swdn(nc,nv),swhr(nc,nl),swupc(nc,nv),swdnc(nc,nv),swhrc(nc,nl)
  REAL :: direct(nc,nv),diffuse(nc,nv),directc(nc,nv),visdir(nc,nv),visdif(nc,nv),nirdir(nc,nv),nirdif(nc,nv)
  REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  REAL(wp) :: dry(nc,nl),expected(nc,nl),fact,mair
  INTEGER :: k

  CALL get_command_argument(1,data_path)
  IF(LEN_TRIM(data_path)==0) ERROR STOP 'usage: test_rrtmgp_host_constants DATA_DIRECTORY'
  plev(1,:)=[1000.,700.,300.,1.]; play(1,:)=[850.,500.,150.]
  tlay(1,:)=[285.,260.,230.]; tlev(1,:)=[290.,275.,245.,210.]; tsfc=290.
  h2o(1,:)=[.01,.003,.0001]; co2=420.e-6; o3(1,:)=[.5e-6,1.e-6,5.e-6]
  n2o=330.e-9; ch4=1.8e-6; o2=.2095; emis=.98
  cf=0.; path=0.; radius=10.; avdir=.15; avdif=.10; andir=.25; andif=.20; mu0=.65; solar=1361.

  CALL rrtmgp_init(TRIM(data_path),gravity=host_g,cp_dry=host_cp,mol_weight_dry=host_mwdry)
  IF(ABS(REAL(grav)-host_g)>1.e-6 .OR. ABS(REAL(cp_dry)-host_cp)>1.e-5 .OR. &
     ABS(REAL(m_dry)-host_mwdry)>1.e-7) ERROR STOP 'host constants were not installed'

  ! Independently check the dry-air molecular column used by the coefficient
  ! machinery, including moist-air correction, host molecular weight, and g.
  dry=get_col_dry(REAL(h2o,wp),REAL(plev,wp)*100._wp)
  DO k=1,nl
    fact=1._wp/(1._wp+REAL(h2o(1,k),wp))
    mair=(REAL(host_mwdry,wp)+m_h2o*REAL(h2o(1,k),wp))*fact
    expected(1,k)=10._wp*ABS(REAL(plev(1,k)-plev(1,k+1),wp)*100._wp)*avogad*fact/ &
         (1000._wp*mair*100._wp*REAL(host_g,wp))
  END DO
  IF(ANY(.NOT.ieee_is_finite(dry)).OR.MAXVAL(ABS(dry-expected))>MAXVAL(expected)*2.e-6_wp) &
    ERROR STOP 'host-constant dry-air column disagrees with hydrostatic molecular-column formula'

  CALL trace_start('LW',1,1)
  CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis,cf,path,path,path, &
       radius,radius,radius,4,2,173,lwup,lwdn,lwhr,lwupc,lwdnc,lwhrc)
  CALL trace_end('LW')
  CALL trace_start('SW',1,1)
  CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
       cf,path,path,path,radius,radius,radius,4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
       direct,diffuse,directc,visdir,visdif,nirdir,nirdif)
  CALL trace_end('SW')
  IF(ANY(.NOT.ieee_is_finite(lwup)).OR.ANY(.NOT.ieee_is_finite(lwdn)).OR.ANY(.NOT.ieee_is_finite(lwhr)) .OR. &
     ANY(.NOT.ieee_is_finite(swup)).OR.ANY(.NOT.ieee_is_finite(swdn)).OR.ANY(.NOT.ieee_is_finite(swhr))) &
    ERROR STOP 'non-finite flux/heating with host constants'
  CALL energy_check(plev,lwup,lwdn,lwhr,'LW')
  CALL energy_check(plev,swup,swdn,swhr,'SW')
  WRITE(*,'(A,3(1X,ES14.6))') 'HOST_CONSTANTS_OK',grav,cp_dry,m_dry
CONTAINS
  SUBROUTINE energy_check(p,up,dn,hr,label)
    REAL, INTENT(IN) :: p(:,:),up(:,:),dn(:,:),hr(:,:)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL :: energy(nc,nl),scale
    INTEGER :: j
    DO j=1,nl
      energy(:,j)=((up(:,j+1)-up(:,j))-(dn(:,j+1)-dn(:,j)))*host_g*86400. / &
          (host_cp*100.*(p(:,j+1)-p(:,j)))
    END DO
    scale=MAX(1.,MAXVAL(ABS(hr)))
    IF(MAXVAL(ABS(energy-hr))>2.e-5*scale) THEN
      WRITE(*,'(A,1X,A,1X,ES12.4)') 'ENERGY_MISMATCH',label,MAXVAL(ABS(energy-hr))
      ERROR STOP 1
    END IF
  END SUBROUTINE energy_check
END PROGRAM test_rrtmgp_host_constants
