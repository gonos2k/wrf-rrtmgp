module module_state_description
  integer,parameter :: IO_NETCDF=2, DEBUG_LVL=0
end module
SUBROUTINE dim_from_memorder(MemoryOrder,NDim)
!<DESCRIPTION>
!<PRE>
! Decodes array ranks from memory order.  
!</PRE>
!</DESCRIPTION>
  CHARACTER*(*) ,INTENT(IN)  :: MemoryOrder
  INTEGER       ,INTENT(OUT) :: NDim
!Local
  CHARACTER*3                :: MemOrd
!
  CALL Lower_Case(MemoryOrder,MemOrd)
  SELECT CASE (MemOrd)
    CASE ('xyz','xzy','yxz','yzx','zxy','zyx')
      NDim = 3
    CASE ('xy','yx','zz')
      NDim = 2
    CASE ('z','c','0')
      NDim = 1
    CASE DEFAULT
      NDim = 0
      RETURN
  END SELECT
  RETURN
END SUBROUTINE dim_from_memorder

SUBROUTINE lower_case(MemoryOrder,MemOrd)
!<DESCRIPTION>
!<PRE>
! Translates upper-case characters to lower-case.  
!</PRE>
!</DESCRIPTION>
  CHARACTER*(*) ,INTENT(IN)  :: MemoryOrder
  CHARACTER*(*) ,INTENT(OUT) :: MemOrd
!Local
  CHARACTER*1                :: c
  INTEGER       ,PARAMETER   :: upper_to_lower =IACHAR('a')-IACHAR('A')
  INTEGER                    :: i,n,n1
!
  MemOrd = ' '
  N = len(MemoryOrder)
  N1 = len(MemOrd)
  N = MIN(N,N1)
  MemOrd(1:N) = MemoryOrder(1:N)
  DO i=1,N
    c = MemoryOrder(i:i)
    if('A'<=c .and. c <='Z') MemOrd(i:i)=achar(iachar(c)+upper_to_lower)
  ENDDO
  RETURN
END SUBROUTINE Lower_Case

SUBROUTINE wrf_get_var_info ( DataHandle , VarName , NDim , MemoryOrder , Stagger , &
                              DomainStart , DomainEnd , Status )
!<DESCRIPTION>
!<PRE>
! This routine applies only to a dataset that is open for read.  It returns 
! information about a variable.  
!</PRE>
!</DESCRIPTION>
  USE module_state_description
  IMPLICIT NONE
  INTEGER               ,INTENT(IN)     :: DataHandle
  CHARACTER*(*)         ,INTENT(IN)     :: VarName
  INTEGER               ,INTENT(OUT)    :: NDim
  CHARACTER*(*)         ,INTENT(OUT)    :: MemoryOrder
  CHARACTER*(*)         ,INTENT(OUT)    :: Stagger
  INTEGER ,dimension(*) ,INTENT(OUT)    :: DomainStart, DomainEnd
  INTEGER               ,INTENT(OUT)    :: Status
#include "wrf_status_codes.h"
  INTEGER                     :: io_form
  LOGICAL                     :: for_out
  INTEGER, EXTERNAL           :: use_package
  LOGICAL, EXTERNAL           :: wrf_dm_on_monitor, multi_files, use_output_servers_for
  INTEGER                     :: Hndl
  INTEGER                     :: NetCDFFieldType

  CALL wrf_debug( DEBUG_LVL, 'module_io.F: in wrf_get_var_info' )

  Status = 0
  CALL get_handle ( Hndl, io_form , for_out, DataHandle )
  IF ( Hndl .GT. -1 ) THEN
    IF (( multi_files(io_form) .OR.  wrf_dm_on_monitor() ) .AND. .NOT. (for_out .AND. use_output_servers_for(io_form)) ) THEN
      SELECT CASE ( use_package( io_form ) )
#ifdef NETCDF
        CASE ( IO_NETCDF   )
          CALL ext_ncd_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      NetCDFFieldType , Status )
#endif
#ifdef PHDF5
        CASE ( IO_PHDF5)
          CALL ext_phdf5_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
#ifdef NETCDFPAR
        CASE ( IO_NETCDFPAR)
          CALL ext_ncdpar_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
#ifdef PNETCDF
        CASE ( IO_PNETCDF)
          CALL ext_pnc_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
#ifdef PIO
        CASE ( IO_PIO )
          CALL ext_pio_get_var_info ( Hndl , VarName , NDim ,                  &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
#ifdef ADIOS2
        CASE ( IO_ADIOS2)
          CALL ext_adios2_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
#ifdef XXX
        CASE ( IO_XXX )
          CALL ext_xxx_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
#ifdef YYY
        CASE ( IO_YYY )
          CALL ext_yyy_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
#ifdef GRIB1
        CASE ( IO_GRIB1 )
          CALL ext_gr1_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
#ifdef GRIB2
        CASE ( IO_GRIB2 )
          CALL ext_gr2_get_var_info ( Hndl , VarName , NDim ,            &
                                      MemoryOrder , Stagger ,                  &
                                      DomainStart , DomainEnd ,                &
                                      Status )
#endif
        CASE DEFAULT
          Status = 0
      END SELECT
    ELSE IF ( io_form .GT. 0 .AND. for_out .AND. use_output_servers_for(io_form) ) THEN
      CALL wrf_quilt_get_var_info ( Hndl , VarName , NDim ,            &
                                    MemoryOrder , Stagger ,                  &
                                    DomainStart , DomainEnd ,                &
                                    Status )
    ELSE
      Status = 0
    ENDIF
  ELSE
    Status = WRF_ERR_FATAL_BAD_FILE_STATUS
  ENDIF
  RETURN

END SUBROUTINE wrf_get_var_info



subroutine get_handle(hndl,io_form,for_out,datahandle)
  integer,intent(in) :: datahandle
  integer,intent(out) :: hndl,io_form
  logical,intent(out) :: for_out
  hndl=datahandle;io_form=2;for_out=.false.
end subroutine
integer function use_package(io_form)
  integer,intent(in)::io_form
  use_package=io_form
end function
logical function multi_files(io_form)
  integer,intent(in)::io_form
  multi_files=.false.
end function
logical function wrf_dm_on_monitor()
  wrf_dm_on_monitor=.true.
end function
logical function use_output_servers_for(io_form)
  integer,intent(in)::io_form
  use_output_servers_for=.false.
end function
