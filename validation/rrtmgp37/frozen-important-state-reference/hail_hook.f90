module reference_hail_hook
 use iso_fortran_env,only:real64
 use ieee_arithmetic,only:ieee_is_finite
 use module_ra_rrtmgp_trace,only:trace_active,trace_result
 implicit none
 integer,save::layer=0
 real(real64),save::temperature=0,lambda=0,path=0,kappa(16)=0
contains
 subroutine load_reference(filename)
 character(*),intent(in)::filename
 integer::u
 if(trim(filename)=='-')return
 open(newunit=u,file=filename,status='old')
 read(u,*)layer,temperature,lambda,path
 read(u,*)kappa
 close(u)
 if(layer<1.or.any(.not.ieee_is_finite(kappa)).or.any(kappa<0))error stop 'invalid reference absorption'
 end subroutine
 subroutine apply_reference(ht,t,h,lam)
 real(real64),intent(inout)::ht(:,:,:)
 real,intent(in)::t(:,:),h(:,:),lam(:,:)
 if(layer==0)return
 if(size(ht,1)/=1.or.size(ht,3)/=16.or.layer>size(ht,2))error stop 'selected state dimensions'
 if(real(t(1,layer),real64)/=temperature.or.real(h(1,layer),real64)/=path.or. &
 real(lam(1,layer),real64)/=lambda)error stop 'selected actual state mismatch'
 if(trace_active('LW'))call trace_result('LW','REFERENCE_HAIL_BEFORE',ht)
 ht(1,layer,:)=path*.001_real64*kappa
 if(trace_active('LW'))call trace_result('LW','REFERENCE_HAIL_AFTER',ht)
 end subroutine
end module
