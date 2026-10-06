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
for phase in lw sw; do
  gfortran -O0 -ffree-line-length-none -o "$work_dir/vendor-rfmip-$phase" \
    "$example_dir/rrtmgp_rfmip_$phase.o" "$example_dir/mo_simple_netcdf.o" \
    "$example_dir/mo_rfmip_io.o" "$example_dir/mo_load_coefficients.o" \
    "$work_dir/vendor/libwrf_rrtmgp.a" -L"$netcdf_lib" -Wl,-rpath,"$netcdf_lib" -lnetcdff -lnetcdf
done
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
    "$lw" 8 "$input" "$data_dir/rrtmgp-gas-lw-g128.nc" 1 1
    "$sw" 8 "$input" "$data_dir/rrtmgp-gas-sw-g112.nc" 1
  )
done
gfortran --version > "$work_dir/compiler.txt"
git -C "$repo_root" rev-parse HEAD > "$work_dir/vendor-checkout-head.txt"
(
  cd "$repo_root"
  rg --files WRF/external/rte_rrtmgp -g '*.F90' -g 'CMakeLists.txt' -g 'SOURCE.json' \
    | sort | xargs sha256sum
) > "$work_dir/VENDOR_SOURCE_SHA256SUMS.txt"
sha256sum "$work_dir/vendor/libwrf_rrtmgp.a" "$work_dir"/vendor-rfmip-* \
  "$example_dir/rrtmgp_rfmip_lw" "$example_dir/rrtmgp_rfmip_sw" \
  > "$work_dir/BINARY_SHA256SUMS.txt"
python3 "$repo_root/validation/rrtmgp37/upstream-reference/compare_rfmip.py" \
  --upstream "$work_dir/run-upstream" --vendor "$work_dir/run-vendor" \
  --output "$work_dir/backend-comparison.json"
