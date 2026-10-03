# GNU CMake OpenMP dependency evidence

This evidence supports the six-line build-system change in `WRF/external/rte_rrtmgp/CMakeLists.txt`: when WRF is configured with `USE_OPENMP=ON`, the vendored `wrf_rrtmgp` target publicly links `OpenMP::OpenMP_Fortran`. The target already gets its compiler flags from the OpenMP imported target in the WRF build; making the dependency public also propagates the runtime link requirement through the installed `WRF::wrf_rrtmgp` target. With `USE_OPENMP=OFF`, this block has no effect. The registration receipt pins the edited CMake file.

The full build used GNU Fortran 13.3.0, CMake 3.31.6, Ninja 1.13, Release, ARW `EM_REAL`, `USE_MPI=OFF`, `USE_OPENMP=ON`, `USE_DOUBLE=OFF`, nesting `NONE`, and the recorded NetCDF installation. It built and installed WRF/RRTMGP. Compile-command inspection found `-fopenmp` on all 26 vendored RRTMGP Fortran objects, all seven adapter Fortran objects, and the radiation driver. Fresh installed-package consumers (`rrtmgp-only` and `core-plus`) configured, built, and ran without caller-supplied OpenMP flags. The vendor standalone project configured and built with OpenMP both off and on. The adapter OpenMP CTests passed 2/2 and column CTest passed 1/1.

Three one-minute WRF runs used the same RA37/MP27 frozen-optics mode-1 restart, two tiles, and a 512 MiB stack: one OpenMP worker, two workers, and two workers with a diagnostic GOMP interposer. Their 211-variable history files were byte-identical, including 61,252,177 numeric values and 1,342 attributes. An independent readback confirmed finite, unmasked, non-fill numeric data and the exact `2010-06-11_12:01:00` time. The interposer observed the radiation-driver OpenMP callback execute on workers 0 and 1 in a two-thread team, with balanced enter/exit events and both LW and SW calls in the callback.

These bounded results establish build/export integration and host-thread execution for this case. They do not establish MPI or GPU behavior, long-duration forecast behavior, physical accuracy, or a performance/speedup result. Failed setup attempts are retained in the build receipt and are explicitly classified as setup errors with corrected passing runs; they are not presented as model failures.

## Reproduction

The receipts retain the exact source and build hashes and logs. The tested OpenMP source was based on serial integration overlay `bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291` with this conditional CMake change. In the clean PR worktree the same change is represented by `patches/conditional-openmp-link.patch` over base `275b9e08dce14e198deaae410a287226cad06075`.

Use a fresh WRF checkout with its pinned submodules and the NetCDF prefix from `receipts/build/toolchain.cmake`. Configure as ARW/EM_REAL, Release, nesting NONE, MPI off, OpenMP on, single precision, allocatables on; use `receipts/build/configure.log` and `build-install.log` for exact observed toolchain settings and command output. Build/install WRF targets `wrf real ndown tc` and helper targets, then install. The consumer source and build/run receipts are under `consumers/` and `receipts/consumers/`. Standalone CTest and vendor off/on receipts are under `receipts/standalone/`.

Runtime scripts in `scripts/` are preserved with their source hashes in the index. Runtime preflights/results are receipts, not a request to rerun the case; the checkpoint and full model outputs are intentionally not included. The interposer source, analyzer, event log, proof, and gzip-compressed `objdump` disassembly for `__module_radiation_driver_MOD_radiation_driver._omp_fn.1` are under `probe/` and `receipts/runtime/omp2-probe/`. The disassembly is from the exact probed executable; its SHA-256 is listed in `evidence.json`.

Validate package payload hashes by running:

```sh
python3 scripts/verify_artifacts.py
```

The hash index omits itself to avoid a self-referential digest; its own SHA is recorded in the parent review message after finalization.
