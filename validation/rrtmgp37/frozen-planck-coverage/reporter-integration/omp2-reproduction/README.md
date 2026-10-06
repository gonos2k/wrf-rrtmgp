# PR65 OMP2 fatal-reporter reproduction (prepared, not run)

This isolated one-hour case is prepared to check that the PR65 reporter emits a direct `RRTMGP_FATAL` diagnostic for the previously observed frozen-graupel LW table-temperature failure with MPI 4, OpenMP 2, and batch size 32. It uses the same Matthew `wrfinput_d01` and `wrfbdy_d01`, 2016-10-06 00:00–01:00 interval, radiation configuration, coefficients, and old frozen table as the preserved OMP1 diagnostic. The only runtime setting changed for the reproduction is `OMP_NUM_THREADS=2`; batch size remains 32.

The staged old table is SHA-256 `8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583`. The expected failure is the LW graupel lookup refusing extrapolation below the table temperature axis `[180, 300] K`, at wavenumber `20000 m-1`, with a positive path. The earlier OMP1 run reported `179.996 K`, `6.054224e-4 g m-2`; those values are a diagnostic reference, not hard-coded as the OMP2 outcome. The one-hour OMP1 failure and prior OMP2 MPI abort remain untouched in their original directories.

Preparation has not launched a model. The plan is deliberately `STAGED_WAITING_FOR_REPORTER_EXECUTABLE_PIN_AND_ROOT_AUTHORIZATION`; the copied stage has no `wrf.exe`. When the incremental reporter build is ready, `bind_reporter.py` can record the explicitly supplied executable hash and resolved runtime-library pins. A separate root-issued authorization must then bind the final plan, manifest, runner, executable, old table, and exact MPI/OMP/batch settings. `run_once.py` refuses to execute while any pin or authorization is absent and permits only one attempt, with a 3600-second timeout and process-group cleanup.

A reproduction passes only if the process returns code 1, all nine expected rank/stdout logs exist, at least one log contains the direct `RRTMGP_FATAL` line and the expected graupel/LW/table-bound fields (including a temperature below 180 K), and all pinned inputs/assets remain stable. Rank success markers are recorded but are not required for this intentional fatal test. Any deviation is preserved as a failure receipt; there are no retries, table changes, or forecast-completion claims.

From the workspace root, staging was prepared with:

```sh
python3 -B build/udm37-pr65-worker-fatal-reproduction-v1/prepare.py
python3 -B build/udm37-pr65-worker-fatal-reproduction-v1/seal_stage.py
python3 -B build/udm37-pr65-worker-fatal-reproduction-v1/selftest.py
```

No execution command is issued by this preparation. Root review and a future executable pin are prerequisites.
