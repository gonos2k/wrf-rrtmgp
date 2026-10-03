# Corrected paired 24-hour comparison, V2 map-factor weighting

The approved V2 analyzer completed on the paired RA4/RA37 case. Both runs are
`BOTH_VALIDATED`: four MPI ranks, 25 hourly output records from 2010-06-11 00Z
to 2010-06-12 00Z, finite history arrays, and validated 12 h/24 h restart
files. Executable SHA256 is
`176f589d657ca87df670cef3429d7474e674f3e44445eb7886aed871e36bef8f`; the exact
analysis script SHA is recorded in `analysis.json`.

V2's primary weights estimate projected cell ground area as
`DX*DY/(MAPFAC_MX*MAPFAC_MY)`, from checked static, positive map factors and
DX=DY=20,000 m. The derived cell weights range from 363,804,003.76 to
406,941,005.42 m² and sum to 21,597,025,075,456.72 m². These are cell-center
map-factor area estimates, not geodesic integration over cell boundaries or
an exact Earth-surface area integral. WRF `AREA2D` is reported separately.
Source `WRF/phys/module_physics_init.F:5882-5895` leaves the map-factor area
formula under `#if 0`; active code assigns `AREA2D=DX*DY`. Thus V1's nominal
integrals and weights remain correct for the active model-defined `AREA2D`,
but they are not physical Earth-area integrals. See `../V1-ERRATUM.md`.

The area-weighted 01Z–24Z means below are arithmetic means of 24 hourly saved
spatial means; the 00Z initial snapshot is excluded from these means. The
endpoint is 24Z. Each cell-metric and the corresponding model-AREA2D metric
are available at every time in `analysis.json` and `hourly_area_metrics.csv`.
Differences are RA37 minus RA4. Hourly saved fields are snapshots, not hourly
mean fluxes. L-infinity is unweighted over the same 54,621 physical grid cells.

| Field | Units | Mean RA4 | Mean RA37 | Mean difference | 24Z difference | Max hourly RMSE | Max hourly L∞ |
|---|---:|---:|---:|---:|---:|---:|---:|
| SWDOWN | W m⁻² | 324.6628 | 319.3570 | -5.3058 | -6.1355 | 79.2312 | 896.2209 |
| GLW | W m⁻² | 345.1996 | 345.5219 | +0.3223 | +0.5554 | 9.3165 | 96.8758 |
| OLR | W m⁻² | 260.4671 | 261.4461 | +0.9790 | +0.4090 | 11.2749 | 153.0675 |
| T2 | K | 291.6914 | 291.6822 | -0.0092 | -0.0183 | 0.3200 | 5.3461 |
| PSFC | Pa | 96852.3926 | 96851.1433 | -1.2493 | -4.7564 | 12.2746 | 196.0156 |

Daily endpoint energy differences use WRF timestep accumulators at 00Z and
24Z. Both arms have `BUCKET_J=-1`, so accumulator totals use AC alone. The
energy-derived average flux difference is endpoint-delta divided by 86,400 s.
The V2 physical-map-area and active-model-AREA2D values are shown separately:

| Accumulator | Physical-area RA4 delta (J m⁻²) | Physical-area RA37 delta (J m⁻²) | Physical-area difference / 86400 (W m⁻²) | Model-AREA2D difference / 86400 (W m⁻²) |
|---|---:|---:|---:|---:|
| ACSWDNB | 28,105,838.69 | 27,651,279.37 | -5.2611 | -5.3119 |
| ACLWDNB | 29,806,700.87 | 29,834,329.24 | +0.3198 | +0.3203 |
| ACSWUPT | 8,778,666.57 | 8,801,151.71 | +0.2602 | +0.3076 |
| ACLWUPT | 22,515,570.52 | 22,599,201.20 | +0.9679 | +0.9610 |

The field math contract has 225 checks: 125 PASS, 0 FAIL, 100 SKIP. Available
identities GLW=LWDNB and OLR=LWUPT pass at all 25 outputs in both arms, as does
RA37 SWDOWN=SWDNB. The output omits RTHRATEN/RTHRATLW/RTHRATSW in both arms,
and omits RA37 SWDDIR/SWDDIF and GSW at every output; those identities are
explicitly skipped. Overall status remains `INCOMPLETE_FIELD_MATH_CONTRACTS`.
No identity mismatch was found among evaluated checks; missing identities are
not treated as passing. Full per-output tolerances and maximum normalized
errors are in `analysis.json`.

This is a paired coupled-trajectory comparison, not a same-state solver
attribution, an observational skill score, or evidence of forecast superiority.
Changing radiation affects the evolving atmospheric state. A separate
same-executable continuity check restarted each arm from its own 12Z checkpoint
and compared the resulting 13Z history against that arm's continuous 13Z
history. Both arms matched every numeric field exactly (201 variables for RA4,
204 for RA37); an independent raw-array-byte check also matched all numeric
arrays and the `Times` array bitwise. Each whole-file comparison still reports
the expected global `START_DATE` change from 00Z to 12Z, so no full-file-byte
identity is claimed. The restart receipt, preflight, and raw-array recheck are
packaged separately from these trajectory metrics. V1 outputs and script
remain preserved unchanged.
