# UDM27 negative radiation-input contract

Option 37 corrects finite negative hydrometeor inputs only when their magnitude is strictly below a ceiling supplied by UDM. The correction is applied to the radiation builder's local copy; raw WRF state, UDM equations, all positive inputs and the existing RRTMG4 path remain unchanged. Any positive hail is still unsupported, even below a negative-input ceiling.

## Policy and evidence

| Phase | Native process-scale ceiling (kg/kg) | Recorded minimum in the successful RRTMG4 24-hour hourly history (kg/kg) |
|---|---:|---:|
| cloud liquid / QC | `qcmin = 1e-12` | -2.24e-16 |
| cloud ice / QI | `qcmin = 1e-12` | -5.35e-14 |
| rain / QR | `qrmin = 1e-9` | -2.60e-15 |
| snow / QS | `qrmin = 1e-9` | -3.18e-12 |
| graupel / QG | `qrmin = 1e-9` | -1.77e-20 |
| hail / QH | `qrmin = 1e-9` | -8.92e-24 |

These are **deliberate process-scale operational clip ceilings, not floating-point error bounds**. UDM uses `qcmin`/`qrmin` in positive process activation, number and size calculations. Separately, its existing `flgzero` branch clips negative inputs in its internal working copies. The pure `udm_radiation_negative_limits()` helper exports the existing constants in L/I/R/S/G/H order; it does not change microphysics.

The [24-hour receipt](../../../validation/rrtmgp37/native-hydro/24h-comparison-receipt.json) and [native input observations](NATIVE_HYDRO_DIAGNOSTICS.md) motivate compatibility with the host's existing nonnegative working-state treatment. The first strict 37 failure was QI = -2.887890293650070e-35 kg/kg at radiation time 600 s. The healthy RRTMG4 hourly-history minima are within the selected ceilings, but they are not every radiation activation or the evolving 37 state. In particular, the precipitation ceiling is substantially larger than the observed minima. Acceptance does not establish that a negative was caused by roundoff, or that all future negatives within that bound are harmless.

## Exact acceptance and accounting

The standalone builder remains strict when `negative_q_limits` is absent. A supplied vector must have six finite nonnegative values. For each phase, only `-limit < q < 0` is replaced with zero. Equality, larger-magnitude negatives, and nonfinite inputs remain fatal with species, value, limit, column context and vector-layer index. A zero ceiling remains strict. No positive mass is removed, including positive amounts below the native process activation scales.

Optional outputs preserve the original accepted negatives in `clipped_negative_q(nlay,6)` and the positive correction to signed grid water path in `negative_grid_correction(nlay,6)`, both in L/I/R/S/G/H order. Mixing-ratio units are kg/kg; path units are g/m2:

```
correction = -min(q_raw,0) * dp_hPa * 100 / g * 1000
signed_raw_grid_path + correction = prepared_nonnegative_grid_path
```

The algebraic closure is evaluated at the output precision; a path smaller than a representable REAL quantum may underflow to zero while its original negative q remains recorded.

The WRF wrappers supply UDM's ceilings only for the 37 path. They aggregate accepted-layer counts, maximum absolute corrected q and summed grid-path correction per phase and tile activation. Counts use the original negative q, so an underflowed path does not erase the event. LW and SW summaries describe the same physical inputs separately and must not be added as separate removed masses. Path sums across cells/layers are not area-integrated domain mass or time accumulation.

Raw capture adds `NEGATIVE_Q_LIMITS`, `NUMERIC_CLIPPED_QC/QI/QR/QS/QG/QH` and `NEGATIVE_GRID_CORRECTION_LWP/IWP/RWP/SWP/GWP/HWP`. Despite the historical `NUMERIC_CLIPPED` tag, these records indicate operational input corrections, not a diagnosed numerical cause. The raw mixing ratios remain signed. Physical replay input remains nonnegative and uses the existing format. Python replay validation independently checks bounds and correction records before reconstructing the prepared paths. The native observer continues to record every raw negative and its global indices before the wrapper runs.

## Validation scope

`test_udm_negative_policy.py` compiles the actual builder and checks accepted six-phase corrections, strict defaults and boundaries, invalid limits, nonfinite values, unchanged input bits, positive-input invariance, underflow counts, positive-hail refusal and independent raw-record reconstruction. Whole-library tests, real serial WRF paired SCM/replay and a new MPI real-data attempt are recorded separately. A successful short run does not establish 24-hour 37 forecast accuracy, graupel/hail support or observational skill.

## Actual MPI real-data check

The rebuilt GNU MPI4/OMP1 `em_real` executable used the same official NCAR case and identical initialized/boundary files as the previous attempt. It completed the previously rejected 600-second radiation activation with bounded negative corrections. All four native diagnostic tiles were complete at 0, 600 and 1200 seconds. At 1200 seconds, rank 2 reported unsupported positive hail at i=106, j=114, k=15: QHAIL = 4.3357061e-11 kg/kg and grid path = 1.316034e-5 g/m2. The requested one-hour run exited through MPI_Abort; it is not a completed one-hour or 24-hour forecast.

The saved 1200-second history precedes the failing radiation evaluation. The matching RRTMG4 observer-on/off histories also contain 407 positive hail cells at that sampled time; at the reported cell, QHAIL = 4.3325440e-11 kg/kg. This identifies an unsupported UDM state, rather than evidence that the correction uniquely generated hail. It does not establish either scheme's physical accuracy or explain all coupled flux differences. No hail threshold, graupel mapping, cloud fraction or delta-scaling policy was changed to continue the run.

[Runtime receipt](../../../validation/rrtmgp37/negative-input/runtime-result.json), [same-time state comparison](../../../validation/rrtmgp37/negative-input/same-time-hydro-history.json), [native phase summaries](../../../validation/rrtmgp37/negative-input/hydro-summary-0-600-1200.csv) and [raw rank events](../../../validation/rrtmgp37/negative-input/radiation-diagnostic-events.csv) retain this limited outcome. Raw WRF diagnostic log lines do not carry timestamps; their file/line order is preserved without inventing event times. The native observer CSVs separately identify activation seconds.
