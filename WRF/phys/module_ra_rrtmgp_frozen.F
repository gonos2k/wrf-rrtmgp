! Experimental immutable table lookup for frozen UDM particle optics.
MODULE module_ra_rrtmgp_frozen
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE netcdf, ONLY: nf90_open,nf90_close,nf90_nowrite,nf90_inquire_dimension, &
       nf90_inq_dimid,nf90_inq_varid,nf90_inquire_variable,nf90_get_var,nf90_get_att, &
       nf90_strerror,nf90_noerr,nf90_double,nf90_global,nf90_fill_double, &
       nf90_inquire_attribute,nf90_enotatt
  USE module_ra_rrtmgp_hash, ONLY: rrtmgp_file_sha256
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: FROZEN_GRAUPEL=1,FROZEN_HAIL=2
  INTEGER, PARAMETER, PUBLIC :: FROZEN_NSW=14,FROZEN_NLW=16
  INTEGER, PARAMETER, PUBLIC :: FROZEN_OK=0,FROZEN_BAD_STATE=1,FROZEN_BAD_INPUT=2
  INTEGER, PARAMETER, PUBLIC :: FROZEN_BAD_TABLE=3,FROZEN_RANGE_ERROR=4
  CHARACTER(*), PARAMETER :: MODEL_ID='EXPERIMENTAL_HOMOGENEOUS_ICE_EXPONENTIAL_PSD_V1'
  CHARACTER(*), PARAMETER :: STATUS_ID='NUMERICAL_GENERATION_ONLY_NOT_WRF_VALIDATED'
  REAL(real64), PARAMETER :: RHO_BULK(2)=[500._real64,912._real64]
  REAL(real64), PARAMETER :: SW_BOUNDS(2,FROZEN_NSW)=RESHAPE([ &
       820.,2680.,2680.,3250.,3250.,4000.,4000.,4650.,4650.,5150., &
       5150.,6150.,6150.,7700.,7700.,8050.,8050.,12850.,12850.,16000., &
       16000.,22650.,22650.,29000.,29000.,38000.,38000.,50000. ],[2,FROZEN_NSW])
  REAL(real64), PARAMETER :: LW_BOUNDS(2,FROZEN_NLW)=RESHAPE([ &
       10.,250.,250.,500.,500.,630.,630.,700.,700.,820.,820.,980., &
       980.,1080.,1080.,1180.,1180.,1390.,1390.,1480.,1480.,1800., &
       1800.,2080.,2080.,2250.,2250.,2390.,2390.,2680.,2680.,3250. ],[2,FROZEN_NLW])

  TYPE :: table_type
    REAL(real64), ALLOCATABLE :: lambda(:),temperature(:)
    ! Fortran NetCDF reads expose dimensions in reversed C/Python order.
    REAL(real64), ALLOCATABLE :: sw_ext(:,:),sw_sca(:,:),sw_sg(:,:),sw_abs(:,:)
    REAL(real64), ALLOCATABLE :: lw_ext(:,:,:),lw_sca(:,:,:),lw_sg(:,:,:),lw_abs(:,:,:)
  END TYPE
  TYPE(table_type), SAVE :: data
  LOGICAL, SAVE :: ready=.FALSE.
  CHARACTER(LEN=:), ALLOCATABLE, SAVE :: loaded_path
  CHARACTER(LEN=64), SAVE :: loaded_sha=''

  PUBLIC :: initialize, query_sw, query_lw, frozen_table_sha256

