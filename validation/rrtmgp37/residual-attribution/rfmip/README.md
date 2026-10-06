# RFMIP SW residual and output-rounding diagnostic

This is a read-only analysis of the completed v5 standalone RFMIP SW diagnostic. It does not change the solver, coefficients, or the strict published threshold.

The execution receipt is `../execution.json` (SHA256 `88d2975310338bbec6b72280592dd9c1fc70742fc389842c7d04385fb68bbe3d`). It records exactly two standalone SW solver calls: current coefficients first, then the targeted old-solar coefficient counterfactual. Both returned 0 without timeout; each arm reproduced its respective retained stage-v7 RSD/RSU arrays bitwise and passed exact float32 conversion over 135 selected profiles × 61 levels × both outputs (16,470 values per arm). Captured broadband-normalization closure was at most `4.55e-13` for current coefficients and `2.28e-13` for old solar. There were zero WRF/REAL forecast calls.

The selected 155 cells are 116 RSD and 39 RSU locations from the pre-existing failure selector. Under the targeted old-solar counterfactual:

- All 155 stored float32 values remain outside the `1e-5` strict threshold, each exactly one float32 ULP from its published float32 value.
- All 155 float64 prewrite fluxes lie outside the published value’s float32 rounding interval. For 99 cells, the prewrite difference already exceeds `1e-5`; for the other 56, the prewrite difference is within `1e-5`, but the stored float32 difference exceeds it.
- Thus output conversion can move some values across the threshold, but it cannot be the sole explanation for the residual. In 99 cells, the prewrite solver flux already exceeds the threshold, and at all 155 cells it would round to a float32 value other than the published value.

For the current-coefficient arm, 154 of those same 155 selected cells exceed `1e-5` before and after conversion; one selected cell matches the published float32 value. This selected-cell count is not a recomputation of the full-array strict gate. The retained old-solar counterfactual’s full-array strict failure inventory remains 116 RSD and 39 RSU points at `atol=1e-5`, `rtol=0`; this is not a current-arm full-array recount, and the threshold is unchanged.

The captured optical-property arrays (`tau`, `ssa`, `g`) are bitwise identical across the two arms for all 135 profiles, while pre/post-normalized solar source vectors and fluxes differ. This is consistent with a solar-input-only counterfactual affecting the source rather than gas optical properties. It does not identify the exact historical generator behind the label `RTE-RRTMGP-181204`: the old-solar file is a targeted counterfactual, not an authenticated historical coefficient set or source revision. The remaining strict discrepancy is not attributed to a WRF port defect, and this clear-sky experiment makes no physical-accuracy claim.

## Reproduction and artifacts

Run the standard-library summarizer with Python 3.12.3 and the pinned NumPy/netCDF4 environment:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B summarize_execution_v5.py
```

The script verifies the exact execution-receipt hash, then recomputes threshold counts, ULP distributions, and the cast/normalization summaries already stored in the receipt. Summary JSON SHA256: `1f2d407b4ff9b5927005966e07b8b8be2a6b7b3c763c7ee9d4b14970c37e6f1f`.

Key provenance: plan SHA256 `14f1d2250db599f898463fbcf990bc32cd72b14a03c16e096e64868f33f16798`; patched diagnostic source SHA256 `8c55012d7b34722fce2d29a6c13d1cb55cf5f6e919340decad250a8c031f3354`; diagnostic executable SHA256 `4883cdf468bf3a386a71d66d4c4af8f7fd7c8ce94b3a991831a1e7be146d29c3`; input SHA256 `b8dc05d7cd2e0e6354b4a6198771ddf3bc09f18d72b49f20a41e2024e2fd51f4`; current SW coefficients SHA256 `584f1dd41ea9fc07d4ee3754eb1dafbd46ad3161cd6fd20fa06b6922b6f0702e`; targeted old-solar file SHA256 `02d4cd320696b9b8a3006a373855a3b4b95fdb6495251fe5f5692d6a9fddfaa4`.

The full output NetCDFs and diagnostic capture binaries remain in the sibling `current/` and `old_solar/` directories. Their hashes are recorded in the execution receipt; they are not duplicated by this report.
