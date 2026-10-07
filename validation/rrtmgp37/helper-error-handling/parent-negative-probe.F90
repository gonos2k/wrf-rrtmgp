program invalid_probe
 use wrf_data
 use ext_ncd_support_routines
 implicit none
 include 'wrf_status_codes.h'
 character(80) :: names(4),ordered(4)
 integer :: status
 names='first';ordered='sentinel'
 call ExtOrderStr('qq',names,ordered,status)
 if(status/=WRF_WARN_BAD_MEMORYORDER) error stop 71
 print *, 'ERROR_STATUS_RETURNED'
end program
subroutine wrf_debug(level,message)
 integer,intent(in)::level
 character(*),intent(in)::message
end subroutine
