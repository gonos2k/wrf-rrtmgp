! NetCDF-C initialization bridge. No global state; errors do not STOP the host.
module rrtmgp37_netcdf
  use iso_c_binding
  use iso_fortran_env, only: real64
  implicit none
  private
  public :: nc_info, nc_read, nc_names
  interface
    integer(c_int) function c_info(path,var,rank,dims,xtype,msg,cap) bind(C,name="gp37_nc_info")
      import
      character(c_char),intent(in) :: path(*),var(*)
      integer(c_int),intent(out) :: rank,xtype
      integer(c_int64_t),intent(out) :: dims(4)
      character(c_char),intent(out) :: msg(*)
      integer(c_size_t),value :: cap
    end function
    integer(c_int) function c_read(path,var,rank,dims,out,n,msg,cap) bind(C,name="gp37_nc_read_f64")
      import
      character(c_char),intent(in) :: path(*),var(*)
      integer(c_int),value :: rank
      integer(c_int64_t),intent(in) :: dims(*)
      real(c_double),intent(inout) :: out(*)
      integer(c_size_t),value :: n,cap
      character(c_char),intent(out) :: msg(*)
    end function
    integer(c_int) function c_names(path,var,n,width,out,msg,cap) bind(C,name="gp37_nc_read_names")
      import
      character(c_char),intent(in) :: path(*),var(*)
      integer(c_int),value :: n,width
      character(c_char),intent(inout) :: out(*)
      character(c_char),intent(out) :: msg(*)
      integer(c_size_t),value :: cap
    end function
  end interface
  interface nc_read
    module procedure read0,read1,read2,read3,read4
  end interface
