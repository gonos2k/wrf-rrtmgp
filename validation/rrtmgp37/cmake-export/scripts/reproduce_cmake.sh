#!/usr/bin/env bash
set -euo pipefail
: "${ROOT:?Set ROOT to the RRTMGP workspace root}"
: "${SRC:?Set SRC to the clean checkout with this five-file patch}"
PKG="$SRC/validation/rrtmgp37/cmake-export"
NETCDF="$ROOT/build/deps/netcdf"
BUILD="${BUILD:-$ROOT/build/repro-udm-cmake-export}"
INSTALL="${INSTALL:-$BUILD/install}"
cmake -S "$SRC/WRF" -B "$BUILD/wrf" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$PKG/receipts/cmake/toolchain-repro.cmake" \
  -DCMAKE_INSTALL_PREFIX="$INSTALL" -DCMAKE_BUILD_TYPE=Release \
  -DWRF_CORE=ARW -DWRF_CASE=EM_REAL -DWRF_NESTING=NONE \
  -DUSE_MPI=OFF -DUSE_OPENMP=OFF -DUSE_DOUBLE=OFF \
  -DnetCDF_ROOT="$NETCDF" -DnetCDF-Fortran_ROOT="$NETCDF"
cmake --build "$BUILD/wrf" --parallel 12 --target wrf real ndown tc
cmake --build "$BUILD/wrf" --parallel 12 --target diffwrf_int
cmake --build "$BUILD/wrf" --parallel 12
cmake --install "$BUILD/wrf"
for variant in rrtmgp-only core-plus; do
  cmake -S "$PKG/consumer/$variant" -B "$BUILD/consumer-$variant" -G Ninja \
    -DCMAKE_PREFIX_PATH="$INSTALL;$NETCDF" -DWRF_DIR="$INSTALL/lib/cmake/WRF"
  cmake --build "$BUILD/consumer-$variant" --parallel 2
  LD_LIBRARY_PATH="$NETCDF/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$BUILD/consumer-$variant/consumer"
done
