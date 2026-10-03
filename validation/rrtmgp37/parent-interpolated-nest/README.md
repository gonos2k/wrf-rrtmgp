# UDM27 / RRTMGP37 delayed-nest runtime evidence

This package records one bounded, successful WRF integration run using the existing parent-only real-data input. The parent ran from **2010-06-11 00:00 to 02:00 UTC**; the 61×61 child activated at **01:00 UTC** and ran through 02:00. The child used WRF's parent-interpolation initialization path. No `wrfinput_d02`, `geo_em.d02`, or `met_em.d02` was staged, and `real.exe` was not run.

The run is a parent-interpolated runtime smoke test, not a high-resolution nested forecast evaluation. With `input_from_file=.false.` for d02, atmospheric, surface, and terrain fields were interpolated from d01. It does not evaluate high-resolution child land/soil/topography, a 24-hour nested run, restart continuity, MPI decomposition equivalence, observational agreement, or forecast skill.

## Configuration and provenance

- Four MPICH Hydra ranks, one OpenMP thread per rank; `OMP_STACKSIZE=512M` and a 512 MiB main-thread stack limit.
- Both domains used UDM `mp_physics=27`, RRTMGP LW/SW options 37, PBL option 1, surface option 2, and sfclay option 1. Cumulus was 1 on d01 and 0 on d02.
- Parent grid: 289×189 mass points, 39 mass layers, 20 km spacing. Child grid: 60×60 mass points, 39 mass layers, 6.6666667 km spacing, parent-grid ratio 3. Both used 40 staggered vertical levels.
- Frozen-particle optics mode 1 used the pinned experimental table SHA256 `8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583`. This table and the gas/cloud coefficient NetCDFs are **not included**; their original paths and hashes are in `runner/preflight.json` and `results/provenance.json`.
- `rrtmgp_data_path` and the frozen table path were global process settings shared by both domains. WRF history files do not serialize the custom frozen-optics mode/table hash as global attributes; the exact namelist, preflight, source pins, and execution receipt establish those settings.
- Capture/audit environment settings were disabled and no per-column seed values were captured. The source's deterministic seed key includes domain id, global i/j, year, day-of-year, and radiation phase; this package does not claim independent random realizations.
- The executable is identified by SHA256 `176f589d657ca87df670cef3429d7474e674f3e44445eb7886aed871e36bef8f`; the binary and runtime libraries are not included. The 13 tracked production source hashes match base commit `792f36b6bbc442f0db37b5cb9fdf19dd33600082` (`fix-udm-sr-row`). The separately generated `configure.wrf` is identified by hash only.

See `runner/execution.json` for the exact invocation, environment, input hashes, 95 staged-asset hashes, 117 pinned-file checks before/after, all four rank results, and output-validation receipt. The root's independent selected-field readback is in `results/root-independent-history-readback.json` and is tied to the execution receipt SHA.

`results/build-source-provenance.json` is the original build-stage record; its “no runtime launched” wording describes that build task before this separate nested integration run. The execution receipt is the runtime evidence.

## Result

The run finished with launcher exit code 0 and four `SUCCESS COMPLETE WRF` rank markers. The source log confirms initialization of nest domain 2 by horizontal interpolation from parent domain 1. No child input file appeared after the run.

The runner validated the exact history schedule, grid dimensions, grid spacing, parent/nest and physics metadata, required radiation and hydrometeor output shapes, and every numeric variable in each history file. There were 13 d01 records and 7 d02 records, with no duplicate timestamps, masked values, or nonfinite numeric values. The complete check covered 4,080 numeric-variable/file combinations; all 95 staged assets and all 117 external pins matched before and after the run.

Child d02 contained positive graupel and hail during this integration: per-record instantaneous domain maxima over the seven output times were `8.0210943e-5 kg kg-1` for QGRAUP and `4.3977685e-8 kg kg-1` for QHAIL. These maxima show state presence only; they are not time-integrated mass or a skill measure.

## Derived history summaries

Raw WRF histories are intentionally not copied into this package. `results/summary-v2/history_file_inventory.json` records the 20 original history-file names, byte sizes, SHA256 hashes, timestamps, dimensions, and selected global metadata. The inventory enables verification against the original case directory without shipping roughly 1 GB of NetCDF output.

`results/summary-v2/state_presence.json` records instantaneous per-record QGRAUP/QHAIL maxima and positive layer-grid-cell counts. A count summed over records repeats cells from different times; it is not a unique-cell count, path integral, or mass integral. `radiation_gridpoint_stats.csv` records per-record minimum, maximum, standard deviation, and arithmetic mean over grid points for SWDOWN, GLW, and OLR. These are instantaneous spatial statistics, not geographically area-weighted or time-averaged fluxes. The plot illustrates the same definitions.

The timestamp at the initial start of each domain is an initialization record rather than a completed radiation step: d01's 00:00 SWDOWN/GLW/OLR and d02's 01:00 GLW/OLR are zero in the stored output. Treat subsequent history records as the per-time snapshots for these radiation-field summaries.

## Rechecking

The portable `verify_evidence.py` needs only the Python standard library to check archived hashes and receipt contracts. If the original WRF output directory remains available, `--case-dir` also hashes all 20 raw history files against the inventory. Recomputing the NetCDF summaries requires the Python `netCDF4`, NumPy, and Matplotlib packages, but this evidence package does not vendor them.

```sh
python3 verify_evidence.py
python3 verify_evidence.py --case-dir /path/to/original/case-v2
```

Exact run and summary commands are preserved in `commands.md`. The approved 512 MiB stack-only adjustment relative to the parent-reviewed runner is recorded in `runner/resource-adjustment.diff`; both earlier runner snapshots are preserved with hashes in the preflight JSON.
