# Optional column workspace reuse

The WRF adapter can reuse allocation owned by one radiation tile invocation. `rrtmgp_lw_column` and `rrtmgp_sw_column` append an optional `workspace` argument of type `ty_rrtmgp_lw_workspace` or `ty_rrtmgp_sw_workspace`. Existing callers that omit it retain the fresh local workspace path. Call `rrtmgp_release_workspace` when the owner finishes; release is idempotent.

The WRF LW/SW wrappers create separate local workspace objects, pass them through the existing column loop, and release them before returning. The wrappers and column procedures are `RECURSIVE` so each concurrent invocation owns its local object. There are no new shared `SAVE` arrays, threadprivate caches, vendor changes, or live gas-object copies. This storage is local to each tile invocation; it is **not persistent across timesteps**. WRF still calls the adapter with **`ncol=1`**. This change does not pack or batch WRF columns.

Reuse requires the exact current shape. Gas concentrations are initialized only on a new owner/shape, then every supplied gas field is overwritten, including absent CFC zeros. Optical numeric arrays and LW source arrays are allocated only when absent or differently shaped; immutable spectral descriptors remain attached to their phase. SW band/g-point maps are cached once per owner. Requested raw diagnostics are allocated lazily and reset before use, including arrays accumulated with `+=`. Frozen optical arrays have the same ownership/shape rules. Existing input validation, cloud masks, seeds, phase behavior, trace/audit calls and output arithmetic remain in place.

The explicit optional argument avoids depending on OpenMP threadprivate derived-type finalization and gas pointer-copy semantics. One workspace must have one active owner; separate concurrent tile calls use separate objects. Release explicitly finalizes the gas object and LW source, releases optical numeric arrays and descriptors, and clears SW diagnostics/cache arrays.

## Evidence

The retained evidence is in [`validation/rrtmgp37/udm-column-workspace`](../../../validation/rrtmgp37/udm-column-workspace/README.md) at repository root.

- GNU debug/OpenMP standalone checks passed all 103 tests, including legacy fallback, exact-shape reuse, shape changes, release/reuse, changing profiles, night/day, CFC absence, frozen0/1 and independent concurrent owners at 1/2/3/4 threads. Frozen-mode changes retain the existing rejection.
- An independently compiled original adapter at commit `792f36b6bbc442f0db37b5cb9fdf19dd33600082` matched every byte of all six LW and seventeen SW outputs in Debug/Release and frozen0/1. Each of the four cases also matched all 576 full-precision capture files, including raw optical depth/cloud masks and predelta outputs.
- Allocation instrumentation of actual calls showed zero warmed gas initialization, spectral descriptor initialization, optical numeric allocation, LW source allocation and requested SW diagnostic allocation. The host-style SW fixture always requests all four predelta outputs. Unchanged solver scratch allocations remain.
- A fresh GNU32 serial build passed RA37 frozen1 (12:00–12:11) and RA4 legacy (12:00–12:01), with all twelve histories byte-identical to matching references. RA4 matters because adding `RECURSIVE` can affect compiler local storage.
- A matching fresh GNU35 MPI/OpenMP build passed RA37 MPI1/OMP1, MPI1/OMP2 and MPI4/OMP1, plus RA4 MPI4/OMP1. All 34 histories, every variable and every global/variable attribute matched their corresponding references bitwise. A diagnostic-only GOMP probe verified both OMP2 workers execute the callback containing the LW/SW calls, with substantial thread CPU time.

Comparisons use the same process/thread layout on both sides. Existing differences between MPI decompositions are not attributed to workspace reuse. Frozen1 uses paired RA37/UDM27; RA4 uses frozen0 with an empty frozen-table setting, as required by the existing namelist guard. The namelist tile key is `numtiles`, as declared in Registry.

The five-pair Release column benchmark uses 1,500 changing daylight calls per phase at one column/60 layers and always requests SW predelta outputs. Median LW call time decreased about 2.5% (frozen0) and 3.0% (frozen1). SW changes were about 0.8%/0.7%, with overlapping run ranges. These modest column-level measurements are **not a WRF speedup claim**. Full-model timings were validation timings with overlapping processes. Intel validation and broader forecast/accuracy metrics are outside this evidence.
