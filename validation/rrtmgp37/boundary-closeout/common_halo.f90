program common_specified_halo
 use module_bc,only:set_physical_bc2d
 use module_configure,only:grid_config_rec_type
 implicit none
 type(grid_config_rec_type)::cfg
 integer,parameter::ids=1,ide=13,jds=1,jde=11,ims=-2,ime=15,jms=-2,jme=13
 real::before(ims:ime,jms:jme),whole(ims:ime,jms:jme),tile(ims:ime,jms:jme),repeat(ims:ime,jms:jme)
 integer::i,j,policy,method,n,ix,jy,order,ilo,ihi,jlo,jhi,count
 cfg%specified=.true.;cfg%nested=.false.;cfg%periodic_x=.false.;cfg%periodic_y=.false.
 cfg%symmetric_xs=.false.;cfg%symmetric_xe=.false.;cfg%symmetric_ys=.false.;cfg%symmetric_ye=.false.
 cfg%open_xs=.false.;cfg%open_xe=.false.;cfg%open_ys=.false.;cfg%open_ye=.false.;cfg%polar=.false.
 before=-999.
 do j=jds,jde-1
 do i=ids,ide-1
  before(i,j)=real(100*j+i)+real(i+j)/1024.
 enddo
 enddo
 count=0
 do policy=0,1
  cfg%udm_number_policy=policy
  whole=before
  call fill(whole,ids,ide,jds,jde)
  call check(whole)
  repeat=whole;call fill(repeat,ids,ide,jds,jde)
  if(any(transfer(repeat,[0],size(repeat))/=transfer(whole,[0],size(whole))))error stop 'non-idempotent whole halo'
  do method=1,4
   tile=before
   do n=1,merge(4,2,method<=2)
    order=n
    if(method==2)order=5-n
    if(method<=2)then
     ix=mod(order-1,2);jy=(order-1)/2
    else if(method==3)then
     ix=n-1;jy=0
    else
     ix=0;jy=n-1
    endif
    ilo=1;ihi=13;jlo=1;jhi=11
    if(method<=3)then
     if(ix==0)ihi=6
     if(ix==1)ilo=7
    endif
    if(method<=2.or.method==4)then
     if(jy==0)jhi=5
     if(jy==1)jlo=6
    endif
    call fill(tile,ilo,ihi,jlo,jhi)
   enddo
   call check(tile)
   if(any(transfer(tile,[0],size(tile))/=transfer(whole,[0],size(whole))))error stop 'tile partition/order changed halo'
   count=count+1
   write(*,'(A,2I3)')'HALO_POLICY_METHOD_PASS',policy,method
  enddo
 enddo
 print *,'COMMON_SPECIFIED_HALO_COMPLETE',count
 contains
 subroutine fill(a,is,ie,js,je)
 real,intent(inout)::a(ims:ime,jms:jme)
 integer,intent(in)::is,ie,js,je
 call set_physical_bc2d(a,'t',cfg,ids,ide,jds,jde,ims,ime,jms,jme,ids,ide,jds,jde,is,ie,js,je)
 end subroutine
 subroutine check(a)
 real,intent(in)::a(ims:ime,jms:jme)
 integer::x,y
 if(any(transfer(a(ids:ide-1,jds:jde-1),[0],120)/=transfer(before(ids:ide-1,jds:jde-1),[0],120)))error stop 'physical MU modified'
 do y=jms,jme
 do x=ims,ime
  if(a(x,y)/=before(max(ids,min(ide-1,x)),max(jds,min(jde-1,y))))error stop 'halo not newest physical edge'
 enddo
 enddo
 end subroutine
end program
