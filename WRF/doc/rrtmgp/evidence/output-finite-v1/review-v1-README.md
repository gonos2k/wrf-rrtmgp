# Independent review: output finite guards

**Result: PASS_SCOPED_READ_ONLY_CODE_REVIEW.** Reviewed the candidate delta from base `33632eafff3fa06a164c7c56f258fac6fb545205` in `build/udm37-output-finite-pr-work`. No successful-path arithmetic or array assignment change was found. The new checks only inspect already-produced arrays and route nonfinite values through the existing fatal path.

The adapter keeps wp and default REAL checks separate. LW clear/all-sky fluxes and heating are checked in wp before conversion and default REAL after conversion. SW clear/all-sky fluxes, heating, direct/band outputs, and diagnostics are checked; optional pre-delta arrays are checked only when requested. The all-night early return checks the arrays initialized to zero, including optional diagnostics. Diagnostics carry phase/stage/field/column and interface or layer; band indices and precision are included where applicable.

The regression additions cover normal column/overlap/day/night/repeat calls and optional pre-delta outputs. Fault tests create isolated source copies from anchored production call sites (the generator rejects changed/ambiguous anchor counts) and inject a clear-LW flux NaN, all-sky SW heating NaN, and a value finite in wp but overflowing during conversion to default REAL. CTest requires the precise fatal marker and a nonzero exit.

**Kind caveat:** the cast-overflow fixture assumes wp is wider than default REAL, as in the normal repository configuration (`wp=c_double`, WRF default `REAL` single). Nonstandard `RTE_USE_SP` or `-fdefault-real-8` configurations may need a kind-aware expectation for that one fixture; the production guards themselves check the declared array kinds.

No build, tests, models, or RTE calls were run for this review. Root-owned focused validation remains authoritative for execution. Observed file hashes are recorded in `review.json`.
