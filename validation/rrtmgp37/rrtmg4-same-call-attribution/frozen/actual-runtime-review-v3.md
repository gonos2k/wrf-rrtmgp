# Same-call RRTMG4 and RRTMGP observer comparison

This is a read-only comparison of the instrumented RRTMG4 result and the actual RRTMGP37 trace from one ON forecast call: domain 1, grid point `(i,j)=(24,55)`, step 2161, source time 129600 s. The RRTMG4 export reports the same call context. It does not compare whole forecasts or establish which radiation scheme is more accurate.

The reproducible parser/analysis is `compare_actual_v3.py`; its machine-readable result is `actual-same-call-comparison-v3.json`. Run from the repository root with:

```sh
python3 build/udm37-current-rrtmg4-optics-export-analysis-v1/compare_actual_v2.py
```

The analysis checks selected RRTMG4 export and adapter `input/result/raw` records against the independent `audit/same_state.csv` row at `(24,55)`. The ten selected CSV metric rows (surface down, TOA up, and heat at native layers 1, 31, and 44, in both phases) provide 20 engine-value comparisons. They agree with their exported/captured results to at most `1.2e-7` in the written decimal representation. This establishes observer placement and output correspondence for those selected values; it is not a tolerance or accuracy test.

## Matched and differing inputs

After normalizing only the known one-column GP leading dimension, the radiatively used pressure and layer-temperature profiles match bit-for-bit between the export and GP replay: PLAY, PLEV, TLAY, and (for LW) TLEV and TSFC. Six major-gas VMRs match bit-for-bit in each phase; the four LW CFC VMRs also match. The GP LW adapter passes those CFC arrays to `set_gases_lw`, which sets all four species (`module_ra_rrtmgp.F:469-520, 788`). They are active LW inputs, not merely trace records. SW thermal TLEV/TSFC values in the GP replay are zero and are not SW thermal boundary inputs, so they are not treated as state comparisons. SW cosine zenith and the four direct/diffuse VIS/NIR albedos match bit-for-bit.

The dry-air molecular columns are not equal. Both are in molecules cm⁻²: RRTMGP uses native WRF dry layer mass for the first 44 layers, then its pressure/VMR extension (`module_ra_rrtmgp.F:574-586, 789, 1019`); RRTMG4 derives its column from pressure thickness and thermodynamic composition (`module_ra_rrtmg_lw.F:11475-11477`, `module_ra_rrtmg_sw.F:9998-10000`). The maximum absolute relative difference is 0.2883% at layer 19 (zero-based 18, 449.288 hPa); the mean absolute relative difference across all solver layers (57 LW, 45 SW) is 0.1351% LW and 0.1619% SW. On native layers only (44), the maximum remains 0.2883%; the extension-layer maximum is 0.0347%. This is a distinct input construction to preserve in causal attribution, not by itself evidence of a defect.

RRTMG4 exports cloud mass paths and masks per stochastic g-point (`module_ra_rrtmg_lw.F:11122-11129`, `module_ra_rrtmg_sw.F:9432-9443`). The GP replay provides one column of layer cloud/path inputs plus its own sampled result mask. The representations, masks, and seeds differ, so equality of those path arrays or g-point masks is not a valid comparison. Liquid and ice radii RELIQ/REL and REICE/REI do match exactly. Snow size differs in eight cloudy layers: GP RES is 146.49–376.16 µm while the RRTMG4-exported RESNOW is 130 µm in those layers; both have positive snow path there. The report records the layerwise values. That observed difference is relevant to optical attribution, but this single pair does not prove its effect on the flux residual.

Final RRTMG4 flags are INFLAG=5, ICEFLAG=5, LIQFLAG=1, ICLD=2; the GP replay input carries ice flag 4. The respective optical models and cloud treatments differ. LW g-point counts are 140 for RRTMG4 and 128 for GP; SW counts are 112 each, but those points are not positionally interchangeable. The first shared SW band edge is 2600 cm⁻¹ in RRTMG4 and 2680 cm⁻¹ in GP; an 80 cm⁻¹ split difference prevents an exact spectral-band identity claim. No unweighted g-point averaging is used here.

## Observed outputs

All flux differences below are GP minus RRTMG4 in W m⁻². Level arrays are in the captured bottom-to-top order; the first level is the surface and the last is TOA.

| Phase / output | RRTMG4 | GP | GP − RRTMG4 |
|---|---:|---:|---:|
| LW surface down | 450.3628 | 451.9713 | +1.6085 |
| LW TOA up | 105.0011 | 107.1411 | +2.1400 |
| SW surface down | 0.42945 | 0.37963 | −0.04982 |
| SW TOA up | 159.9565 | 149.2337 | −10.7228 |
| SW TOA down | 193.70111 | 193.70079 | −0.00032 |

The SW cosine zenith is 0.14109275. Surface-down flux is small in this column while TOA-up differs by 10.72 W m⁻², so surface similarity is not evidence that the column radiative solutions agree. The SW direct-flux profile also differs internally (maximum absolute profile difference 35.64 W m⁻²); its near-zero surface difference should not be generalized to the atmosphere.

Heating is K day⁻¹. Native comparisons use only the 44 layers present in the raw WRF capture; the adapter solver arrays additionally contain 13 LW and 1 SW extension layers. GP minus RRTMG4 maximum absolute native heating differences are 4.6959 K day⁻¹ LW and 1.7825 K day⁻¹ SW, both at native layer 31 (zero-based 30), 160.394 hPa. LW values there are −18.2911 GP and −13.5952 RRTMG4; SW values are +3.35939 GP and +1.57687 RRTMG4. RRTMG4 source explicitly resets its final SW heating layer to zero after the heating loop (`module_ra_rrtmg_sw.F:9636-9647`); that extension-only discrepancy is kept separate from native layers.

These results localize substantial profile and SW TOA differences under one common thermodynamic/gas state. They do not isolate engine-only effects: dry molecular columns, snow radii, optical models, stochastic masks, spectral bands/g-points, and solver implementations are not all identical. Further causal attribution would need a separately controlled matched-optics experiment.

## Provenance

The executed runtime receipt is `build/udm37-rrtmg4-export-runtime-v4/execution.json` (SHA-256 `31c5eac1d76b346bd6a1397146f4f2542f5cd3a93eb27c9b55400c606ab975bc`). The selected LW and SW exports have SHA-256 `44ad6a5d0e2bb9cee48fe0ec821341dde61a240e53dc0c6bce28f26b7044a303` and `6afbe0cf7d5c83d0589a77b44afd27396f7e63ea566610c4a22925b4c1b110b6`. GP trace files, source hashes, source commit, and CSV hash are recorded in the JSON. The runtime executable was built from source commit `b7b5f6f9cd657408e3bde3018d7e882ab3e4bce3`. The analysis checkout is `5f3034e9c43209a352977da4885a3fc15b46c532`; although the commits differ due to later documentation/registration metadata, the executed and analysis `WRF` subtrees have the identical Git tree `13a8b1479945d9a3ad3393fa38a2e341706e27fb`. The JSON records both commit and tree identities. The runtime receipt contains the coefficient and frozen-table input pins.
