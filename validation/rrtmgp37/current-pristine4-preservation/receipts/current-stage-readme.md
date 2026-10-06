# Current-head pristine RA4 serial SCM regression (prepared, not run)

This stage checks whether the current PR74 WRF source still reproduces the official WRF 4.8.0 UDM/RRTMG4 control and mixed 60-second SCM cases. The source54 regression passed previously; it is not evidence for current HEAD. The current-source runner is dry by default, and no model has been launched from this stage.

Current binary: `build/udm37-rrtmg4-export-serial-build-v1/source/WRF/main/wrf.exe` (SHA-256 `5091946b34cdf9c3397f07f03133dfe2ce0c36059b1d0ec4caa90c013d5a1a57`). It was built from compiled-source commit `b7b5f6f9cd657408e3bde3018d7e882ab3e4bce3`; current target HEAD is `5f3034e9c43209a352977da4885a3fc15b46c532`. A whole-`WRF/` Git tree comparison reports no differences between those commits. Configure SHA is `6a2fcd322bbff92ff61a141671d492eb8d74e3d56af28582306c024775b89c68`; the build command was GNU serial `csh -f ./compile -j 12 em_real`. See `compile-target-compatibility.json` for why the generic WRF executable can execute SCM inputs; runtime equivalence remains untested.

The references are the official pristine outputs and the independently tested source54 current-source outputs. Existing input files and runtime tables are copied byte-for-byte into fresh case directories. The two planned current-source cases are control and mixed, each 60 seconds, using the existing input, namelist, and radiation IO selection. The runner checks all 208 variables without exclusions: whole-file hash, NetCDF model, dimensions and unlimited flags, variable/global attributes, dtype, raw bytes, and finite/unmasked values. It snapshots source/configuration/executable/build receipts and the official/source54/staged input trees before and after each run. Each process exit record is atomically persisted before any log or NetCDF validation.

No build or model execution is requested by this preparation. `run_current_cases.py` without arguments performs preflight only; `--execute` is intentionally withheld for root review/launch.

Key pins are recorded in `stage-manifest-final.json`; the dry preflight is `current-preflight.json`. `inventory.json` preserves the earlier source-gap inventory.
