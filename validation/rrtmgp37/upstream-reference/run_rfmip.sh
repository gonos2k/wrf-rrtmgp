#!/usr/bin/env bash
# Independent pinned upstream versus current vendored CPU library at WRF gas resolution.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
work_dir="${1:?usage: run_rfmip.sh NEW_BUILD_DIRECTORY}"
mkdir -p "$(dirname "$work_dir")"
work_dir="$(cd "$(dirname "$work_dir")" && pwd)/$(basename "$work_dir")"
if [[ -e "$work_dir" ]]; then
  echo "Refusing to reuse $work_dir; select a fresh build directory" >&2
  exit 2
fi
mkdir "$work_dir"
exec > >(tee "$work_dir/run.log") 2>&1
source_pin=41c5fcd950fed09b8afe186dede266824eca7fd3
data_pin=ea788bb39876948fa8d2c235665ccff19b4686b5
for item in source data; do
  if [[ "$item" == source ]]; then
    remote=https://github.com/earth-system-radiation/rte-rrtmgp.git
    pin="$source_pin"
  else
    remote=https://github.com/earth-system-radiation/rrtmgp-data.git
    pin="$data_pin"
  fi
  git init -q "$work_dir/$item"
  git -C "$work_dir/$item" fetch --depth 1 "$remote" "$pin"
  git -C "$work_dir/$item" checkout -q --detach FETCH_HEAD
  [[ "$(git -C "$work_dir/$item" rev-parse HEAD)" == "$pin" ]]
done
source_dir="$work_dir/source"
data_dir="$work_dir/data"
netcdf_include="${NETCDF_INCLUDE_DIR:-$(nf-config --includedir)}"
netcdf_lib="${NETCDF_LIBRARY_DIR:-$(nc-config --libdir)}"
export LD_LIBRARY_PATH="$netcdf_lib:${LD_LIBRARY_PATH:-}"
make -C "$source_dir/build" FC=gfortran FCFLAGS='-O0 -ffree-line-length-none' \
  FCINCLUDE="-I$netcdf_include"
example_dir="$source_dir/examples/rfmip-clear-sky"
make -C "$example_dir" FC=gfortran FCFLAGS='-O0 -ffree-line-length-none' \
  FCINCLUDE="-I$netcdf_include -I$source_dir/build" \
  LDFLAGS="-L$source_dir/build -L$netcdf_lib" \
  RRTMGP_ROOT="$source_dir" RRTMGP_DATA="$data_dir" all
cmake -S "$repo_root/WRF/external/rte_rrtmgp" -B "$work_dir/vendor" \
  -DCMAKE_Fortran_COMPILER=gfortran -DCMAKE_Fortran_FLAGS='-O0 -ffree-line-length-none' \
  -DNETCDF_INCLUDE_DIR="$netcdf_include" -DNETCDF_LIBRARY_DIR="$netcdf_lib"
cmake --build "$work_dir/vendor" --target wrf_rrtmgp --parallel 2
vendor_client="$work_dir/vendor-rfmip-client"
mkdir -p "$vendor_client/src" "$vendor_client/obj" "$vendor_client/mod"
# The upstream make-built .mod/.o files are not ABI compatible with the
# vendored modules. Compile fresh copies of the same pinned client sources in
# an isolated tree with only the vendor module directory on the module path.
cp "$source_dir/examples/mo_simple_netcdf.F90" \
  "$source_dir/examples/mo_load_coefficients.F90" \
  "$source_dir/examples/rfmip-clear-sky/mo_rfmip_io.F90" \
  "$source_dir/examples/rfmip-clear-sky/rrtmgp_rfmip_lw.F90" \
  "$source_dir/examples/rfmip-clear-sky/rrtmgp_rfmip_sw.F90" \
  "$vendor_client/src/"
vendor_modules="$work_dir/vendor/modules"
(
  cd "$vendor_client/obj"
  flags=(-O0 -ffree-line-length-none -I"$netcdf_include" -I"$vendor_modules" -I"$vendor_client/mod" -J"$vendor_client/mod")
  gfortran "${flags[@]}" -c "$vendor_client/src/mo_simple_netcdf.F90" -o mo_simple_netcdf.o
  gfortran "${flags[@]}" -c "$vendor_client/src/mo_rfmip_io.F90" -o mo_rfmip_io.o
  gfortran "${flags[@]}" -c "$vendor_client/src/mo_load_coefficients.F90" -o mo_load_coefficients.o
  gfortran "${flags[@]}" -c "$vendor_client/src/rrtmgp_rfmip_lw.F90" -o rrtmgp_rfmip_lw.o
  gfortran "${flags[@]}" -c "$vendor_client/src/rrtmgp_rfmip_sw.F90" -o rrtmgp_rfmip_sw.o
  for phase in lw sw; do
    gfortran -O0 -ffree-line-length-none -o "$work_dir/vendor-rfmip-$phase" \
      "rrtmgp_rfmip_$phase.o" mo_simple_netcdf.o mo_rfmip_io.o mo_load_coefficients.o \
      "$work_dir/vendor/libwrf_rrtmgp.a" -L"$netcdf_lib" -Wl,-rpath,"$netcdf_lib" -lnetcdff -lnetcdf
  done
)
sha256sum "$vendor_client/src/"*.F90 "$vendor_client/obj/"*.o "$vendor_client/mod/"*.mod \
  "$work_dir/vendor-rfmip-lw" "$work_dir/vendor-rfmip-sw" > "$work_dir/VENDOR_CLIENT_SHA256SUMS.txt"