contains
  subroutine copy_error(cmsg,msg)
    character(c_char),intent(in) :: cmsg(:)
    character(*),intent(out) :: msg
    integer :: i
    msg=''
    do i=1,min(size(cmsg),len(msg))
      if(cmsg(i)==c_null_char) exit
      msg(i:i)=cmsg(i)
    end do
  end subroutine
  subroutine nc_info(path,var,rank,dims,xtype,msg)
    character(*),intent(in) :: path,var
    integer,intent(out) :: rank,xtype
    integer(c_int64_t),intent(out) :: dims(4)
    character(*),intent(out) :: msg
    integer(c_int) :: r,t,rc
    character(c_char) :: cmsg(512)
    rank=-1;xtype=-1;dims=0;msg=''
    if(index(path,c_null_char)>0.or.index(var,c_null_char)>0) then
      msg='Embedded NUL in path or variable';return
    end if
    rc=c_info(trim(path)//c_null_char,trim(var)//c_null_char,r,dims,t,cmsg,512_c_size_t)
    if(rc/=0) then
      call copy_error(cmsg,msg);return
    end if
    rank=r;xtype=t
  end subroutine
  subroutine read_flat(path,var,expected,values,msg)
    character(*),intent(in) :: path,var
    integer,intent(in) :: expected(:)
    real(c_double),allocatable,intent(out) :: values(:)
    character(*),intent(out) :: msg
    integer :: rank,xtype,j,astat
    integer(c_int) :: rc
    integer(c_int64_t) :: dims(4),n
    character(c_char) :: cmsg(512)
    call nc_info(path,var,rank,dims,xtype,msg)
    if(msg/='') return
    if(rank/=size(expected)) then
      msg='NC_RANK_MISMATCH';return
    end if
    if(any(expected<0)) then
      msg='NC_NEGATIVE_EXPECTED_EXTENT';return
    end if
    if(any(dims(1:rank)/=int(expected,c_int64_t))) then
      msg='NC_SHAPE_MISMATCH';return
    end if
    n=1
    do j=1,rank
      if(dims(j)>0) then
        if(n>67108864_c_int64_t/dims(j)) then
          msg='NC_READ_EXCEEDS_MEMORY_LIMIT';return
        end if
      end if
      n=n*dims(j)
    end do
    allocate(values(n),stat=astat)
    if(astat/=0) then
      msg='NC_ALLOCATION_FAILED';return
    end if
    rc=c_read(trim(path)//c_null_char,trim(var)//c_null_char,int(rank,c_int),dims,values, &
              int(n,c_size_t),cmsg,512_c_size_t)
    if(rc/=0) then
      call copy_error(cmsg,msg);deallocate(values)
    end if
  end subroutine
  subroutine read0(path,var,value,msg)
    character(*),intent(in) :: path,var
    real(real64),intent(inout) :: value
    character(*),intent(out) :: msg
    real(c_double),allocatable :: flat(:)
    integer :: empty(0)
    call read_flat(path,var,empty,flat,msg)
    if(msg=='') value=flat(1)
  end subroutine
  subroutine read1(path,var,expected,value,msg)
    character(*),intent(in) :: path,var
    integer,intent(in) :: expected(1)
    real(real64),allocatable,intent(inout) :: value(:)
    character(*),intent(out) :: msg
    real(c_double),allocatable :: flat(:)
    real(real64),allocatable :: trial(:)
    integer :: astat
    call read_flat(path,var,expected,flat,msg)
    if(msg/='') return
    allocate(trial(expected(1)),stat=astat)
    if(astat/=0) then
      msg='NC_ALLOCATION_FAILED';return
    end if
    trial=reshape(flat,expected)
    call move_alloc(trial,value)
  end subroutine
  subroutine read2(path,var,expected,value,msg)
    character(*),intent(in) :: path,var
    integer,intent(in) :: expected(2)
    real(real64),allocatable,intent(inout) :: value(:,:)
    character(*),intent(out) :: msg
    real(c_double),allocatable :: flat(:)
    real(real64),allocatable :: trial(:,:)
    integer :: astat
    call read_flat(path,var,expected,flat,msg)
    if(msg/='') return
    allocate(trial(expected(1),expected(2)),stat=astat)
    if(astat/=0) then
      msg='NC_ALLOCATION_FAILED';return
    end if
    trial=reshape(flat,expected)
    call move_alloc(trial,value)
  end subroutine
  subroutine read3(path,var,expected,value,msg)
    character(*),intent(in) :: path,var
    integer,intent(in) :: expected(3)
    real(real64),allocatable,intent(inout) :: value(:,:,:)
    character(*),intent(out) :: msg
    real(c_double),allocatable :: flat(:)
    real(real64),allocatable :: trial(:,:,:)
    integer :: astat
    call read_flat(path,var,expected,flat,msg)
    if(msg/='') return
    allocate(trial(expected(1),expected(2),expected(3)),stat=astat)
    if(astat/=0) then
      msg='NC_ALLOCATION_FAILED';return
    end if
    trial=reshape(flat,expected)
    call move_alloc(trial,value)
  end subroutine
  subroutine read4(path,var,expected,value,msg)
    character(*),intent(in) :: path,var
    integer,intent(in) :: expected(4)
    real(real64),allocatable,intent(inout) :: value(:,:,:,:)
    character(*),intent(out) :: msg
    real(c_double),allocatable :: flat(:)
    real(real64),allocatable :: trial(:,:,:,:)
    integer :: astat
    call read_flat(path,var,expected,flat,msg)
    if(msg/='') return
    allocate(trial(expected(1),expected(2),expected(3),expected(4)),stat=astat)
    if(astat/=0) then
      msg='NC_ALLOCATION_FAILED';return
    end if
    trial=reshape(flat,expected)
    call move_alloc(trial,value)
  end subroutine
  subroutine nc_names(path,var,n,value,msg)
    character(*),intent(in) :: path,var
    integer,intent(in) :: n
    character(32),allocatable,intent(inout) :: value(:)
    character(*),intent(out) :: msg
    character(c_char),allocatable :: buffer(:)
    character(c_char) :: cmsg(512)
    character(32),allocatable :: trial(:)
    integer :: j,k,astat
    integer(c_int) :: rc
    msg=''
    if(n<0.or.n>1000000) then
      msg='NC_INVALID_NAME_COUNT';return
    end if
    if(index(path,c_null_char)>0.or.index(var,c_null_char)>0) then
      msg='Embedded NUL in path or variable';return
    end if
    allocate(buffer(32*n),trial(n),stat=astat)
    if(astat/=0) then
      msg='NC_ALLOCATION_FAILED';return
    end if
    rc=c_names(trim(path)//c_null_char,trim(var)//c_null_char,int(n,c_int),32_c_int,buffer,cmsg,512_c_size_t)
    if(rc/=0) then
      call copy_error(cmsg,msg);return
    end if
    do j=1,n
      do k=1,32
        trial(j)(k:k)=buffer((j-1)*32+k)
      end do
    end do
    call move_alloc(trial,value)
  end subroutine
end module
