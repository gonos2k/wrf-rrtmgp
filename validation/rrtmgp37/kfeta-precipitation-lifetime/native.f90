program kfeta_lifetime
 use module_physics_addtendc,only:advance_ppt
 use module_configure,only:grid_config_rec_type
 use module_state_description,only:KFETASCHEME,MSKFSCHEME,KFCUPSCHEME,P_QI,P_QS
 implicit none
 type(grid_config_rec_type)::c
 real::th(4,3,4),qv(4,3,4),qc(4,3,4),qr(4,3,4),qi(4,3,4),qs(4,3,4),cf(4,3,4)
 real::rc(4,4),cv(4,4),sh(4,4),pr(4,4),ps(4,4),nca(4,4),ht(4,4),hb(4,4),ct(4,4),cb(4,4),ppt(4,4)
 real::surface(4,4)
 integer::scheme,step,u,which
 character(50)::filename
 P_QI=5;P_QS=6
 do which=1,3
  select case(which)
  case(1);scheme=KFETASCHEME
  case(2);scheme=MSKFSCHEME
  case(3);scheme=KFCUPSCHEME
  end select
  c%cu_physics=scheme
  th=1; qv=2;qc=3;qr=4;qi=5;qs=6;cf=7
  rc=10;cv=15;sh=0;pr=.25;ps=0;nca=120;ht=0;hb=0;ct=2;cb=1;ppt=1;surface=0
  write(filename,'(a,i0,a)')'scheme-',scheme,'.bin'
  open(newunit=u,file=trim(filename),access='stream',form='unformatted',status='replace')
  do step=1,5
   ! Same ordering as first_rk_step_part1: surface uses the preceding interval.
   surface=surface+cv
   ! A newly active driver supplies a new interval rate and water tendencies.
   if(step==4)then
    pr=.5;cv=30;nca=60;th=1;qv=2;qc=3;qr=4;qi=5;qs=6
   endif
   call advance_ppt(th,qv,qc,qr,cf,qi,qs,rc,cv,sh,pr,ps,nca,ht,hb,ct,cb,ppt,60.,c, &
    1,4,1,4,1,3,1,4,1,4,1,3,1,3,1,3,1,2)
   write(u)th,qv,qc,qr,qi,qs,cf,rc,cv,sh,pr,ps,nca,ht,hb,ct,cb,ppt,surface
   write(*,'(a,2(i0,1x),*(es25.16e3,1x))')'NATIVE ',scheme,step,rc(2,2),cv(2,2),pr(2,2), &
     nca(2,2),ppt(2,2),qv(2,1,2),surface(2,2)
  enddo
  close(u)
 enddo
 print *,'NATIVE_LIFETIME_COMPLETE'
end program
