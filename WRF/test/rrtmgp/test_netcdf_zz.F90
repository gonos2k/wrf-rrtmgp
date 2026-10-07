! Synthetic MPI wrapper around the actual ext_ncd backend, not WRF module_io.
program backend_zz
#ifdef USE_MPI
  use mpi
#endif
  use wrf_data
  use ext_ncd_support_routines
  implicit none
  include 'netcdf.inc'
  include 'wrf_status_codes.h'
  integer :: ierr,rank,nproc,h,status,comm,io_comm,i,j,n,mode,vid,xtype,nd,ncid,dids(4),lens(3),unlimited_id,record
  integer :: field(3,5),got(3,5),s(3),e(3),a(4),b(4),gtype,dimlen,tobits(30),fobits(15)
  integer :: xbuf(1,15),fbuf(1,3,5,1)
  real :: converted(15),rf(3,5),real_input(3,5)
  real(kind=8) :: df(3,5),double_read(3,5)
  character(256) :: filename,arg
  character(19),parameter :: dates(2)=[character(19) :: "2026-10-06_00:00:00", "2026-10-06_01:00:00"]
  character(80) :: names(4),rnames(4),dname
  character(3) :: mo
  character(1) :: stagger
  logical :: zero
  type(wrf_data_handle),pointer :: handle
  rank=0; nproc=1
#ifdef USE_MPI
  call MPI_Init(ierr)
  call MPI_Comm_rank(MPI_COMM_WORLD,rank,ierr)
  call MPI_Comm_size(MPI_COMM_WORLD,nproc,ierr)
