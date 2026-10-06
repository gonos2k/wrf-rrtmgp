# Current PR60 diagnostics in one active-CU 24-hour run

One fresh January 24 12:00 → January 25 12:00 WRF run used four MPI ranks, configured two OpenMP threads, batch size 1 and a 512 MiB main stack. It produced 225 history variables over 25 hourly output times and 667 variables in each saved 12 h/24 h checkpoint. Posthoc comparison reports exact arrays, dimensions/unlimitedness, dtypes, variable sets and full variable/global attributes, with no exclusions or tolerances. The whole-file SHA256 also matches its same-configuration pre-diagnostic baseline for exactly these three files. This records current PR60 diagnostic preservation in one exercised active-CU configuration.

| Output | Variables | Times | Whole-file SHA256 equal to baseline |
|---|---:|---|---|
| History | 225 | January 24 12:00 through January 25 12:00, 25 hourly records |`2f916abf9689affd608c20f106877f9c23b4ba149610f104630adda56d3deddb`|
| 12 h checkpoint | 667 | January 25 00:00 |`d8472905694b5c6c2fc5480f6a529e9ef4a3b07d26741096071d5ed4d214fc9d`|
| 24 h checkpoint | 667 | January 25 12:00 |`ff4bf3c55f7d6358b1d7ba59404d32e2c6d48e1dcdb0748e7e414e87e7b9361f`|

All numeric history/checkpoint values were finite, unmasked and without default/explicit fill values. The history quality readback supplies the 25 output times; the original `comparison.history[0].times` is null and is not used as a time-verification claim. The mass grid is 73 × 60 × 32. This run saves checkpoints; **no restart was launched**. Configured thread count is recorded, without claiming a new instrumented two-worker proof or broader OpenMP/decomposition invariance.

The four `rsl.error` logs contain 1,556 CU population rows, 778 CU clipping rows and 3,338 native four-phase path rows. Positive CU path and clipping are observed. The 7,149 historical diagnostic rows remain numerically unchanged across 72 aggregate groups. New rows use the existing domain/step/time/tile context. These are call/tile observations: LW and SW are distinct, and path sums across phases/ranks/calls are not unique physical domain mass, area integrals or time-integrated precipitation.

## Preserved bookkeeping failure

The frozen runner completed the model/output work but failed final JSON serialization because `diagnostics.native_cf0_detail_aggregate` used tuple dictionary keys. [The original receipt](failure/original-running-execution.json) remains `RUNNING`; its truncated `.tmp` is externally pinned in [index.json](index.json). Neither was repaired or reclassified. The numeric launcher return code is **UNAVAILABLE**, not inferred zero. All four rank logs have `SUCCESS COMPLETE WRF`, and separate posthoc quality/equality/immutability checks pass. There was no model rerun for bookkeeping.

[summary.json](summary.json) is a compact derived ledger tied to the exact original posthoc receipt SHA256 `4cd445300683a08b71287da443dd291a819a5214707e150751e4e5c8122f7a2c`. The [posthoc helper](helpers/verify_posthoc.py) is copied verbatim with SHA256 `6601e7224eca98036595cf5a2584a3d77a097eec9550fd84ad0651aebbe5d467`. The full posthoc metadata, source manifest, preflight/stage receipts, diagnostic logs and NetCDF outputs remain at externally pinned paths. The [independent posthoc review](independent/README.md) passes the raw output, metadata, Times and diagnostic context/arithmetic checks while preserving the unavailable launcher RC. Its exact receipt SHA256 is `99da7816f2583560bf9df05e52272f86b2c474e22a01f55b8e5e14f144df94b1`.

## Verification and limits

Run `python3 -I -S verify_artifacts.py` here to check retained hashes and compact receipt contracts using the standard library. It does not recompute external numerical arrays/log diagnostics or execute any model, solver or build. The build result, source freeze, pre-run independent review, original failed receipt and execution/posthoc helper snapshots are retained byte-for-byte. The helpers have original workspace paths and transitive external dependencies; they are **nonportable provenance snapshots**, not directly runnable checkout workflows. No binaries, coefficients, full diagnostic logs or NetCDF files are copied.

This evidence addresses diagnostic noninterference, not physical accuracy, independent optical truth, native/CU radius validity, CF0 precipitation occurrence policy, LUT clipping error, G/H operational approval or a restart execution. The underlying experimental physical assumptions remain open. Curation adds zero model/build/reference calls; the only model counted here is the existing 24 h invocation.
