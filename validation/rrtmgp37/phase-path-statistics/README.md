# Phase and path diagnostic validation

This validation adds tile-local diagnostics for cloud-fraction-zero omissions and liquid/ice LUT size clipping. It does not change any path, size coordinate, LUT clamp, or radiation result.

This PR worktree is based on `bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291`, a test-configuration follow-up to workspace commit `6f0f3ea3e73fbd43325fdad1050b000eecd70138`. The fresh GNU Fortran 13.3 serial32/nest0 `em_real` build used the exact workspace configure file. The production-source difference from that workspace was exactly four files: `module_ra_rrtmgp.F`, the LW and SW wrappers, and `module_ra_rrtmgp_input.F`. The CMake test and documentation are test/documentation changes. The staged source manifest was unchanged during the build.

The RA37 run used the same 94 immutable runtime assets, namelist, and 12:00 restart as the validated workspace candidate and ran through 12:11. The RA4 comparison used the corresponding workspace RA4 run through 12:01. Both candidate cases passed byte-level comparisons of every history variable, dimensions, dtype, and attributes. The independent whole-file check also passed all 12 RA37/RA4 file pairs.

At the first recorded radiation call (12:00Z), upper-bound ice-size clipping affected 23,924 LW layers and 21,208 daytime SW layers. The corresponding clipped grid-path fractions were 36.6514% for LW ice and 41.6700% for SW ice. No lower-bound clips occurred. CF=0 omission counted 89,151 LW and 65,013 SW rain layer-cells; the maximum omitted rain path was 652.0806 g m-2. The coefficient files have the same coordinate limits in both bands: liquid effective radius 2.5–21.5 µm and ice effective diameter 10–180 µm.

These are tile-local path statistics. Sums are sums of per-layer grid-mean paths in g m-2, not horizontal-area-integrated mass, time-integrated precipitation, or domain-total mass. LW and SW refer to separate radiation calls; their counts must not be added as unique atmospheric material. The clipping fraction weights out-of-range paths by grid path; it is not a flux-error percentage and does not establish that clipping is radiatively negligible. The results leave cloud-size clipping and precipitation-fraction accuracy open. SW summaries occur only when the SW wrapper executes in daylight. Graupel and hail are outside the four-phase CF=0 summary and retain their separate existing handling. The new summaries have no MPI reduction and are not validated for MPI output.

## Reproduction

Run commands from repository root `/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP` unless stated otherwise. The exact executed staging/build/run scripts are retained here and their hashes and original invocation paths are recorded in `execution-scripts.json`.

The tested registration command and standalone CMake/CTest commands were:

```sh
cd build/pr-wrf-rrtmgp/build/udm-phase-path-statistics-pr
python3 tools/register37.py --check

cmake -S WRF/test/rrtmgp -B build/phase-path-statistics-ctest \
  -DNETCDF_INCLUDE_DIR=/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/include \
  -DNETCDF_LIBRARY_DIR=/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/lib \
  -DFROZEN_TABLE=/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/pr-wrf-rrtmgp/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc
cmake --build build/phase-path-statistics-ctest --target test_rrtmgp_phase_path_stats -j 4
LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/lib \
  ctest --test-dir build/phase-path-statistics-ctest -R '^udm_phase_path_statistics$' --output-on-failure
```

The recorded full WRF build command was `./build_serial_em_real.sh`, which runs `csh -f ./compile -j 12 em_real` in the isolated staged source with GNU serial32/nest0 configuration, `NETCDF=/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf`, `NETCDF_classic=1`, and `OMP_NUM_THREADS=1`. The executed runner was `run_integrated_candidate.py --phase ra37` and then `--phase ra4`; it checks source, executable, runtime assets, and restart hashes before and after each run, requires the WRF success marker, and performs strict output comparisons. The summary parser validates the saved run receipts, checks full stdout hashes, reads table bounds directly from coefficient files, and extracts the 24 logged diagnostic lines.

This evidence validates noninterference for these two serial cases only. It does not establish forecast accuracy, diagnostic coverage over all decompositions/configurations, or radiative impact.
