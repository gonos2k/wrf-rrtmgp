# RFMIP `RTE-RRTMGP-181204` provenance check

This is a read-only provenance and coefficient-file comparison. It did not run a model or build software.

## Finding

`RTE-RRTMGP-181204` is a CMIP6 `source_id` label. The official CMIP6 CV expands it to “RTE+RRTMGP (2018-12-04 full-resolution)”; the published reference file repeats that label and has a 2023 creation timestamp and tracking ID. Neither the CV nor the file attributes identify a Git commit, executable hash, or coefficient-repository commit. The `181204` substring therefore cannot be treated as an exact commit date or SHA.

The public `rte-rrtmgp` tag `v1.0.0` is a real candidate release, resolving to commit `ed5b0113109fcd23a010a90c61f21bad551146ef` (commit date 2019-08-08). Its tree contains files named `rrtmgp-data-{lw-g256,sw-g224}-2018-12-04.nc`. The Zenodo software record says this release commit was used to create data for its cited journal paper, but does not establish that this exact commit and coefficient pair generated the CMIP6 `RTE-RRTMGP-181204` reference files. No exact mapping was found. The similarly dated Git commit `f3dc8d1646ccee939c7f0f674811dc8539172f60` is only date-correlated; it is not provenance evidence for the published output.

## Coefficient comparison

The two files from `v1.0.0` were fetched from the tag's raw GitHub URLs. Their Git blob IDs and SHA256 values are recorded in `provenance.json`. Their common gas coefficient/lookup arrays match the currently pinned data exactly: 30 of 30 shared LW variables and 29 of 29 shared SW variables.

They are **not directly schema-compatible** with the current v1.8 example loader. The old LW file lacks `optimal_angle_fit`. The old SW file contains one `solar_source` vector, while the current loader expects `solar_source_quiet`, `solar_source_facular`, `solar_source_sunspot`, `tsi_default`, `mg_default`, and `sb_default`. Current default reconstruction of the split SW sources differs from the old stored vector by up to `5.0016945e-4` in the stored spectrum over 224 points. That fact alone does not attribute any flux difference in the published RFMIP output.

The current RFMIP regression remains a reproduction against the available published reference using the explicitly pinned current source/data. It must not be described as a bit-for-bit or exact-source reconstruction of the historical `source_id` implementation. The separate local RFMIP comparison records its own current-pinned results and tolerances.

## Reproduction artifacts

- `provenance.json`: findings, candidate release, source/data pins, and published sample attributes.
- `coefficient-content-comparison.json`: dimensions, variable inventories, common-array exact comparisons, and solar-spectrum comparison.
- `compare_coefficient_content.py`: comparison script.
- `v1.0.0-commit.json`, `v1.0.0-ref.json`, and `tagged-source-tree.json`: public GitHub API responses for the release and file tree.
- `v1.0.0-mo_load_coefficients.F90`: loader from the tagged source.
- `rrtmgp-data-lw-g256-2018-12-04.nc` and `rrtmgp-data-sw-g224-2018-12-04.nc`: coefficient files downloaded from the tag.
- `commits-2018-12-03-06.json` and `data-commits-2018-12-03-06.json`: bounded API query used to check whether date-adjacent commits supplied an exact mapping.

Primary public references: [CMIP6 source ID controlled vocabulary](https://wcrp-cmip.github.io/CMIP6_CVs/docs/CMIP6_source_id), [published CMIP6 dataset metadata](https://www.wdc-climate.de/ui/cmip6?input=CMIP6.RFMIP.RTE-RRTMGP-Consortium.RTE-RRTMGP-181204), [RRTMGP v1.0.0 software record](https://zenodo.org/records/3403173), and [the tagged source tree](https://github.com/earth-system-radiation/rte-rrtmgp/tree/v1.0.0).