#endif
  call expect(storage_size(field(1,1))==32.and.storage_size(real_input(1,1))==32.and. &
    storage_size(df(1,1))==64,'fixture requires INTEGER32 REAL32 DOUBLE64 storage')
  s=[1,1,1]; e=[3,5,1]
  names=''
  names(1)='vertical_k'; names(2)='independent_n'
  do j=1,5
    do i=1,3
      field(i,j)=1000*j+17*i
      df(i,j)=real(field(i,j),8)+0.5_8
      real_input(i,j)=real(field(i,j))+0.25
    enddo
  enddo
  got=-999
  comm=0;io_comm=0
  if(rank==0) then
    call check_helper_orders()
    call dim_from_memorder('ZZ',n)
    call expect(n==2,'generic uppercase rank two')
    call dim_from_memorder('zz',n)
    call expect(n==2,'generic lowercase rank two')
    call dim_from_memorder('XY',n)
    call expect(n==2,'generic horizontal rank retained')
    call dim_from_memorder('xyz',n)
    call expect(n==3,'generic spatial rank retained')
    call dim_from_memorder('qq',n)
    call expect(n==0,'generic unsupported order rejected')
    call GetDim('qq',n,status)
    call expect(status==WRF_WARN_BAD_MEMORYORDER,'unsupported qq remains rejected')
    call ext_ncd_ioinit('use_netcdf_classic',status)
    call good(status,'init')
    filename='zz.nc'
    call ext_ncd_open_for_write_begin(filename,comm,io_comm,'REAL_OUTPUT_SIZE=4',h,status)
    call good(status,'open write begin')
    call ext_ncd_write_field(h,'2026-10-06_00:00:00','INT_UPPER',field,WRF_INTEGER,comm,io_comm,0, &
      'ZZ','',names,s,e,s,e,s,e,status)
      call good(status,'define upper integer')
      call ext_ncd_write_field(h,'2026-10-06_00:00:00','INT_LOWER',field,WRF_INTEGER,comm,io_comm,0, &
        'zz','',names,s,e,s,e,s,e,status)
      call good(status,'define lower integer')
      tobits=transfer(df,tobits)
      call ext_ncd_write_field(h,'2026-10-06_00:00:00','FLOAT_LOWER',tobits,WRF_DOUBLE,comm,io_comm,0, &
        'zz','',names,s,e,s,e,s,e,status)
      call good(status,'define double converted to REAL4')
      fobits=transfer(real_input,fobits)
      call ext_ncd_write_field(h,'2026-10-06_00:00:00','FLOAT_REAL',fobits,WRF_REAL,comm,io_comm,0, &
        'ZZ','',names,s,e,s,e,s,e,status)
      call good(status,'define real')
      call ext_ncd_write_field(h,'2026-10-06_00:00:00','UNSUPPORTED',field,WRF_INTEGER,comm,io_comm,0, &
        'QQ','',names,s,e,s,e,s,e,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER,'backend rejects qq')
      call ext_ncd_open_for_write_commit(h,status)
      call good(status,'commit')
      do record=1,2
        call prepare_record(record)
        do mode=1,4
          call write_one(mode,record)
        enddo
      enddo
      call ext_ncd_ioclose(h,status)
      call good(status,'close write')
      ! Independent low-level NetCDF inquiry, not a reuse of backend helper expectations.
      call good(nf_open(filename,NF_NOWRITE,ncid),'nf open')
      call good(nf_inq_unlimdim(ncid,unlimited_id),'unlimited Time inquiry')
      do mode=1,4
        call good(nf_inq_varid(ncid,varname(mode),vid),'nf variable')
        call good(nf_inq_vartype(ncid,vid,xtype),'nf type')
        if(mode<=2) then
          call expect(xtype==NF_INT,'integer storage type')
        else
          call expect(xtype==NF_FLOAT,'float output storage type')
        endif
        call good(nf_inq_varndims(ncid,vid,nd),'nf rank')
        call expect(nd==3,'two nonspatial axes plus Time')
        call good(nf_inq_vardimid(ncid,vid,dids),'nf dimids')
        do i=1,3
          call good(nf_inq_dim(ncid,dids(i),dname,dimlen),'nf dimension')
          lens(i)=dimlen
          select case(i)
          case(1)
            call expect(trim(dname)=='vertical_k'.and.dimlen==3,'first name/length')
          case(2)
            call expect(trim(dname)=='independent_n'.and.dimlen==5,'second name/length')
          case(3)
            call expect(trim(dname)=='Time'.and.dimlen==2,'Time name/length')
            call expect(dids(i)==unlimited_id,'Time is unlimited')
          end select
        enddo
      enddo
      status=nf_inq_varid(ncid,'UNSUPPORTED',vid)
      call expect(status==NF_ENOTVAR,'no unsupported variable defined')
      call good(nf_close(ncid),'nf close')
      call ext_ncd_open_for_read(filename,comm,io_comm,'',h,status)
      call good(status,'backend reopen read')
      call GetDH(h,handle,status)
      call good(status,'direct FieldIO handle')
      call good(nf_inq_varid(handle%NCID,'INT_UPPER',vid),'direct FieldIO variable')
      a=[3,5,1,1]
      got=-999
      call FieldIO('read',h,dates(1),a,'qq',WRF_INTEGER,handle%NCID,vid,got,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER,'direct FieldIO rejects bad order before dispatch')
      call expect(all(got==-999),'direct FieldIO invalid read leaves buffer unchanged')
      do record=1,2
        call prepare_record(record)
        do mode=1,4
        a=-1;b=-1;mo='';stagger=''
        call ext_ncd_get_var_info(h,varname(mode),n,mo,stagger,a,b,gtype,status)
        call good(status,'backend var info')
        call expect(n==2.and.mo=='ZZ'.and.all(a(1:2)==[1,1]).and.all(b(1:2)==[3,5]),'backend rank/order/bounds')
        if(mode<=2) then
          call expect(gtype==WRF_INTEGER,'backend integer type')
          got=-999
          call ext_ncd_read_field(h,dates(record),varname(mode),got,WRF_INTEGER,comm,io_comm,0, &
            'ZZ','',names,s,e,s,e,s,e,status)
          call good(status,'backend read integer')
          call expect(all(got==field),'3x5 unique integers exact')
        else
          call expect(gtype==WRF_REAL,'backend float type')
          fobits=0
          call ext_ncd_read_field(h,dates(record),varname(mode),fobits,WRF_REAL,comm,io_comm,0, &
            'zz','',names,s,e,s,e,s,e,status)
          call good(status,'backend read converted float')
          rf=reshape(transfer(fobits,converted),[3,5])
          if(mode==3) then
            call expect(all(rf==real(df)),'3x5 float conversion exact')
          else
            call expect(all(rf==real_input),'3x5 real exact')
          endif
          tobits=0
          call ext_ncd_read_field(h,dates(record),varname(mode),tobits,WRF_DOUBLE,comm,io_comm,0, &
            'ZZ','',names,s,e,s,e,s,e,status)
          call good(status,'backend REAL4 read as DOUBLE')
          double_read=reshape(transfer(tobits,reshape(df,[15])),[3,5])
          call expect(all(double_read==real(rf,8)),'REAL4 to DOUBLE identity conversion')
        endif
        enddo
      enddo
      call ext_ncd_read_field(h,dates(1),'INT_UPPER',got,WRF_INTEGER,comm,io_comm,0, &
        'QQ','',names,s,e,s,e,s,e,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER,'backend rejects qq on read')
      call ext_ncd_read_field(h,dates(2),'INT_UPPER',got,WRF_INTEGER,comm,io_comm,0, &
        'zz','',names,s,e,s,e,s,e,status)
      call good(status,'valid read after invalid-order rejection')
      call expect(all(got==field),'second record retains distinct values')
      call ext_ncd_ioclose(h,status)
      call good(status,'close read')
      call set_chunking('zz',zero)
      call expect(.not.zero,'no horizontal chunking requested')
      a=[3,5,1,1]
      zero=ZeroLengthHorzDim('zz',a,status)
      call good(status,'zero horizontal helper')
      call expect(.not.zero,'no horizontal axis')
      call ExtOrder('zz',a,status)
      call good(status,'ExtOrder')
      call expect(all(a==[3,5,1,1]),'length order retained')
      call ExtOrderStr('zz',names,rnames,status)
      call good(status,'ExtOrderStr')
      call expect(all(rnames(1:2)==names(1:2)),'name order retained')
      print *, 'BACKEND_ROUNDTRIP_PASS',nproc,15,4,lens
  endif
    call prepare_record(2)
