program netcdf_probe
  use netcdf
  implicit none
  integer :: fid, did, vid, status
  real(8) :: values(3) = [1.25d0, -2.5d0, 3.75d0], got(3)
  call check(nf90_create('probe.nc', ior(nf90_clobber,nf90_netcdf4), fid))
  call check(nf90_def_dim(fid, 'x', 3, did))
  call check(nf90_def_var(fid, 'x', nf90_double, [did], vid))
  call check(nf90_enddef(fid))
  call check(nf90_put_var(fid, vid, values))
  call check(nf90_close(fid))
  call check(nf90_open('probe.nc', nf90_nowrite, fid))
  call check(nf90_inq_varid(fid, 'x', vid))
  call check(nf90_get_var(fid, vid, got))
  call check(nf90_close(fid))
  if (any(got /= values)) error stop 'round trip mismatch'
  print *, 'NETCDF_USE_CREATE_READ_PASS ', trim(nf90_inq_libvers())
contains
  subroutine check(code)
    integer, intent(in) :: code
    if (code /= nf90_noerr) then
      print *, trim(nf90_strerror(code))
      error stop 1
    end if
  end subroutine
end program
