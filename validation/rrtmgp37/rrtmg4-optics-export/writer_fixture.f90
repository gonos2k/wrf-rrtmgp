PROGRAM writer_fixture
  USE module_rrtmg4_optics_export
  IMPLICIT NONE
  REAL :: profile(3), spectral(2,3)
  INTEGER :: flags(2)
  CHARACTER(LEN=16) :: mode

  profile = [1.25, -2.5, 3.75]
  spectral = RESHAPE([1.,2.,3.,4.,5.,6.], [2,3])
  flags = [4,9]
  CALL GET_COMMAND_ARGUMENT(1,mode)
  IF (mode == 'disabled') THEN
    CALL rrtmg4_export_begin('lw',1,2161,129600.,24,55)
    IF (rrtmg4_export_active()) ERROR STOP 10
    CALL rrtmg4_export_end()
    STOP
  END IF

  CALL write_phase('lw')
  CALL write_phase('sw')
CONTAINS
  SUBROUTINE write_phase(phase)
    CHARACTER(LEN=*), INTENT(IN) :: phase
    CALL rrtmg4_export_begin(phase,1,2161,129600.,24,55)
    CALL rrtmg4_export_stage('INPUT')
    CALL rrtmg4_export_real1('PROFILE','K',profile)
    CALL rrtmg4_export_int1('FLAGS',flags)
    CALL rrtmg4_export_stage('CLOUD')
    CALL rrtmg4_export_real2('TAU','1',spectral)
    CALL rrtmg4_export_stage('GAS')
    CALL rrtmg4_export_real1('GAS_TAU','1',profile)
    CALL rrtmg4_export_stage('RESULT')
    CALL rrtmg4_export_real1('FLUX','W_m-2',profile)
    CALL rrtmg4_export_end()
  END SUBROUTINE write_phase
END PROGRAM writer_fixture