#ifdef USE_MPI
    call MPI_Bcast(got,15,MPI_INTEGER,0,MPI_COMM_WORLD,ierr)
#endif
    call expect(all(got==field),'MPI wrapper replicated integer state exact')
    print *, 'REPLICA_PASS',rank,nproc
#ifdef USE_MPI
  call MPI_Finalize(ierr)
#endif
contains
  subroutine check_helper_orders()
    ! Call the actual backend helpers directly, without upper-level I/O guards.
    ! Invalid orders fit the API's three-character MemoryOrder representation.
    character(3),parameter :: orders(20)=[character(3) :: &
      'xyz','xzy','yxz','yzx','zxy','zyx','xsz','xez','ysz','yez', &
      'xy','yx','xs','xe','ys','ye','z','c','zz','0']
    character(3),parameter :: invalid(5)=[character(3) :: 'qq','QQ','q','qxz','']
    integer :: lengths(4),before(4),expected(4),dims,m,axis
    character(80) :: input_names(4),output_names(4),expected_names(4)
    logical :: is_zero
    before=[3,5,7,11]
    input_names=[character(80) :: 'first','second','third','tail']
    do m=1,size(orders)
      expected=before
      select case(trim(orders(m)))
      case('xzy'); expected(1:3)=before([1,3,2])
      case('yxz'); expected(1:3)=before([2,1,3])
      case('yzx'); expected(1:3)=before([3,1,2])
      case('zxy'); expected(1:3)=before([2,3,1])
      case('zyx'); expected(1:3)=before([3,2,1])
      case('yx'); expected(1:2)=before([2,1])
      end select
      call GetDim(orders(m),dims,status)
      call good(status,'valid helper GetDim')
      call expect(dims==len_trim(orders(m)).or.trim(orders(m))=='0','valid helper dimension')
      if(trim(orders(m))=='0') call expect(dims==0,'scalar helper dimension')
      lengths=before
      call ExtOrder(orders(m),lengths,status)
      call good(status,'valid helper ExtOrder')
      call expect(all(lengths==expected),'valid helper permutation and tail')
      expected_names=''
      do axis=1,dims
        select case(expected(axis))
        case(3); expected_names(axis)=input_names(1)
        case(5); expected_names(axis)=input_names(2)
        case(7); expected_names(axis)=input_names(3)
        end select
      enddo
      output_names='sentinel'
      call ExtOrderStr(orders(m),input_names,output_names,status)
      call good(status,'valid helper ExtOrderStr')
      call expect(all(output_names==expected_names),'valid helper name permutation and defined tail')
      is_zero=ZeroLengthHorzDim(orders(m),before,status)
      call good(status,'valid helper ZeroLengthHorzDim')
      call expect(.not.is_zero,'positive helper horizontal lengths')
    enddo
    lengths=[0,5,7,11]
    is_zero=ZeroLengthHorzDim('xy',lengths,status)
    call good(status,'zero xy horizontal dimension')
    call expect(is_zero,'xy zero horizontal length detected')
    is_zero=ZeroLengthHorzDim('zz',lengths,status)
    call good(status,'zz is nonspatial')
    call expect(.not.is_zero,'zz is not a horizontal zero')
    do m=1,size(invalid)
      output_names='sentinel'
      call ExtOrderStr(invalid(m),input_names,output_names,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER,'invalid helper ExtOrderStr status retained')
      call expect(all(output_names==''),'invalid helper names defined blank')
      lengths=before
      call ExtOrder(invalid(m),lengths,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER,'invalid helper ExtOrder status retained')
      call expect(all(lengths==before),'invalid helper lengths unchanged')
      is_zero=ZeroLengthHorzDim(invalid(m),before,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER,'invalid helper ZeroLengthHorzDim status retained')
      call expect(is_zero,'invalid helper logical result defined')
      dims=99
      call GetDim(invalid(m),dims,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER.and.dims==0,'invalid helper GetDim dimension defined')
    enddo
    ! Rejection must not contaminate a subsequent valid call.
    lengths=before
    call ExtOrder('YX',lengths,status)
    call good(status,'valid helper after invalid order')
    call expect(all(lengths==[5,3,7,11]),'valid permutation after invalid order')
    print *, 'HELPER_ORDER_CONTRACT_PASS',size(orders),size(invalid)
  end subroutine
  subroutine good(rc,label)
    integer,intent(in)::rc
    character(*),intent(in)::label
    call expect(rc==0,label)
  end subroutine
  subroutine expect(ok,label)
    logical,intent(in)::ok
    character(*),intent(in)::label
    integer::error
    if(.not.ok) then
      write(*,*) 'FAIL ',trim(label),' status=',status,' rank=',rank
