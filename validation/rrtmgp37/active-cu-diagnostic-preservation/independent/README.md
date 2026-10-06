# PR60 active-CU candidate output review

**Independent data and diagnostic readback: PASS. Numeric launcher return code: unavailable.** This review used the completed candidate files and pinned `long-b1` baseline only. No model rerun or rebuild occurred.

The candidate history and both restart files are whole-file SHA-256 identical to the baseline. I independently opened each NetCDF file, compared dimensions, variable names/dtypes/shapes, global and per-variable attributes, and every raw array block. The history has 25 `Times` records from `2000-01-24_12:00:00` through `2000-01-25_12:00:00` and 225 variables. Each of the two restart files has its expected single `Times` record and 667 variables. All compared arrays are equal; no masks, fill values, or nonfinite numeric values were found.

The active-CU case emitted 3,338 `RRTMGP_UDM_PHASE_PATH` rows, 1,556 `RRTMGP_CU_POPULATION` rows, and 778 `RRTMGP_CU_LUT_CLIP` rows across four MPI tile ranges. Context fields consistently identify domain 1, overlap 2, and source time `(radiation_step-1) × 60 s`. Native omission fractions and CU clipping fractions match their formulae within 7.4e-17 and 8.5e-17 absolute error respectively. After stripping the newly appended context and ignoring only newly added CU tile keys, all 7,149 prior CU/omission/clipping numeric diagnostic records exactly match the baseline.

All four rank logs contain `SUCCESS COMPLETE WRF` and no `FATAL`. The original runner receipt remains `RUNNING`, and its `.tmp` is truncated by JSON serialization; neither contains a durable numeric launcher return code. The posthoc verifier explicitly preserves that limitation.

Pins, individual output comparisons, and diagnostic checks are in [review.json](review.json), [output-comparison.json](output-comparison.json), and [diagnostics-independent-v1.json](diagnostics-independent-v1.json). The posthoc receipt and original runner files remain unchanged.
