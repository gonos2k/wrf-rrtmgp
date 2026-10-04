# Same-call RRTMG4 / RRTMGP evidence

This package gathers a bounded, read-only comparison at domain 1, grid point `(i=24,j=55)`, WRF step 2161 (`source_seconds=129600`, 2016-10-07 12:00 UTC). It includes three one-minute executions (`OLD_OFF`, `NEW_OFF`, `NEW_ON`), one LW and one SW first-call replay trace from each arm, the selected `NEW_ON` observer CSV, and deterministic gzip copies of the corresponding RRTMG4 LW/SW exports. No model, solver, or build is run by the portable verifier.

The frozen v3 analysis and v2 dry-column reconstruction are retained byte-for-byte in `frozen/`. Their original reports/scripts contain workspace-specific paths; treat them as historical snapshots. `reproduce.py` is the portable package-relative verifier. From this directory, run:

```sh
python3 -B reproduce.py --output /tmp/rrtmg4-same-call-reproduction.json
```

The output must be outside this package. It verifies the exact artifact roster and hashes, decompresses both exports and checks their raw-byte pins, parses all six trace filesets (two phase calls per arm, each with input/raw/result; LW uses V10 and SW V11), checks selected point/time/native-layer headers, and reproduces the same-call input and CSV/output checks. It uses only the Python standard library and the bundled `parser/read_export.py`.

## What the evidence shows

The paired captures have matching thermodynamic and gas inputs at the selected point, while the radiation configurations retain different cloud-path/mask representations, particle-radius conventions, and spectral discretizations. RRTMGP has 128 LW and 112 SW g-points; RRTMG has 140 LW and 112 SW g-points. Their g-points are not positionally aligned. The first common SW band boundary is 2600 cm⁻¹ in RRTMG and 2680 cm⁻¹ in RRTMGP, so the 80 cm⁻¹ difference is an index-match approximation, not a one-to-one spectral mapping.

The CSV summarizes 128 observer seeds. Each GP trace is one captured phase call/seed; it is not the CSV ensemble mean. The CSV values checked here are the selected rows for `SURFACE_DOWN`, `TOA_UP`, `HEAT_1`, `HEAT_31`, and `HEAT_44`. The verifier checks binary32 representation where values cross the WRF REAL32 boundary. These checks establish that the selected observer rows correspond to the exported/replayed values; they do not establish full-array solver equivalence.

The dry-column reconstruction separates 44 native model layers from RRTMGP extension layers: 13 in LW and 1 in SW. The captured REAL32 native dry masses, promoted to REAL64 and multiplied by the initialized molecular conversion, reproduce the native `GAS_COL_DRY` prefixes exactly. Separately, the legacy operation-by-operation REAL32 reconstruction reports 0 ULP for the 102 captured legacy `COLDry`/`COLDRY` values across all solver layers (57 LW + 45 SW; 88 native-layer values total) against the REAL32 reconstruction. For actual exported columns, the reported mean/max absolute relative difference is 0.1651868890% / 0.2891570627% when normalized by native values; the maximum normalized by legacy values is 0.2883233554%. These are denominator-specific summaries, not contradictory estimates. Formula-only REAL64 ratios in the frozen reconstruction are not actual-export ratios.

The separate layer-31 context analysis reproduced its frozen result and reviewed coefficient joins for 11 LW and 12 SW physical bands. In the frozen layer-31 JSON, generic `TOTAL_*` fields named `values_by_band` are actually g-point vectors; the explicit coefficient-based joins provide the band mapping. Captured LW trace inputs use V10 and SW use V11. All inspected masks were one in native layers 30–32 at this point. That rules out a missed cloudy sample in those local layers, but not McICA effects elsewhere in the column that can affect boundary fluxes or heating.

## Limits

This is a descriptive comparison of two operational configurations at one selected column and call. Different masks, paths, radii, and spectral spaces prevent interpreting it as a pure engine effect. The layer-context evidence does not provide a sampled-cloud bundle or flux attribution. Nothing here establishes independent observational accuracy, forecast skill, an overall winner, or that a remaining flux residual is normal or bug-free.

The external pin files identify the existing PR74 runtime/build and exported coefficient/data evidence without bundling executables or large coefficient NetCDF files. The frozen historical analyses are preserved unchanged; the portable verifier and this README clarify their scope without rewriting their results.
