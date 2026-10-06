# Fixed-RTE RFMIP optical-input replay

This saved evidence isolates optical-input differences for 20 profiles associated with 21 selected strict-failure cells. It injects saved current-old-solar and historical optical properties into the same current RRTMGP shortwave RTE, with the exact shared `source_post` vectors. The frozen Fortran harness is copied verbatim to `WRF/test/rrtmgp/rrtmgp_rfmip_sw_fixed_rte.F90` (SHA-256 `5a46c11921b045a3dc1ff9bbe911cd2f886250773b8686dfe1345ff042fd9925`). It bypasses `gas_optics`; no WRF or REAL forecast is involved.

The actual v4 receipt is `execution-v4/execution.json`. It records five successful, reaped children, 40 fixed-RTE calls, zero gas-optics calls, and zero forecasts. The current-optics arm reproduced its saved current-old-solar solver and written streams byte-for-byte for all 20 profiles. The historical-optics arm differs from the saved historical solver outputs for all 20 profiles; that difference is descriptive because the saved historical outputs used a different RTE source revision. The strict published RFMIP gate remains unchanged and failing.

`fixed-rte-component-analysis.json` reports signed flux differences for all 20 profiles, 61 levels, and both flux directions. It defines `delta_optics = current-RTE(historical optics) - current-RTE(current optics)`, `delta_post_optics_residual = saved historical flux - current-RTE(historical optics)`, and `delta_total = saved historical flux - current-RTE(current optics)`. Their sum closes exactly at every one of 2,440 scalar flux values. The second component includes the historical/current RTE implementation difference and remaining capture/replay convention differences; it is not atmospheric transport.

The maximum absolute differences were 2.1581377041e-7 W m-2 for `delta_optics`, 6.0628156007e-7 W m-2 for the post-optics residual, and 8.2209533048e-7 W m-2 for the total; the maximum closure error was exactly zero. These are conditional results for this fixed RTE and saved source, not an accuracy verdict.

The 21-row table in the analysis is the selected subset of the unchanged original strict-failure ledger. Its 13 float32-cast and 14 raw-double threshold exceedances for the fixed-current-RTE historical-optics replay are diagnostics over those selected 21 cells only. They are not the global strict-failure count or a gate pass. The original published strict tolerance remains `atol=1e-5`, `rtol=0`; other strict failures outside this selected subset are not reassessed here. No coefficient, tolerance, or production code was changed.

The current, old-solar, and historical coefficient files share the same band-edge and band-to-g-point limit metadata. This aligns the band descriptors only; it does not establish a physical one-to-one mapping between correlated-k g-points across coefficient generations. The historical-optics comparison is an index-ordered optical-input counterfactual under one current RTE.

## Rechecking the saved package

The package contains deterministic gzip copies of the eight 20-profile subset streams. Verify the package without running any solver:

```sh
python3 validation/rrtmgp37/rfmip-fixed-rte/verify_saved.py
```

To repeat the saved-output byte checks, run the copied `validate_replay.py` with the four `execution-v4/replay_*.bin` output files, the four `references/*.bin` saved streams, and `inputs/profiles20.txt`. Its exact gate applies only to the current-optics arm; historical-arm differences remain descriptive.

The original 135-profile captures and the eight supplemental v3 captures remain preserved at their pinned source locations. `inputs/record-provenance.json` records each selected record’s donor path, stream hash, record index, and record hash. Earlier fixed-RTE runner preflight failures are preserved separately and are not scientific results.