CONTAINS

  SUBROUTINE initialize(table_path,status,message)
    CHARACTER(*), INTENT(IN) :: table_path
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    TYPE(table_type) :: candidate
    CHARACTER(64) :: hash0,hash1
    CHARACTER(256) :: why
    INTEGER :: ncid,nl,nt,stat
    status=FROZEN_OK;message=''
    IF(ready) THEN
      IF(TRIM(table_path)==loaded_path) RETURN
      CALL fail(status,message,FROZEN_BAD_STATE,'frozen table path is immutable after initialization')
      RETURN
    END IF
    CALL rrtmgp_file_sha256(TRIM(table_path),hash0,stat,why)
    IF(stat/=0) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'table hash failed: '//TRIM(why));RETURN
    END IF
    stat=nf90_open(TRIM(table_path),nf90_nowrite,ncid)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'NetCDF open: '//TRIM(nf90_strerror(stat)));RETURN
    END IF
    CALL attr_text(ncid,'model',MODEL_ID,status,message)
    IF(status/=0) GOTO 900
    CALL attr_text(ncid,'status',STATUS_ID,status,message)
    IF(status/=0) GOTO 900
    CALL attr_text(ncid,'size_coordinate','lambda of N(D)=N0 exp(-lambda D); geometric sphere diameter D in m',status,message)
    IF(status/=0) GOTO 900
    CALL attr_text(ncid,'mass_normalization', &
      'kappa*rho_bulk=lambda/4 * integral exp(-u) u^2 Q du; divide by species bulk density',status,message)
    IF(status/=0) GOTO 900
    CALL attr_text(ncid,'solar_source', &
      'NOAA NNLSSI1 Reference Spectra, BaselineModel column, W m-2 nm-1; not NRLSSI2',status,message)
    IF(status/=0) GOTO 900
    CALL attr_text(ncid,'LW_temperature', &
      'Planck source weighting only; material index is a static ice-Ih compilation',status,message)
    IF(status/=0) GOTO 900
    CALL attr_text(ncid,'udm_constants', &
      'graupel:N0=4e6,rho_bulk=500;hail:N0=4e4,rho_bulk=912;lambda_max=20000; process q cutoff=1e-9', &
      status,message)
    IF(status/=0) GOTO 900
    CALL dim_size(ncid,'lambda',nl,status,message)
    IF(status/=0) GOTO 900
    CALL dim_size(ncid,'temperature',nt,status,message)
    IF(status/=0) GOTO 900
    IF(nl<1.OR.nt<1) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'table axes must be nonempty');GOTO 900
    END IF
    ALLOCATE(candidate%lambda(nl),candidate%temperature(nt))
    CALL read_axis(ncid,'lambda','m-1',candidate%lambda,status,message)
    IF(status/=0) GOTO 900
    CALL read_axis(ncid,'temperature','K',candidate%temperature,status,message)
    IF(status/=0) GOTO 900
    IF(ANY(candidate%lambda<=0.).OR.ANY(candidate%temperature<=0.).OR. &
       ANY(candidate%lambda(2:)<=candidate%lambda(:nl-1)).OR. &
       ANY(candidate%temperature(2:)<=candidate%temperature(:nt-1))) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'axes must be positive and strictly increasing');GOTO 900
    END IF
    CALL read_bounds(ncid,'sw_bounds','sw_band',FROZEN_NSW,SW_BOUNDS,status,message)
    IF(status/=0) GOTO 900
    CALL read_bounds(ncid,'lw_bounds','lw_band',FROZEN_NLW,LW_BOUNDS,status,message)
    IF(status/=0) GOTO 900
    ALLOCATE(candidate%sw_ext(FROZEN_NSW,nl),candidate%sw_sca(FROZEN_NSW,nl), &
      candidate%sw_sg(FROZEN_NSW,nl),candidate%sw_abs(FROZEN_NSW,nl))
    ALLOCATE(candidate%lw_ext(FROZEN_NLW,nt,nl),candidate%lw_sca(FROZEN_NLW,nt,nl), &
      candidate%lw_sg(FROZEN_NLW,nt,nl),candidate%lw_abs(FROZEN_NLW,nt,nl))
    CALL read_moment(ncid,'sw_extinction_times_density',2,[FROZEN_NSW,nl], &
      [character(len=8)::'sw_band','lambda'],candidate%sw_ext,status,message)
    IF(status/=0) GOTO 900
    CALL read_moment(ncid,'sw_scattering_times_density',2,[FROZEN_NSW,nl], &
      [character(len=8)::'sw_band','lambda'],candidate%sw_sca,status,message)
    IF(status/=0) GOTO 900
    CALL read_moment(ncid,'sw_scatter_times_g_times_density',2,[FROZEN_NSW,nl], &
      [character(len=8)::'sw_band','lambda'],candidate%sw_sg,status,message)
    IF(status/=0) GOTO 900
    CALL read_moment(ncid,'sw_absorption_times_density',2,[FROZEN_NSW,nl], &
      [character(len=8)::'sw_band','lambda'],candidate%sw_abs,status,message)
    IF(status/=0) GOTO 900
    CALL read_moment(ncid,'lw_extinction_times_density',3,[FROZEN_NLW,nt,nl], &
      [character(len=11)::'lw_band','temperature','lambda'],candidate%lw_ext,status,message)
    IF(status/=0) GOTO 900
    CALL read_moment(ncid,'lw_scattering_times_density',3,[FROZEN_NLW,nt,nl], &
      [character(len=11)::'lw_band','temperature','lambda'],candidate%lw_sca,status,message)
    IF(status/=0) GOTO 900
    CALL read_moment(ncid,'lw_scatter_times_g_times_density',3,[FROZEN_NLW,nt,nl], &
      [character(len=11)::'lw_band','temperature','lambda'],candidate%lw_sg,status,message)
    IF(status/=0) GOTO 900
    CALL read_moment(ncid,'lw_absorption_times_density',3,[FROZEN_NLW,nt,nl], &
      [character(len=11)::'lw_band','temperature','lambda'],candidate%lw_abs,status,message)
    IF(status/=0) GOTO 900
    CALL validate3(candidate%lw_ext,candidate%lw_sca,candidate%lw_sg,candidate%lw_abs,status,message)
    IF(status/=0) GOTO 900
    CALL validate2(candidate%sw_ext,candidate%sw_sca,candidate%sw_sg,candidate%sw_abs,status,message)

