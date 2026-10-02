# PR20 frozen-mode 24-hour paired WRF comparison

This is a post-run comparison of the completed 25-record hourly MPI4 mode-1 run and the completed RA4 reference. It is classified as a **coupled trajectory difference**. The initial state and boundary files are byte-identical, and the first history record has zero differences for every reported field. After that instant, the runs evolve under different radiation/microphysics treatment, so the later differences include feedback through the coupled model. They are not same-state intrinsic radiation differences and are not observational bias or accuracy scores.

The mode-1 receipt records a successful 24-hour run from `2010-06-11_00:00:00` through `2010-06-12_00:00:00`, with 25 finite history records and no fatal/table-range diagnostics. Its executable SHA-256 is `4c979fb248b26d8ce61f05fd602f55e0492e173a312e3532021fecda508e2503`; the frozen table SHA-256 is `8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583`. The RA4 case-local executable SHA-256 is `ab2d648284d54ff2b0ff3c90e738e3f91f31169b9677190096c7fc9231c08424`. Both `wrfinput_d01` files hash to `5ef7abe34c516fba107f346bdbdb3777edacb5d48493df467ea2dd8bcf6a75ff`; both `wrfbdy_d01` files hash to `e687b73730ab9a2cee4842e1a92b225a4edb074ba080b6053d96d81ec1731a2d`. The full SHA-256 for each hourly history is recorded in `coupled-metrics.json`.

The mode-1 build is based on source commit `f8cbfeea7f4c59e5e0655bd2f23e3b424b8359b3` with the run-specific production overlay tracked by `frozen-overlay-receipt.json`; its receipt hashes every overlaid source file. Do not interpret the base commit alone as the complete runtime source identity.

Metrics use the complete common native mass grid (289 × 189); there is no boundary mask. The cell weights are `AREA2D` read from the histories (m²), and the grid is required to be identical between runs. For paired differences `d = RRTMG4 - PR20 RRTMGP37 mode1`, the area-weighted mean is `sum(d*A)/sum(A)`, area-weighted RMSE is `sqrt(sum(d²*A)/sum(A))`, and L∞ is `max(abs(d))` over every native cell. The JSON reports hourly values, the initial-time difference, summaries across all 25 times, and later-hour feedback maxima.

Six column hydrometeor paths are independently reconstructed at every history time from the native WRF dry layer mass:

`dry_mass = -DNW * (C1H * (MU + MUB) + C2H) / 9.81` kg dry air m⁻²,

then `path = 1000 * sum(q_species * dry_mass)` over the native `bottom_top` layers, in g m⁻². This matches the native dry-mass expression used by the WRF UDM host path (`module_first_rk_step_part1.F`, `udm_dry_layer_mass` construction); `g=9.81 m s⁻²` is WRF's `module_model_constants.F`. The mixing ratios are per kg dry air. No extension layers are added to these native WRF column paths.

`RAINC` and `RAINNC` are cumulative fields. For each run independently, the initial value is subtracted before comparison; raw negative increments, if any, are retained (never clamped). Their reported differences are therefore differences in accumulated increments from the common initial time.

RA4 retains its earlier UDM generic-radius behavior and legacy cloud/precipitation optics. PR20 mode 1 uses UDM-native radii, CCPP rain/snow and experimental homogeneous-ice PSD optics for graupel/hail. This PR20 executable sets six explicit gas VMRs and omits CFC11/CFC12/CFC22/CCl4 profiles that the existing RRTMG wrapper uses. PR21 subsequently corrects that omission; it was not present in this 24-hour trial. These configuration differences limit interpretation of the coupled comparison.

The history files do not contain `GSW`, `SWDDIR`, `SWDDIF`, `RTHRATLW`, or `RTHRATSW`; `coupled-metrics.json` explicitly lists these requested diagnostics as unavailable rather than substituting differently named fluxes. This evaluation establishes finite runtime and quantifies the paired run differences only. It does not establish long-forecast readiness or scientific accuracy.

Across all 25 times, area-weighted RMSE was 44.51 W m⁻² for SWDOWN, 6.68 W m⁻² for GLW, 7.47 W m⁻² for OLR, 0.207 K for T2, and 6.29 Pa for PSFC. The largest later-hour single-cell absolute differences were 902.7 W m⁻² (SWDOWN), 96.7 W m⁻² (GLW), 151.4 W m⁻² (OLR), 5.41 K (T2), and 200.4 Pa (PSFC). These maxima are whole-domain extrema, not domain-mean departures. Among the reconstructed paths, all-time area-weighted RMSE ranged from 10.43 g m⁻² (IWP) to 44.46 g m⁻² (SWP); later-hour L∞ maxima ranged from 342.7 g m⁻² (IWP) to 14,788.4 g m⁻² (LWP). All reported fields had exactly zero initial-record differences.

Reproduce with `python build/udm-frozen-24h-comparison/script.py --mode1 build/udm-frozen-runtime-mpi/case-mode1 --ra4 build/udm-realdata-24h/ra4 --output build/udm-frozen-24h-comparison/metrics.json --mode1-exe build/udm-frozen-runtime-mpi/WRF/main/wrf.exe --ra4-exe build/udm-realdata-24h/ra4/wrf.exe --frozen-table build/udm-frozen-runtime-wrf/source/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc`.

During review, gas/radius descriptions, the signed difference convention, initial zero-radiation interpretation and HAILNC/GRAUPELNC units were corrected. `coupled-provenance-corrections.json` identifies the untouched original scratch files and annotations; measured arrays and numerical metrics were not changed.
