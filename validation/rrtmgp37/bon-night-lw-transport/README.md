# BON night LW angular-transport sensitivity

Three successful standalone calls used one unchanged first BON night input, with all 45 gas dry columns already matched to the actual legacy export. A single private diagnostic driver compile/link succeeded. There were no WRF forecasts, REAL runs or production source changes in this experiment. The existing repository reference source remains unchanged; the private snapshot and patch are archived under `frozen/`.

| Transport policy | Surface down LW, W m⁻² | Change from default, W m⁻² | Remaining difference from actual legacy, W m⁻² | Maximum native-32 heating change, K day⁻¹ |
| --- | ---: | ---: | ---: | ---: |
| Original one-angle default | 189.0875147367 | 0 | +1.2498835111 | 0 |
| Uniform transport secant 1.66 | 189.3456966635 | +0.2581819268 | +1.5080654379 | 0.0089633783 |
| Four Gauss-Jacobi angles | 188.5389184336 | −0.5485963032 | +0.7012872080 | 0.0318063447 |

The actual legacy surface flux is 187.8376312256 W m⁻². Full 45-layer heating maxima are 0.0392875966 and 0.2745417162 K day⁻¹ for the two altered policies; these include 13 upper extension layers and must not be labeled native WRF maxima. All-sky and clear heating responses coincide in this inactive-cloud call; tiny frozen optical depths remain nonzero. Full values and TOA fluxes are retained in [summary.json](summary.json).

Policy 1 reproduces the previous matched-dry result byte-for-byte. Eighteen main optical/gas/cloud/mask/radius fields and five source/band fields are IEEE64-identical across all three policies. This isolates angular-policy sensitivity within this GP closure, without identifying which engine is accurate. The five sidecar fields are SOURCE_LAYER, SOURCE_LEVEL, SOURCE_SURFACE, BAND_LIMITS_GPOINT and BAND_LIMITS_WAVENUMBER; they are not per-band fluxes. The sidecar name `LW_DIFFUSIVITY_ANGLE` stores a transport **secant**, not an angle in degrees. All three calls use the same executable, input, data and frozen table.

Legacy uses water-column-dependent band diffusivity, rather than a uniform 1.66 secant. Its first two bands are 10–350/350–500 cm⁻¹, while GP uses 10–250/250–500. Only legacy/GP bands 3–13 have exactly matching physical edges; gpoint grids differ (140 versus 128). Uniform 1.66 is therefore a sensitivity experiment, not exact RRTMG angular or spectral parity. Four-angle proximity to the retained legacy number is not an accuracy winner. The remaining residual combines gas/source/spectral/transport and other implementation differences. Neither finite band-edge metadata nor this experiment proves a Planck-tail support mismatch.

The [background-gas audit](audits/background-gases/README.md) confirms current production and reference gas lists omit explicit N2 minor terms. This is a source/coefficient finding only: **all three measured transport modes retain that same gas closure, and this package contains no measured N2-enabled results**. The source-contract audit also records exact gas/thermodynamic joins and REAL32 legacy CFC column reconstruction. These audit scripts retain original absolute workspace paths and require external coefficient/source files; they are provenance snapshots, not portable full-analysis entry points. Their original reports and preparation status labels remain verbatim.

The input, previous matched-dry baseline and actual legacy export are reused by relative, hashed links to [PR85 dry attribution](../bon-night-dry-column-attribution/README.md) and [BON same-state evidence](../bon-night-same-state/README.md). Six compressed result/sidecar files, three logs and original source/build/run/authorization/independent-review receipts are retained with exact origin hashes. Original preparation receipts still say unrun; authoritative execution and terminal receipts record the three completed calls. The receipt's zero WRF/REAL/build field refers to the run phase; the separate build receipt records one private compile.

From this repository checkout:

```sh
python3 -I -S validation/rrtmgp37/bon-night-lw-transport/verify.py --output build/bon-lw-transport-verification.json
python3 -I -S validation/rrtmgp37/bon-night-lw-transport/test_verify.py
```

The stdlib verifier checks the closed 38-payload roster, origin/decompression hashes, reused dependencies, archived build/run/authorization/source joins, three distinct PIDs and RC 0, exact default baseline bytes, 24-section result rosters, finite arrays, policy sidecar shapes/values, 18 held fields, five held source/band fields, and recomputed surface/TOA/heating metrics. Its seven offline controls reject missing gas fields, signed-zero or source changes, wrong policy values and unexpected sidecar fields. They test the Python evidence contract, not compiled Fortran rejection paths. Verification invokes no numerical engine and writes only a new report outside the package.

External source/ELF/library/NetCDF stability is archived execution and independent-review attestation. The portable verifier does not reopen unbundled binaries, coefficient tables, forecast histories or all external source files, and does not recalculate gas optics or Planck functions. This one night column uses experimental frozen mode 1 and roughness 1, with the old-checkpoint CF3 limitations inherited from PR85. No observational LW-bias resolution, general accuracy, production policy change or physical-normal conclusion is established.
