#!/usr/bin/env bash
# Independent pinned all-sky band-cloud backend validation.
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
prepared="${1:?usage: run_allsky.sh PREPARED_RFMIP_BUILD_DIR [FRESH_OUTPUT_DIR]}"
prepared="$(cd "$prepared" && pwd)"
if [[ ! -d "$prepared/source/.git" || ! -d "$prepared/data/.git" || ! -f "$prepared/vendor/libwrf_rrtmgp.a" ]]; then
  echo "prepared directory must contain source/, data/, and vendor/libwrf_rrtmgp.a: $prepared" >&2
  exit 2
fi
if [[ $# -ge 2 ]]; then
  output="$2"; mkdir -p "$(dirname "$output")"
  output="$(cd "$(dirname "$output")" && pwd)/$(basename "$output")"
else
  output="$prepared/allsky"
fi
[[ ! -e "$output" ]] || { echo "Refusing to reuse output directory: $output" >&2; exit 2; }
mkdir -p "$output"
exec > >(tee "$output/run.log") 2>&1

source_pin=41c5fcd950fed09b8afe186dede266824eca7fd3
data_pin=ea788bb39876948fa8d2c235665ccff19b4686b5
cloud_sw_sha=7671835992a45afe66244b591a02c0b3df73d7d59ecb746bbffd9763497651cd
cloud_lw_sha=09d6704c5b863b4c3ceb417d20bb3076ec492e6bf2dfbcc9f3c5996a3706f0b0
source="$prepared/source"; data="$prepared/data"
vendor_archive="$prepared/vendor/libwrf_rrtmgp.a"
[[ "$(git -C "$source" rev-parse HEAD)" == "$source_pin" ]]
[[ "$(git -C "$data" rev-parse HEAD)" == "$data_pin" ]]
[[ -f "$prepared/BINARY_SHA256SUMS.txt" ]] || {
  echo 'prepared run is missing BINARY_SHA256SUMS.txt; cannot verify vendor archive provenance' >&2; exit 2; }
vendor_expected="$(awk -v archive="$vendor_archive" '$2 == archive {print $1}' "$prepared/BINARY_SHA256SUMS.txt")"
vendor_actual="$(sha256sum "$vendor_archive" | awk '{print $1}')"
[[ -n "$vendor_expected" && "$vendor_actual" == "$vendor_expected" ]] || {
  echo 'vendor archive does not match the prepared RFMIP build checksum manifest' >&2; exit 1; }
git -C "$source" diff --quiet HEAD --
git -C "$source" diff --cached --quiet
git -C "$data" diff --quiet HEAD --
git -C "$data" diff --cached --quiet
for item in "$cloud_sw_sha  $data/rrtmgp-clouds-sw-bnd.nc" "$cloud_lw_sha  $data/rrtmgp-clouds-lw-bnd.nc"; do
  expected="${item%%  *}"; path="${item#*  }"
  [[ "$(sha256sum "$path" | awk '{print $1}')" == "$expected" ]] || { echo "checksum mismatch: $path" >&2; exit 1; }
done
for item in "$source/build/librrtmgp.a" "$source/build/librte.a" \
  "$source/examples/all-sky/mo_load_cloud_coefficients.F90" \
  "$data/rrtmgp-clouds-sw-bnd.nc" "$data/rrtmgp-clouds-lw-bnd.nc" \
  "$data/rrtmgp-gas-sw-g112.nc" "$data/rrtmgp-gas-lw-g128.nc"; do
  [[ -f "$item" ]] || { echo "missing prepared input: $item" >&2; exit 1; }
done
python3 - "$data" "$output" <<'PY'
import json, sys
from pathlib import Path
import netCDF4
import numpy as np
data, output = map(Path, sys.argv[1:])
schema = {}
for phase, gas_name, cloud_name, nband, ngpt in (
    ('sw', 'rrtmgp-gas-sw-g112.nc', 'rrtmgp-clouds-sw-bnd.nc', 14, 112),
    ('lw', 'rrtmgp-gas-lw-g128.nc', 'rrtmgp-clouds-lw-bnd.nc', 16, 128),
):
    with netCDF4.Dataset(data/gas_name) as gas, netCDF4.Dataset(data/cloud_name) as cloud:
        if gas.dimensions['bnd'].size != nband or gas.dimensions['gpt'].size != ngpt:
            raise SystemExit(f'{phase}: unexpected gas bands/g-points')
        if cloud.dimensions['nband'].size != nband:
            raise SystemExit(f'{phase}: cloud LUT nband does not match gas bnd')
        expected = {
            'extliq': ('nband', 'nsize_liq'), 'ssaliq': ('nband', 'nsize_liq'),
            'asyliq': ('nband', 'nsize_liq'),
            'extice': ('nrghice', 'nband', 'nsize_ice'),
            'ssaice': ('nrghice', 'nband', 'nsize_ice'),
            'asyice': ('nrghice', 'nband', 'nsize_ice'),
        }
        expected_units = {name: ('m2/g' if name.startswith('ext') else 'unitless') for name in expected}
        expected_units.update({name: 'microns' for name in ('radliq_lwr','radliq_upr','diamice_lwr','diamice_upr')})
        expected_units['bnd_limits_wavenumber'] = 'cm-1'
        for name, units in expected_units.items():
            if getattr(cloud.variables[name], 'units', None) != units:
                raise SystemExit(f'{phase}:{name}: unexpected LUT units')
        for name, dims in expected.items():
            if cloud.variables[name].dimensions != dims:
                raise SystemExit(f'{phase}:{name}: unexpected dimensions {cloud.variables[name].dimensions}')
            values = np.asarray(cloud.variables[name][:])
            if not np.isfinite(values).all():
                raise SystemExit(f'{phase}:{name}: nonfinite coefficients')
        if not np.array_equal(gas.variables['bnd_limits_wavenumber'][:], cloud.variables['bnd_limits_wavenumber'][:]):
            raise SystemExit(f'{phase}: cloud and gas band edges differ')
        schema[phase] = {
            'gas_dimensions': {k: gas.dimensions[k].size for k in ('bnd','gpt')},
            'cloud_dimensions': {k: cloud.dimensions[k].size for k in ('nband','nsize_liq','nsize_ice','nrghice')},
            'cloud_variables': {n: list(cloud.variables[n].dimensions) for n in expected},
            'axis_values_microns': {n: float(cloud.variables[n][...]) for n in ('radliq_lwr','radliq_upr','diamice_lwr','diamice_upr')},
            'band_edges_match_gas': True,
            'verified_cloud_units': expected_units,
        }
(output/'band-input-schema.json').write_text(json.dumps(schema, indent=2)+'\n')
PY

netcdf_include="${NETCDF_INCLUDE_DIR:-}"
netcdf_lib="${NETCDF_LIBRARY_DIR:-}"
if [[ -z "$netcdf_include" ]]; then
  if command -v nf-config >/dev/null 2>&1; then
    netcdf_include="$(nf-config --includedir)"
  else
    netcdf_include="$(sed -n 's/^NETCDF_INCLUDE_DIR:[^=]*=//p' "$prepared/vendor/CMakeCache.txt" | head -1)"
  fi
fi
if [[ -z "$netcdf_lib" ]]; then
  if command -v nc-config >/dev/null 2>&1; then
    netcdf_lib="$(nc-config --libdir)"
  else
    netcdf_lib="$(sed -n 's/^NETCDF_LIBRARY_DIR:[^=]*=//p' "$prepared/vendor/CMakeCache.txt" | head -1)"
  fi
fi
[[ -d "$netcdf_include" && -d "$netcdf_lib" ]] || {
  echo 'NetCDF paths unavailable; set NETCDF_INCLUDE_DIR and NETCDF_LIBRARY_DIR' >&2; exit 2; }
export LD_LIBRARY_PATH="$netcdf_lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# Preserve the original pinned all-sky loader failure for both band files in
# a separate scratch copy before adapting any source strings.
original_source="$output/source-original"
original_example="$original_source/examples/all-sky"
mkdir -p "$original_example"
cp "$source/examples/all-sky/Makefile" "$original_example/"
cp "$source/examples/all-sky/"*.F90 "$original_example/"
cp "$source/examples/mo_simple_netcdf.F90" "$source/examples/mo_load_coefficients.F90" \
  "$original_source/examples/"
make -C "$original_example" FC=gfortran FCFLAGS='-O0 -ffree-line-length-none' \
  FCINCLUDE="-I$netcdf_include -I$source/build" \
  LDFLAGS="-L$source/build -L$netcdf_lib -Wl,-rpath,$netcdf_lib" \
  RRTMGP_ROOT="$source" RRTMGP_DATA="$data" all
for phase in sw lw; do
  run_dir="$output/original-band-$phase"; mkdir "$run_dir"
  if [[ "$phase" == sw ]]; then
    gas="$data/rrtmgp-gas-sw-g112.nc"; cloud="$data/rrtmgp-clouds-sw-bnd.nc"; out=sw-g112.nc
  else
    gas="$data/rrtmgp-gas-lw-g128.nc"; cloud="$data/rrtmgp-clouds-lw-bnd.nc"; out=lw-g128.nc
  fi
  if (cd "$run_dir" && "$original_example/rrtmgp_allsky" 24 72 1 "$out" "$gas" "$cloud") \
       > "$run_dir/original-run.log" 2>&1; then
    echo "unmodified loader unexpectedly accepted $phase band data" >&2; exit 1
  fi
  grep -F "read_field: can't find variable radice_lwr" "$run_dir/original-run.log"
done

scratch_source="$output/source"; scratch_example="$scratch_source/examples/all-sky"
mkdir -p "$scratch_example"
cp "$source/examples/all-sky/Makefile" "$scratch_example/"
cp "$source/examples/all-sky/"*.F90 "$scratch_example/"
cp "$source/examples/mo_simple_netcdf.F90" "$source/examples/mo_load_coefficients.F90" "$scratch_source/examples/"

python3 - "$source/examples/all-sky/mo_load_cloud_coefficients.F90" "$scratch_example/mo_load_cloud_coefficients.F90" "$output" <<'PY'
import difflib, hashlib, json, sys
from pathlib import Path
original, adapted, outdir = map(Path, sys.argv[1:])
source = original.read_text()
replacements = {
    "read_field(ncid, 'radice_lwr')": "read_field(ncid, 'diamice_lwr')",
    "read_field(ncid, 'radice_upr')": "read_field(ncid, 'diamice_upr')",
    "read_field(ncid, 'lut_extliq'": "read_field(ncid, 'extliq'",
    "read_field(ncid, 'lut_ssaliq'": "read_field(ncid, 'ssaliq'",
    "read_field(ncid, 'lut_asyliq'": "read_field(ncid, 'asyliq'",
    "read_field(ncid, 'lut_extice'": "read_field(ncid, 'extice'",
    "read_field(ncid, 'lut_ssaice'": "read_field(ncid, 'ssaice'",
    "read_field(ncid, 'lut_asyice'": "read_field(ncid, 'asyice'",
}
patched = source
for old, new in replacements.items():
    n = patched.count(old)
    if n != 1: raise SystemExit(f"expected exactly one {old!r}, found {n}")
    patched = patched.replace(old, new)
if len(replacements) != 8: raise SystemExit("expected exactly eight dataset-string substitutions")
adapted.write_text(patched)
diff = ''.join(difflib.unified_diff(source.splitlines(True), patched.splitlines(True), fromfile=str(original), tofile=str(adapted)))
(outdir / 'loader-only-adaptation.diff').write_text(diff)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
(outdir / 'loader-adaptation.json').write_text(json.dumps({
    'original_path': str(original.resolve()), 'original_sha256': sha(original),
    'adapted_path': str(adapted.resolve()), 'adapted_sha256': sha(adapted),
    'diff_path': str((outdir / 'loader-only-adaptation.diff').resolve()),
    'diff_sha256': hashlib.sha256(diff.encode()).hexdigest(),
    'replacement_map': replacements, 'total_replacements': len(replacements),
    'numerical_or_dimension_changes': 0,
}, indent=2) + '\n')
PY

make -C "$scratch_example" FC=gfortran FCFLAGS='-O0 -ffree-line-length-none' \
  FCINCLUDE="-I$netcdf_include -I$source/build" \
  LDFLAGS="-L$source/build -L$netcdf_lib -Wl,-rpath,$netcdf_lib" \
  RRTMGP_ROOT="$source" RRTMGP_DATA="$data" all
objects=("$scratch_example/rrtmgp_allsky.o" "$scratch_example/mo_simple_netcdf.o" \
  "$scratch_example/mo_load_coefficients.o" "$scratch_example/mo_load_cloud_coefficients.o" \
  "$scratch_example/mo_load_aerosol_coefficients.o")
gfortran -O0 -ffree-line-length-none -o "$output/rrtmgp_allsky_vendor" "${objects[@]}" \
  -L"$netcdf_lib" -Wl,-rpath,"$netcdf_lib" -Wl,-Map,"$output/vendor-link.map" \
  "$vendor_archive" -lnetcdff -lnetcdf
cp "$scratch_example/rrtmgp_allsky" "$output/rrtmgp_allsky_upstream"
grep -q 'libwrf_rrtmgp.a(mo_cloud_optics_rrtmgp.F90.o)' "$output/vendor-link.map"
grep -q 'libwrf_rrtmgp.a(mo_aerosol_optics_rrtmgp_merra.F90.o)' "$output/vendor-link.map"
if printf '%s\n' "${objects[@]}" | grep -Eq 'mo_cloud_optics_rrtmgp\.o|mo_aerosol_optics_rrtmgp_merra\.o'; then
  echo 'upstream cloud/aerosol frontend object unexpectedly included in vendor link' >&2; exit 1
fi
nm -A "$output/rrtmgp_allsky_vendor" > "$output/vendor-symbols.txt"
grep -E '__mo_(cloud_optics_rrtmgp_MOD_(cloud_optics|load_lut)|aerosol_optics_rrtmgp_merra_MOD_(aerosol_optics|load_lut))' \
  "$output/vendor-symbols.txt" > "$output/vendor-frontend-symbol-evidence.txt"
[[ "$(wc -l < "$output/vendor-frontend-symbol-evidence.txt")" -ge 4 ]]

for engine in upstream vendor; do
  run_dir="$output/run-$engine"; mkdir "$run_dir"
  binary="$output/rrtmgp_allsky_$engine"
  ( cd "$run_dir"
    "$binary" 24 72 1 sw-g112.nc "$data/rrtmgp-gas-sw-g112.nc" "$data/rrtmgp-clouds-sw-bnd.nc"
    "$binary" 24 72 1 lw-g128.nc "$data/rrtmgp-gas-lw-g128.nc" "$data/rrtmgp-clouds-lw-bnd.nc"
  )
done

vendor_build_head="$(cat "$prepared/vendor-checkout-head.txt" 2>/dev/null || git -C "$repo_root" rev-parse HEAD)"
git -C "$repo_root" diff --quiet "$vendor_build_head" HEAD -- WRF/external/rte_rrtmgp || {
  echo 'vendored source differs since recorded prepared build checkout' >&2; exit 1; }
git -C "$repo_root" diff --quiet HEAD -- WRF/external/rte_rrtmgp || {
  echo 'vendored source has uncommitted changes relative to checkout' >&2; exit 1; }
git -C "$repo_root" diff --cached --quiet HEAD -- WRF/external/rte_rrtmgp || {
  echo 'vendored source has staged changes relative to checkout' >&2; exit 1; }
git -C "$repo_root" ls-files -z WRF/external/rte_rrtmgp | xargs -0 sha256sum > "$output/vendor-source-sha256.txt"
upstream_sources=(
  "$source/examples/all-sky/rrtmgp_allsky.F90"
  "$source/examples/all-sky/mo_load_cloud_coefficients.F90"
  "$source/examples/all-sky/mo_load_aerosol_coefficients.F90"
  "$source/examples/mo_simple_netcdf.F90"
  "$source/examples/mo_load_coefficients.F90"
  "$source/rrtmgp-frontend/mo_cloud_optics_rrtmgp.F90"
  "$source/rrtmgp-frontend/mo_aerosol_optics_rrtmgp_merra.F90"
)
sha256sum "${upstream_sources[@]}" > "$output/upstream-source-sha256.txt"
sha256sum "$source/build/"*.mod > "$output/upstream-module-sha256.txt"
sha256sum "${objects[@]}" "$output/rrtmgp_allsky_upstream" "$output/rrtmgp_allsky_vendor" \
  > "$output/compiled-artifact-sha256.txt"
sha256sum "$source/build/librrtmgp.a" "$source/build/librte.a" "$vendor_archive" \
  "$data/rrtmgp-clouds-sw-bnd.nc" "$data/rrtmgp-clouds-lw-bnd.nc" \
  "$data/rrtmgp-gas-sw-g112.nc" "$data/rrtmgp-gas-lw-g128.nc" > "$output/input-library-data-sha256.txt"
gfortran --version > "$output/compiler.txt"

python3 - "$prepared" "$output" "$source_pin" "$data_pin" "$vendor_build_head" "$repo_root" \
  "$netcdf_include" "$netcdf_lib" "$script_dir/run_allsky.sh" "$script_dir/compare_allsky.py" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
prepared, output, source_pin, data_pin, vendor_head, repo = map(Path, sys.argv[1:7])
netcdf_include, netcdf_lib = sys.argv[7:9]
runner_path, comparator_path = map(Path, sys.argv[9:11])
prepared, output, repo = prepared.resolve(), output.resolve(), repo.resolve()
runner_path, comparator_path = runner_path.resolve(), comparator_path.resolve()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
source, data = prepared/'source', prepared/'data'
adapt = json.loads((output/'loader-adaptation.json').read_text())
report = {
 'source_pin': str(source_pin), 'data_pin': str(data_pin), 'prepared_build_dir': str(prepared),
 'output_dir': str(output), 'prepared_vendor_checkout_head': str(vendor_head),
 'repository_checkout_head': subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
 'validation_scripts': {
   'runner': {'path':str(runner_path),'sha256':sha(runner_path)},
   'comparator': {'path':str(comparator_path),'sha256':sha(comparator_path)},
 },
 'source_files': {
   'allsky_driver': {'path':str(source/'examples/all-sky/rrtmgp_allsky.F90'),'sha256':sha(source/'examples/all-sky/rrtmgp_allsky.F90')},
   'original_cloud_loader': {'path':str(source/'examples/all-sky/mo_load_cloud_coefficients.F90'),'sha256':sha(source/'examples/all-sky/mo_load_cloud_coefficients.F90')},
   'adaptation': adapt,
   'original_band_loader_failure_logs': {
     phase: str(output/f'original-band-{phase}'/'original-run.log') for phase in ('sw','lw')
   },
   'original_band_loader_failure_verified': True,
   'upstream_source_hash_manifest':str(output/'upstream-source-sha256.txt'),
   'upstream_source_hash_manifest_sha256':sha(output/'upstream-source-sha256.txt'),
 },
 'libraries': {
   'upstream_librrtmgp': {'path':str(source/'build/librrtmgp.a'),'sha256':sha(source/'build/librrtmgp.a')},
   'upstream_librte': {'path':str(source/'build/librte.a'),'sha256':sha(source/'build/librte.a')},
   'wrf_vendor_archive': {'path':str(prepared/'vendor/libwrf_rrtmgp.a'),'sha256':sha(prepared/'vendor/libwrf_rrtmgp.a')},
   'wrf_vendor_source_hash_manifest':str(output/'vendor-source-sha256.txt'),
   'wrf_vendor_source_hash_manifest_sha256':sha(output/'vendor-source-sha256.txt'),
   'upstream_module_hash_manifest':str(output/'upstream-module-sha256.txt'),
   'upstream_module_hash_manifest_sha256':sha(output/'upstream-module-sha256.txt'),
   'compiled_artifact_hash_manifest':str(output/'compiled-artifact-sha256.txt'),
   'compiled_artifact_hash_manifest_sha256':sha(output/'compiled-artifact-sha256.txt'),
 },
 'data_files': {n:{'path':str(data/n),'sha256':sha(data/n)} for n in (
   'rrtmgp-clouds-sw-bnd.nc','rrtmgp-clouds-lw-bnd.nc','rrtmgp-gas-sw-g112.nc','rrtmgp-gas-lw-g128.nc')},
 'linkage': {'vendor_link_map':str(output/'vendor-link.map'),'vendor_link_map_sha256':sha(output/'vendor-link.map'),
   'vendor_frontend_symbols':str(output/'vendor-frontend-symbol-evidence.txt'),
   'vendor_frontend_symbols_sha256':sha(output/'vendor-frontend-symbol-evidence.txt'),
   'upstream_cloud_and_aerosol_frontend_objects_omitted':True},
 'configuration': {'ncol':24,'nlay':72,'nloops':1,'roughness_index':2,
   'shortwave':'g112 gas + band LUT','longwave':'g128 gas + band LUT',
   'netcdf_include':netcdf_include,'netcdf_library_dir':netcdf_lib,
   'verified_band_schema':json.loads((output/'band-input-schema.json').read_text())},
 'scope':'Synthetic cloudy all-sky paired backend check; not published-reference accuracy, WRF adapter, UDM, or McICA validation.'
}
(output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
PY
python3 "$script_dir/compare_allsky.py" --upstream "$output/run-upstream" \
  --vendor "$output/run-vendor" --provenance "$output/provenance.json" \
  --output "$output/allsky-backend-comparison.json"
echo "all-sky band-cloud validation completed: $output"
