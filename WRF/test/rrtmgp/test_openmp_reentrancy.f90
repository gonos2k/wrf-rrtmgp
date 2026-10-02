program openmp_reentrancy_stress
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use omp_lib, only: omp_set_dynamic, omp_set_num_threads, omp_get_num_threads
  use module_ra_rrtmgp, only: rrtmgp_init, rrtmgp_lw_column, rrtmgp_sw_column
  implicit none
  integer, parameter :: nc=64, nl=3, nv=nl+1
  real :: play(nc,nl),plev(nc,nv),tlay(nc,nl),tlev(nc,nv),tsfc(nc)
  real :: h2o(nc,nl),co2(nc,nl),o3(nc,nl),n2o(nc,nl),ch4(nc,nl),o2(nc,nl)
  real :: emis(nc,1),cf(nc,nl),lwp(nc,nl),iwp(nc,nl),swp(nc,nl),rel(nc,nl),rei(nc,nl),res(nc,nl)
  real :: rwp(nc,nl)
  real :: avdir(nc),avdif(nc),andir(nc),andif(nc),mu0(nc),solar
  real :: serial(72,nc), parallel(72,nc)
  integer :: c,k,nthreads,repeat,observed_threads,env_status
  character(len=512) :: data_path,capture_env
  call get_command_argument(1,data_path)
  if (len_trim(data_path)==0) error stop 'usage: openmp_reentrancy DATA_DIRECTORY'
  call get_environment_variable("WRF_RRTMGP_CAPTURE_DIR",capture_env,status=env_status)
  if(env_status==0.and.len_trim(capture_env)>0) error stop "stress test requires capture disabled"
  call omp_set_dynamic(.false.)
  call initialize_inputs()
  ! All shared coefficient tables and constants are initialized serially exactly once.
  call rrtmgp_init(trim(data_path))
  do c=1,nc
    call run_column(c,serial(:,c))
  end do
  do k=1,3
    select case(k)
    case(1); nthreads=1
    case(2); nthreads=2
    case default; nthreads=4
    end select
    call omp_set_num_threads(nthreads)
    do repeat=1,8
      parallel=-huge(1.)
      observed_threads=0
      !$omp parallel do schedule(static) private(c) reduction(max:observed_threads)
      do c=1,nc
        observed_threads=omp_get_num_threads()
        call run_column(c,parallel(:,c))
      end do
      !$omp end parallel do
      if (observed_threads/=nthreads) error stop 'FAIL requested thread team not observed'
      if (.not.all(ieee_is_finite(parallel))) error stop 'FAIL non-finite parallel output'
      if (any(abs(parallel-serial)>2.e-5*max(1.,abs(serial)))) then
        write(*,'(A,I0,A,I0,A,ES12.4)') 'FAIL threads=',nthreads,' repeat=',repeat,' maxdiff=',maxval(abs(parallel-serial))
        error stop 1
      end if
    end do
    write(*,'(A,I0,A,ES12.4)') 'PASS threads=',nthreads,' maxdiff=',maxval(abs(parallel-serial))
  end do
