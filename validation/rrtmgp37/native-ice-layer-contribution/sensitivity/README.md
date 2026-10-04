# Native ice-layer contribution at a held call

Exactly six additional offline reference invocations were authorized and executed: two unchanged SW prepared-optics controls, two SW ice-removal overrides, and two LW IWP-zero variants. There are no new WRF models, builds, production changes or ensemble seeds. The earlier separate baseline task used six reference invocations; this receipt counts only the six here.

Inputs are historical exact radiation-call captures, not a current PR60 WRF trajectory. Baselines come from `build/udm37-occurrence-clipping-baseline-replay-v1/runs-v1`, whose immutable receipt is SHA256 `fd1264d843996eeaef44e28cd0ae393a95f3be08c0a8e3dc5fa36612ebc13603`. The existing reference executable is SHA256 `67261df7bda1fa7472216b87fdc79b1c93c72fdeae5ff812e2e3e7c372d5d21a`; its source matches current reference source `9ab10866c9b398c059310c74b3824b7273c42f180dd48a1643229d76714464cd`. Original inputs, baseline outputs, sources, coefficients, frozen table and resolved libraries remain hash-identical.

Both anchors have no CU population and use separate rain/snow precipitation optics. Selected native layers have positive IWP and CF, exactly zero LWP, requested ice diameter above180µm and used diameter exactly180µm. At i132,j35 the removed layers are k15–18, totaling125.855381g/m² grid IWP. At i170,j72 they are k17–19, totaling189.403839g/m²; mixed-phase k14–16 were deliberately retained. Layer selection, requested/used diameter, grid and in-cloud IWP, CF and actual sampled gpoint counts are in `runs-v1/execution.json`.

The low anchor realizes LW masks11/128,40/128,128/128,128/128 and SW masks17/112,41/112,112/112,112/112. The three high-anchor selected layers are fully sampled in both phases. These are fixed-seed spectral sampling fractions, not physical domain coverage or time means.

The two SW control overrides reproduce all46 baseline arrays bitwise, including solver fluxes/heating and masks. The SW variants replace only selected prepared cloud layers with the original **delta-scaled PRECIP_TAU/SSA/G**. This removes their native cloud-ice component while retaining rain/snow and subsequent frozen addition. Unselected prepared layers, gas/precip/frozen arrays, mask and clear-sky results remain bitwise unchanged. LW variants change only selected IWP entries; every other parsed input, including CF/seed/atmosphere/surface/gases/radii/frozen inputs, remains exact. Their unchanged gas, precipitation, frozen, mask and clear-sky arrays are checked.

Two kinds of no-solver negative controls pass: the actually mixed high-anchor k16 is rejected, and replacing selected layers with original CLOUD optics rather than precipitation-only optics is rejected for each anchor. No extra reference invocations were used for these controls.

Differences below are **variant minus baseline**. Downward-positive net flux is DN−UP. Heating is K/day.

| Anchor | Phase | Δsurface DN (W/m²) | Δsurface UP (W/m²) | Δsurface net down (W/m²) | ΔTOA UP (W/m²) | Max absolute Δheating (K/day) |
|---|---|---:|---:|---:|---:|---:|
| i132,j35; k15–18 | SW | +4.282318 | +0.865268 | +3.417050 | −9.156327 | 0.599907 |
| i170,j72; k17–19 | SW | +1.834641 | +0.294141 | +1.540500 | −3.600610 | 0.490496 |
| i132,j35; k15–18 | LW | −6.275781 | −0.291618 | −5.984163 | +17.310539 | 7.560809 |
| i170,j72; k17–19 | LW | −0.000078 | −0.000005 | −0.000073 | +2.603474 | 3.590214 |

SW solver DIRECT and DIFFUSE changes are retained separately in the receipt. The surface solver DIRECT changes are +2.970358W/m² and approximately0W/m² for the low and high anchors; corresponding DIFFUSE changes are +1.311960 and+1.834641W/m².

**EXCLUDED_FROM_COUNTERFACTUAL:** RAW_CLOUD_TAU and the separate DIRECT_PREDELTA/VISDIR_PREDELTA/NIRDIR_PREDELTA remain their baseline values under the prepared-optics override. They are checked unchanged and are not a variant unscattered-direct solution. Thus these results describe the RTE prepared-optics solver response, not a physically consistent change to every SW output. The current override leaves that raw-extinction route untouched by design.

This measures the finite-layer contribution of ice whose lookup diameter was clipped to180µm. It is not clipping error: the entire selected ice contribution is removed, without supplying a valid out-of-LUT optical oracle. It is not physical accuracy, a domain average, an ensemble bound, CF0 precipitation occurrence evidence, CU ice isolation, or operational approval. Native/CU radius and occurrence policies remain scientific questions. All old artifacts and failure scopes remain unchanged.
