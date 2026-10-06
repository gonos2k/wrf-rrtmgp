! Fresh/reused state and shape oracle. Scratch builds can define
! RRTMGP_BASELINE_REFERENCE to run this identical fixture on the original adapter.
MODULE test_workspace_cases
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32,int64
  USE module_ra_rrtmgp, ONLY: rrtmgp_init,rrtmgp_lw_column,rrtmgp_sw_column
#ifndef RRTMGP_BASELINE_REFERENCE
  USE module_ra_rrtmgp, ONLY: ty_rrtmgp_lw_workspace,ty_rrtmgp_sw_workspace,rrtmgp_release_workspace
#endif
  USE module_ra_rrtmgp_trace, ONLY: trace_start,trace_end
  IMPLICIT NONE
#ifdef RRTMGP_BASELINE_REFERENCE
  TYPE :: ty_rrtmgp_lw_workspace
    INTEGER :: unused
  END TYPE
  TYPE :: ty_rrtmgp_sw_workspace
    INTEGER :: unused
  END TYPE
#endif
  LOGICAL :: frozen
CONTAINS
  RECURSIVE SUBROUTINE exercise(tile,unit,sig)
    INTEGER, INTENT(IN) :: tile,unit
    INTEGER(int64), INTENT(OUT) :: sig
    TYPE(ty_rrtmgp_lw_workspace) :: lw
    TYPE(ty_rrtmgp_sw_workspace) :: sw
    sig=0_int64
    CALL shape_cases(1,3,tile,unit,lw,sw,sig)
    CALL shape_cases(1,60,tile,unit,lw,sw,sig)
    CALL shape_cases(8,37,tile,unit,lw,sw,sig)
    CALL shape_cases(3,37,tile,unit,lw,sw,sig)
    CALL shape_cases(1,3,tile,unit,lw,sw,sig)
#ifndef RRTMGP_BASELINE_REFERENCE
    CALL rrtmgp_release_workspace(lw); CALL rrtmgp_release_workspace(sw)
    CALL rrtmgp_release_workspace(lw); CALL rrtmgp_release_workspace(sw)
#endif
    ! A released workspace must behave exactly like a new one.
    CALL shape_cases(1,3,tile,unit,lw,sw,sig)
#ifndef RRTMGP_BASELINE_REFERENCE
    CALL rrtmgp_release_workspace(lw); CALL rrtmgp_release_workspace(sw)
