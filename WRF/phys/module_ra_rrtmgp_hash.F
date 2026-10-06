! SHA-256 as specified by NIST FIPS 180-4 (2015), section 6.2.
! This provides an artifact checksum only; it is not an authentication primitive.
module module_ra_rrtmgp_hash
  use iso_fortran_env, only: int64
  implicit none
  private
  public :: rrtmgp_file_sha256

  integer(int64), parameter :: mask32 = int(z'FFFFFFFF', int64)
  integer(int64), parameter :: mod32 = int(z'100000000', int64)
  integer(int64), parameter :: k(0:63) = [ &
    int(z'428A2F98',int64), int(z'71374491',int64), int(z'B5C0FBCF',int64), int(z'E9B5DBA5',int64), &
    int(z'3956C25B',int64), int(z'59F111F1',int64), int(z'923F82A4',int64), int(z'AB1C5ED5',int64), &
    int(z'D807AA98',int64), int(z'12835B01',int64), int(z'243185BE',int64), int(z'550C7DC3',int64), &
    int(z'72BE5D74',int64), int(z'80DEB1FE',int64), int(z'9BDC06A7',int64), int(z'C19BF174',int64), &
    int(z'E49B69C1',int64), int(z'EFBE4786',int64), int(z'0FC19DC6',int64), int(z'240CA1CC',int64), &
    int(z'2DE92C6F',int64), int(z'4A7484AA',int64), int(z'5CB0A9DC',int64), int(z'76F988DA',int64), &
    int(z'983E5152',int64), int(z'A831C66D',int64), int(z'B00327C8',int64), int(z'BF597FC7',int64), &
    int(z'C6E00BF3',int64), int(z'D5A79147',int64), int(z'06CA6351',int64), int(z'14292967',int64), &
    int(z'27B70A85',int64), int(z'2E1B2138',int64), int(z'4D2C6DFC',int64), int(z'53380D13',int64), &
    int(z'650A7354',int64), int(z'766A0ABB',int64), int(z'81C2C92E',int64), int(z'92722C85',int64), &
    int(z'A2BFE8A1',int64), int(z'A81A664B',int64), int(z'C24B8B70',int64), int(z'C76C51A3',int64), &
    int(z'D192E819',int64), int(z'D6990624',int64), int(z'F40E3585',int64), int(z'106AA070',int64), &
    int(z'19A4C116',int64), int(z'1E376C08',int64), int(z'2748774C',int64), int(z'34B0BCB5',int64), &
    int(z'391C0CB3',int64), int(z'4ED8AA4A',int64), int(z'5B9CCA4F',int64), int(z'682E6FF3',int64), &
    int(z'748F82EE',int64), int(z'78A5636F',int64), int(z'84C87814',int64), int(z'8CC70208',int64), &
    int(z'90BEFFFA',int64), int(z'A4506CEB',int64), int(z'BEF9A3F7',int64), int(z'C67178F2',int64) ]

