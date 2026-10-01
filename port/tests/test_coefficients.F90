program test_coefficients
  use iso_fortran_env,only:real64,int64
  use rrtmgp37_netcdf
  use rrtmgp37_coefficients
  implicit none
  type(coefficient_table),allocatable :: table
  character(512) :: msg,path,base
  character(32),parameter :: cases(*)=[character(32)::'missing','negative','nan','pressure','bandgap', &
    'fractional','flag','minor_bounds','rayleigh','longname','rank','default_fill','explicit_fill','missing_attr']
  real(real64),allocatable :: a(:,:),b(:,:,:,:),one(:)
  character(32),allocatable :: gas(:)
  real(real64) :: scalar,sig
  integer(int64) :: dims(4)
  integer :: rank,xtype,j,g,m,p,t,ncheck=0
  call get_command_argument(1,base)
  path=trim(base)//'/lw.nc'
  call nc_info(trim(path),'kmajor',rank,dims,xtype,msg)
  call check(msg==''.and.rank==4.and.all(dims==[4,2,3,3]),'dimension reversal')
  call nc_read(trim(path),'kmajor',[4,2,3,3],b,msg)
  call check(msg=='','read real rank4')
  do t=1,3
   do p=1,3
    do m=1,2
     do g=1,4
      call check(abs(b(g,m,p,t)-(1.+g-1+10*(m-1)+100*(p-1)+1000*(t-1)))<1.e-12_real64,'C/Fortran axis identity')
     end do
    end do
   end do
  end do
  call nc_read(trim(path),'bnd_limits_wavenumber',[2,2],a,msg)
  call check(msg==''.and.abs(a(2,1)-500._real64)<1.e-12_real64,'rank2')
  call nc_read(trim(path),'temp_ref',[3],one,msg)
  call check(msg==''.and.abs(one(2)-250._real64)<1.e-12_real64,'rank1')
  scalar=-777.
  call nc_read(trim(path),'absorption_coefficient_ref_P',scalar,msg)
  call check(msg==''.and.abs(scalar-101325._real64)<1.e-12_real64,'scalar')
  call nc_names(trim(path),'gas_names',2,gas,msg)
  call check(msg==''.and.gas(1)=='h2o'.and.gas(2)=='co2','name matrix padding')
  sig=sum(b)
  call nc_read(trim(path),'kmajor',[4,2,3,4],b,msg)
  call check(msg/=''.and.abs(sum(b)-sig)<1.e-12_real64,'shape failure is atomic')
  call nc_read(trim(path),'not_here',[4,2,3,3],b,msg)
  call check(msg/=''.and.abs(sum(b)-sig)<1.e-12_real64,'missing failure is atomic')
  call nc_read(trim(path),'gas_names',[40,2],a,msg)
  call check(msg/=''.and.all(shape(a)==[2,2]),'numeric string rejection is atomic')
  call nc_read(trim(path),'temp_ref',scalar,msg)
  call check(msg/=''.and.abs(scalar-101325._real64)<1.e-12_real64,'scalar rank mismatch atomic')
  call nc_names(trim(base)//'/bad_longname.nc','gas_names',2,gas,msg)
  call check(msg/=''.and.gas(1)=='h2o','reject nonblank truncation')
  call read_coefficients(trim(path),table,msg)
  if(msg/='')print *,trim(msg)
  call check(msg==''.and.allocated(table),'complete synthetic LW schema')
  call check(table%is_lw,'LW classification')
  call check(all(shape(table%kmajor)==[4,2,3,3]),'LW kmajor extents')
  sig=sum(table%kmajor)
  do j=1,size(cases)
    path=trim(base)//'/bad_'//trim(cases(j))//'.nc'
    call read_coefficients(trim(path),table,msg)
    call check(msg/='','reject bad '//trim(cases(j)))
    call check(abs(sum(table%kmajor)-sig)<1.e-12_real64.and.table%is_lw,'failed reload preserved '//trim(cases(j)))
    print '(a)', 'EXPECTED_REJECTION '//trim(cases(j))//': '//trim(msg)
  end do
  call read_coefficients(trim(base)//'/sw.nc',table,msg)
  if(msg/='')print *,trim(msg)
  call check(msg==''.and..not.table%is_lw,'complete synthetic SW schema')
  call check(abs(sum(table%solar_quiet)-1361._real64)<1.e-12_real64,'SW source load')
  do j=1,12
    call read_coefficients(trim(base)//'/lw.nc',table,msg)
    call check(msg=='','reinitialize LW')
    call read_coefficients(trim(base)//'/sw.nc',table,msg)
    call check(msg=='','reinitialize SW')
  end do
  print '(a,i0)','COEFFICIENT_IO_ASSERTIONS_PASS=',ncheck
  print '(a)','SCOPE=NETCDF_C_IO_AND_SYNTHETIC_SCHEMA_NOT_REAL_SPECTROSCOPY'
contains
  subroutine check(ok,label)
    logical,intent(in)::ok
    character(*),intent(in)::label
    if(.not.ok)then
      print *, 'FAIL: ',label
      error stop 1
    end if
    ncheck=ncheck+1
  end subroutine
end program
