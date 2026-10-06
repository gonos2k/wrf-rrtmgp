# Current-source CMake integration

This change repairs the CMake path on current main, rather than importing the historical PR38 branch or relabeling its results. `wrf_rrtmgp` is exported with WRF Core; its Fortran modules are installed and its public include paths distinguish build and install usage. UDM diagnostic optional arrays accept both pointer and allocatable actual arrays, with WRF memory lower bounds retained. The six restart sentinel checks select `ALLOCATED` for allocatable storage and retain `ASSOCIATED` for pointer storage.

`LOCAL_VALIDATION.json` records the exact source commit/tree, GNU toolchain, installation, executable hashes and terminal process results. The fresh serial REAL32 `USE_ALLOCATABLES=ON` build at `45c640e` configured, built and installed successfully. It installed 27 RTE/RRTMGP `.mod` files. Two source-selected guard fixtures compiled and ran; two independent consumer projects configured and built against the installation and ran three executables. One of those executables is a documented optional-array language mirror. The core consumer references the actual installed driver interface/symbol without calling WRF physics. The consumers were rerun after fixing post-launch journal-failure cleanup and bounding the post-KILL wait; both attempts passed (four consumer configurations/builds and six consumer executions in total). A two-case process test covers a mocked journal failure and an actual Python timeout; it launches no compiler or model. Compiler include paths contained installed modules and external dependencies, without producer source or binary paths.

The installed executables also ran one ideal seed and one 60-second UDM37 SCM forecast. The startup-snow fixture preserved the background source radius and prepared 134.778076171875 micrometres for optics; the selected snow-only layer had positive LW contribution in all 16 bands and SW contribution above the numerical floor in all 14 bands. This run makes no engine4/pristine comparison.

Failures remain recorded: the first build omitted the standard WRF toolchain and failed preprocessing; the next build exposed six invalid `ASSOCIATED` calls on allocatable fields; both returned RC2. A runtime runner initially selected a nonexistent Python executable and launched no ideal/forecast process. The corrected runner used `/usr/bin/python3` and passed. None of these failures was overwritten with a success.

Reproduce with WRF's GNU serial toolchain (including `/lib/cpp`) and fresh build/install directories:

```sh
cmake -S WRF -B build/cmake-current/producer \
  -DCMAKE_TOOLCHAIN_FILE=/absolute/path/wrf_gnu_serial.cmake \
  -DCMAKE_INSTALL_PREFIX="$PWD/build/cmake-current/install" \
  -DWRF_CORE=ARW -DWRF_CASE=EM_SCM_XY -DUSE_ALLOCATABLES=ON \
  -DUSE_MPI=OFF -DUSE_OPENMP=OFF -DUSE_IPO=OFF -DFORCE_NETCDF_CLASSIC=ON
cmake --build build/cmake-current/producer --parallel 2
cmake --install build/cmake-current/producer
python3 WRF/test/rrtmgp/test_cmake_installed_consumers.py \
  --install-prefix "$PWD/build/cmake-current/install" \
  --output-dir "$PWD/build/cmake-current/consumers" \
  --forbidden-root "$PWD/WRF" --forbidden-root "$PWD/build/cmake-current/producer"
```

`validate-cmake-package.yml` adds fresh build/install, installed consumer and runtime-only SCM coverage. `validate-port.yml` runs the focused source guard fixture in both storage modes. An existing output directory is rejected to avoid silently reusing previous consumer results.

This is scoped engineering evidence. It does not close Nc/population/PSD meaning, published RFMIP strict differences, LBLRTM negative optical depths, general relocation, all toolchains or forecast accuracy. Historical evidence pins are unchanged. The optional interface ABI requires dependent objects to be rebuilt; the validation used a fresh build.

The first remote package job (run37442785026) failed during configuration before building WRF: the inherited Fortran dependency finder ignored Ubuntu multiarch library paths. The repair now honors every explicit `-L` directory from `nf-config --flibs` and the CMake library architecture suffix. Three inert configure-only cases pass (flat prefix, multiarch prefix, and a nonprefix link directory after other flags). The corrected original-source control passes the flat case and rejects the multiarch case. An earlier incomplete control omitted the companion C finder and is retained as a fixture-preparation failure. Empty library placeholders are never linked; these tests do not authenticate a real NetCDF library or execute a compiler/model. Remote real-library/full-build verification remains separate.