contains

  subroutine rrtmgp_file_sha256(filename, digest, status, message)
    character(len=*), intent(in) :: filename
    character(len=64), intent(out) :: digest
    integer, intent(out) :: status
    character(len=*), intent(out) :: message
    integer(int64) :: h(0:7), block(0:63), file_size, position
    integer :: unit, ios, nread, j, nblock, close_status
    character(len=:), allocatable :: chunk
    character(len=16), parameter :: hex = '0123456789abcdef'
    integer(int64) :: bit_hi, bit_lo

    digest = repeat('0',64)
    message = ''
    status = 0
    open(newunit=unit, file=filename, access='stream', form='unformatted', &
         status='old', action='read', iostat=ios)
    if (ios /= 0) then
      call set_error(ios, 'open failed for '//trim(filename), status, message)
      return
    end if
    inquire(unit=unit, size=file_size, iostat=ios)
    if (ios /= 0 .or. file_size < 0_int64) then
      if (ios == 0) ios = 1
      call set_error(ios, 'size inquiry failed for '//trim(filename), status, message)
      close(unit, iostat=close_status)
      return
    end if

    h = [ int(z'6A09E667',int64), int(z'BB67AE85',int64), &
          int(z'3C6EF372',int64), int(z'A54FF53A',int64), &
          int(z'510E527F',int64), int(z'9B05688C',int64), &
          int(z'1F83D9AB',int64), int(z'5BE0CD19',int64) ]
    block = 0_int64
    nblock = 0
    position = 1_int64
    do while (position <= file_size)
      nread = int(min(4096_int64, file_size-position+1_int64))
      allocate(character(len=nread) :: chunk)
      read(unit, pos=position, iostat=ios) chunk
      if (ios /= 0) then
        call set_error(ios, 'read failed for '//trim(filename), status, message)
        deallocate(chunk)
        close(unit, iostat=close_status)
        return
      end if
      do j = 1, nread
        block(nblock) = int(iachar(chunk(j:j)),int64)
        nblock = nblock + 1
        if (nblock == 64) then
          call compress(block,h)
          nblock = 0
        end if
      end do
      deallocate(chunk)
      position = position + int(nread,int64)
    end do
    close(unit, iostat=ios)
    if (ios /= 0) then
      call set_error(ios, 'close failed for '//trim(filename), status, message)
      return
    end if

    ! Append the mandatory one bit, then zeros and the 64-bit message length.
    block(nblock) = int(z'80',int64)
    nblock = nblock + 1
    if (nblock > 56) then
      block(nblock:63) = 0_int64
      call compress(block,h)
      block = 0_int64
      nblock = 0
    end if
    block(nblock:55) = 0_int64
    ! Express the bit length as two unsigned 32-bit words without overflowing
    ! signed int64 when converting a large byte count to bits.
    bit_hi = modulo(file_size / 536870912_int64, mod32)
    bit_lo = modulo(modulo(file_size,536870912_int64) * 8_int64, mod32)
    do j = 0, 3
      block(56+j) = iand(ishft(bit_hi,-8*(3-j)), int(z'FF',int64))
      block(60+j) = iand(ishft(bit_lo,-8*(3-j)), int(z'FF',int64))
    end do
    call compress(block,h)

    do j = 0, 7
      call word_hex(h(j), digest(8*j+1:8*j+8), hex)
    end do
  end subroutine rrtmgp_file_sha256

  subroutine set_error(code, text, status, message)
    integer, intent(in) :: code
    character(len=*), intent(in) :: text
    integer, intent(out) :: status
    character(len=*), intent(out) :: message
    status = code
    message = text
  end subroutine set_error

  pure integer(int64) function rotr32(x,n)
    integer(int64), intent(in) :: x
    integer, intent(in) :: n
    rotr32 = ior(ishft(x,-n), ishft(iand(x,ishft(1_int64,n)-1_int64),32-n))
  end function rotr32

  pure integer(int64) function big_sigma0(x)
    integer(int64), intent(in) :: x
    big_sigma0 = ieor(ieor(rotr32(x,2),rotr32(x,13)),rotr32(x,22))
  end function big_sigma0

  pure integer(int64) function big_sigma1(x)
    integer(int64), intent(in) :: x
    big_sigma1 = ieor(ieor(rotr32(x,6),rotr32(x,11)),rotr32(x,25))
  end function big_sigma1

  pure integer(int64) function small_sigma0(x)
    integer(int64), intent(in) :: x
    small_sigma0 = ieor(ieor(rotr32(x,7),rotr32(x,18)),ishft(x,-3))
  end function small_sigma0

  pure integer(int64) function small_sigma1(x)
    integer(int64), intent(in) :: x
    small_sigma1 = ieor(ieor(rotr32(x,17),rotr32(x,19)),ishft(x,-10))
  end function small_sigma1

  pure subroutine compress(block,h)
    integer(int64), intent(in) :: block(0:63)
    integer(int64), intent(inout) :: h(0:7)
    integer(int64) :: w(0:63), a,b,c,d,e,f,g,hh,t1,t2,ch,maj
    integer :: i
    do i = 0, 15
      w(i) = ior(ior(ishft(block(4*i),24),ishft(block(4*i+1),16)), &
                 ior(ishft(block(4*i+2),8),block(4*i+3)))
    end do
    do i = 16, 63
      w(i) = modulo(small_sigma1(w(i-2)) + w(i-7) + small_sigma0(w(i-15)) + w(i-16),mod32)
    end do
    a=h(0); b=h(1); c=h(2); d=h(3); e=h(4); f=h(5); g=h(6); hh=h(7)
    do i = 0, 63
      ch = ieor(iand(e,f),iand(ieor(e,mask32),g))
      maj = ieor(ieor(iand(a,b),iand(a,c)),iand(b,c))
      t1 = modulo(hh + big_sigma1(e) + ch + k(i) + w(i),mod32)
      t2 = modulo(big_sigma0(a) + maj,mod32)
      hh=g; g=f; f=e; e=modulo(d+t1,mod32); d=c; c=b; b=a; a=modulo(t1+t2,mod32)
    end do
    h(0)=modulo(h(0)+a,mod32); h(1)=modulo(h(1)+b,mod32)
    h(2)=modulo(h(2)+c,mod32); h(3)=modulo(h(3)+d,mod32)
    h(4)=modulo(h(4)+e,mod32); h(5)=modulo(h(5)+f,mod32)
    h(6)=modulo(h(6)+g,mod32); h(7)=modulo(h(7)+hh,mod32)
  end subroutine compress

  pure subroutine word_hex(word,text,hex)
    integer(int64), intent(in) :: word
    character(len=8), intent(out) :: text
    character(len=16), intent(in) :: hex
    integer :: n, nibble
    do n = 0, 7
      nibble = int(ibits(word,28-4*n,4))
      text(n+1:n+1) = hex(nibble+1:nibble+1)
    end do
  end subroutine word_hex
end module module_ra_rrtmgp_hash
