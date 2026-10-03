# SURFRAD point-flux comparison for the 2010-06-11 WRF case

This evidence package compares surface radiation at Fort Peck (FPK) and Desert Rock (DRA) against the already completed, paired WRF UDM27 24-hour runs using RRTMG 4/4 and RRTMGP 37/37. It is a two-station, one-day point comparison. It does not establish a winning scheme, physical accuracy, or cloud/microphysics skill.

## Data and pairing

The included daily observations are NOAA GML SURFRAD final quality-controlled files: FPK and DRA for 2010-06-11 (DOY 162), plus 2010-06-12 (DOY 163) for the end-of-run minute. The original files are preserved in `surfrad/`. `download-receipt.json` and `endpoint-download-receipt.json` preserve the exact official URLs, retrieval time, HTTP response headers, byte counts, and SHA-256 hashes. `README_SURFRAD.txt` is the NOAA format/QC documentation used by the parser. The original unit-label mistake in the V1 station summary is preserved with its erratum; use `station-summary-v2.json` for corrected units.

SURFRAD timestamps are UTC minute-average end times. The score uses only QC=0 finite, nonmissing observations; QC-passing negative SW is retained. For the hourly snapshot diagnostic, each WRF HH:00 flux is paired with the SURFRAD minute mean ending at that same time. This comparison has a temporal representativeness limitation because the WRF radiation diagnostic can be held between radiation calls.

For hourly energy, each WRF accumulator increment `A(t1)-A(t0)` is compared against the sum of the 60 observed minute means ending in `(t0,t1]`, multiplied by 60 s. The run uses the WRF default `bucket_J=-1` (inactive), so the accumulated radiation fields are scored as direct J m-2 values. Full-day energy is reported only if all 1,440 minute records pass QC. DRA downwelling LW has a flagged/missing minute at 14:28 UTC; its 14:00–15:00 hourly bin and 24-hour downwelling-LW total are omitted without interpolation. Its other three daily integrals and its 23 valid downwelling-LW hourly bins are retained.

Model fields map to observations as follows: `SWDOWN` to `dw_solar`, `SWUPB` to `uw_solar`, `GLW` to `dw_ir`, and `LWUPB` to `uw_ir`. Observation/model masks are paired field-by-field. The verifier requires both run arms to have completed with all four MPI-rank success markers, exact hourly coverage from 2010-06-11 00 UTC to 2010-06-12 00 UTC, finite and unmasked values, matching static grid/land mask, the expected model field units and dimensions, and unchanged input hashes. The exact history files are not included; all 50 history SHA-256 values are retained in `results/metrics.json` so the local run can be checked against the source files.

## Results

The primary results below are hourly accumulator errors converted to flux-equivalent W m-2 by dividing J m-2 errors by 3600 s. Bias is model minus observation; RMSE uses the same bins.

| Station / flux | Valid hours | RA4 bias / RMSE (W m-2) | RA37 bias / RMSE (W m-2) |
|---|---:|---:|---:|
| FPK downwelling SW | 24 | -31.61 / 117.18 | -26.22 / 112.06 |
| FPK upwelling SW | 24 | -2.58 / 16.36 | -1.64 / 15.97 |
| FPK downwelling LW | 24 | -19.83 / 28.10 | -20.86 / 28.65 |
| FPK upwelling LW | 24 | -9.51 / 12.53 | -9.01 / 12.89 |
| DRA downwelling SW | 24 | +16.29 / 68.43 | +12.03 / 58.45 |
| DRA upwelling SW | 24 | +26.47 / 44.80 | +25.29 / 41.64 |
| DRA downwelling LW | 23 | -17.63 / 34.81 | -20.24 / 35.72 |
| DRA upwelling LW | 24 | -39.01 / 42.81 | -40.51 / 44.44 |

Complete daily energy totals (J m-2) and daily-mean flux errors are:

| Station / flux | Observed energy | RA4 energy | RA37 energy | RA4 / RA37 daily-mean error (W m-2) |
|---|---:|---:|---:|---:|
| FPK downwelling SW | 9,936,930 | 7,205,843.5 | 7,671,590.5 | -31.610 / -26.219 |
| FPK upwelling SW | 1,471,566 | 1,248,676.75 | 1,329,448.75 | -2.580 / -1.645 |
| FPK downwelling LW | 31,866,690 | 30,153,360 | 30,064,228 | -19.830 / -20.862 |
| FPK upwelling LW | 33,766,272 | 32,944,682 | 32,987,690 | -9.509 / -9.011 |
| DRA downwelling SW | 27,324,822 | 28,732,366 | 28,363,948 | +16.291 / +12.027 |
| DRA upwelling SW | 5,634,120 | 7,920,757 | 7,818,994.5 | +26.466 / +25.288 |
| DRA downwelling LW | **Not scored** | — | — | Missing/flagged observation at 14:28 UTC |
| DRA upwelling LW | 40,759,980 | 37,389,196 | 37,259,828 | -39.014 / -40.511 |