900 CONTINUE
    stat=nf90_close(ncid)
    IF(status==0.AND.stat/=nf90_noerr) CALL fail(status,message,FROZEN_BAD_TABLE,'NetCDF close failed')
    IF(status/=0) RETURN
    CALL rrtmgp_file_sha256(TRIM(table_path),hash1,stat,why)
    IF(stat/=0) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'table re-hash failed: '//TRIM(why));RETURN
    END IF
    IF(hash0/=hash1) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'table changed during load');RETURN
    END IF
    data=candidate
    loaded_sha=hash0
    loaded_path=TRIM(table_path)
    ready=.TRUE.
  END SUBROUTINE initialize

  FUNCTION frozen_table_sha256() RESULT(value)
    CHARACTER(64) :: value
    value=''
    IF(ready) value=loaded_sha
  END FUNCTION frozen_table_sha256

  PURE SUBROUTINE query_sw(species,lambda_m_inv,path_g_m2,tau,tauomega,tauomegag,status,message)
    INTEGER, INTENT(IN) :: species
    REAL(real64), INTENT(IN) :: lambda_m_inv(:,:),path_g_m2(:,:)
    REAL(real64), INTENT(OUT) :: tau(:,:,:),tauomega(:,:,:),tauomegag(:,:,:)
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    INTEGER :: c,k,b,i0,i1
    REAL(real64) :: f,x,n0,n1,factor
    status=FROZEN_OK;message='';tau=0.;tauomega=0.;tauomegag=0.
    IF(.NOT.ready) THEN
      status=FROZEN_BAD_STATE;message='frozen table is not initialized';RETURN
    END IF
    IF(species<1.OR.species>2) THEN
      status=FROZEN_BAD_INPUT;message='unknown frozen species';RETURN
    END IF
    IF(ANY(SHAPE(lambda_m_inv)/=SHAPE(path_g_m2)).OR.SIZE(tau,1)/=SIZE(lambda_m_inv,1).OR. &
       SIZE(tau,2)/=SIZE(lambda_m_inv,2).OR.SIZE(tau,3)/=FROZEN_NSW.OR. &
       ANY(SHAPE(tauomega)/=SHAPE(tau)).OR.ANY(SHAPE(tauomegag)/=SHAPE(tau))) THEN
      status=FROZEN_BAD_INPUT;message='SW frozen optics shape mismatch';RETURN
    END IF
    DO k=1,SIZE(lambda_m_inv,2); DO c=1,SIZE(lambda_m_inv,1)
      IF(.NOT.ieee_is_finite(lambda_m_inv(c,k)).OR..NOT.ieee_is_finite(path_g_m2(c,k))) THEN
        WRITE(message,'(A,A,A,I0,A,I0,A,ES14.6,A,ES14.6)') &
          'SW lambda/path must be finite species=',TRIM(species_label(species)), &
          ' column=',c,' layer=',k,' lambda_m_inv=',lambda_m_inv(c,k),' path_g_m2=',path_g_m2(c,k)
        status=FROZEN_BAD_INPUT;RETURN
      END IF
      IF(lambda_m_inv(c,k)<=0..OR.path_g_m2(c,k)<0.) THEN
        WRITE(message,'(A,A,A,I0,A,I0,A,ES14.6,A,ES14.6)') &
          'SW lambda must be positive and path nonnegative species=',TRIM(species_label(species)), &
          ' column=',c,' layer=',k,' lambda_m_inv=',lambda_m_inv(c,k),' path_g_m2=',path_g_m2(c,k)
        status=FROZEN_BAD_INPUT;RETURN
      END IF
      IF(path_g_m2(c,k)==0.) CYCLE
      x=lambda_m_inv(c,k)
      IF(x<data%lambda(1).OR.x>data%lambda(SIZE(data%lambda))) THEN
        WRITE(message,'(A,A,A,I0,A,I0,A,ES14.6,A,ES14.6,A,ES14.6,A,ES14.6,A,ES14.6,A)') &
          'SW lambda outside table range; extrapolation forbidden species=',TRIM(species_label(species)), &
          ' column=',c,' layer=',k,' lambda_m_inv=',x,' path_g_m2=',path_g_m2(c,k), &
          ' axis_m_inv=[',data%lambda(1),',',data%lambda(SIZE(data%lambda)),']'
        status=FROZEN_RANGE_ERROR;RETURN
      END IF
      CALL bracket_lambda(x,i0,i1,f)
      factor=path_g_m2(c,k)*1.e-3_real64/RHO_BULK(species)
      DO b=1,FROZEN_NSW
        n0=data%sw_ext(b,i0)/data%lambda(i0);n1=data%sw_ext(b,i1)/data%lambda(i1)
        tau(c,k,b)=x*((1.-f)*n0+f*n1)*factor
        n0=data%sw_sca(b,i0)/data%lambda(i0);n1=data%sw_sca(b,i1)/data%lambda(i1)
        tauomega(c,k,b)=x*((1.-f)*n0+f*n1)*factor
        n0=data%sw_sg(b,i0)/data%lambda(i0);n1=data%sw_sg(b,i1)/data%lambda(i1)
        tauomegag(c,k,b)=x*((1.-f)*n0+f*n1)*factor
      END DO
    END DO; END DO
    IF(ANY(.NOT.ieee_is_finite(tau)).OR.ANY(.NOT.ieee_is_finite(tauomega)).OR. &
       ANY(.NOT.ieee_is_finite(tauomegag))) THEN
      status=FROZEN_BAD_INPUT;message='SW optical depth overflow'
      tau=0.;tauomega=0.;tauomegag=0.
    END IF
  END SUBROUTINE query_sw

  PURE SUBROUTINE query_lw(species,lambda_m_inv,temperature_k,path_g_m2,tau_abs,status,message)
    INTEGER, INTENT(IN) :: species
    REAL(real64), INTENT(IN) :: lambda_m_inv(:,:),temperature_k(:,:),path_g_m2(:,:)
    REAL(real64), INTENT(OUT) :: tau_abs(:,:,:)
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    INTEGER :: c,k,b,i0,i1,j0,j1
    REAL(real64) :: fl,ft,x,t,n00,n01,n10,n11,factor
    status=FROZEN_OK;message='';tau_abs=0.
    IF(.NOT.ready) THEN
      status=FROZEN_BAD_STATE;message='frozen table is not initialized';RETURN
    END IF
    IF(species<1.OR.species>2) THEN
      status=FROZEN_BAD_INPUT;message='unknown frozen species';RETURN
    END IF
    IF(ANY(SHAPE(lambda_m_inv)/=SHAPE(temperature_k)).OR.ANY(SHAPE(lambda_m_inv)/=SHAPE(path_g_m2)).OR. &
       SIZE(tau_abs,1)/=SIZE(lambda_m_inv,1).OR.SIZE(tau_abs,2)/=SIZE(lambda_m_inv,2).OR. &
       SIZE(tau_abs,3)/=FROZEN_NLW) THEN
      status=FROZEN_BAD_INPUT;message='LW frozen optics shape mismatch';RETURN
    END IF
    DO k=1,SIZE(lambda_m_inv,2); DO c=1,SIZE(lambda_m_inv,1)
      IF(.NOT.ieee_is_finite(lambda_m_inv(c,k)).OR..NOT.ieee_is_finite(temperature_k(c,k)).OR. &
         .NOT.ieee_is_finite(path_g_m2(c,k))) THEN
        WRITE(message,'(A,A,A,I0,A,I0,A,ES14.6,A,ES14.6,A,ES14.6)') &
          'LW lambda/temperature/path must be finite species=',TRIM(species_label(species)), &
          ' column=',c,' layer=',k,' lambda_m_inv=',lambda_m_inv(c,k), &
          ' temperature_k=',temperature_k(c,k),' path_g_m2=',path_g_m2(c,k)
        status=FROZEN_BAD_INPUT;RETURN
      END IF
      IF(lambda_m_inv(c,k)<=0..OR.temperature_k(c,k)<=0..OR.path_g_m2(c,k)<0.) THEN
        WRITE(message,'(A,A,A,I0,A,I0,A,ES14.6,A,ES14.6,A,ES14.6)') &
          'LW lambda and temperature must be positive; path nonnegative species=',TRIM(species_label(species)), &
          ' column=',c,' layer=',k,' lambda_m_inv=',lambda_m_inv(c,k), &
          ' temperature_k=',temperature_k(c,k),' path_g_m2=',path_g_m2(c,k)
        status=FROZEN_BAD_INPUT;RETURN
      END IF
      IF(path_g_m2(c,k)==0.) CYCLE
      x=lambda_m_inv(c,k);t=temperature_k(c,k)
      IF(x<data%lambda(1).OR.x>data%lambda(SIZE(data%lambda))) THEN
        WRITE(message,'(A,A,A,I0,A,I0,A,ES14.6,A,ES14.6,A,ES14.6,A,ES14.6,A,ES14.6,A)') &
          'LW lambda outside table range; extrapolation forbidden species=',TRIM(species_label(species)), &
          ' column=',c,' layer=',k,' lambda_m_inv=',x,' temperature_k=',t, &
          ' path_g_m2=',path_g_m2(c,k),' axis_m_inv=[',data%lambda(1),',',data%lambda(SIZE(data%lambda)),']'
        status=FROZEN_RANGE_ERROR;RETURN
      END IF
      IF(t<data%temperature(1).OR.t>data%temperature(SIZE(data%temperature))) THEN
        WRITE(message,'(A,A,A,I0,A,I0,A,ES14.6,A,ES14.6,A,ES14.6,A,ES14.6,A,ES14.6,A)') &
          'LW temperature outside table range; extrapolation forbidden species=',TRIM(species_label(species)), &
          ' column=',c,' layer=',k,' lambda_m_inv=',x,' temperature_k=',t, &
          ' path_g_m2=',path_g_m2(c,k),' axis_K=[',data%temperature(1),',',data%temperature(SIZE(data%temperature)),']'
        status=FROZEN_RANGE_ERROR;RETURN
      END IF
      CALL bracket_lambda(x,i0,i1,fl);CALL bracket_temp(t,j0,j1,ft)
      factor=path_g_m2(c,k)*1.e-3_real64/RHO_BULK(species)
      DO b=1,FROZEN_NLW
        n00=data%lw_abs(b,j0,i0)/data%lambda(i0);n01=data%lw_abs(b,j1,i0)/data%lambda(i0)
        n10=data%lw_abs(b,j0,i1)/data%lambda(i1);n11=data%lw_abs(b,j1,i1)/data%lambda(i1)
        tau_abs(c,k,b)=x*((1.-fl)*((1.-ft)*n00+ft*n01)+fl*((1.-ft)*n10+ft*n11))*factor
      END DO
    END DO; END DO
    IF(ANY(.NOT.ieee_is_finite(tau_abs))) THEN
      status=FROZEN_BAD_INPUT;message='LW optical depth overflow';tau_abs=0.
    END IF
  END SUBROUTINE query_lw

  PURE SUBROUTINE bracket_lambda(x,lo,hi,f)
    REAL(real64), INTENT(IN) :: x
    INTEGER, INTENT(OUT) :: lo,hi
    REAL(real64), INTENT(OUT) :: f
    INTEGER :: mid,n
    n=SIZE(data%lambda)
    IF(n==1) THEN
      lo=1;hi=1;f=0.;RETURN
    END IF
    IF(x==data%lambda(n)) THEN
      lo=n-1;hi=n;f=1.;RETURN
    END IF
    lo=1;hi=n
    DO WHILE(hi-lo>1)
      mid=(lo+hi)/2
      IF(x<data%lambda(mid)) THEN
        hi=mid
      ELSE
        lo=mid
      END IF
    END DO
    f=(LOG(x)-LOG(data%lambda(lo)))/(LOG(data%lambda(hi))-LOG(data%lambda(lo)))
  END SUBROUTINE bracket_lambda

  PURE SUBROUTINE bracket_temp(x,lo,hi,f)
    REAL(real64), INTENT(IN) :: x
    INTEGER, INTENT(OUT) :: lo,hi
    REAL(real64), INTENT(OUT) :: f
    INTEGER :: mid,n
    n=SIZE(data%temperature)
    IF(n==1) THEN
      lo=1;hi=1;f=0.;RETURN
    END IF
    IF(x==data%temperature(n)) THEN
      lo=n-1;hi=n;f=1.;RETURN
    END IF
    lo=1;hi=n
    DO WHILE(hi-lo>1)
      mid=(lo+hi)/2
      IF(x<data%temperature(mid)) THEN
        hi=mid
      ELSE
        lo=mid
      END IF
    END DO
    f=(x-data%temperature(lo))/(data%temperature(hi)-data%temperature(lo))
  END SUBROUTINE bracket_temp

  PURE FUNCTION species_label(species) RESULT(label)
    INTEGER, INTENT(IN) :: species
    CHARACTER(7) :: label
    SELECT CASE(species)
    CASE(FROZEN_GRAUPEL)
      label='graupel'
    CASE(FROZEN_HAIL)
      label='hail   '
    CASE DEFAULT
      label='unknown'
    END SELECT
  END FUNCTION species_label

  SUBROUTINE dim_size(ncid,name,n,status,message)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(*), INTENT(IN) :: name
    INTEGER, INTENT(OUT) :: n,status
    CHARACTER(*), INTENT(OUT) :: message
    INTEGER :: id,stat
    status=0;message='';n=0
    stat=nf90_inq_dimid(ncid,name,id)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'missing dimension '//TRIM(name));RETURN
    END IF
    stat=nf90_inquire_dimension(ncid,id,len=n)
    IF(stat/=nf90_noerr) CALL fail(status,message,FROZEN_BAD_TABLE,'cannot read dimension '//TRIM(name))
  END SUBROUTINE dim_size

  SUBROUTINE attr_text(ncid,name,expected,status,message)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(*), INTENT(IN) :: name,expected
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    CHARACTER(1024) :: value
    INTEGER :: stat
    status=0;message='';value=''
    stat=nf90_get_att(ncid,nf90_global,name,value)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'missing table attribute '//TRIM(name));RETURN
    END IF
    IF(TRIM(value)/=TRIM(expected)) CALL fail(status,message,FROZEN_BAD_TABLE,'unexpected table attribute '//TRIM(name))
  END SUBROUTINE attr_text

  SUBROUTINE read_axis(ncid,name,units,value,status,message)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(*), INTENT(IN) :: name,units
    REAL(real64), INTENT(OUT) :: value(:)
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    INTEGER :: varid,ndims,xtype,dimids(1),stat,n
    CHARACTER(80) :: dname,actual_units
    status=0;message=''
    stat=nf90_inq_varid(ncid,name,varid)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'missing axis '//TRIM(name));RETURN
    END IF
    stat=nf90_inquire_variable(ncid,varid,xtype=xtype,ndims=ndims,dimids=dimids)
    IF(stat/=nf90_noerr.OR.ndims/=1.OR.xtype/=nf90_double) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'axis type/rank mismatch '//TRIM(name));RETURN
    END IF
    CALL check_storage_attrs(ncid,varid,name,status,message)
    IF(status/=0) RETURN
    stat=nf90_inquire_dimension(ncid,dimids(1),name=dname,len=n)
    IF(stat/=nf90_noerr.OR.TRIM(dname)/=name.OR.n/=SIZE(value)) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'axis dimension mismatch '//TRIM(name));RETURN
    END IF
    stat=nf90_get_att(ncid,varid,'units',actual_units)
    IF(stat/=nf90_noerr.OR.TRIM(actual_units)/=units) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'axis units mismatch '//TRIM(name));RETURN
    END IF
    stat=nf90_get_var(ncid,varid,value)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'axis read failed '//TRIM(name));RETURN
    END IF
    IF(ANY(.NOT.ieee_is_finite(value))) CALL fail(status,message,FROZEN_BAD_TABLE,'non-finite axis '//TRIM(name))
    IF(ANY(value==nf90_fill_double)) CALL fail(status,message,FROZEN_BAD_TABLE,'fill value in axis '//TRIM(name))
  END SUBROUTINE read_axis

  SUBROUTINE read_bounds(ncid,name,bandname,nb,expected,status,message)
    INTEGER, INTENT(IN) :: ncid,nb
    CHARACTER(*), INTENT(IN) :: name,bandname
    REAL(real64), INTENT(IN) :: expected(2,nb)
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    INTEGER :: varid,ndims,xtype,dimids(2),stat,n1,n2
    CHARACTER(80) :: d1,d2,units
    REAL(real64) :: value(2,nb)
    status=0;message=''
    stat=nf90_inq_varid(ncid,name,varid)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'missing band bounds '//TRIM(name));RETURN
    END IF
    stat=nf90_inquire_variable(ncid,varid,xtype=xtype,ndims=ndims,dimids=dimids)
    IF(stat/=nf90_noerr.OR.ndims/=2.OR.xtype/=nf90_double) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'band bounds type/rank mismatch');RETURN
    END IF
    CALL check_storage_attrs(ncid,varid,name,status,message)
    IF(status/=0) RETURN
    stat=nf90_inquire_dimension(ncid,dimids(1),name=d1,len=n1)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'band bounds dim invalid');RETURN
    END IF
    stat=nf90_inquire_dimension(ncid,dimids(2),name=d2,len=n2)
    IF(stat/=nf90_noerr.OR.TRIM(d1)/='bound'.OR.TRIM(d2)/=bandname.OR.n1/=2.OR.n2/=nb) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'band bounds dimensions/order mismatch');RETURN
    END IF
    stat=nf90_get_att(ncid,varid,'units',units)
    IF(stat/=nf90_noerr.OR.TRIM(units)/='cm-1') THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'band bounds units mismatch');RETURN
    END IF
    stat=nf90_get_var(ncid,varid,value)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'band bounds read failed')
      RETURN
    END IF
    IF(ANY(.NOT.ieee_is_finite(value)).OR.ANY(value/=expected)) &
      CALL fail(status,message,FROZEN_BAD_TABLE,'band bounds do not match pinned band order')
    IF(ANY(value==nf90_fill_double)) CALL fail(status,message,FROZEN_BAD_TABLE,'fill value in band bounds')
  END SUBROUTINE read_bounds

  SUBROUTINE read_moment(ncid,name,rank,lengths,names,value,status,message)
    INTEGER, INTENT(IN) :: ncid,rank,lengths(:)
    CHARACTER(*), INTENT(IN) :: name
    CHARACTER(*), INTENT(IN) :: names(:)
    REAL(real64), INTENT(OUT) :: value(..)
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    INTEGER :: varid,ndims,xtype,dimids(3),stat,i,n
    CHARACTER(80) :: dname,units
    status=0;message='';varid=-1
    stat=nf90_inq_varid(ncid,name,varid)
    IF(stat/=nf90_noerr) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'missing moment variable '//TRIM(name));RETURN
    END IF
    stat=nf90_inquire_variable(ncid,varid,xtype=xtype,ndims=ndims,dimids=dimids)
    IF(stat/=nf90_noerr.OR.ndims/=rank.OR.xtype/=nf90_double) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'moment type/rank mismatch '//TRIM(name));RETURN
    END IF
    CALL check_storage_attrs(ncid,varid,name,status,message)
    IF(status/=0) RETURN
    DO i=1,rank
      stat=nf90_inquire_dimension(ncid,dimids(i),name=dname,len=n)
      IF(stat/=nf90_noerr.OR.TRIM(dname)/=TRIM(names(i)).OR.n/=lengths(i)) THEN
        CALL fail(status,message,FROZEN_BAD_TABLE,'moment dimension/order mismatch '//TRIM(name));RETURN
      END IF
    END DO
    stat=nf90_get_att(ncid,varid,'units',units)
    IF(stat/=nf90_noerr.OR.TRIM(units)/='m-1') THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'moment units mismatch '//TRIM(name));RETURN
    END IF
    SELECT RANK(value)
    RANK(2)
      stat=nf90_get_var(ncid,varid,value)
      IF(stat/=nf90_noerr) CALL fail(status,message,FROZEN_BAD_TABLE,'moment read failed '//TRIM(name))
    RANK(3)
      stat=nf90_get_var(ncid,varid,value)
      IF(stat/=nf90_noerr) CALL fail(status,message,FROZEN_BAD_TABLE,'moment read failed '//TRIM(name))
    RANK DEFAULT
      CALL fail(status,message,FROZEN_BAD_TABLE,'unsupported moment rank')
    END SELECT
  END SUBROUTINE read_moment

  SUBROUTINE check_storage_attrs(ncid,varid,name,status,message)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(*), INTENT(IN) :: name
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    CHARACTER(16), PARAMETER :: forbidden(4)=[character(len=16) :: &
      '_FillValue','missing_value','scale_factor','add_offset']
    INTEGER :: i,stat
    status=FROZEN_OK;message=''
    DO i=1,SIZE(forbidden)
      stat=nf90_inquire_attribute(ncid,varid,TRIM(forbidden(i)))
      IF(stat==nf90_noerr) THEN
        CALL fail(status,message,FROZEN_BAD_TABLE, &
          'unsupported storage attribute '//TRIM(forbidden(i))//' on '//TRIM(name))
        RETURN
      ELSE IF(stat/=nf90_enotatt) THEN
        CALL fail(status,message,FROZEN_BAD_TABLE, &
          'cannot inspect storage attributes on '//TRIM(name))
        RETURN
      END IF
    END DO
  END SUBROUTINE check_storage_attrs

  SUBROUTINE validate3(ext,sca,sg,absorb,status,message)
    REAL(real64), INTENT(IN) :: ext(:,:,:),sca(:,:,:),sg(:,:,:),absorb(:,:,:)
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    status=0;message=''
    IF(ANY(.NOT.ieee_is_finite(ext)).OR.ANY(.NOT.ieee_is_finite(sca)).OR. &
       ANY(.NOT.ieee_is_finite(sg)).OR.ANY(.NOT.ieee_is_finite(absorb))) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'non-finite LW moment');RETURN
    END IF
    IF(ANY(ext<=0.).OR.ANY(sca<0.).OR.ANY(absorb<0.).OR.ANY(ABS(sg)>sca+1.e-10_real64).OR. &
       ANY(ABS(ext-sca-absorb)>1.e-10_real64*MAX(1._real64,ABS(ext)))) &
      CALL fail(status,message,FROZEN_BAD_TABLE,'LW moment bounds/closure violation')
  END SUBROUTINE validate3

  SUBROUTINE validate2(ext,sca,sg,absorb,status,message)
    REAL(real64), INTENT(IN) :: ext(:,:),sca(:,:),sg(:,:),absorb(:,:)
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    status=0;message=''
    IF(ANY(.NOT.ieee_is_finite(ext)).OR.ANY(.NOT.ieee_is_finite(sca)).OR. &
       ANY(.NOT.ieee_is_finite(sg)).OR.ANY(.NOT.ieee_is_finite(absorb))) THEN
      CALL fail(status,message,FROZEN_BAD_TABLE,'non-finite SW moment');RETURN
    END IF
    IF(ANY(ext<=0.).OR.ANY(sca<0.).OR.ANY(absorb<0.).OR.ANY(ABS(sg)>sca+1.e-10_real64).OR. &
       ANY(ABS(ext-sca-absorb)>1.e-10_real64*MAX(1._real64,ABS(ext)))) &
      CALL fail(status,message,FROZEN_BAD_TABLE,'SW moment bounds/closure violation')
  END SUBROUTINE validate2

  SUBROUTINE fail(status,message,code,text)
    INTEGER, INTENT(OUT) :: status
    CHARACTER(*), INTENT(OUT) :: message
    INTEGER, INTENT(IN) :: code
    CHARACTER(*), INTENT(IN) :: text
    status=code;message=text
  END SUBROUTINE fail
END MODULE module_ra_rrtmgp_frozen
