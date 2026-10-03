#!/usr/bin/env bash
set -euo pipefail
: "${ROOT:?Set ROOT to the RRTMGP workspace root}"
: "${SRC:?Set SRC to the clean checkout with this five-file patch}"
NETCDF="$ROOT/build/deps/netcdf"
BUILD="${BUILD:-$ROOT/build/repro-udm-rrtmgp-columns}"
cmake -S "$SRC/WRF/test/rrtmgp" -B "$BUILD" -G Ninja \
  -DCMAKE_PREFIX_PATH="$NETCDF" -DRRTMGP_DATA_DIR="$SRC/WRF/run"
cmake --build "$BUILD" --parallel 12
LD_LIBRARY_PATH="$NETCDF/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  ctest --test-dir "$BUILD" -R '^wrf_rrtmgp_columns$' --output-on-failure