#endif
  END SUBROUTINE

  RECURSIVE SUBROUTINE shape_cases(nc,nl,tile,unit,lw,sw,sig)
    INTEGER, INTENT(IN) :: nc,nl,tile,unit
    TYPE(ty_rrtmgp_lw_workspace), INTENT(INOUT) :: lw
    TYPE(ty_rrtmgp_sw_workspace), INTENT(INOUT) :: sw
    INTEGER(int64), INTENT(INOUT) :: sig
    REAL :: play(nc,nl),plev(nc,nl+1),tlay(nc,nl),tlev(nc,nl+1),tsfc(nc),emis(nc,1)
    REAL :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl),cfc(nc,nl)
    REAL :: cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rwp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl)
    REAL :: gwp(nc,nl),hwp(nc,nl),lg(nc,nl),lh(nc,nl),dry(nc,nl-1)
    REAL :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
    REAL :: ref(nc,nl+1,23),got(nc,nl+1,23),legacy(nc,nl+1,23)
    REAL, ALLOCATABLE :: cfc_opt(:,:),rain_opt(:,:),g_opt(:,:),h_opt(:,:),lg_opt(:,:),lh_opt(:,:),snapshot(:)
    INTEGER :: c,k,state,overlap,seeds(nc)
    INTEGER(int32) :: bits(nc*(nl+1)*23)
    DO state=1,12
      DO c=1,nc
        DO k=1,nl+1
          plev(c,k)=(1000.+c+tile)*EXP(LOG(.002)*REAL(k-1)/REAL(nl))
          tlev(c,k)=286.-70.*REAL(k-1)/REAL(nl)+.02*state+.01*tile
        END DO
        tsfc(c)=tlev(c,1)+.1*state; emis(c,1)=.9+.003*state
        avdir(c)=.1+.005*state; avdif(c)=.08+.002*c
        andir(c)=.2+.003*c; andif(c)=.15+.002*tile
        mu0(c)=.4+.005*state+.003*c
        seeds(c)=1337+7919*c+997*tile+17*state
      END DO
      play=.5*(plev(:,1:nl)+plev(:,2:nl+1)); tlay=.5*(tlev(:,1:nl)+tlev(:,2:nl+1))
      h2o=.005+state*.00001; co2=420.e-6+state*1.e-6; o3=1.e-6+state*1.e-8
      n2o=330.e-9;ch4=1.8e-6;o2=.2095;cfc=2.51e-10+state*1.e-12
      cf=.4;lwp=10.+state;iwp=3.+.1*state;swp=5.+.2*state;rwp=2.+.1*state
      rel=10.+.1*state;rei=30.+.2*state;res=100.+state
      gwp=5.+state;hwp=2.+.1*state;lg=2000.+state;lh=800.+state
      dry=(plev(:,1:nl-1)-plev(:,2:nl))*100./9.80665
      solar=1361.+state;overlap=1
      ! Cloud -> clear -> overlap-zero -> cloud; positive frozen -> zero frozen;
      ! daylight -> night -> daylight; optional CFC/rain toggles within a shape.
      IF(MOD(state,4)==2) THEN
        cf=0.;lwp=0.;iwp=0.;swp=0.;rwp=0.;gwp=0.;hwp=0.
      END IF
      IF(MOD(state,4)==3) overlap=0
      IF(state==5.OR.state==9) mu0=0.
      IF(ALLOCATED(cfc_opt)) DEALLOCATE(cfc_opt)
      IF(ALLOCATED(rain_opt)) DEALLOCATE(rain_opt)
      IF(MOD(state,2)==1) cfc_opt=cfc
      IF(MOD(state,3)/=0) rain_opt=rwp
      IF(frozen) THEN
        g_opt=gwp;h_opt=hwp;lg_opt=lg;lh_opt=lh
      END IF
      snapshot=input_values()
      CALL run(ref)
      CALL run(got,lw,sw)
      IF(ANY(TRANSFER(ref,[0_int32],SIZE(ref))/=TRANSFER(got,[0_int32],SIZE(got)))) THEN
        WRITE(*,*) 'workspace mismatch tile,nc,nl,state=',tile,nc,nl,state,MAXVAL(ABS(ref-got))
        ERROR STOP 'workspace output bits differ from fresh call'
      END IF
      IF(ANY(TRANSFER(snapshot,[0_int32],SIZE(snapshot))/=TRANSFER(input_values(),[0_int32],SIZE(snapshot)))) &
        ERROR STOP 'workspace mutated caller input'
      ! Toggle pre-delta off and then on while retaining diagnostics storage.
      IF(state==4) THEN
        CALL run(legacy,lw,sw,without_predelta=.TRUE.)
        IF(ANY(TRANSFER(legacy(:,:,1:19),[0_int32],SIZE(legacy(:,:,1:19)))/= &
               TRANSFER(ref(:,:,1:19),[0_int32],SIZE(ref(:,:,1:19))))) ERROR STOP 'optional-off changed ordinary outputs'
        CALL run(got,lw,sw)
        IF(ANY(TRANSFER(ref,[0_int32],SIZE(ref))/=TRANSFER(got,[0_int32],SIZE(got)))) &
          ERROR STOP 'optional-off left stale workspace values'
      END IF
      IF(unit/=0) WRITE(unit) nc,nl,state,got
      bits=TRANSFER(got,bits)
      DO k=1,SIZE(bits)
        sig=IEOR(ISHFTC(sig,1),INT(bits(k),int64))
      END DO
    END DO
  CONTAINS
    FUNCTION input_values() RESULT(v)
      REAL, ALLOCATABLE :: v(:)
      v=[RESHAPE(play,[SIZE(play)]),RESHAPE(plev,[SIZE(plev)]),RESHAPE(tlay,[SIZE(tlay)]), &
        RESHAPE(tlev,[SIZE(tlev)]),tsfc,RESHAPE(emis,[SIZE(emis)]),RESHAPE(h2o,[SIZE(h2o)]), &
        RESHAPE(co2,[SIZE(co2)]),RESHAPE(o3,[SIZE(o3)]),RESHAPE(n2o,[SIZE(n2o)]),RESHAPE(ch4,[SIZE(ch4)]), &
        RESHAPE(o2,[SIZE(o2)]),RESHAPE(cf,[SIZE(cf)]),RESHAPE(lwp,[SIZE(lwp)]),RESHAPE(iwp,[SIZE(iwp)]), &
        RESHAPE(swp,[SIZE(swp)]),RESHAPE(rwp,[SIZE(rwp)]),RESHAPE(rel,[SIZE(rel)]),RESHAPE(rei,[SIZE(rei)]), &
        RESHAPE(res,[SIZE(res)]),RESHAPE(cfc,[SIZE(cfc)]),RESHAPE(dry,[SIZE(dry)]), &
        RESHAPE(gwp,[SIZE(gwp)]),RESHAPE(hwp,[SIZE(hwp)]),RESHAPE(lg,[SIZE(lg)]),RESHAPE(lh,[SIZE(lh)]), &
        avdir,avdif,andir,andif,mu0,solar]
      IF(ALLOCATED(cfc_opt)) v=[v,RESHAPE(cfc_opt,[SIZE(cfc_opt)])]
      IF(ALLOCATED(rain_opt)) v=[v,RESHAPE(rain_opt,[SIZE(rain_opt)])]
      IF(ALLOCATED(g_opt)) v=[v,RESHAPE(g_opt,[SIZE(g_opt)]),RESHAPE(h_opt,[SIZE(h_opt)]), &
        RESHAPE(lg_opt,[SIZE(lg_opt)]),RESHAPE(lh_opt,[SIZE(lh_opt)])]
    END FUNCTION
    RECURSIVE SUBROUTINE run(out,lw_ws,sw_ws,without_predelta)
      REAL, INTENT(OUT) :: out(nc,nl+1,23)
      TYPE(ty_rrtmgp_lw_workspace), OPTIONAL, INTENT(INOUT) :: lw_ws
      TYPE(ty_rrtmgp_sw_workspace), OPTIONAL, INTENT(INOUT) :: sw_ws
      LOGICAL, OPTIONAL, INTENT(IN) :: without_predelta
      REAL, ALLOCATABLE :: du(:,:),dcu(:,:),vdu(:,:),ndu(:,:)
      LOGICAL :: predelta
      out=0.;predelta=.TRUE.
      IF(PRESENT(without_predelta)) predelta=.NOT.without_predelta
      IF(predelta) ALLOCATE(du(nc,nl+1),dcu(nc,nl+1),vdu(nc,nl+1),ndu(nc,nl+1))
      CALL trace_start('LW',1,1)
      CALL rrtmgp_lw_column(play,plev,tlay,tlev,tsfc,h2o,co2,o3,n2o,ch4,o2,emis, &
        cf,lwp,iwp,swp,rel,rei,res,4,overlap,771, &
        out(:,:,1),out(:,:,2),out(:,1:nl,3),out(:,:,4),out(:,:,5),out(:,1:nl,6), &
        column_seeds=seeds,rwp=rain_opt,native_dry_layer_mass_kg_m2=dry,gwp=g_opt,hwp=h_opt,lambda_g=lg_opt,lambda_h=lh_opt, &
#ifndef RRTMGP_BASELINE_REFERENCE
        workspace=lw_ws, &
#endif
        cfc11vmr=cfc_opt,cfc12vmr=cfc_opt,cfc22vmr=cfc_opt,ccl4vmr=cfc_opt)
      CALL trace_end('LW')
      CALL trace_start('SW',1,1)
      CALL rrtmgp_sw_column(play,plev,tlay,h2o,co2,o3,n2o,ch4,o2,avdir,avdif,andir,andif,mu0,solar, &
        cf,lwp,iwp,swp,rel,rei,res,4,overlap,771,out(:,:,7),out(:,:,8),out(:,1:nl,9), &
        out(:,:,10),out(:,:,11),out(:,1:nl,12),out(:,:,13),out(:,:,14),out(:,:,15), &
        out(:,:,16),out(:,:,17),out(:,:,18),out(:,:,19),column_seeds=seeds,rwp=rain_opt, &
        native_dry_layer_mass_kg_m2=dry,gwp=g_opt,hwp=h_opt,lambda_g=lg_opt,lambda_h=lh_opt, &
#ifndef RRTMGP_BASELINE_REFERENCE
        workspace=sw_ws, &
#endif
        direct_unscaled=du,directc_unscaled=dcu,visdir_unscaled=vdu,nirdir_unscaled=ndu)
      CALL trace_end('SW')
      IF(predelta) THEN
        out(:,:,20)=du;out(:,:,21)=dcu;out(:,:,22)=vdu;out(:,:,23)=ndu
      END IF
    END SUBROUTINE
  END SUBROUTINE
