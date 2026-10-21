module module_boundary_closeout_probe
 implicit none
 private
 public::cbo_context,cbo_clear,cbo_emit,cbo_selected
 integer,save::species=0,rk=0
 real(8),save::source_time=0
 logical,save::checked=.false.,enabled=.false.
 contains
 subroutine cbo_context(code,time,step)
 integer,intent(in)::code,step
 real(8),intent(in)::time
 if(.not.checked)then
  inquire(file='boundary_closeout.enabled',exist=enabled)
  checked=.true.
 endif
 species=0
 if(enabled.and.time>=21540.d0.and.time<=21660.d0)species=code
 source_time=time;rk=step
 end subroutine
 subroutine cbo_clear()
 species=0
 end subroutine
 logical function cbo_selected(i,k,j,kind)
 integer,intent(in)::i,k,j,kind
 cbo_selected=species>0.and.i==24.and.k==1.and.((kind==1.and.j==2).or.(kind==2.and.j==1))
 end function
 subroutine cbo_emit(label,values)
 character(*),intent(in)::label
 real,intent(in)::values(:)
 integer::unit,n
 open(newunit=unit,file='boundary-closeout.txt',position='append',status='unknown')
 write(unit,'(A,1X,I1,1X,I1,1X,F12.3)',advance='no')label,species,rk,source_time
 do n=1,size(values)
  write(unit,'(1X,Z8.8)',advance='no')transfer(values(n),0)
 enddo
 write(unit,*)
 close(unit)
 end subroutine
end module
