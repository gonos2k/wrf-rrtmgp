# LBLRTM selected PANEL R2→R1 deposit evidence

This archive independently reproduces one narrow calculation from 45 lossless `POCKOWN7` Fortran record pairs extracted from the successful saved continuation. For each of eight selected layer-21 output samples, it obtains the stage-2 R2 operands and stage-2/stage-3 R1 values, derives the global sample as `j1 = NLO + panel_sample - 1`, then evaluates the `PANEL` `DO 20` stencil in source operation order. The predicted stage-3 R1 values match all eight saved binary64 values bit for bit (maximum residual: 0 ULP).

The capsule records each event's sequence number and byte offset into the pinned complete trace, full-source trace hash and size, exact raw event bytes, and exact output-panel header bytes from ODdeflt_021. The 45 event pairs and two unique owner headers total about 17 KB. The complete trace and OD samples are not bundled; offline verification consumes only this lossless selected-record capsule and the copied terminal/provenance receipts.

The calculation closes only the selected R2-to-R1 interpolation deposits. It does not establish the complete CNVFNV line-to-R3 deposit, line-group completeness, RADFNI multiplication, continuum/cross-section closure, total-OD nonnegativity, or physical validity. The saved v7 trace has zero RADFNI observer records; strict validation remains rejected. A later strict v10 parser receipt remains RC2 on the missing target-5 predecessor header. The layer-21 all-active OD still has 654 negative samples, minimum −4.884429085432753, and its negative-OD gate remains FAIL. The earlier full-file OD strict failure also remains preserved: all 45 files match outside the source-authoritative HTIME bytes, while zero files match byte for byte.

The first capped attempt is excluded. Its currently retained trace and OD21 hashes differ from the successful RC0 continuation. All package event bytes come from the successful continuation case pinned in `manifest.json` and supported by its terminal RC0, postflight, output-inventory, and OD-comparison receipts.

Run the standard-library verifier from any working directory:

```sh
python3 -I -S validation/rrtmgp37/lblrtm-pocket-deposit/test_verify_saved.py
python3 -I -S validation/rrtmgp37/lblrtm-pocket-deposit/verify_saved.py
```

Expected status: `PASS_SAVED_CAPSULE_RECONSTRUCTION`. This is a scoped arithmetic result, not a physics-acceptance status.

The mutation controls confirm that the verifier rejects a repinned manifest
with a duplicate target in place of target 8, and an unlisted nested file
named `package-integrity.json`.
