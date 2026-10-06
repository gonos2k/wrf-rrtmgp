#!/bin/sh
set -eu
# Reproduce the production-resolution RFMIP clear-sky paired run
cd /NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP
ROOT="$PWD/build/official-rrtmgp-reference"
DATA="$ROOT/data"
EX="$ROOT/source/examples/rfmip-clear-sky"
NETCDF_LIB="$PWD/build/deps/root/usr/lib/x86_64-linux-gnu"
INPUT="$DATA/examples/rfmip-clear-sky/inputs/multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc"
LW_COEFF="$DATA/rrtmgp-gas-lw-g128.nc"
SW_COEFF="$DATA/rrtmgp-gas-sw-g112.nc"
mkdir -p "$ROOT/run-upstream-g128-g112" "$ROOT/run-wrf-cpu-g128-g112"
for d in run-upstream-g128-g112 run-wrf-cpu-g128-g112; do cp "$DATA"/examples/rfmip-clear-sky/reference/*.nc "$ROOT/$d/"; done

(cd "$ROOT/run-upstream-g128-g112" && LD_LIBRARY_PATH="$NETCDF_LIB" /NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/official-rrtmgp-reference/source/examples/rfmip-clear-sky/rrtmgp_rfmip_lw 8 "$INPUT" "$LW_COEFF" 1 1 && LD_LIBRARY_PATH="$NETCDF_LIB" /NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/official-rrtmgp-reference/source/examples/rfmip-clear-sky/rrtmgp_rfmip_sw 8 "$INPUT" "$SW_COEFF" 1)
(cd "$ROOT/run-wrf-cpu-g128-g112" && LD_LIBRARY_PATH="$NETCDF_LIB" /NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/official-rrtmgp-reference/rrtmgp_rfmip_lw_wrf_cpu 8 "$INPUT" "$LW_COEFF" 1 1 && LD_LIBRARY_PATH="$NETCDF_LIB" /NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/official-rrtmgp-reference/rrtmgp_rfmip_sw_wrf_cpu 8 "$INPUT" "$SW_COEFF" 1)

# See g128-g112-comparison.json for same-resolution equality and descriptive-only high/low sensitivity.
