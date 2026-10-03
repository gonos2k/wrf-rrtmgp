| Case (i,j) | Checkpoint CF0 rain/snow proxy g/m² | Actual LW omitted rain/snow g/m² | Actual SW omitted rain/snow g/m² | Actual eligible clipped ice grid path LW/SW g/m² | Strict LW/SW | Criterion |
|---|---:|---:|---:|---:|---|---|
| cf0_rain_low_cloud_proxy (136,48) | 202.42864 / 0.00010622782 | 202.42864 / 0.00010622782 | 202.42864 / 0.00010622782 | 0 / 0 | 20 PASS / 46 PASS | ACTUAL_CF0_RAIN_PRESENT |
| cf0_snow_high_cloud_proxy (155,115) | 10.69339 / 203.00873 | 5.1033723 / 2.9917718e-12 | 5.1033723 / 2.9917718e-12 | 15.96409 / 15.96409 | 20 PASS / 46 PASS | MATERIAL_CF0_SNOW_UNMET: captured omission is ~3e-12 g/m2, unlike 203 g/m2 checkpoint proxy |
| ice_clip_low_cloud_proxy (132,35) | 0.24286113 / 0.75698496 | 0.24286112 / 0.75698488 | 0.24286112 / 0.75698488 | 125.85538 / 125.85538 | 20 PASS / 46 PASS | ACTUAL_ICE_CLIPPING_PRESENT |
| ice_clip_high_cloud_proxy (170,72) | 36.583759 / 9.606246e-07 | 36.583758 / 9.6062457e-07 | 36.583758 / 9.6062457e-07 | 259.60771 / 259.60771 | 20 PASS / 46 PASS | ACTUAL_ICE_CLIPPING_PRESENT |
| clear_control (126,87) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 20 PASS / 46 PASS | CLEAR_ANCHOR |
| unclipped_cloud_control (22,37) | 0 / 0 | 0 / 0 | Not run: night | 0 / unavailable | 20 PASS / unavailable | LW_UNCLIPPED_ANCHOR_ONLY; DAYLIGHT_SW_CONTROL_UNMET |

Five profiles have complete LW/SW strict anchors. The control at **i=22, j=37** has a LW anchor only; COSZEN=-0.25774246 and production skips SW at night. Original FAIL receipts remain unchanged.

Checkpoint proxies and actual captured radiation fields are separate. Eligible ice path uses actual positive IWP, CF>0 and requested 2*REI>180; realized-mask coverage is recorded separately in summary.json. These are native mass paths, not optical depths or domain sensitivity bounds.
