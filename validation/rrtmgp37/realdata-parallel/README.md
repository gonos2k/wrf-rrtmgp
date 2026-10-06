# UDM27 actual-domain parallel runtime validation

## PR20 four-rank 24-hour experiment

The completed trial uses committed PR20 production sources
`9ecf7e1eca9c2612420f8874f03961467a7497de`, GNU dmpar/MPICH, four ranks,
one thread per rank, and the explicit experimental frozen-optics mode 1.
It covers 2010-06-11 00:00 through June 12 00:00 on the existing NCAR
2010061100 developer-test domain, 290 by 190 horizontal points and 40
vertical interfaces, with a 60-second step.

`pr20-24h-mpi4.json` records exit 0 and success on all four ranks, 25 hourly
outputs with 204 variables each (189 floating-point variables, all finite),
and a finite 24-hour restart. `pr20-post-run-source-check.json` independently
checks all thirteen build-recorded production source hashes against both the
post-run worktree and the committed PR20 files. Input and boundary files are
byte-identical to the existing RRTMG4/UDM27 baseline.

`boundary-coverage.json` records both this-boundary and next-boundary clock
metadata. The four beginning times 00/06/12/18 have next times 06/12/18/24;
the final tendency interval covers the requested integration endpoint. The
boundary file was neither extended nor changed. The recorded namelist retains
the original time step, damping and remaining physical settings.

The runtime used homogeneous ice spheres with an exponential PSD for graupel
and hail, occurrence fraction one and absorption-only frozen LW. It tests
numerical execution for this explicit experiment; it does not establish
NOAA internal UDM parity, wet/melting-particle fidelity or observed forecast
accuracy. It also predates the PR21 LW CFC input correction. Do not claim that
this trial validates PR21 over 24 hours.

`pr20-positive-frozen-inventory.json` hashes all 25 hourly outputs and the
restart and inventories actual native dry-mass-derived graupel/hail paths.
Both species exceed 1e-9 kg/kg from hour 01 onward, so the run is not merely
a zero-frozen-particle bypass. The recorded maximum warm-positive path shares
are about 21.46% for graupel and 59.27% for hail. Warm air temperature alone
does not diagnose particle melt fraction; these are inventory diagnostics,
not evidence that homogeneous ice spheres describe those particles accurately.

## Coupled RRTMG4 comparison

`coupled-metrics.json` and its read-only script compare the 25 paired hourly
outputs on the full common 289 by 189 native mass grid, using identical
`AREA2D` weights and dry-mass-derived hydrometeor paths. Output at initialization
contains zero radiation fields in both runs; equality there proves common
initial state, not agreement of the first actual radiation calculations.
The area-weighted space/time RMSEs include about 44.51 W/m2 for SWDOWN,
6.68 W/m2 for GLW, 7.47 W/m2 for OLR and 0.207 K for T2. Local differences
are much larger. These are differences between coupled trajectories, not
observational errors and not a same-state intrinsic radiation comparison.
The RRTMG4 configuration also retains its prior UDM radius behavior and
legacy precipitation optics. PR20 still omitted the four LW trace gases
subsequently connected by PR21. These configuration differences and state
feedback cannot be separated by this history comparison alone.

[Radiation time-series plot](coupled-radiation.png) ([PDF](coupled-radiation.pdf))
shows area-weighted means and spatial RMS differences. Signed differences are
RRTMG4 minus PR20 RRTMGP37 mode 1. The plot is generated from the recorded
metrics by `plot-coupled.py`; RMS differences are not observational errors.

## PR20 12-hour checkpoint and 12-to-13-hour restart

The isolated restart trial reused the prepared PR20 four-rank mode-1 binary;
it did not modify the active 24-hour case, source, or frozen table. The exact
comparison at 2010-06-11 13:00 found **no numerical array differences** across
all 204 variables and 54,643,036 numeric values, with no non-finite values.
The only output difference was the global `START_DATE` attribute: 00:00 for
the continuous run and 12:00 for the restarted run. Therefore the comparator's
overall exact-match result is false due to metadata; its separate numerical
`dynamics_passed` result is true. Do not describe the metadata mismatch as a
dynamics failure or hide it.