contains
  subroutine initialize_inputs()
    integer :: j
    real :: f
    solar=1361.
    do c=1,nc
      f=real(c-1)/real(nc-1)
      plev(c,:)=[990.+10.*f,700.+8.*f,300.+5.*f,merge(0.,1.,mod(c,2)==0)]
      play(c,:)=[0.5*(plev(c,1)+plev(c,2)),0.5*(plev(c,2)+plev(c,3)),0.5*(plev(c,3)+plev(c,4))]
      tlev(c,:)=[286.+3.*f,276.+2.*f,244.+4.*f,210.+8.*f]
      do j=1,nl
        tlay(c,j)=0.5*(tlev(c,j)+tlev(c,j+1))
      end do
      tsfc(c)=tlev(c,1)
      h2o(c,:)=[0.009+0.002*f,0.0025+0.0005*f,0.00008+0.00004*f]
      co2(c,:)=410.e-6+20.e-6*f
      o3(c,:)=[0.4e-6+0.2e-6*f,1.e-6+0.2e-6*f,4.e-6+f*1.e-6]
      n2o(c,:)=320.e-9+20.e-9*f; ch4(c,:)=1.7e-6+0.2e-6*f; o2(c,:)=0.209+0.001*f
      emis(c,1)=0.96+0.03*f
      cf(c,:)=[0.2+0.2*f,0.45+0.2*f,0.3+0.3*f]
      lwp(c,:)=[10.+10.*f,60.+35.*f,20.+20.*f]
      iwp(c,:)=[5.+10.*f,30.+30.*f,45.+20.*f]
      swp(c,:)=[2.+5.*f,18.+20.*f,8.+10.*f]
      rwp(c,:)=[5.+2.*f,10.+5.*f,4.+3.*f]
      rel(c,:)=8.+8.*f; rei(c,:)=25.+30.*f; res(c,:)=25.+60.*f
      avdir(c)=0.1+0.2*f; avdif(c)=0.12+0.18*f
      andir(c)=0.18+0.22*f; andif(c)=0.2+0.2*f; mu0(c)=0.3+0.5*f
    end do
  end subroutine
  subroutine run_column(col,x)
    integer,intent(in)::col
    real,intent(out)::x(72)
    real :: up(1,nv),dn(1,nv),hr(1,nl),upc(1,nv),dnc(1,nv),hrc(1,nl)
    real :: swup(1,nv),swdn(1,nv),swhr(1,nl),swupc(1,nv),swdnc(1,nv),swhrc(1,nl)
    real :: direct(1,nv),diffuse(1,nv),directc(1,nv),visdir(1,nv),visdif(1,nv),nirdir(1,nv),nirdif(1,nv)
    integer :: p
    call rrtmgp_lw_column(play(col:col,:),plev(col:col,:),tlay(col:col,:),tlev(col:col,:),tsfc(col:col), &
      h2o(col:col,:),co2(col:col,:),o3(col:col,:),n2o(col:col,:),ch4(col:col,:),o2(col:col,:),emis(col:col,:), &
      cf(col:col,:),lwp(col:col,:),iwp(col:col,:),swp(col:col,:),rel(col:col,:),rei(col:col,:),res(col:col,:), &
      4,2,173,up,dn,hr,upc,dnc,hrc,column_seeds=[1009*col+173],rwp=rwp(col:col,:))
    call rrtmgp_sw_column(play(col:col,:),plev(col:col,:),tlay(col:col,:),h2o(col:col,:),co2(col:col,:), &
      o3(col:col,:),n2o(col:col,:),ch4(col:col,:),o2(col:col,:),avdir(col:col),avdif(col:col),andir(col:col), &
      andif(col:col),mu0(col:col),solar,cf(col:col,:),lwp(col:col,:),iwp(col:col,:),swp(col:col,:), &
      rel(col:col,:),rei(col:col,:),res(col:col,:),4,2,173,swup,swdn,swhr,swupc,swdnc,swhrc, &
      direct,diffuse,directc,visdir,visdif,nirdir,nirdif,column_seeds=[1009*col+173],rwp=rwp(col:col,:))
    p=1
    x(p:p+3)=up(1,:); p=p+4; x(p:p+3)=dn(1,:); p=p+4
    x(p:p+2)=hr(1,:); p=p+3; x(p:p+3)=upc(1,:); p=p+4
    x(p:p+3)=dnc(1,:); p=p+4; x(p:p+2)=hrc(1,:); p=p+3
    x(p:p+3)=swup(1,:); p=p+4; x(p:p+3)=swdn(1,:); p=p+4
    x(p:p+2)=swhr(1,:); p=p+3; x(p:p+3)=swupc(1,:); p=p+4
    x(p:p+3)=swdnc(1,:); p=p+4; x(p:p+2)=swhrc(1,:); p=p+3
    x(p:p+3)=direct(1,:); p=p+4; x(p:p+3)=diffuse(1,:); p=p+4
    x(p:p+3)=directc(1,:); p=p+4; x(p:p+3)=visdir(1,:); p=p+4
    x(p:p+3)=visdif(1,:); p=p+4; x(p:p+3)=nirdir(1,:); p=p+4
    x(p:p+3)=nirdif(1,:); p=p+4
  end subroutine
end program
