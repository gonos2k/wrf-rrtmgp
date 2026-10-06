#!/usr/bin/env bash
# Reproduce the WRF Shinhong dependency race using original WRF Fortran sources.
# Usage: reproduce.sh <configured-WRF-root> <new-output-directory>
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR/../../.." rev-parse --show-toplevel)
BASE_COMMIT=361c05ad36c149dc7e9d700fa80fc47ea8843d60
TEMPLATE=${1:?pass a configured WRF root containing configure.wrf and tools/standard.exe}
OUT=${2:?pass a new output directory; existing output is never overwritten}
TEMPLATE=$(cd "$TEMPLATE" && pwd)
if [[ -e "$OUT" ]]; then
  echo "Refusing existing output directory: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT/bin"
OUT=$(cd "$OUT" && pwd)
cat > "$OUT/bin/gfortran" <<'SHIM'
#!/bin/sh
# Deterministically expose the missing dependency by delaying only the module
# producer's Fortran compile. All compiler invocations use the same real gfortran.
for arg in "$@"; do
  case "$arg" in
    *ccpp_kind_types.f90) sleep 3 ;;
  esac
done
exec /usr/bin/gfortran "$@"
SHIM
chmod +x "$OUT/bin/gfortran"

run_case() {
  local variant=$1 graph=$2 target=$3
  local case_dir="$OUT/$variant-$graph"
  mkdir -p "$case_dir/WRF/phys/physics_mmm" "$case_dir/WRF/main"
  cp "$REPO_ROOT/WRF/phys/Makefile" "$case_dir/WRF/phys/Makefile"
  cp "$REPO_ROOT/WRF/phys/ccpp_kind_types.F" "$case_dir/WRF/phys/ccpp_kind_types.F"
  cp "$REPO_ROOT/WRF/phys/module_bl_shinhong.F" "$case_dir/WRF/phys/module_bl_shinhong.F"
  cp "$REPO_ROOT/WRF/phys/physics_mmm/bl_shinhong.F90" "$case_dir/WRF/phys/physics_mmm/bl_shinhong.F90"
  cp "$TEMPLATE/configure.wrf" "$case_dir/WRF/configure.wrf"
  if [[ "$variant" == baseline ]]; then
    git -C "$REPO_ROOT" show "$BASE_COMMIT:WRF/main/depend.common" > "$case_dir/WRF/main/depend.common"
  else
    cp "$REPO_ROOT/WRF/main/depend.common" "$case_dir/WRF/main/depend.common"
  fi
  local log="$OUT/$variant-$graph.log"
  local status=0
  (cd "$case_dir/WRF/phys" && PATH="$OUT/bin:$PATH" make -j2 \
    WRF_SRC_ROOT_DIR="$TEMPLATE" SFC="$OUT/bin/gfortran" \
    MODULE_DIRS='-I. -I../frame -I../share' "$target") > "$log" 2>&1 || status=$?
  if [[ "$variant" == baseline ]]; then
    if [[ $status -eq 0 ]] || ! grep -q 'Cannot open module file.*ccpp_kind_types.mod' "$log"; then
      echo "Expected missing-module failure not reproduced: $variant $graph (status=$status)" >&2
      exit 1
    fi
    echo "EXPECTED_FAILURE $variant $graph: status $status, missing ccpp_kind_types.mod"
  else
    if [[ $status -ne 0 ]]; then
      echo "Fixed dependency target failed: $variant $graph (status=$status)" >&2
      tail -60 "$log" >&2
      exit 1
    fi
    echo "PASS $variant $graph"
  fi
}

run_case baseline wrapper-fanout module_bl_shinhong.o
run_case fixed wrapper-fanout module_bl_shinhong.o
run_case baseline direct-target physics_mmm/bl_shinhong.o
run_case fixed direct-target physics_mmm/bl_shinhong.o
