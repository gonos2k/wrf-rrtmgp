PROGRAM test_column_selection
  USE module_ra_rrtmgp_trace, ONLY: trace_column_selection,trace_column_in_tile,trace_start,trace_active
  IMPLICIT NONE
  CHARACTER(LEN=32) :: mode
  INTEGER :: i,j
  LOGICAL :: selected
  CALL GET_COMMAND_ARGUMENT(1,mode)
  IF(TRIM(mode)=='legacy') THEN
    CALL trace_column_selection(1,201,1,121,selected,i,j)
    IF(selected.OR.i/=1.OR.j/=1) ERROR STOP 'no-selector mode must preserve legacy defaults'
    IF(.NOT.trace_column_in_tile(1,201,1,121,1,40,1,40)) &
      ERROR STOP 'no-selector mode must preserve full-tile audit eligibility'
    CALL trace_start('LW',1,1,1,201,1,121)
    IF(.NOT.trace_active('LW')) ERROR STOP 'legacy trace selection must remain column 1,1'
  ELSE IF(TRIM(mode)=='selected') THEN
    CALL trace_column_selection(1,201,1,121,selected,i,j)
    IF(.NOT.selected.OR.i/=169.OR.j/=80) ERROR STOP 'selected pair was not returned exactly'
    IF(trace_column_in_tile(1,201,1,121,1,40,1,40)) &
      ERROR STOP 'target outside this tile must skip this tile'
    IF(.NOT.trace_column_in_tile(1,201,1,121,169,180,80,90)) &
      ERROR STOP 'target in tile must allow selected audit'
    CALL trace_start('LW',1,1,1,201,1,121)
    IF(trace_active('LW')) ERROR STOP 'selected trace must skip other columns'
    CALL trace_start('LW',169,80,1,201,1,121)
    IF(.NOT.trace_active('LW')) ERROR STOP 'selected trace did not activate requested column'
  ELSE IF(TRIM(mode)=='out-i') THEN
    CALL trace_column_selection(1,201,1,121,selected,i,j)
  ELSE IF(TRIM(mode)=='out-j') THEN
    CALL trace_column_selection(1,201,1,121,selected,i,j)
  ELSE IF(TRIM(mode)=='boundary') THEN
    CALL trace_column_selection(1,201,1,121,selected,i,j)
    IF(.NOT.selected.OR.i/=200.OR.j/=120) ERROR STOP 'last physical mass column must be accepted'
  ELSE
    ERROR STOP 'unknown test mode'
  END IF
  WRITE(*,'(A)') 'column selection contract passed: '//TRIM(mode)
END PROGRAM test_column_selection
