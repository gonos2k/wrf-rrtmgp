## Summary

CMake-built WRF consumers could not link `wrf_rrtmgp` from the installed `WRF::` package, and the CMake allocatable-array configuration rejected UDM host dummies declared as pointers. This patch exports the radiation library and generated modules through relocatable install paths, and changes the two UDM host entry points to optional assumed-shape arrays with explicit WRF lower bounds. The same interface builds in both CMake and traditional GNU Make configurations.

## Validation

- Fresh GNU CMake/Ninja Release `em_real` build and install passed. The installed package contains `libwrf_rrtmgp.a`, 26 RRTMGP modules, and exported `WRF::wrf_rrtmgp`/`WRF::WRF_Core` targets without embedded source/build paths.
- Two fresh downstream consumers passed: RRTMGP target alone, and WRF core plus RRTMGP target.
- Standalone `wrf_rrtmgp_columns` CTest passed (1/1).
- Bounded CMake serial RA37/frozen-on and RA4/frozen-off restarts completed and passed schedule, metadata/layout, fill-marker, and finite-value checks. RA37/frozen-off rejected the hail-positive restart before history output; serial `STOP 'wrf_abort'` returns code 0.
- A fresh traditional GNU Make build passed. Its one-minute RA37/frozen-on and RA4/frozen-off outputs matched corresponding PR30 GNU serial histories byte-for-byte, including variable/global metadata.

See `README.md` and `evidence.json` for commands, source pins, output counts, hashes, and validation scope. These bounded runs do not establish MPI/OpenMP/GPU behavior or forecast-duration performance.