The 12:00 checkpoint recorded `Times=2010-06-11_12:00:00`, `ITIMESTEP=720`,
and `XTIME=720.0`. Immutable asset checks passed after each segment and at
completion (21 pinned assets, zero mismatches). The run receipt includes
production-source, executable, table, initial-state, boundary, namelist, and
continuous-output hashes. Key hashes are: WRF executable
`4c979fb248b26d8ce61f05fd602f55e0492e173a312e3532021fecda508e2503`, frozen
table `8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583`,
`wrfinput_d01` `5ef7abe34c516fba107f346bdbdb3777edacb5d48493df467ea2dd8bcf6a75ff`,
`wrfbdy_d01` `e687b73730ab9a2cee4842e1a92b225a4edb074ba080b6053d96d81ec1731a2d`,
continuous 13:00 output
`d8304ec34048bc04955bf6b7decf798b59f0221849574e940b964ba87b30a07a`, and
restarted 13:00 output
`aac5811137fa4ce9962f79f042060386af04a5f75d96afcc64f1cff42724f829`.
The executable was built from the recorded base commit
`f8cbfeea7f4c59e5e0655bd2f23e3b424b8359b3`; this is the PR20 validation
binary and does not include the later PR21 LW trace-gas correction.

Receipts and the exact comparator are preserved in the `pr20-restart-*`
artifacts alongside this README. The copied runner/comparator source hashes are
recorded in `pr20-restart-run-receipt.json`. The executed reproduction command
was:

```sh
python3 build/udm-frozen-restart-plan/run_mode1_restart_trial.py --execute
```

The runner configured the MPICH, NetCDF, and root dependency library paths,
used four ranks and one OpenMP thread, and compared every output variable
without tolerances or ignored variables. `pr20-restart-comparator-self-test.json`
records the comparator's self-test against the continuous output; it validates
reader coverage, not restart continuity. The archived overall receipt status
is `FAIL` because metadata is part of its exact-match contract, while the
separate numerical result is `dynamics_passed=true`.

## PR21 fresh MPI+OpenMP build and restart matrix

The GNU dm+sm executable was freshly built from committed PR21
`e73b353f2b76f323809f99bed19a29eaaf25af02`, with `-fopenmp`, MPICH 4.2.0,
and resolved NetCDF/libgomp libraries. `pr21-dm-sm-build.json` records the
source and executable hashes. The post-run worktree has no tracked source
differences. PR21's eight remote CI jobs also succeeded (`pr21-ci.json`).

Four isolated trials restarted the same PR20 12-hour checkpoint and ran to
12:11 with the newer PR21 executable. This tests decomposition of a shared
restart state, not PR21's full 24-hour trajectory or continuous/restarted
equivalence across executable versions. Every trial reached the requested
time, produced finite fields and reported successful WRF completion.

| Comparison against MPI1/OMP1 | Numeric result at 12:11 | Metadata |
| --- | --- | --- |
| MPI2/OMP1, layout 1×2 | All 204 variables and 54,643,036 numeric values exact | Expected NTASKS provenance differs |
| MPI1/OMP2, two physical tiles | All numeric values exact | Exact |
| MPI4/OMP1, layout 2×2 | **FAIL: 83 variables and 8,617,206 values differ** | NTASKS provenance differs |

The OpenMP receipt matches `/proc` executable identity and records CPU time
on both actual WRF threads; the log shows two disjoint physical tiles.
The MPI4 discrepancy is already present at 12:01 (62 variables differ),
including UDM number concentrations, pressure and radiation. The all-field
maximum of 1.375×10⁸ is across mixed units and must not be reported as a flux
error. Per-variable differences are preserved in the two MPI4 comparisons.
No numerical tolerance was introduced, and the overall receipt is
`MATRIX_RUN_COMPLETED_WITH_DIFFERENCES`, not a decomposition PASS.
Its origin in restart reading, host UDM or the radiation port remains under
investigation; successful finite runtime alone does not resolve it.

The initial trial completed but did not write the requested 12:11 history:
WRF restored the checkpoint's next hourly alarm at 13:00. Its no-history
failure is retained as `pr21-parallel-v1-failure.json`. The source contract
in `WRF/share/input_wrf.F` restores these alarms when
`override_restart_timers` is false. The new isolated v2 trials explicitly
set `override_restart_timers=.true.` and use one-minute history. Physics,
time step, radiation interval, checkpoint, coefficient files and optical
table remain identical across the matrix. The archived runner describes
the corrected v2 trial; original attempt receipts and logs remain available.

## Further work

Resolve the 2×2 MPI discrepancy before declaring decomposition equivalence.
Long-run observation accuracy, wet-particle optics, nests and actual WRF
column packing remain separate work. The 24-hour coupled contrast and
successful numerical restart are useful evidence, not general forecast
approval.
