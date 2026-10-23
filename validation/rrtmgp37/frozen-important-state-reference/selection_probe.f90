module module_frozen_selection_probe
 use iso_fortran_env,only:real64
 implicit none
 integer,save::u=0
contains
 subroutine select_column(i,j,time,t,h,lam)
 integer,intent(in)::i,j
 real,intent(in)::time,t(:),h(:),lam(:)
 logical::warm(size(t))
 integer::k
 if(time/=3000.)return
 if(u==0)open(newunit=u,file='frozen-selection.txt',status='replace')
 warm=t>273.15.and.h>0
 k=maxloc(merge(h,-1.,warm),dim=1)
 write(u,'(3(i0,1x),*(es25.16e3,1x))')i,j,count(warm),real(time,real64), &
 sum(real(h,real64),mask=warm),sum(real(h,real64)),real(k,real64), &
 real(t(k),real64),real(h(k),real64),real(lam(k),real64)
 end subroutine
end module
