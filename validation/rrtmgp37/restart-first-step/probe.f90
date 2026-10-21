module module_restart_first_step_probe
 use module_domain, only: domain
 implicit none
 integer,save::un=-1
 logical,save::checked=.false.,enabled=.false.
 contains
 subroutine begin_probe(tag,grid,time,time2,rk,iteration)
 character(*),intent(in)::tag
 type(domain),intent(in)::grid
 real(8),intent(in)::time,time2
 integer,intent(in)::rk,iteration
 integer::il,iu,jl,ju,kl,ku,meta
 character(200)::path
 if(.not.checked)then
 inquire(file='restart_probe.enabled',exist=enabled)
 checked=.true.
 endif
 if(.not.enabled.or.(time/=21540.d0.and.time/=21600.d0))return
 write(path,'(A,I6.6,A,I1,A,I2.2,A,A)')'probe-',nint(time),'-r',rk,'-a',iteration,'-',tag
 open(newunit=meta,file=trim(path)//'.txt',status='replace')
 write(meta,*)time,time2,grid%itimestep,grid%dtbc,grid%dt
 write(meta,*)grid%sd31,grid%ed31,grid%sd32,grid%ed32,grid%sd33,grid%ed33
 close(meta)
 open(newunit=un,file=trim(path)//'.bin',status='replace',access='stream',form='unformatted',convert='little_endian')
 il=max(grid%sm31,19);iu=min(grid%em31,27)
 jl=max(grid%sm33,grid%ed33-8);ju=min(grid%em33,grid%ed33)
 kl=1;ku=min(grid%em32,grid%ed32)
 call array3('u_1',grid%u_1(il:iu,kl:ku,jl:ju))
 call array3('u_2',grid%u_2(il:iu,kl:ku,jl:ju))
 call array3('v_1',grid%v_1(il:iu,kl:ku,jl:ju))
 call array3('v_2',grid%v_2(il:iu,kl:ku,jl:ju))
 call array3('w_1',grid%w_1(il:iu,kl:ku,jl:ju))
 call array3('w_2',grid%w_2(il:iu,kl:ku,jl:ju))
 call array3('t_1',grid%t_1(il:iu,kl:ku,jl:ju))
 call array3('t_2',grid%t_2(il:iu,kl:ku,jl:ju))
 call array3('ph_1',grid%ph_1(il:iu,kl:ku,jl:ju))
 call array3('ph_2',grid%ph_2(il:iu,kl:ku,jl:ju))
 call array3('phb',grid%phb(il:iu,kl:ku,jl:ju))
 call array3('p',grid%p(il:iu,kl:ku,jl:ju))
 call array3('pb',grid%pb(il:iu,kl:ku,jl:ju))
 call array3('al',grid%al(il:iu,kl:ku,jl:ju))
 call array3('alb',grid%alb(il:iu,kl:ku,jl:ju))
 call array3('alt',grid%alt(il:iu,kl:ku,jl:ju))
 call array3('rho',grid%rho(il:iu,kl:ku,jl:ju))
 call array3('php',grid%php(il:iu,kl:ku,jl:ju))
 call array3('ru',grid%ru(il:iu,kl:ku,jl:ju))
 call array3('rv',grid%rv(il:iu,kl:ku,jl:ju))
 call array3('rw',grid%rw(il:iu,kl:ku,jl:ju))
 call array3('ww',grid%ww(il:iu,kl:ku,jl:ju))
 call array3('ww_m',grid%ww_m(il:iu,kl:ku,jl:ju))
 call array3('ru_tend',grid%ru_tend(il:iu,kl:ku,jl:ju))
 call array3('rv_tend',grid%rv_tend(il:iu,kl:ku,jl:ju))
 call array3('rthraten',grid%rthraten(il:iu,kl:ku,jl:ju))
 call array3('rthratenlw',grid%rthratenlw(il:iu,kl:ku,jl:ju))
 call array3('rthratensw',grid%rthratensw(il:iu,kl:ku,jl:ju))
 call array3('rthratenlwc',grid%rthratenlwc(il:iu,kl:ku,jl:ju))
 call array3('rthratenswc',grid%rthratenswc(il:iu,kl:ku,jl:ju))
 call array2('mu_1',grid%mu_1(il:iu,jl:ju))
 call array2('mu_2',grid%mu_2(il:iu,jl:ju))
 call array2('mub',grid%mub(il:iu,jl:ju))
 call array2('mut',grid%mut(il:iu,jl:ju))
 call array2('muts',grid%muts(il:iu,jl:ju))
 call array2('muu',grid%muu(il:iu,jl:ju))
 call array2('muv',grid%muv(il:iu,jl:ju))
 call array2('muus',grid%muus(il:iu,jl:ju))
 call array2('muvs',grid%muvs(il:iu,jl:ju))
 call array2('mudf',grid%mudf(il:iu,jl:ju))
 call array2('msftx',grid%msftx(il:iu,jl:ju))
 call array2('msfty',grid%msfty(il:iu,jl:ju))
 call array3('u_bye',grid%u_bye(il:iu,kl:ku,:))
 call array3('u_btye',grid%u_btye(il:iu,kl:ku,:))
 call array3('v_bye',grid%v_bye(il:iu,kl:ku,:))
 call array3('v_btye',grid%v_btye(il:iu,kl:ku,:))
 call array3('w_bye',grid%w_bye(il:iu,kl:ku,:))
 call array3('w_btye',grid%w_btye(il:iu,kl:ku,:))
 call array3('ph_bye',grid%ph_bye(il:iu,kl:ku,:))
 call array3('ph_btye',grid%ph_btye(il:iu,kl:ku,:))
 call array3('t_bye',grid%t_bye(il:iu,kl:ku,:))
 call array3('t_btye',grid%t_btye(il:iu,kl:ku,:))
 end subroutine
 subroutine array3(name,x)
 character(*),intent(in)::name
 real,intent(in)::x(:,:,:)
 character(32)::key
 if(un==-1)return
 key=name
 write(un)key,shape(x),x
 end subroutine
 subroutine array2(name,x)
 character(*),intent(in)::name
 real,intent(in)::x(:,:)
 character(32)::key
 if(un==-1)return
 key=name
 write(un)key,size(x,1),size(x,2),1,x
 end subroutine
 subroutine end_probe()
 if(un==-1)return
 close(un)
 un=-1
 end subroutine
end module
