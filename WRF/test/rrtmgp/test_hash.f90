program test_hash
  use module_ra_rrtmgp_hash, only: rrtmgp_file_sha256
  implicit none
  integer :: nargs
  character(len=4096) :: path, expected

  call check_fixture(0, 0, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
  call check_fixture(3, 1, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  call check_fixture(55,0,'463eb28e72f82e0a96c0a4cc53690c571281131f672aa229e0d45ae59b598b59')
  call check_fixture(56,0,'da2ae4d6b36748f2a318f23e7ab1dfdf45acdc9d049bd80e59de82a60895f562')
  call check_fixture(63,0,'29af2686fd53374a36b0846694cc342177e428d1647515f078784d69cdb9e488')
  call check_fixture(64,0,'fdeab9acf3710362bd2658cdc9a29e8f9c757fcf9811603a8c447cd1d9151108')
  call check_fixture(65,0,'4bfd2c8b6f1eec7a2afeb48b934ee4b2694182027e6d0fc075074f2fabb31781')
  call check_fixture(8193,2,'d37426b71db09954cacd4d2be0059f5dbd7ad5d32fc42ab0eeda4ed1a4e1bebc')
  call check_missing_file()

  ! Optional external-file check lets Python's hashlib provide an independent
  ! oracle for a real NetCDF coefficient table or an arbitrary binary fixture:
  ! test_hash <path> <expected-lowercase-sha256>
  nargs = command_argument_count()
  if (nargs /= 0) then
    if (nargs /= 2) error stop 'usage: test_hash [file expected_sha256]'
    call get_command_argument(1,path)
    call get_command_argument(2,expected)
    call check_file(trim(path),trim(expected))
  end if
  print '(a)', 'test_hash: PASS'
contains
  subroutine check_fixture(n, kind, expected_digest)
    integer, intent(in) :: n, kind
    character(len=*), intent(in) :: expected_digest
    character(len=64) :: actual
    character(len=256) :: message
    character(len=40) :: filename
    character(len=:), allocatable :: bytes
    integer :: status, unit, i, value, ios
    write(filename,'("hash-fixture-",i0,".bin")') n
    allocate(character(len=n) :: bytes)
    do i = 1, n
      select case (kind)
      case (0)
        value = modulo(i-1,256)
      case (1)
        value = iachar('abc'(i:i))
      case (2)
        value = modulo((i-1)*37+11,256)
      case default
        error stop 'bad fixture kind'
      end select
      bytes(i:i) = achar(value)
    end do
    open(newunit=unit,file=trim(filename),access='stream',form='unformatted', &
         status='replace',action='write',iostat=ios)
    if (ios /= 0) error stop 'could not create hash fixture'
    if (n > 0) write(unit,iostat=ios) bytes
    if (ios /= 0) error stop 'could not write hash fixture'
    close(unit,iostat=ios)
    if (ios /= 0) error stop 'could not close hash fixture'
    call rrtmgp_file_sha256(trim(filename),actual,status,message)
    if (status /= 0) then
      print '(a)', trim(message)
      error stop 'SHA256 failed on fixture'
    end if
    if (actual /= expected_digest) then
      print '(a,i0,2a)', 'length ',n,' expected ',expected_digest
      print '(a)', 'actual   '//actual
      error stop 'SHA256 fixture mismatch'
    end if
    open(newunit=unit,file=trim(filename),status='old',iostat=ios)
    if (ios == 0) close(unit,status='delete')
  end subroutine check_fixture

  subroutine check_file(filename, expected_digest)
    character(len=*), intent(in) :: filename, expected_digest
    character(len=64) :: actual
    character(len=256) :: message
    integer :: status
    call rrtmgp_file_sha256(filename,actual,status,message)
    if (status /= 0) then
      print '(a)', trim(message)
      error stop 'SHA256 failed on external file'
    end if
    if (actual /= expected_digest) then
      print '(3a)', 'SHA256 mismatch for ',trim(filename),': '//actual
      error stop 'SHA256 external-file mismatch'
    end if
  end subroutine check_file

  subroutine check_missing_file()
    character(len=64) :: actual
    character(len=256) :: message
    integer :: status
    call rrtmgp_file_sha256('file-that-must-not-exist-rrtmgp-hash-test',actual,status,message)
    if (status == 0 .or. len_trim(message) == 0) error stop 'missing-file error was not returned'
  end subroutine check_missing_file
end program test_hash