input="$data_dir/examples/rfmip-clear-sky/inputs/multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc"
printf '%s  %s\n' \
  b8dc05d7cd2e0e6354b4a6198771ddf3bc09f18d72b49f20a41e2024e2fd51f4 "$input" \
  70ad65d116531122660318e5da2a2af9db74b425916202860e9527ef2375b8f6 "$data_dir/rrtmgp-gas-lw-g128.nc" \
  361ed541324068ded28a275a4dd757bcaa0a845aebefa630f43a04678668fe62 "$data_dir/rrtmgp-gas-sw-g112.nc" \
  > "$work_dir/INPUT_SHA256SUMS.txt"
sha256sum -c "$work_dir/INPUT_SHA256SUMS.txt"
for engine in upstream vendor; do
  run_dir="$work_dir/run-$engine"
  mkdir "$run_dir"
  cp "$data_dir"/examples/rfmip-clear-sky/reference/*.nc "$run_dir/"
  if [[ "$engine" == upstream ]]; then
    lw="$example_dir/rrtmgp_rfmip_lw"
    sw="$example_dir/rrtmgp_rfmip_sw"
  else
    lw="$work_dir/vendor-rfmip-lw"
    sw="$work_dir/vendor-rfmip-sw"
  fi
  (
    cd "$run_dir"
    lw_started_ns="$(date +%s%N)"
    "$lw" 8 "$input" "$data_dir/rrtmgp-gas-lw-g128.nc" 1 1 > lw.log 2>&1
    if grep -Eiq 'STOP|ERROR|FATAL|segmentation fault|floating-point exception|k-distribution file isn.t LW' lw.log; then
      cat lw.log >&2; echo "$engine LW driver did not complete cleanly" >&2; exit 1
    fi
    grep -q 'Calculation uses RFMIP gases:' lw.log
    python3 - "$lw_started_ns" <<'PY'
from pathlib import Path
import sys
started = int(sys.argv[1])
for name in ('rld_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc',
             'rlu_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'):
    p = Path(name)
    if not p.is_file() or p.stat().st_size == 0:
        raise SystemExit(f'LW output was not written: {name}')
    if p.stat().st_mtime_ns <= started:
        raise SystemExit(f'LW output timestamp shows no fresh write: {name}')
PY
    sw_started_ns="$(date +%s%N)"
    "$sw" 8 "$input" "$data_dir/rrtmgp-gas-sw-g112.nc" 1 > sw.log 2>&1
    if grep -Eiq 'STOP|ERROR|FATAL|segmentation fault|floating-point exception|k-distribution file isn.t LW' sw.log; then
      cat sw.log >&2; echo "$engine SW driver did not complete cleanly" >&2; exit 1
    fi
    grep -q 'Calculation uses RFMIP gases:' sw.log
    python3 - "$sw_started_ns" <<'PY'
from pathlib import Path
import sys
started = int(sys.argv[1])
for name in ('rsd_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc',
             'rsu_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'):
    p = Path(name)
    if not p.is_file() or p.stat().st_size == 0:
        raise SystemExit(f'SW output was not written: {name}')
    if p.stat().st_mtime_ns <= started:
        raise SystemExit(f'SW output timestamp shows no fresh write: {name}')
PY
  )
done
gfortran --version > "$work_dir/compiler.txt"
git -C "$repo_root" rev-parse HEAD > "$work_dir/vendor-checkout-head.txt"
(
  cd "$repo_root"
  rg --files WRF/external/rte_rrtmgp -g '*.F90' -g 'CMakeLists.txt' -g 'SOURCE.json' \
    | sort | xargs sha256sum
) > "$work_dir/VENDOR_SOURCE_SHA256SUMS.txt"
sha256sum "$work_dir/vendor/libwrf_rrtmgp.a" "$work_dir/vendor-rfmip-lw" "$work_dir/vendor-rfmip-sw" \
  "$example_dir/rrtmgp_rfmip_lw" "$example_dir/rrtmgp_rfmip_sw" \
  > "$work_dir/BINARY_SHA256SUMS.txt"
python3 "$repo_root/validation/rrtmgp37/upstream-reference/compare_rfmip.py" \
  --upstream "$work_dir/run-upstream" --vendor "$work_dir/run-vendor" \
  --output "$work_dir/backend-comparison.json"
