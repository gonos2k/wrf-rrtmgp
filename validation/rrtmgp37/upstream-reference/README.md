# Independent RFMIP clear-sky validation

This validation record compares the official RFMIP clear-sky driver run in two builds: (1) the pinned upstream RTE+RRTMGP library and (2) the WRF-vendored CPU-only library. Both use the same official driver, input and gas coefficients. Each run is also checked against the pinned published reference files. This does not use the WRF adapter and does not directly validate WRF's g128/g112 configuration.

Pins: `earth-system-radiation/rte-rrtmgp@41c5fcd950fed09b8afe186dede266824eca7fd3` and `earth-system-radiation/rrtmgp-data@ea788bb39876948fa8d2c235665ccff19b4686b5`. The input has 1800 profiles. GNU Fortran 13.3.0 was used serially with `-O0 -ffree-line-length-none`; `RTE_USE_SP` was not defined, so `wp=c_double`. Output NetCDF flux variables are `float32`. Input, coefficients, sources, library/executable outputs and NetCDF outputs are hashed in `SHA256SUMS.txt`; detailed metrics are in `rfmip-comparison.json`.

At the upstream test tolerance (`atol=1e-5`, `rtol=0`), LW `rld` and `rlu` match published references exactly. SW `rsd` and `rsu` fail that unchanged tolerance with maximum absolute errors of `6.103515625e-4` and `1.8310546875e-4` W m-2. The WRF-vendored CPU backend is bitwise identical to the pinned upstream executable for all four arrays; it has the same SW residual. The published files identify `RTE-RRTMGP-181204`; whether the SW mismatch reflects source/reference-generation revision differences remains unresolved.

The WRF-vendored source declares the same upstream source pin and lists local changes in `WRF/external/rte_rrtmgp/SOURCE.json`: cloud reader field-name/diameter adaptation, a fatal callback, and CPU-only target directive guards. Exact equality here demonstrates execution agreement only for this clear-sky test case; it does not establish equivalence for every backend configuration.

## Reproduction

Run from the RRTMGP workspace root shown below, or set `WS` to that root. `NETCDF_INCLUDE` deliberately points at `build/deps/root/usr/include` (the include directory is not under the library directory).

```sh
cd /NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP
WS="$PWD"
ROOT="$WS/build/official-rrtmgp-reference"
WRF="$WS/build/pr-wrf-rrtmgp/WRF"
DEP="$WS/build/deps/root/usr/lib/x86_64-linux-gnu"
NETCDF_INCLUDE="$WS/build/deps/root/usr/include"
NETCDF_LIB="$DEP"
SOURCE="$ROOT/source"
DATA="$ROOT/data"
mkdir -p "$ROOT"

# Fresh checkouts at the exact pins. Skip clone if these pinned checkouts already exist.
if [ ! -d "$SOURCE/.git" ]; then
  git clone https://github.com/earth-system-radiation/rte-rrtmgp.git "$SOURCE"
fi
git -C "$SOURCE" checkout --detach 41c5fcd950fed09b8afe186dede266824eca7fd3
if [ ! -d "$DATA/.git" ]; then
  git clone https://github.com/earth-system-radiation/rrtmgp-data.git "$DATA"
fi
git -C "$DATA" checkout --detach ea788bb39876948fa8d2c235665ccff19b4686b5

# Build upstream libraries, then its unmodified RFMIP drivers/helper objects.
make -C "$SOURCE/build" FC=gfortran FCFLAGS="-O0 -ffree-line-length-none" \
  FCINCLUDE="-I$NETCDF_INCLUDE"
make -C "$SOURCE/examples/rfmip-clear-sky" \
  FC=gfortran FCFLAGS="-O0 -ffree-line-length-none" \
  FCINCLUDE="-I$NETCDF_INCLUDE -I$SOURCE/build" \
  LDFLAGS="-L$SOURCE/build -L$NETCDF_LIB" \
  RRTMGP_ROOT="$SOURCE" RRTMGP_DATA="$DATA" all

# Build the WRF-vendored CPU-only backend with the same serial optimization flags.
cmake -S "$WRF/external/rte_rrtmgp" -B "$ROOT/wrf-cpu-lib" \
  -DCMAKE_Fortran_COMPILER=gfortran \
  -DCMAKE_Fortran_FLAGS="-O0 -ffree-line-length-none" \
  -DNETCDF_INCLUDE_DIR="$NETCDF_INCLUDE" -DNETCDF_LIBRARY_DIR="$NETCDF_LIB"
cmake --build "$ROOT/wrf-cpu-lib" --target wrf_rrtmgp -j2

# Link the unchanged upstream driver/helper objects against the WRF-vendored archive.
EX="$SOURCE/examples/rfmip-clear-sky"
gfortran -O0 -ffree-line-length-none -o "$ROOT/rrtmgp_rfmip_lw_wrf_cpu" \
  "$EX/rrtmgp_rfmip_lw.o" "$EX/mo_simple_netcdf.o" "$EX/mo_rfmip_io.o" "$EX/mo_load_coefficients.o" \
  "$ROOT/wrf-cpu-lib/libwrf_rrtmgp.a" -L"$NETCDF_LIB" -Wl,-rpath,"$NETCDF_LIB" -lnetcdff -lnetcdf
gfortran -O0 -ffree-line-length-none -o "$ROOT/rrtmgp_rfmip_sw_wrf_cpu" \
  "$EX/rrtmgp_rfmip_sw.o" "$EX/mo_simple_netcdf.o" "$EX/mo_rfmip_io.o" "$EX/mo_load_coefficients.o" \
  "$ROOT/wrf-cpu-lib/libwrf_rrtmgp.a" -L"$NETCDF_LIB" -Wl,-rpath,"$NETCDF_LIB" -lnetcdff -lnetcdf

# The drivers overwrite files in their working directory; give each run writable copies.
mkdir -p "$ROOT/run-upstream" "$ROOT/run-wrf-cpu"
for d in run-upstream run-wrf-cpu; do cp "$DATA"/examples/rfmip-clear-sky/reference/*.nc "$ROOT/$d/"; done
INPUT="$DATA/examples/rfmip-clear-sky/inputs/multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc"
(cd "$ROOT/run-upstream" && LD_LIBRARY_PATH="$NETCDF_LIB" "$EX/rrtmgp_rfmip_lw" 8 "$INPUT" "$DATA/rrtmgp-gas-lw-g256.nc" 1 1 && LD_LIBRARY_PATH="$NETCDF_LIB" "$EX/rrtmgp_rfmip_sw" 8 "$INPUT" "$DATA/rrtmgp-gas-sw-g224.nc" 1)
(cd "$ROOT/run-wrf-cpu" && LD_LIBRARY_PATH="$NETCDF_LIB" "$ROOT/rrtmgp_rfmip_lw_wrf_cpu" 8 "$INPUT" "$DATA/rrtmgp-gas-lw-g256.nc" 1 1 && LD_LIBRARY_PATH="$NETCDF_LIB" "$ROOT/rrtmgp_rfmip_sw_wrf_cpu" 8 "$INPUT" "$DATA/rrtmgp-gas-sw-g224.nc" 1)

# Backend agreement and published-reference accuracy are distinct exit statuses.
python "$WS/build/pr-wrf-rrtmgp/validation/rrtmgp37/upstream-reference/compare_rfmip.py" \
  --upstream "$ROOT/run-upstream" --vendor "$ROOT/run-wrf-cpu" \
  --output "$ROOT/backend-comparison.json"
# Expected exit code 1 for the recorded SW reference residual; do not widen tolerance.
python "$WS/build/pr-wrf-rrtmgp/validation/rrtmgp37/upstream-reference/compare_rfmip.py" \
  --upstream "$ROOT/run-upstream" --vendor "$ROOT/run-wrf-cpu" \
  --published-reference "$DATA/examples/rfmip-clear-sky/reference" \
  --output "$ROOT/published-reference-comparison.json"
```

