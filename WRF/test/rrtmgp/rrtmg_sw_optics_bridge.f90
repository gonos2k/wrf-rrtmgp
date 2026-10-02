! Diagnostic bridge to the actual WRF RRTMG cloud optics, not a new radiation
! scheme. Input paths are already in-cloud g/m2; input ice size is the Fu
! generalized effective size in micrometres, supplied explicitly by the caller.
! Cloud occurrence and gas optics remain controlled by the independent replay.
program rrtmg_sw_optics_bridge
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use parkind, only: rb => kind_rb
  use parrrsw, only: ngptsw, nbndsw, jpb1
  use rrsw_wvn, only: ngb, wavenum1, wavenum2
  use rrtmg_sw_init, only: swdatinit, swcmbdat, swcldpr
  use rrtmg_sw_cldprmc, only: cldprmc_sw
  use module_ra_rrtmg_lw, only: reicalc
  implicit none
  character(1024) :: input_path, output_path
  character(80) :: magic
  integer :: unit_in, unit_out, nl, iceflag, radius_mode, k, b, gb, gp, ios
  real(rb), allocatable :: mask(:,:), iwp(:,:), lwp(:,:), swp(:,:)
  real(rb), allocatable :: ri(:), rl(:), rs(:), tau(:,:), ssa(:,:), asym(:,:), original(:,:), forward(:,:)
  integer :: map(nbndsw)
  real(rb), allocatable :: temperature(:,:), host_radius(:,:)
  real(rb) :: limits(2,nbndsw), row(7)
  if (command_argument_count() /= 2) error stop 'usage: rrtmg_sw_optics_bridge input output'
  call get_command_argument(1,input_path)
  call get_command_argument(2,output_path)
  open(newunit=unit_in,file=trim(input_path),status='old',action='read')
  read(unit_in,'(a)') magic
  if (trim(magic) /= 'WRF_RRTMG_SW_CLOUD_INPUT_V1') error stop 'invalid cloud input magic'
  read(unit_in,*) nl,iceflag,radius_mode
  if (nl < 1 .or. iceflag < 3 .or. iceflag > 5) error stop 'invalid nl/iceflag'
  if (radius_mode<0 .or. radius_mode>1) error stop 'invalid radius mode'
  allocate(mask(ngptsw,nl),iwp(ngptsw,nl),lwp(ngptsw,nl),swp(ngptsw,nl))
  allocate(ri(nl),rl(nl),rs(nl),tau(ngptsw,nl),ssa(ngptsw,nl),asym(ngptsw,nl))
  allocate(original(ngptsw,nl),forward(ngptsw,nl))
  allocate(temperature(1,nl),host_radius(1,nl))
  do k=1,nl
    read(unit_in,*,iostat=ios) row
    if (ios /= 0 .or. any(.not.ieee_is_finite(row))) error stop 'invalid cloud input row'
    if (any(row(1:3)<0._rb)) error stop 'negative water path'
    if (row(4)<1.5_rb .or. row(4)>60._rb) error stop 'liquid size out of range'
    if (row(5)<5._rb .or. row(5)>140._rb) error stop 'ice Fu size out of range'
    if (row(3)>0._rb .and. iceflag/=5) error stop 'snow requires iceflag5'
    if (row(3)>0._rb .and. (row(6)<5._rb .or. row(6)>140._rb)) error stop 'snow Fu size out of range'
    lwp(:,k)=row(1); iwp(:,k)=row(2); swp(:,k)=row(3)
    rl(k)=row(4); ri(k)=row(5); rs(k)=row(6)
    temperature(1,k)=row(7)
  end do
  close(unit_in)
  if (radius_mode==1) then
    call reicalc(1,1,nl,temperature,host_radius)
    ri=min(140._rb,host_radius(1,:)*1.0315_rb)
  end if
  ! These are the exact WRF cloud initialization procedures. Gas absorption
  ! tables and their reduction are unnecessary for this optical-only bridge.
  call swdatinit(1004.5_rb)
  call swcmbdat()
  call swcldpr()
  mask=1._rb; tau=0._rb; ssa=1._rb; asym=0._rb; forward=0._rb
  call cldprmc_sw(nl,2,iceflag,1,mask,iwp,lwp,swp,ri,rl,rs,original,tau,ssa,asym,forward)
  if (any(.not.ieee_is_finite(tau)) .or. any(.not.ieee_is_finite(ssa)) .or. &
      any(.not.ieee_is_finite(asym))) error stop 'nonfinite RRTMG cloud optics'
  if (any(tau<0._rb) .or. any(ssa<0._rb) .or. any(ssa>1._rb) .or. &
      any(abs(asym)>1._rb)) error stop 'invalid RRTMG cloud optics'
  ! RRTMG places 820--2600 last. RRTMGP uses ascending band wavenumbers.
  map(1)=nbndsw
  do b=2,nbndsw
    map(b)=b-1
  end do
  do b=1,nbndsw
    gb=map(b)+jpb1-1
    limits(:,b)=[wavenum1(gb),wavenum2(gb)]
    gp=findloc(ngb,gb,dim=1)
    if (gp==0) error stop 'RRTMG band has no gpoint'
    do k=1,nl
      if (any(abs(pack(tau(:,k),ngb==gb)-tau(gp,k))>1.e-6_rb) .or. &
          any(abs(pack(ssa(:,k),ngb==gb)-ssa(gp,k))>1.e-6_rb) .or. &
          any(abs(pack(asym(:,k),ngb==gb)-asym(gp,k))>1.e-6_rb)) &
          error stop 'RRTMG cloud optics not constant within band'
    end do
  end do
  open(newunit=unit_out,file=trim(output_path),status='replace',action='write')
  write(unit_out,'(a)') 'WRF_SW_OPTICS_OVERRIDE_V1'
  write(unit_out,*) 1,nl,nbndsw
  write(unit_out,'(a,2i8)') 'BAND_LIMITS ',2,nbndsw
  write(unit_out,'(es25.16e3)') limits
  call write_optics('TAU',tau)
  call write_optics('SSA',ssa)
  call write_optics('ASYM',asym)
  close(unit_out)
contains
  subroutine write_optics(label,values)
    character(*),intent(in) :: label
    real(rb),intent(in) :: values(ngptsw,nl)
    integer :: band,point,layer
    write(unit_out,'(a,3i8)') trim(label)//' ',1,nl,nbndsw
    do band=1,nbndsw
      point=findloc(ngb,map(band)+jpb1-1,dim=1)
      do layer=1,nl
        write(unit_out,'(es25.16e3)') values(point,layer)
      end do
    end do
  end subroutine write_optics
end program rrtmg_sw_optics_bridge
