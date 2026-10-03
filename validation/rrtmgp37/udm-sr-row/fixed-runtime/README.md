# Fixed SR-row build and bounded runtime evidence

This bundle adds the fresh build and two short RA4 restart runs to the original SR-row review bundle one directory above. The original five files and `curation-before-runtime.json` were not modified.

## Change and build

The test source is commit `faf3ea0c6b37bee97e089b7c2a102d19d8557e80` plus one local scratch commit, `e7c97ed661403b3922fcf752300c052611ef89cd`. The only source change is in `WRF/phys/module_mp_udm.F`: the legacy fallback call now passes the current row `sr(ims,j)` to rank-1 `udm2d`, matching the native call. The full patch and module SHA are recorded here. A fresh GNU dm+sm build used configure answers 35/1, O2/vectorization, MPICH 4.2, NetCDF-Fortran 4.5.4, and passed `csh -f ./compile -j 12 em_real`.

## Bounded comparison

MPI1 and MPI4 each restarted from the same 2010-06-11 12:00 checkpoint and ran exactly one 60-second RA4 step to 12:01. The namelist and 88 runtime links per case were hash-checked against the already reviewed official-pristine and PR21 cases. The per-case receipts require a success marker from every rank.

A strict raw-byte comparator checks all 202 official output variables, dimensions, shapes, dtypes, explicit `_FillValue`/`missing_value` masks, and finite values outside masks. It applies no tolerance. Metadata differences are recorded separately. Both corrected outputs match their corresponding official pristine outputs in all 202 variables and their entire output-file SHA256 hashes. The pre-fix PR21 output differed from each corresponding pristine output only in `SR`: the pre-fix output had zero nonzero SR cells, whereas pristine and corrected output each have 317 nonzero SR cells.

The corrected MPI1-versus-MPI4 pair remains a strict failure with the same 63 differing fields as the official pristine MPI1-versus-MPI4 pair; 139 fields match exactly. There are no field-set, shape, dtype, mask, or unmasked-finiteness discrepancies. Only global `NTASKS_TOTAL`, `NTASKS_X`, and `NTASKS_Y` attributes differ between those rank layouts.

## Coupled impact and limits

This is not a cosmetic diagnostic fix. The WRF state `SR` is the frozen-precipitation fraction. With the tested `sf_surface_physics=2` Noah scheme, `module_sf_noahdrv.F` passes `SR(I,J)` into `FFROZP`; Noah `SFLX` uses `FFROZP>0.5` to classify precipitating conditions as snow, which can update the surface snowpack, and the driver accumulates snowfall based on the same fraction. A bad SR field can therefore alter later land-surface forcing and the coupled trajectory.

The prior 24-hour RA4–RRTMGP37 comparison remains confounded by this RA4 `SR` problem. These one-step RA4 matches show the corrected path agrees with pristine WRF for this checkpoint and timestep; they do not quantify the later 24-hour effect or turn the old archived deltas into radiation-only differences.

The base also contains the existing CF-extent change (`cldf_diag` retains caller-initialized values above diagnosed cloud top via `intent(inout)`). Exact one-step RA4 agreement does not validate that formal's longer-run impact. This bundle is limited to the 60-second, MP27/RA4/4 restart comparison and does not establish MPI1/MPI4 bitwise reproducibility or option-37 forecast validation.

## Reproduction and retained evidence

The archived `run_case.sh` is the exact launcher used in the scratch build tree; it expects the adjacent isolated source/build directories and pre-staged runtime cases, which are not copied into this evidence bundle. The strict comparator is included and likewise resolves the original scratch cases. `manifest.json` indexes every copied file and hashes the full executable, NetCDF histories, and compiler log that remain in the scratch tree. No executables or full NetCDF outputs are copied here.
