| Canonical anchor | i,j | Actual CF0 omitted rain/snow g/m² (LW = SW) | Eligible ice diameter >180 grid mass g/m² | Strict sections LW/SW |
|---|---|---:|---:|---|
| cf0_rain_low_cloud_proxy | 136,48 | 202.428637 / 0.000106227821 | 0 | 20 / 46 PASS |
| material_cf0_snow_daylight_proxy | 103,156 | 0.00159405937 / 5.62248349 | 0 | 20 / 46 PASS |
| ice_clip_low_cloud_proxy | 132,35 | 0.242861116 / 0.756984884 | 125.85538 | 20 / 46 PASS |
| ice_clip_high_cloud_proxy | 170,72 | 36.5837584 / 9.60624566e-07 | 259.607706 | 20 / 46 PASS |
| clear_control | 126,87 | 0 / 0 | 0 | 20 / 46 PASS |
| daylight_unclipped_liquid_cloud_control | 268,27 | 0 / 0 | 0 | 20 / 46 PASS |

Historical audits: cf0_snow_high_cloud_proxy i=155,j=115 passed20LW/46SW but its intended materialCF0snow criterion was unmet (actualomission2.99e-12g/m² vs checkpoint203.00873g/m²). unclipped_cloud_control i=22,j=37 passed20LW; SW was never called because COSZEN=-0.25774246.

Total8WRFanchors =7fullLW/SW+1LWnight; actual8LW+7SWreferencecalls, including6canonicaltwo-phase anchors. The canonical liquid control has positive active liquid, explicitREL5.26817846µm and no active ice; it does not establish active-ice-unclipped coverage. Ice rows describe actual eligible positive native ice input and separate realized-mask counts are retained in index.json. No path is called opticaltau.
