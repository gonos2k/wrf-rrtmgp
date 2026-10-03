# UDM/RRTMGP nested runtime evidence

This is an additive evidence subtree for PR #50. It reuses source/build evidence in the sibling `../udm-ccn-runtime/` package and does not duplicate its source archive or model outputs. The package documents one two-hour nested runtime and its own restart continuation.

Both WRF invocations completed with return code 0 and all four MPI ranks reported success. The original strict execution receipts remain `FAIL_PRESERVED`: the continuous output contract rejected missing `RTHRATLW` and `RTHRATSW` history fields; the restart contract rejected the `WRF_ALARM_SECS_TIL_NEXT_RING_51` metadata difference. The posthoc reports provide scoped stored-state analysis and do not convert those original receipts to PASS.

The continuous run contains 20 history files (13 parent, 7 child) and compares four selected checkpoints (01:10 and 02:00 for each domain). The own-restart continuation compares 12 history files and two final checkpoints; its two 01:10 restart inputs are separately hash-pinned. Across paired histories, 2478 of 2484 variable comparisons match raw bytes. The six differences are the three documented UDM diagnostic resets in each domain's initial restart history. Both final checkpoints match all 1299 variable payloads. The full raw per-variable hash rows are in `reports/restart-variable-raw-hashes.csv`.

The root-frozen v11 comparator report corrects one source citation relative to the preserved v10 comparator. Model-output and raw variable-data hashes, numeric comparisons, and quality results match v10; the comparator/report file hashes change with the citation text. No model was rerun for this citation correction. The parent uses CU scheme 1 with radiation feedback. The delayed-start child receives interpolated parent state and inherited static fields; CU is disabled there, and the child is all-land with no sea ice. This tests nested runtime and restart plumbing, not child-local CU radiation or fine-grid child geography. The existing PR50 source/build attestation is referenced by hash; the nested runtime did not trigger a new build. Model NetCDF histories/restarts, executable, coefficient files, restart inputs and shared libraries are external; their paths, sizes and SHA-256 values are retained in the reports and output inventory. `verify.py` checks packaged integrity and report consistency, but cannot recompute arrays in absent NetCDF files.

## Verification

Run from this directory:

```sh
python3 -I -S verify.py
PYTHONDONTWRITEBYTECODE=1 python3 -I -S -m unittest discover -s . -p test_verify.py -v
```

The v10 comparator and its 13 synthetic controls (3 accepted fixtures and 10 rejected mutations) are retained under `tools/`; the v11 root-frozen comparator corrects a citation only, and its report preserves the same numeric comparisons. A separate receipt records five additional root-run numeric-quality rejections against v11. The dtype mutation case is not among the 13 original controls. No model was run for these controls. Reproduction requires the separately pinned model outputs and existing build/data environment. The verifier starts no model or forecast.
