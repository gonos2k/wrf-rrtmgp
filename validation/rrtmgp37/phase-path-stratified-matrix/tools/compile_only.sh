#!/usr/bin/env bash
set -euo pipefail
ROOT=/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP
BASE="$ROOT/build/udm-phase-path-sensitivity-work/ensemble-build"
HERE="$ROOT/build/udm-stratified-final-manifest/diagnostic-exe-v1"
NETCDF="$ROOT/build/deps/root/usr/lib/x86_64-linux-gnu"
mkdir -p "$HERE/obj"
cd "$HERE/obj"
/usr/bin/f95 -ffree-line-length-none -fcheck=bounds \
  -I"$BASE/rte_rrtmgp/modules" -I"$BASE/frozen_modules" \
  -c "$HERE/reference_column.f90" -o reference_column.f90.o
/usr/bin/f95 -Wl,-rpath,"$NETCDF" reference_column.f90.o -o reference_column \
  "$BASE/rte_rrtmgp/libwrf_rrtmgp.a" "$BASE/libtest_rrtmgp_frozen.a" \
  "$NETCDF/libnetcdff.so" "$NETCDF/libnetcdf.so"
sha256sum reference_column
