# One-column dry-gas counterfactual readback

This is a read-only analysis of the completed four-call `reference_column` replay in `build/dgcf-runtime-v2/run-v1`. Its analyzer rechecks the terminal execution receipt and each recorded input/output SHA, reads the saved GP capture and RRTMG4 observer exports, and writes the descriptive results to `analysis.json`:

```sh
python3 -B build/udm37-dry-gas-causal-analysis-v1/analyze.py \
  --output build/udm37-dry-gas-causal-analysis-v1/analysis.json
```

The three comparisons are kept distinct: (1) baseline GP replay against the actual GP-captured `RRTMG_RESULT` arrays; (2) the baseline GP dry column against the actual RRTMG4 observer `INPUT/COLDry` or `INPUT/COLDRY` export; and (3) counterfactual minus baseline GP replay. The counterfactual changes only the first 44 `NATIVE_DRY_LAYER_MASS_KG_M2` value tokens, mapping the exported legacy molecule column back to kg m-2 with captured `MOL_WEIGHT_DRY` and Avogadro's constant. LW's 13 upper extension levels and SW's one upper extension level remain unchanged. The check also confirms the cloud, CU, precipitation, frozen, mask, and radius result sections are bit-identical between each baseline/counterfactual pair.

For the actual WRF capture comparison, aggregate UP/DN/HR and clear-sky UPC/DNC/HRC arrays round to the same REAL32 values as the standalone baseline. The raw decimal values differ because the two outputs cross different serialization precision boundaries. The SW VIS/NIR partition fields are not all identical after REAL32 rounding and are reported individually; SW gas SSA differences are at roughly 3.3e-16. This is not an assertion that every captured diagnostic matches.

The observed native-versus-legacy GP dry-column residual over 44 layers is 0.1652% mean absolute relative difference and 0.2892% maximum (layer 19). The transformed replay's resulting `GAS_COL_DRY` matches the observer column to 1.25e-16 maximum relative difference, showing the input transformation was realized. This is a controlled sensitivity of one captured column at d01/i24/j55, step 2161, source second 129600; it does not establish which engine is more accurate or generalize to the domain.

Selected flux and heating deltas (counterfactual minus baseline) are in `analysis.json`. At the surface (pressure level index 0), all-sky downward LW changes +0.00841 W m-2 and clear-sky downward LW +0.08916 W m-2. TOA upward LW changes -0.000196 W m-2 (clear sky -0.06128). Surface downward SW changes -0.000213 W m-2 and TOA upward SW -0.00144 W m-2 (clear-sky counterparts are also tabulated). Heating is K day-1: layer 31 changes +2.63e-4 in LW and -1.33e-5 in SW; largest absolute native-44-layer changes are 7.51e-4 at LW layer 6 and 2.13e-4 at SW layer 44. Upper extensions are summarized separately. Large changes in maximum raw gas optical depth occur in strongly absorbing spectral bins; they should not be read as flux-error magnitudes.

The replay used a scratch `reference_column` built from the source and one-file test-only guard documented in `build/udm37-dry-gas-sensitivity-design-v3`. The SW counterfactual skips only the stale captured-gas-tau identity check after intentionally changing dry mass; baseline checks remain active. No WRF forecast, REAL initialization, observation comparison, or accuracy assessment was performed for this analysis.
