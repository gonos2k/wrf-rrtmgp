# Exact layer counts and snow-radius eligibility

These tables use the exact raw arrays in the pinned LW captures; the paired SW raw captures carry the same native path/radius values and are separately pinned in `captured-layer-audit.json`. Layers are 1-based native WRF indices. No threshold is applied to path values.

## Rain anchor `(i,j)=(136,48)`

Strictly positive `RWP_OMITTED`: 16 of 39 layers; sum 202.428637028 g m⁻².

| k | CF | QR (kg kg⁻¹) | RWP omitted (g m⁻²) |
|---:|---:|---:|---:|
| 1 | 0 | 4.6482826e-05 | 3.13205695152 |
| 2 | 0 | 4.6746547e-05 | 4.1988902092 |
| 3 | 0 | 4.6761659e-05 | 5.45885801315 |
| 5 | 0 | 4.741408e-05 | 8.65418624878 |
| 6 | 0 | 4.8322156e-05 | 10.5648422241 |
| 7 | 0 | 4.9267899e-05 | 12.6580266953 |
| 8 | 0 | 5.0267899e-05 | 14.6400527954 |
| 9 | 0 | 5.1495554e-05 | 16.5711135864 |
| 10 | 0 | 5.2917334e-05 | 18.4321060181 |
| 11 | 0 | 5.4368378e-05 | 20.1522903442 |
| 12 | 0 | 5.5720677e-05 | 21.6965084076 |
| 13 | 0 | 5.6613408e-05 | 22.8730545044 |
| 14 | 0 | 5.0303104e-05 | 20.8864803314 |
| 15 | 0 | 3.3532495e-05 | 14.1799316406 |
| 16 | 0 | 1.5866184e-05 | 6.77333164215 |
| 17 | 0 | 3.6391739e-06 | 1.55690741539 |

## Snow anchor `(i,j)=(103,156)`

Strictly positive `SWP_OMITTED`: 13 of 39 layers; sum 5.62248348848 g m⁻². The source radius capability flag is `HAS_REQS=1`; across all 13 active layers `SOURCE_RE_SNOW` is not the float32 `RE_QS_BG=9.99e-6 m` sentinel. `RES` equals that source radius converted to µm within 3.78e-06 µm maximum absolute difference, and every `RES` is above the pinned LW helper's 10-µm snow threshold. These are captured source-radius facts; they do not independently prove the microphysics diagnostic history. The wrapper's BG fallback requires CF>0, so it is not applied on these CF=0 layers.

| k | QS (kg kg⁻¹) | SWP omitted (g m⁻²) | source RE snow (µm) | `RES` (µm) | BG sentinel? |
|---:|---:|---:|---:|---:|:---:|
| 8 | 9.8239347e-08 | 0.026411825791 | 55.684937 | 55.684937 | no |
| 9 | 1.151095e-06 | 0.340280711651 | 100.30276 | 100.30276 | no |
| 10 | 9.858868e-07 | 0.314141750336 | 94.717354 | 94.717354 | no |
| 11 | 2.6854527e-06 | 0.907756924629 | 114.94348 | 114.94348 | no |
| 12 | 5.2058408e-06 | 1.84556162357 | 124.50786 | 124.50786 | no |
| 13 | 5.9481649e-06 | 2.18833065033 | 116.59697 | 116.59697 | no |
| 25 | 8.4272724e-17 | 2.07525108209e-11 | 24.999999 | 25 | no |
| 26 | 8.7264612e-15 | 1.97077532071e-09 | 24.999999 | 25 | no |
| 27 | 8.3880757e-16 | 1.73262043601e-10 | 24.999999 | 25 | no |
| 28 | 1.936555e-17 | 3.65542969158e-12 | 24.999999 | 25 | no |
| 29 | 1.8951609e-21 | 3.26247815706e-16 | 24.999999 | 25 | no |
| 30 | 1.8658602e-23 | 2.92238216165e-18 | 24.999999 | 25 | no |
| 31 | 2.5685625e-20 | 3.65217652263e-15 | 24.999999 | 25 | no |
