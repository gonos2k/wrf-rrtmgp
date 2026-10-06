# Historical RFMIP SW source candidate

This archive records one isolated clear-sky SW g224 run using the RTE+RRTMGP v1.0.0 source candidate at commit `ed5b0113109fcd23a010a90c61f21bad551146ef` and the authenticated v1.0 SW coefficient file (SHA-256 `b9f4b15796d132880fffb49ac45c29753c1ee70a8ee3fed733899cb315c75e9b`). It is a candidate historical source/coefficient pair, **not proof of the generator used for the published `RTE-RRTMGP-181204` outputs**. See the [lineage archive](../rfmip-reference-lineage/README.md) for reference-byte and coefficient provenance. The original BSD `source/LICENSE` is retained with the driver files. Large coefficient/input/reference NetCDF files, executables, and diagnostic capture binaries are intentionally omitted.

At the unchanged strict threshold `abs(candidate-reference) <= 1e-5`, `rtol=0`, the full-array current-source/old-solar arm has 155 failures (116 RSD, 39 RSU); the historical-source/authentic-coefficient candidate has 21 (13 RSD, 8 RSU). This is not closure of the inherited current-reference gate: its 104,071 failures remain an independently recorded result, and this archive does not rerun or recount that comparison. In the original 155-cell selector, 142 cells become strict passes and 13 remain failures; 8 additional failures are outside that selector.

| Full-array comparison | RSD failures | RSU failures | Total |
| --- | ---: | ---: | ---: |
| Current source with old-solar coefficients | 116 | 39 | 155 |
| Historical-source candidate with authenticated old coefficients | 13 | 8 | 21 |

Of the 21 candidate failures, 13 are on captured profiles and 8 are on eight distinct uncaptured profiles. For the 13 captured residual cells, all prewrite values lie outside the published float32 rounding interval, by only `4.94e-10` to `1.43e-7 W m-2`. These prewrite differences are measured against the published float32 value, not the unavailable original generator double flux; the interval distances are not estimates of true physical or numerical error. Eight prewrite values already fail the `1e-5` comparison, while five additional stored-value threshold crossings are all RSU. The 8 uncaptured cells have no prewrite interval classification. Among stored candidate/reference values, 16 RSD and 112 RSU values are nonidentical, each by one float32 ULP; maximum absolute residuals are `6.103515625e-5 W m-2` (RSD) and `3.0517578125e-5 W m-2` (RSU). These are small clear-sky g224 results and do not explain larger cloud/precipitation differences.

Across the 135 captured profiles only, pre/post source spectra are bitwise identical; optical depth and single-scattering albedo differ, while asymmetry `g` is bitwise identical. The selected double-precision solver-flux maximum absolute difference is `8.1281382e-7 W m-2`; stored float32 casts are exact for the captured outputs. This indicates a source-tree/API-version effect for this candidate but does not isolate a kernel cause. It is neither an RRTMGP37-versus-RRTMG4 comparison nor validation of the production g112/UDM cloud path or forecast accuracy.

The archived [loader-equivalence receipt](receipts/loader-equivalence.json) supports reuse of the retained current-code old-solar arm for the stated 29 common non-solar arrays and 224-value solar-vector mapping. It does not prove equal gas-optics behavior: captured `tau` and `ssa` differ. The experiment used one historical standalone SW invocation, no WRF/REAL forecasts, and no production changes.

## Archive contents and checks

`analysis/plan.json`, `analysis/result.json`, `analysis/residual-details.json`, the two small selector files, and the receipts preserve the frozen experiment and its derived checks. `source/observer.patch` shows the diagnostic-only additions to the unmodified pinned driver; both driver forms and the original helper scripts are retained for review. The scripts preserve their recorded experiment paths and are archival execution recipes, not a promise of one-command reproduction from this compact package. NetCDF inputs, coefficients, outputs, binary captures, and executable are external and pinned in the records.

The standard-library verifier checks the closed package roster and hashes, links the experiment records to the frozen run/source pins, and validates the reported strict-failure counts and residual controls. It performs no build, solver, model, NetCDF, or network work:

```sh
python3 -I -S validation/rrtmgp37/rfmip-historical-source/verify.py
```

The isolated CI workflow runs only that integrity check. The historical-source candidate still fails 21 strict cells; no full pass or original-generator identity is claimed.