#ifdef USE_MPI
      call MPI_Abort(MPI_COMM_WORLD,71,error)
#endif
      error stop 71
    endif
  end subroutine
  function varname(m) result(name)
    integer,intent(in)::m
    character(15)::name
    select case(m)
    case(1); name='INT_UPPER'
    case(2); name='INT_LOWER'
    case(3); name='FLOAT_LOWER'
    case(4); name='FLOAT_REAL'
    end select
  end function
  subroutine prepare_record(r)
    integer,intent(in)::r
    integer::ii,jj
    do jj=1,5
      do ii=1,3
        field(ii,jj)=1000*jj+17*ii+100000*(r-1)
        df(ii,jj)=real(field(ii,jj),8)+0.5_8
        real_input(ii,jj)=real(field(ii,jj))+0.25
      enddo
    enddo
  end subroutine
  subroutine write_one(m,r)
    integer,intent(in)::m,r
    character(2)::order
    order='ZZ'
    if(m>1)order='zz'
    if(m<=2) then
      call ext_ncd_write_field(h,dates(r),varname(m),field,WRF_INTEGER,comm,io_comm,0, &
        order,'',names,s,e,s,e,s,e,status)
    elseif(m==3) then
      tobits=transfer(df,tobits)
      call ext_ncd_write_field(h,dates(r),varname(m),tobits,WRF_DOUBLE,comm,io_comm,0, &
        order,'',names,s,e,s,e,s,e,status)
    else
      fobits=transfer(real_input,fobits)
      call ext_ncd_write_field(h,dates(r),varname(m),fobits,WRF_REAL,comm,io_comm,0, &
        'ZZ','',names,s,e,s,e,s,e,status)
    endif
    call good(status,'actual field write')
  end subroutine
end program
subroutine wrf_debug(level,message)
  implicit none
  integer,intent(in)::level
  character(*),intent(in)::message
  ! The only replaced dependency is the diagnostic sink, not the backend API.
  if(index(message,'BAD MEMORY ORDER')>0) print *,trim(message)
end subroutine
