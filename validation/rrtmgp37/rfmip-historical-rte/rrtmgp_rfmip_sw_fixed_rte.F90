! Private fixed-optics replay harness. Prepared but intentionally not compiled/run.
! It follows the pinned RFMIP reader and rte_sw interfaces but bypasses gas_optics:
! saved (tau,ssa,g) are injected directly into ty_optical_props_2str.
program rrtmgp_rfmip_sw_fixed_rte
  use iso_fortran_env, only: int32, int64, error_unit
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use mo_rte_kind, only: wp
  use mo_simple_netcdf, only: read_field
  use netcdf
  use mo_optical_props, only: ty_optical_props_2str
  use mo_rte_sw, only: rte_sw
  use mo_fluxes, only: ty_fluxes_broadband
  use mo_rfmip_io, only: read_size, read_and_block_pt, read_and_block_sw_bc
  implicit none
  integer, parameter :: block_size=8, expected_profiles=20
  character(len=1024) :: input_path, coeff_path, historical_coeff_path, selector_path
  character(len=1024) :: current_optics_path, historical_optics_path
  character(len=1024) :: current_source_path, historical_source_path, output_prefix
  integer :: ncol, nlay, nexp, nblocks, nbnd, ngpt, nargs
  integer :: i, j, k, b, c, arm, ios, e, s, flat, records, arglen
  integer :: ib
  integer :: u_sel, u_out_solver, u_out_written, ncid, dimid
  integer :: e_sel(expected_profiles), s_sel(expected_profiles)
  character(len=1024) :: args(9)
  integer(int64) :: file_bytes, expected_bytes
  character(len=128) :: error_msg
  character(len=2048) :: path
  type(ty_optical_props_2str) :: optics
  type(ty_fluxes_broadband) :: fluxes
  real(wp), allocatable :: p_lay(:,:,:), p_lev(:,:,:), t_lay(:,:,:), t_lev(:,:,:)
  real(wp), allocatable :: albedo(:,:), tsi(:,:), sza(:,:)
  real(wp), allocatable, target :: flux_up(:,:), flux_dn(:,:)
  real(wp), allocatable :: sfc_alb(:,:), mu0(:), source(:,:), saved_source(:,:)
  real(wp), allocatable :: toa_flux(:,:)
  real(wp), allocatable :: flux_up_written(:,:), flux_dn_written(:,:)
  real(wp), allocatable :: band_wvn(:,:), historical_band_wvn(:,:)
  integer, allocatable :: band_gpt(:,:), historical_band_gpt(:,:)
  real(wp), allocatable :: tau_rec(:,:), ssa_rec(:,:), g_rec(:,:)
  real(wp), allocatable :: tau_all(:,:,:,:), ssa_all(:,:,:,:), g_all(:,:,:,:)
  logical, allocatable :: seen(:,:), usecol(:)
  real(wp), parameter :: deg_to_rad=acos(-1._wp)/180._wp

  nargs=command_argument_count()
  if(nargs /= 9) then
    write(error_unit,*) 'usage: fixed_rte input.nc current_coeff.nc historical_coeff.nc profiles20.txt current_optics20.bin historical_optics20.bin current_source_post20.bin historical_source_post20.bin output_prefix'
    error stop 2
  endif
  do i=1,9
    call get_command_argument(i,args(i),length=arglen,status=ios)
    if(ios/=0 .or. arglen>len(args(i))) error stop 'command argument exceeds fixed path capacity'
  enddo
  input_path=args(1); coeff_path=args(2); historical_coeff_path=args(3); selector_path=args(4)
  current_optics_path=args(5); historical_optics_path=args(6)
  current_source_path=args(7); historical_source_path=args(8); output_prefix=args(9)
  if(len_trim(output_prefix)+len('_historical_written.bin')>len(path)) error stop 'output prefix too long'
  if(storage_size(0._wp)/=64 .or. storage_size(0_int32)/=32) error stop 'capture ABI is not float64/int32'

  ! Exact upstream reader path and RFMIP flattening convention from the observer.
  call read_size(trim(input_path),ncol,nlay,nexp)
  if(ncol /= 100 .or. nlay /= 60 .or. nexp /= 18) error stop 'unexpected RFMIP input dimensions'
  open(newunit=u_sel,file=trim(selector_path),status='old',action='read',iostat=ios)
  if(ios /= 0) error stop 'selector open failed'
  do i=1,expected_profiles
    read(u_sel,*,iostat=ios) e_sel(i),s_sel(i)
    if(ios /= 0) error stop 'selector must contain exactly twenty complete rows'
    if(e_sel(i)<1 .or. e_sel(i)>nexp .or. s_sel(i)<1 .or. s_sel(i)>ncol) error stop 'selector key out of range'
    if(i>1) then
      if(e_sel(i)<e_sel(i-1) .or. (e_sel(i)==e_sel(i-1) .and. s_sel(i)<=s_sel(i-1))) &
        error stop 'selector keys must be sorted and unique'
    endif
  enddo
  read(u_sel,*,iostat=ios) e
  if(ios >= 0) error stop 'selector has extra rows'
  close(u_sel)

  nblocks=(ncol*nexp)/block_size
  if(mod(ncol*nexp,block_size)/=0) error stop 'input does not divide into eight-column blocks'
  call read_and_block_pt(trim(input_path),block_size,p_lay,p_lev,t_lay,t_lev)
  call read_and_block_sw_bc(trim(input_path),block_size,albedo,tsi,sza)
  if(.not.all(ieee_is_finite(p_lay)) .or. .not.all(ieee_is_finite(p_lev)) .or. &
     .not.all(ieee_is_finite(t_lay)) .or. .not.all(ieee_is_finite(t_lev)) .or. &
     .not.all(ieee_is_finite(albedo)) .or. .not.all(ieee_is_finite(tsi)) .or. &
     .not.all(ieee_is_finite(sza))) error stop 'nonfinite RFMIP geometry/boundary input'
  call read_spectral_descriptor(trim(coeff_path),band_wvn,band_gpt)
  call read_spectral_descriptor(trim(historical_coeff_path),historical_band_wvn,historical_band_gpt)
  if(size(band_wvn,2)/=size(historical_band_wvn,2)) error stop 'current/historical band counts differ'
  if(any(band_wvn/=historical_band_wvn) .or. any(band_gpt/=historical_band_gpt)) &
    error stop 'current/historical spectral descriptors differ'
  nbnd=size(band_wvn,2); ngpt=maxval(band_gpt)
  if(ngpt /= 224) error stop 'unexpected SW g-point count'
  if(band_gpt(1,1)/=1 .or. any(band_gpt(1,:)>band_gpt(2,:)) .or. &
     any(band_gpt(1,:)<1) .or. any(band_gpt(2,:)>ngpt) .or. band_gpt(2,nbnd)/=ngpt) &
    error stop 'coefficient band g-point limits invalid'
  do ib=1,nbnd-1
    if(band_gpt(2,ib)+1/=band_gpt(1,ib+1)) error stop 'coefficient bands do not form contiguous g-point coverage'
  enddo

  allocate(tau_all(nlay,ngpt,expected_profiles,2),ssa_all(nlay,ngpt,expected_profiles,2), &
           g_all(nlay,ngpt,expected_profiles,2),source(ngpt,expected_profiles), &
           saved_source(ngpt,expected_profiles),seen(ncol,nexp))
  allocate(tau_rec(nlay,ngpt),ssa_rec(nlay,ngpt),g_rec(nlay,ngpt))
  seen=.false.
  call read_optics(trim(current_optics_path),1)
  call read_optics(trim(historical_optics_path),2)
  call read_source(trim(current_source_path),source)
  call read_source(trim(historical_source_path),saved_source)
  if(any(source /= saved_source)) error stop 'shared old-solar source_post differs between source captures'
  if(.not.all(ieee_is_finite(tau_all)) .or. .not.all(ieee_is_finite(ssa_all)) .or. &
     .not.all(ieee_is_finite(g_all)) .or. .not.all(ieee_is_finite(source))) error stop 'nonfinite captured input'
  allocate(flux_up(block_size,nlay+1),flux_dn(block_size,nlay+1), &
           flux_up_written(block_size,nlay+1),flux_dn_written(block_size,nlay+1),mu0(block_size), &
           usecol(block_size),sfc_alb(nbnd,block_size),toa_flux(block_size,ngpt))
  error_msg=optics%alloc_2str(block_size,nlay,band_wvn,band_gpt)
  if(error_msg /= '') then
    write(error_unit,*) trim(error_msg); error stop 'optical allocation failed'
  endif

  do arm=1,2
    if(arm==1) then
      path=trim(output_prefix)//'_current_solver.bin'
    else
      path=trim(output_prefix)//'_historical_solver.bin'
    endif
    open(newunit=u_out_solver,file=trim(path),status='new',access='stream',form='unformatted',action='write',iostat=ios)
    if(ios/=0) error stop 'refusing existing output or cannot create solver stream'
    if(arm==1) then
      path=trim(output_prefix)//'_current_written.bin'
    else
      path=trim(output_prefix)//'_historical_written.bin'
    endif
    open(newunit=u_out_written,file=trim(path),status='new',access='stream',form='unformatted',action='write',iostat=ios)
    if(ios/=0) error stop 'refusing existing output or cannot create masked stream'
    do i=1,expected_profiles
      flat=(e_sel(i)-1)*ncol+(s_sel(i)-1)
      b=flat/block_size+1; c=mod(flat,block_size)+1
      if(b<1 .or. b>nblocks) error stop 'profile block mapping failure'
      do j=1,block_size
      optics%tau(j,:,:)=tau_all(:,:,i,arm)
      optics%ssa(j,:,:)=ssa_all(:,:,i,arm)
      optics%g(j,:,:)=g_all(:,:,i,arm)
        usecol(j)=sza(c,b)<90._wp-2._wp*spacing(90._wp)
        mu0(j)=merge(cos(sza(c,b)*deg_to_rad),1._wp,usecol(j))
        toa_flux(j,:)=source(:,i)
        do k=1,nbnd
          sfc_alb(k,j)=albedo(c,b)
        enddo
      enddo
      error_msg=optics%validate()
      if(error_msg/='') then
        write(error_unit,*) trim(error_msg); error stop 'captured optical properties failed RTE validation'
      endif
      fluxes%flux_up=>flux_up; fluxes%flux_dn=>flux_dn
      error_msg=rte_sw(optics,p_lay(1,1,1)<p_lay(1,nlay,1),mu0,toa_flux, &
                       sfc_alb,sfc_alb,fluxes)
      if(error_msg/='') then
        write(error_unit,*) trim(error_msg); error stop 'rte_sw failed'
      endif
      if(.not.all(ieee_is_finite(flux_up)) .or. .not.all(ieee_is_finite(flux_dn))) &
        error stop 'nonfinite RTE output'
      ! Eight identical columns expose any column-order or hidden state coupling.
      do j=2,block_size
        if(any(flux_up(j,:) /= flux_up(1,:)) .or. any(flux_dn(j,:) /= flux_dn(1,:))) &
          error stop 'cloned-column RTE outputs differ'
      enddo
      write(u_out_solver) int(e_sel(i),int32),int(s_sel(i),int32)
      write(u_out_solver) flux_up(1,:)
      write(u_out_solver) flux_dn(1,:)
      flux_up_written=flux_up; flux_dn_written=flux_dn
      if(.not.usecol(1)) then
        flux_up_written=0._wp; flux_dn_written=0._wp
      endif
      write(u_out_written) int(e_sel(i),int32),int(s_sel(i),int32)
      write(u_out_written) flux_up_written(1,:)
      write(u_out_written) flux_dn_written(1,:)
    enddo
    close(u_out_solver); close(u_out_written)
  enddo