The upstream all-sky example was also tried without modifying its source. It fails on the pinned current cloud dataset because it requests `radice_lwr`, while the dataset provides `diamice_lwr`/`diamice_upr` and renamed optical fields. This is an unsupported all-sky loader check, separate from the clear-sky results above.

`SHA256SUMS.txt` retains the original scratch-artifact paths and hashes. It is not a checksum list for this publication directory: the published inventory corrects raw-GitHub URLs that previously had an extra `data/` component. `publication-manifest.json` records the original and published hashes and this metadata-only correction. The original experiment used vendored source from PR #10 (`ca33525`); it is not presented as a newly rebuilt PR #12 executable.

The checked-in comparator was run on the preserved outputs: backend comparison exits 0; adding the published references exits 1. Those outcomes are preserved separately in `rechecked-backend.json` and `rechecked-published-reference.json`.

## Production-resolution gas backend check

A further run uses gas LW g128/SW g112 with the same 1,800 RFMIP profiles, block size 8, pinned upstream driver and frozen libraries. All four flux arrays are finite and bitwise equal between upstream and vendored CPU builds. This aligns gas resolution with WRF, but still does not exercise the WRF adapter, host constants, clouds or precipitation. `g128-g112-comparison.json` records binaries, inputs, coefficients, outputs and labeled descriptive sensitivity versus g256/g224; `g128-g112-runs.json` retains every launch and per-stage output hash. The LW-stage SW files are still templates until the subsequent SW launch; final arrays are compared only after both phases complete.

The preserved `g128-g112-reproduce.sh` helper is specific to the recorded `/NHNHOME/WORKSPACE/...` workspace. For another checkout use the fresh-build `run_rfmip.sh` runner below. To recheck the preserved outputs, compare without high-resolution published reference files:

```sh
python "$WS/build/pr-wrf-rrtmgp/validation/rrtmgp37/upstream-reference/compare_rfmip.py" \
  --upstream "$ROOT/run-upstream-g128-g112" --vendor "$ROOT/run-wrf-cpu-g128-g112" \
  --output "$ROOT/g128-g112-backend-comparison.json"
```

The recorded maximum g128/g112–g256/g224 flux changes are 1.173/0.601 W m-2 for LW down/up and 2.156/0.813 W m-2 for SW down/up. Those are coefficient-resolution sensitivities, not accuracy pass/fail results. Individual 1.35–1.48 s launch wall times include setup/IO and are not a performance benchmark.

## Continuous independent backend check

`run_rfmip.sh NEW_BUILD_DIRECTORY` fetches and verifies both git pins, builds their unmodified RFMIP driver/helper objects and upstream library, separately builds the **current** vendored CPU library, checks the input/g128/g112 coefficient SHA256s, runs both engines and requires bitwise equality of all four finite flux arrays. It refuses existing build directories. NetCDF paths can be set with `NETCDF_INCLUDE_DIR` and `NETCDF_LIBRARY_DIR`; otherwise `nf-config`/`nc-config` supply them.

The fresh local execution passed with current vendored source (`fresh-build-g128-g112.json`). The independent-rfmip CI job repeats this build/run comparison and uploads fluxes, pins, sources/binaries/input hashes and status. It checks backend execution equivalence at production gas resolution; it does not claim published-reference accuracy for g128/g112. RFMIP supplies its official gas set and uses upstream default constants, so the WRF six-gas subset and WRF host constants are not exercised.