Snapshot metrics are separate in `results/metrics.json`; those compare the WRF timestamp diagnostic with a trailing one-minute observation. Plots show both snapshots (solid) and hourly energy divided by 3600 (dashed), and retain the DRA LW gap.

For separation from the primary integrated-energy score, the snapshot-only hourly diagnostic gives:

| Station / flux | N | RA4 bias / RMSE (W m-2) | RA37 bias / RMSE (W m-2) |
|---|---:|---:|---:|
| FPK downwelling SW | 24 | -26.80 / 98.64 | -26.94 / 114.28 |
| FPK upwelling SW | 24 | -2.37 / 14.57 | -2.39 / 17.53 |
| FPK downwelling LW | 24 | -19.36 / 27.50 | -21.11 / 28.84 |
| FPK upwelling LW | 24 | -9.60 / 12.55 | -9.27 / 14.20 |
| DRA downwelling SW | 24 | +61.93 / 167.16 | +57.24 / 137.20 |
| DRA upwelling SW | 24 | +35.39 / 63.36 | +34.09 / 56.78 |
| DRA downwelling LW | 24 | -14.15 / 33.83 | -17.15 / 34.39 |
| DRA upwelling LW | 24 | -35.75 / 39.43 | -37.28 / 40.81 |

The parent independently recomputed all 8 × 2 station/arm hourly-energy series from the raw minute files and WRF accumulator values. `results/independent-energy-recheck.json` records that check and its agreement with the saved metrics to about 1e-8 W m-2. It validates arithmetic and interval/QC treatment, not physical accuracy.

## Representativeness and limits

The nearest cells are nominal 20 km grid cells. FPK is 11.87 km from its selected cell center, whose terrain is 56.15 m above the station. DRA is 10.49 km from its selected cell center, whose terrain is 156.20 m above the station. These point-to-grid differences matter for interpreting fluxes. Temperature and station pressure are not part of the primary score: SURFRAD air temperature is measured at 10 m versus WRF T2 at 2 m, and station pressure needs a height adjustment. Direct-normal radiation is not compared to a horizontal WRF flux. The input's upstream FNL observation assimilation was not audited, so the station record is an external check and is not asserted to be independent of every assimilated datum.

## Reproduction and artifacts

From a checkout with Python, NumPy, netCDF4, and Matplotlib:

```sh
python3 validation/rrtmgp37/surfrad-2010-06-11/score_surfrad.py --self-test
python3 validation/rrtmgp37/surfrad-2010-06-11/run_score_surfrad.py --score \
  --ra4-dir PATH_TO_VALIDATED_CASES/ra4 \
  --ra37-dir PATH_TO_VALIDATED_CASES/ra37 \
  --run-receipt PATH_TO_VALIDATED_CASES/execution.json \
  --preflight PATH_TO_VALIDATED_CASES/preflight.json \
  --output NEW_OUTPUT_DIRECTORY
python3 validation/rrtmgp37/surfrad-2010-06-11/plot_surfrad_metrics.py \
  NEW_OUTPUT_DIRECTORY --output-dir NEW_PLOT_DIRECTORY
python3 validation/rrtmgp37/surfrad-2010-06-11/verify_artifacts.py \
  validation/rrtmgp37/surfrad-2010-06-11/manifest.json
```

The recorded run used `build/udm-current-24h-plan/execution.json`, `preflight.json`, and the corresponding `cases/ra4` and `cases/ra37`. Its command log and runtime receipt are in `results/`. The first report write failed only because NumPy scalar metadata was not JSON serializable; that attempt is preserved as `results/serialization-failure-run.log`. The corrected serialization path then completed the validated score. No model binaries or history NetCDFs are bundled.

`manifest.json` hashes every included artifact. `results/metrics.json` records hashes of all external observation/model inputs before and after the successful scoring pass; `input_immutability.all_unchanged` is true. Metrics were calculated from the two completed paired runs without modifying observations, WRF histories, namelists, or model source.