END MODULE test_workspace_cases

PROGRAM test_workspace
  USE test_workspace_cases
  IMPLICIT NONE
  CHARACTER(1024) :: data_path,mode,table_path,snapshot_path
  INTEGER :: i,n,u
  INTEGER(int64) :: serial(8),parallel(8),signature
  CALL GET_COMMAND_ARGUMENT(1,data_path)
  CALL GET_COMMAND_ARGUMENT(2,mode)
  CALL GET_COMMAND_ARGUMENT(3,table_path)
  CALL GET_COMMAND_ARGUMENT(4,snapshot_path)
  frozen=TRIM(mode)=='1'.OR.TRIM(mode)=='flip'
  IF(frozen) THEN
    CALL rrtmgp_init(TRIM(data_path),frozen_optics=1,frozen_table=TRIM(table_path))
  ELSE
    CALL rrtmgp_init(TRIM(data_path))
  END IF
  IF(TRIM(mode)=='flip') THEN
    CALL rrtmgp_init(TRIM(data_path),frozen_optics=0)
    ERROR STOP 'workspace test unexpectedly accepted a frozen mode change'
  END IF
  u=0
  IF(LEN_TRIM(snapshot_path)>0) OPEN(NEWUNIT=u,FILE=TRIM(snapshot_path),ACCESS='STREAM',FORM='UNFORMATTED',STATUS='REPLACE')
  CALL exercise(1,u,signature)
  IF(u/=0) CLOSE(u)
  IF(LEN_TRIM(snapshot_path)>0) THEN
    WRITE(*,'(A)') 'WORKSPACE_SNAPSHOT_PASS'
    STOP
  END IF
  DO i=1,8
    CALL exercise(i,0,serial(i))
  END DO
  DO n=1,4
    !$OMP PARALLEL DO DEFAULT(NONE) SHARED(parallel) PRIVATE(i) NUM_THREADS(n) SCHEDULE(DYNAMIC,1)
    DO i=1,8
      CALL exercise(i,0,parallel(i))
    END DO
    !$OMP END PARALLEL DO
    IF(ANY(serial/=parallel)) ERROR STOP 'tile workspace differs from serial results'
  END DO
  WRITE(*,'(A)') 'WORKSPACE_REUSE_STATE_SHAPE_OPENMP_PASS'
END PROGRAM test_workspace
