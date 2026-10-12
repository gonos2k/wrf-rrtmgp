# Local validation

- GNU 13.3 serial REAL32 CMake SCM build: final wrf/ideal targets completed. Initial prefix/configuration and metadata API compile errors were corrected; build logs retained.
- Full UDM module O0/O2 pairs: 32 manufactured cases, 64 UDM calls; final process/radius state equals rounded volume-number control.
- Actual new-candidate WRF: 120s control + 60s resumed forecast; 211 terminal history variables bitwise equal.
- Runtime number capture: 12 calls; 59 cold layers use physical CCN background/rho, 372 positive-liquid radius reconstructions within 2e-6 relative diagnostic tolerance; whole history unchanged with capture.
- Previous vs new legacy default: 211 variables at all 13 times bitwise equal.
- Four representation refusals and one ideal producer refusal observed in actual programs. Fatal STOP can return RC0 in this GNU serial build; success is checked by logs and readback, not RC alone.
- Acceptance 13 tests and existing execution identity 16 tests passed locally. New replay boundaries: four tests.

Old/intermediate campaigns and harness errors are in process-accounting, and do not replace final source/binary evidence. CI checks saved artifacts; it does not recompile Fortran or launch WRF. This is candidate implementation/engineering evidence, not scientific production acceptance or final forecast validation.
