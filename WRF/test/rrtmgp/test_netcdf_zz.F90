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
    call check_long_orders()
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
    call check_write_preflight()
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
      call check_varinfo_buffers()
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
            ' zz ','',names,s,e,s,e,s,e,status)
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
      call check_varinfo_attributes()
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
  subroutine check_long_orders()
    character(8),parameter :: invalid_long(5)=[character(8) :: 'xyzq','zzq','xyz q',' zz','']
    character(8) :: padded
    character(3) :: canonical
    integer :: m,dims,lengths(4),before(4)
    character(80) :: input_names(4),output_names(4)
    logical :: is_zero
    padded='zz';before=[3,5,7,11];input_names='axis'
    call GetDim(padded,dims,status)
    call good(status,'padded GetDim');call expect(dims==2,'padded rank')
    call LowerCase('ZZ      ',canonical);call expect(canonical=='zz','padded LowerCase')
    call UpperCase('zz      ',canonical);call expect(canonical=='ZZ','padded UpperCase')
    call LowerCase('xyzq',canonical);call expect(canonical=='','LowerCase no suffix truncation')
    call UpperCase('xyzq',canonical);call expect(canonical=='','UpperCase no suffix truncation')
    call reorder(padded,canonical);call expect(canonical=='ZZ','padded reorder')
    call reorder('xyzq',canonical);call expect(canonical=='','long reorder safely blank')
    call reorder('xxx',canonical);call expect(canonical=='','invalid token reorder safely blank')
    lengths=before;call ExtOrder(padded,lengths,status)
    call good(status,'padded ExtOrder');call expect(all(lengths==before),'padded order unchanged')
    call ExtOrderStr(padded,input_names,output_names,status);call good(status,'padded ExtOrderStr')
    is_zero=ZeroLengthHorzDim(padded,before,status);call good(status,'padded ZeroLengthHorzDim')
    do m=1,size(invalid_long)
      call GetDim(invalid_long(m),dims,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER.and.dims==0,'invalid long GetDim')
      lengths=before;call ExtOrder(invalid_long(m),lengths,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER.and.all(lengths==before),'invalid long ExtOrder')
      call ExtOrderStr(invalid_long(m),input_names,output_names,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER.and.all(output_names==''),'invalid long ExtOrderStr')
      is_zero=ZeroLengthHorzDim(invalid_long(m),before,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER.and.is_zero,'invalid long ZeroLengthHorzDim')
    enddo
    print *, 'LONG_ORDER_CONTRACT_PASS'
  end subroutine

  subroutine check_write_preflight()
    integer :: bad,follow,local_h,local_vid,td,tl,ft,expected_status,counts(4),starts(4),saved(3,5)
    character(8) :: bad_order
    character(19) :: saved_times(2),next_date,actual_date
    character(30) :: path
    type(wrf_data_handle),pointer :: dh
    ! Twelve independent files exercise same-time and next-time recovery.
    do follow=1,2
      do bad=1,6
        write(path,'(A,I1,A,I1,A)') 'preflight-',bad,'-',follow,'.nc'
        call ext_ncd_open_for_write_begin(trim(path),comm,io_comm,'REAL_OUTPUT_SIZE=4',local_h,status)
        call good(status,'preflight open')
        call ext_ncd_write_field(local_h,dates(1),'FIELD',field,WRF_INTEGER,comm,io_comm,0, &
          'ZZ','',names,s,e,s,e,s,e,status);call good(status,'preflight define')
        call ext_ncd_open_for_write_commit(local_h,status);call good(status,'preflight commit')
        call ext_ncd_write_field(local_h,dates(1),'FIELD',field,WRF_INTEGER,comm,io_comm,0, &
          'ZZ','',names,s,e,s,e,s,e,status);call good(status,'preflight first write')
        call GetDH(local_h,dh,status);call good(status,'preflight handle')
        call good(nf_inq_varid(dh%NCID,'FIELD',local_vid),'preflight varid')
        call good(nf_inq_unlimdim(dh%NCID,td),'preflight Time id')
        call good(nf_inq_dimlen(dh%NCID,td,tl),'preflight initial Time length')
        call expect(tl==1.and.dh%TimeIndex==1,'first record identity')
        saved_times=dh%Times(1:2);saved=field
        bad_order='ZZ';ft=WRF_INTEGER;counts=[3,5,1,1];expected_status=WRF_WARN_BAD_MEMORYORDER
        select case(bad)
        case(1);bad_order='qq'
        case(2);bad_order='xyzq'
        case(3);ft=-999;expected_status=WRF_WARN_DATA_TYPE_NOT_FOUND
        case(4);counts(1)=0;expected_status=WRF_WARN_LENGTH_LESS_THAN_1
        case(5);counts(2)=-1;expected_status=WRF_WARN_LENGTH_LESS_THAN_1
        case(6);bad_order='zzq'
        end select
        call FieldIO('write',local_h,dates(2),counts,bad_order,ft,dh%NCID,local_vid,field,status)
        call expect(status==expected_status,'direct invalid write status')
        call expect(dh%TimeIndex==1.and.all(dh%Times(1:2)==saved_times),'direct invalid write memory Times unchanged')
        call good(nf_inq_dimlen(dh%NCID,td,tl),'rejected write Time length')
        call expect(tl==1.and.all(field==saved),'rejected write file length and buffer unchanged')
        ! Public entry points reject nonblank suffixes before truncation.
        call ext_ncd_write_field(local_h,dates(2),'FIELD',field,WRF_INTEGER,comm,io_comm,0, &
          ' xyzq ','',names,s,e,s,e,s,e,status)
        call expect(status==WRF_WARN_BAD_MEMORYORDER,'public write suffix rejected')
        call expect(dh%TimeIndex==1.and.all(dh%Times(1:2)==saved_times),'public rejection Times unchanged')
        counts=[3,5,1,1];starts=1
        call good(nf_get_vara_int(dh%NCID,local_vid,starts,counts,got),'read existing record after errors')
        call expect(all(got==saved),'existing field preserved')
        next_date=dates(2)
        if(follow==2)next_date='2026-10-06_02:00:00'
        call ext_ncd_write_field(local_h,next_date,'FIELD',field,WRF_INTEGER,comm,io_comm,0, &
          ' ZZ ','',names,s,e,s,e,s,e,status);call good(status,'normal write after rejection')
        call good(nf_inq_dimlen(dh%NCID,td,tl),'recovery Time length')
        call expect(tl==2.and.dh%TimeIndex==2,'no rejected intermediate time record')
        call good(nf_get_vara_text(dh%NCID,dh%TimesVarID,[1,2],[19,1],actual_date),'recovery Times value')
        call expect(actual_date==next_date,'actual recovery date stored')
        starts=[1,1,2,1]
        call good(nf_get_vara_int(dh%NCID,local_vid,starts,counts,got),'recovery field values')
        call expect(all(got==saved),'recovery field exact')
        call ext_ncd_ioclose(local_h,status);call good(status,'preflight close')
      enddo
    enddo
    print *, 'WRITE_PREFLIGHT_CONTRACT_PASS',12
  end subroutine

  subroutine check_varinfo_attributes()
    integer :: local_h,id,file_id,m,dims,local_type,lo(4),hi(4)
    character(30) :: path
    character(8) :: out_order
    character(4) :: bad_attr
    do m=1,3
      write(path,'(A,I1,A)')'bad-order-attribute-',m,'.nc'
      call ext_ncd_open_for_write_begin(trim(path),comm,io_comm,'REAL_OUTPUT_SIZE=4',local_h,status)
      call good(status,'attribute fixture open')
      call ext_ncd_write_field(local_h,dates(1),'FIELD',field,WRF_INTEGER,comm,io_comm,0, &
        'ZZ','',names,s,e,s,e,s,e,status);call good(status,'attribute define')
      call ext_ncd_open_for_write_commit(local_h,status);call good(status,'attribute commit')
      call ext_ncd_ioclose(local_h,status);call good(status,'attribute close')
      call good(nf_open(trim(path),NF_WRITE,file_id),'attribute nf open')
      call good(nf_inq_varid(file_id,'FIELD',id),'attribute varid')
      call good(nf_redef(file_id),'attribute redefine')
      bad_attr='xyzq'
      if(m==2)bad_attr='qq'
      if(m==3)bad_attr=''
      call good(nf_put_att_text(file_id,id,'MemoryOrder',len_trim(bad_attr),trim(bad_attr)),'set malformed attribute')
      call good(nf_enddef(file_id),'attribute enddef')
      call good(nf_close(file_id),'attribute nf close')
      call ext_ncd_open_for_read(trim(path),comm,io_comm,'',local_h,status);call good(status,'attribute reopen')
      out_order='sentinel'
      call ext_ncd_get_var_info(local_h,'FIELD',dims,out_order,stagger,lo,hi,local_type,status)
      call expect(status==WRF_WARN_BAD_MEMORYORDER.and.dims==0.and.out_order=='','malformed attribute safe rejection')
      call ext_ncd_ioclose(local_h,status);call good(status,'attribute read close')
    enddo
    print *, 'VARINFO_ATTRIBUTE_CONTRACT_PASS'
  end subroutine

  subroutine check_varinfo_buffers()
    character(8) :: padded_order
    character(1) :: short_order
    integer :: dims,local_type,lo(4),hi(4)
    padded_order='sentinel';lo=-1;hi=-1
    call wrf_get_var_info(h,'INT_UPPER',dims,padded_order,stagger,lo,hi,status)
    call good(status,'actual selected NetCDF wrapper dispatch')
    call expect(dims==2.and.padded_order=='ZZ'.and.all(hi(1:2)==[3,5]),'wrapper padded output')
    call wrf_get_var_info(h,'MISSING',dims,padded_order,stagger,lo,hi,status)
    call expect(status==WRF_WARN_NETCDF,'wrapper backend error reaches public Status')
    short_order='x'
    call ext_ncd_get_var_info(h,'INT_UPPER',dims,short_order,stagger,lo,hi,local_type,status)
    call expect(status==WRF_WARN_CHARSTR_GT_LENDATA.and.dims==0.and.short_order=='','short output safely rejected')
    short_order='x'
    call wrf_get_var_info(h,'INT_UPPER',dims,short_order,stagger,lo,hi,status)
    call expect(status==WRF_WARN_CHARSTR_GT_LENDATA.and.dims==0.and.short_order=='','wrapper short output rejection')
    call ext_ncd_read_field(h,dates(1),'INT_UPPER',got,WRF_INTEGER,comm,io_comm,0, &
      'xyzq','',names,s,e,s,e,s,e,status)
    call expect(status==WRF_WARN_BAD_MEMORYORDER,'public read suffix rejected')
    print *, 'VARINFO_WRAPPER_CONTRACT_PASS'
  end subroutine

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
    character(8)::order
    order=' ZZ '
    if(m>1)order=' zz '
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
