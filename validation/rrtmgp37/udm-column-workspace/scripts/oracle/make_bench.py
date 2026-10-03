from pathlib import Path
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm-workspace-reuse-work')
s=(root/'WRF/test/rrtmgp/test_workspace.F90').read_text().split('PROGRAM test_workspace\n')[0]
s=s.replace('  LOGICAL :: frozen\n','  LOGICAL :: frozen\n  INTEGER(int64) :: lw_ticks=0,sw_ticks=0,clock_rate\n  INTEGER :: repetitions\n')
s=s.replace('    INTEGER :: c,k,state,overlap,seeds(nc)','    INTEGER :: c,k,state,iteration,overlap,seeds(nc)')
s=s.replace('    DO state=1,12','    DO iteration=1,repetitions\n      state=1+MOD(iteration-1,12)')
s=s.replace('      IF(state==5.OR.state==9) mu0=0.\n','')
a=s.index('      snapshot=input_values()');b=s.index('    END DO\n  CONTAINS',a)
s=s[:a]+'''      CALL run(got,lw,sw)
      sig=IEOR(sig,INT(got(1,1,2)+got(1,1,8),int64))
'''+s[b:]
s=s.replace('      LOGICAL :: predelta','      LOGICAL :: predelta\n      INTEGER(int64) :: started,finished')
s=s.replace('      CALL rrtmgp_lw_column','      CALL SYSTEM_CLOCK(started)\n      CALL rrtmgp_lw_column',1)
s=s.replace("      CALL trace_end('LW')","      CALL SYSTEM_CLOCK(finished)\n      lw_ticks=lw_ticks+finished-started\n      CALL trace_end('LW')",1)
s=s.replace('      CALL rrtmgp_sw_column','      CALL SYSTEM_CLOCK(started)\n      CALL rrtmgp_sw_column',1)
s=s.replace("      CALL trace_end('SW')","      CALL SYSTEM_CLOCK(finished)\n      sw_ticks=sw_ticks+finished-started\n      CALL trace_end('SW')",1)
s+='''PROGRAM bench_workspace
  USE test_workspace_cases
  IMPLICIT NONE
  CHARACTER(1024) :: data,mode,table,reps
  INTEGER(int64) :: sig
  TYPE(ty_rrtmgp_lw_workspace) :: lw
  TYPE(ty_rrtmgp_sw_workspace) :: sw
  CALL GET_COMMAND_ARGUMENT(1,data);CALL GET_COMMAND_ARGUMENT(2,mode)
  CALL GET_COMMAND_ARGUMENT(3,table);CALL GET_COMMAND_ARGUMENT(4,reps)
  READ(reps,*) repetitions
  frozen=TRIM(mode)=='1'
  IF(frozen) THEN
    CALL rrtmgp_init(TRIM(data),frozen_optics=1,frozen_table=TRIM(table))
  ELSE
    CALL rrtmgp_init(TRIM(data))
  END IF
  CALL SYSTEM_CLOCK(COUNT_RATE=clock_rate)
  sig=0
  CALL shape_cases(1,60,1,0,lw,sw,sig)
  WRITE(*,'(I0,A,ES18.10,A,ES18.10,A,I0)') repetitions,',',REAL(lw_ticks,8)/REAL(clock_rate,8),',', &
    REAL(sw_ticks,8)/REAL(clock_rate,8),',',sig
#ifndef RRTMGP_BASELINE_REFERENCE
  CALL rrtmgp_release_workspace(lw);CALL rrtmgp_release_workspace(sw)
#endif
END PROGRAM
'''
Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm-workspace-oracle/bench_workspace.F90').write_text(s)
