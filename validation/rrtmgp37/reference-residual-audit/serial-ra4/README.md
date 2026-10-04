# Source-v4 RA4 serial regression against pristine UDM4

This scratch result builds the frozen current Fortran source-v4 snapshot with the official WRF 4.8.0 GNU 13.3 serial, default-real-32, no-nesting configure settings, then executes the two existing 60-second SCM control/mixed inputs once each. No official pristine case was rerun or changed.

The official `configure.wrf` was kept as the base; its SHA256 is `af7642a54474c075b27f7010db139bef116645e4ba57463be2644cf689791365`. The isolated config SHA256 is `6a2fcd322bbff92ff61a141671d492eb8d74e3d56af28582306c024775b89c68` and differs only by the required RRTMGP module include path `-I$(WRF_SRC_ROOT_DIR)/external/rte_rrtmgp/build`. Compiler, precision, optimization, and serial/OpenMP settings were unchanged. The one-line diff is in [configure.wrf.diff](configure.wrf.diff).

The copied WRF source tree matched all 5,835 WRF entries in the pinned source-v4 manifest before cleanup. Key source hashes are recorded in [build-receipt.json](build-receipt.json). A clean isolated tree was compiled using `csh -f ./compile -j 12 em_scm_xy`; result RC 0, GNU Fortran 13.3, and both executables are hash-pinned there. The complete compiler stdout was captured by the execution session but was not redirected to a disk log; [build-summary.log](build-summary.log) records the exact command, timestamps, return code, terminal success line, and this limitation.

Both fresh cases ended with `SUCCESS COMPLETE WRF`; all 208 variables matched their official pristine counterparts byte-for-byte, including dtype, dimensions, variable/global attributes, and dimensions. The generated files are also identical SHA256 to the old official output files. The per-case receipts include the full static input/runtime asset inventories before and after, command status, logs, and full variable comparison.

| Case | Current history SHA256 | Official history SHA256 | Result |
|---|---|---|---|
| control | `cc34da6667b2569063f7b302985a9e9b44dac4f4b528989255404c1a5cf9da8f` | `cc34da6667b2569063f7b302985a9e9b44dac4f4b528989255404c1a5cf9da8f` | PASS, 208/208 raw variables |
| mixed | `e04dd6fbd89a3df30e9d65e518d022ba2086291b6443268b7a09e293d4f4f216` | `e04dd6fbd89a3df30e9d65e518d022ba2086291b6443268b7a09e293d4f4f216` | PASS, 208/208 raw variables |

This validates only the two defined 60-second RA4 SCM cases against the existing official pristine outputs. It does not establish longer forecast equivalence or broader platform coverage.