contains
  subroutine read_spectral_descriptor(filename,wvn,gpt)
    character(len=*),intent(in)::filename
    real(wp),allocatable,intent(out)::wvn(:,:)
    integer,allocatable,intent(out)::gpt(:,:)
    integer::status,n_bands
    status=nf90_open(trim(filename),NF90_NOWRITE,ncid)
    if(status/=NF90_NOERR) error stop 'coefficient metadata file open failed'
    status=nf90_inq_dimid(ncid,'bnd',dimid)
    if(status/=NF90_NOERR) error stop 'coefficient file missing bnd dimension'
    status=nf90_inquire_dimension(ncid,dimid,len=n_bands)
    if(status/=NF90_NOERR .or. n_bands<1) error stop 'coefficient bnd dimension invalid'
    allocate(wvn(2,n_bands),gpt(2,n_bands))
    wvn=read_field(ncid,'bnd_limits_wavenumber',2,n_bands)
    gpt=int(read_field(ncid,'bnd_limits_gpt',2,n_bands))
    status=nf90_close(ncid)
    if(status/=NF90_NOERR) error stop 'coefficient metadata close failed'
  end subroutine read_spectral_descriptor

  subroutine read_optics(filename,which)
    character(len=*),intent(in)::filename
    integer,intent(in)::which
    integer::u,io,ke,ks,q,idx
    logical::roster(ncol,nexp)
    inquire(file=filename,size=file_bytes,iostat=io)
    if(io/=0) error stop 'cannot stat optics capture'
    expected_bytes=int(expected_profiles,int64)*(2_int64*4_int64+ &
      3_int64*int(nlay,int64)*int(ngpt,int64)*8_int64)
    if(file_bytes/=expected_bytes) error stop 'optics capture byte length does not match strict twenty-record schema'
    open(newunit=u,file=filename,status='old',access='stream',form='unformatted',action='read',iostat=io)
    if(io/=0) error stop 'optics capture open failed'
    records=0; roster=.false.; seen=.false.
    do
      read(u,iostat=io) ke,ks
      if(io<0) exit
      if(io/=0) error stop 'partial optics key/truncated stream'
      if(ke<1 .or. ke>nexp .or. ks<1 .or. ks>ncol) error stop 'optics key out of range'
      if(roster(ks,ke)) error stop 'duplicate optics key in capture stream'
      roster(ks,ke)=.true.
      records=records+1; idx=0
      do q=1,expected_profiles
        if(e_sel(q)==ke .and. s_sel(q)==ks) idx=q
      enddo
      if(idx==0) error stop 'unexpected key in twenty-profile optics subset'
      if(idx/=records) error stop 'optics subset record order differs from selector'
      read(u,iostat=io) tau_rec
      if(io/=0) error stop 'truncated tau record'
      read(u,iostat=io) ssa_rec
      if(io/=0) error stop 'truncated ssa record'
      read(u,iostat=io) g_rec
      if(io/=0) error stop 'truncated g record'
      if(.not.all(ieee_is_finite(tau_rec)) .or. .not.all(ieee_is_finite(ssa_rec)) .or. &
         .not.all(ieee_is_finite(g_rec))) error stop 'nonfinite optics capture record'
      if(seen(ks,ke)) error stop 'duplicate requested optics key'
      seen(ks,ke)=.true.
      tau_all(:,:,idx,which)=tau_rec; ssa_all(:,:,idx,which)=ssa_rec; g_all(:,:,idx,which)=g_rec
    enddo
    close(u)
    if(records/=expected_profiles) error stop 'capture subset must contain exactly the frozen twenty-profile roster'
    if(which==1) then
      do q=1,expected_profiles
        if(.not.seen(s_sel(q),e_sel(q))) error stop 'requested profile absent from current optics capture'
      enddo
    else
      do q=1,expected_profiles
        if(.not.seen(s_sel(q),e_sel(q))) error stop 'requested profile absent from historical optics capture'
      enddo
    endif
  end subroutine read_optics

  subroutine read_source(filename,values)
    character(len=*),intent(in)::filename
    real(wp),intent(out)::values(:,:)
    integer::u,io,ke,ks,q,idx,n
    logical,allocatable::got(:)
    logical::roster(ncol,nexp)
    inquire(file=filename,size=file_bytes,iostat=io)
    if(io/=0) error stop 'cannot stat source capture'
    expected_bytes=int(expected_profiles,int64)*(2_int64*4_int64+int(ngpt,int64)*8_int64)
    if(file_bytes/=expected_bytes) error stop 'source capture byte length does not match strict twenty-record schema'
    allocate(got(expected_profiles)); got=.false.; n=0; roster=.false.
    open(newunit=u,file=filename,status='old',access='stream',form='unformatted',action='read',iostat=io)
    if(io/=0) error stop 'source capture open failed'
    do
      read(u,iostat=io) ke,ks
      if(io<0) exit
      if(io/=0) error stop 'partial source key/truncated stream'
      if(ke<1 .or. ke>nexp .or. ks<1 .or. ks>ncol) error stop 'source key out of range'
      if(roster(ks,ke)) error stop 'duplicate source key in capture stream'
      roster(ks,ke)=.true.
      n=n+1; idx=0
      do q=1,expected_profiles
        if(e_sel(q)==ke .and. s_sel(q)==ks) idx=q
      enddo
      if(idx==0) error stop 'unexpected key in twenty-profile source subset'
      if(idx/=n) error stop 'source subset record order differs from selector'
      if(got(idx)) error stop 'duplicate requested source key'
      read(u,iostat=io) values(:,idx)
      if(io/=0) error stop 'truncated selected source record'
      got(idx)=.true.
    enddo
    close(u)
    if(n/=expected_profiles .or. .not.all(got)) error stop 'source subset roster incomplete'
  end subroutine read_source
end program rrtmgp_rfmip_sw_fixed_rte
