# Observational appendix: one day, three sites

NOAA SURFRAD measurements are independent observations. This comparison is limited to three point measurements and nearby 30 km model cells (about 9.7,11.0,12.3 km separation at Goodwin Creek, Penn State and Bondville). It does not establish domain-wide or general forecast skill.

Each observation interval contains twenty QC0 three-minute means, time-stamped at the interval end, multiplied by 180 s. Nighttime negative measured fluxes remain in the data; no clipping, gap filling or interpolation was used. Model means are hourly cumulative-energy increments divided by 3600 s: ACSWDNB for downward SW, ACLWDNB for downward LW, and ACSWDNB−ACSWUPB for net surface SW. They are not instantaneous SWDOWN/GLW samples. The source/metadata/namelist checks retain the J/m² and disabled-bucket policy.

**RA4 has 24 hourly intervals per site/variable. RA37 has only two common intervals (12–13Z,13–14Z) before its fatal failure. There is no daily RA37 score or winner claim.**

RA4 full-day bias / RMSE, W/m² (model minus observation; n=24 each):

| Site | Downward SW | Downward LW | Net surface SW |
| --- | --- | --- | --- |
| GWN | 15.96 / 25.14 | -10.00 / 17.59 | 14.32 / 22.06 |
| PSU | 18.80 / 28.82 | -20.17 / 25.64 | 46.90 / 78.93 |
| BON | 11.47 / 15.64 | -19.62 / 32.41 | 26.57 / 41.78 |

[The complete comparison](model_observation_comparison.json) retains all MAE/bias/RMSE values and explicitly scoped two-hour paired differences. [The interval CSV](model_hourly_comparison.csv) retains every observed/model mean, energy increment and time window. The hardened comparison script pins its parser outputs, raw six-file set, common input and boundary, arm namelists/physics, history Times/metadata and immutable inputs before/after. Offline synthetic accumulator/gap/repeated-time checks passed; no model engine ran for the observational analysis.

[Download provenance](download_manifest.json), [offline observation receipt](verified_observations.json), [parser/test execution receipt](verification_run.json) and parser/test sources are retained. Six daily raw files (~0.68MB) and two documentation files are hash-only in [external-observation-artifacts.json](external-observation-artifacts.json); the portable verifier does not reparse missing raw files or reread model NetCDF. It verifies retained pins/receipt links and recomputes score arithmetic from the retained interval CSV. It cannot independently establish those CSV values from omitted external data.

[Root independent readback](root-observation-hourly-readback.json) separately reaggregated all six original daily files (480 target samples per site), without the data-fetch parser. All 234 retained comparison-row observation means agreed within 1.14e-13 W/m²; negative QC0 samples were preserved. This derived receipt is retained; its original inline command was not saved as a standalone script.
