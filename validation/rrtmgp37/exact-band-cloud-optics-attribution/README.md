# Exact-band SW cloud-optics sensitivity

The exact two-call standalone experiment completed with both solver calls at RC 0. The full-prepared identity-control output is byte-identical to the retained baseline (`SHA256 5afeb243d0d8e85a36d8c3dd5be7fe8c6c41a2034a142596d9e1d6d765dac53d`). The variant result is `SHA256 a2fc13d1a3e2f6c9438ee93d90c7f573757dadd7faccc84162fddb6d8ad28793`. The independent terminal review passed with zero reviewer solver/build/model calls.

This is a one-column **combined prepared-optics sensitivity**, not a pure engine, PSD, native-only, or accuracy test. It replaces the combined prepared native-cloud + CU + precipitation optical tuple at 36 cells: native layers 30–32 and 12 exact common physical bands. Thus captured raw state and component diagnostic records remain baseline, but CU optics do not remain in the RTE at the swapped cells. The selected arrays are the legacy CLDPRMC tau/SSA/asymmetry emitted after its delta-M transform. This does not constitute a fully consistent direct-beam attribution: raw/pre-delta direct diagnostics are held while RTE direct flux can respond to the prepared-array substitution. The compared legacy-four result is a native-radius observer/counterfactual, not default-RRTMG4 preservation.

The exact physical-band join uses GP bands 3–14 only. GP bands 1–2 retain baseline values because their 820–2680 / 2680–3250 cm⁻¹ bounds do not match the legacy 820–2600 / 2600–3250 split. No spectral averaging or cross-engine g-point positional matching is used. The frozen generator checked 36 eligible band/layer cells, 108 tau/SSA/asymmetry values, CF exactly one and all 112 masks equal one at each selected level, bottom-first native44 versus engine45 pressure context, exact legacy-to-input PLEV/PLAY joins, and field shape checks before reshaping. Six offline rejection controls passed.

## Observed result

The control reproduced the retained baseline as a whole file, with all 54 result sections matching. In the variant, 15 result sections changed and 39 remained bit-identical; held component optics, masks, pre-delta diagnostics, and clear-sky flux/heating sections remained exact. The independent review found moment-composition residuals no larger than 8.88e-16 and all-sky/clear-sky heating residuals of zero for both calls.

| Diagnostic | Control | Variant | Variant − control |
| --- | ---: | ---: | ---: |
| Layer 31 SW heating (K day⁻¹) | 3.3593932936 | 1.9689481185 | −1.3904451751 |
| Legacy-four layer 31 heating (K day⁻¹) | 1.5768657923 | — | — |
| Layer 31 absolute gap to legacy-four (K day⁻¹) | 1.7825275013 | 0.3920823262 | — |
| Surface downward SW flux (W m⁻²) | 0.3796296068 | 0.3772884531 | −0.0023411537 |
| TOA upward SW flux (W m⁻²) | 149.2336962792 | 153.1811386064 | +3.9474423272 |

Layer 31's absolute heating gap to the legacy-four native-radius observer decreased by 78.004%. Across only the 44 native layers, the maximum absolute gap changed from 1.7825275 K day⁻¹ at layer 31 to 0.8309791 K day⁻¹ at layer 29. The engine's upper extension is reported separately: its variant gap is 1.9139636 K day⁻¹. These profile differences do not establish physical accuracy or a general ranking between schemes.

The direct and diffuse flux profiles are retained in `results/flux-profile-46-interfaces.csv`; the 45-layer heating comparison to the legacy-four export is in `results/heating-profile-45-layers.csv`; and the 36 selected optics rows are in `results/selected-optics-36-cells.csv`. `results/analysis.json` is the portable recomputation snapshot. The independent terminal receipt additionally records the endpoint and moment-closure checks; the portable analyzer checks result-file integrity, exact cell and held-section support, and profile metrics, rather than recomputing the independent review's closure calculation.

## Provenance and reproduction

The package reuses the PR evidence by relative paths: the SW export/input/raw are under `../rrtmg4-same-call-attribution/`, and the same-executable baseline gzip is `../cf0-precip-cu-replay/outputs/baseline-sw.result.txt.gz`. It bundles the actual control and variant results (gzip), logs, runtime plan/runner/authorization and execution receipts, frozen V4 generator/plan/overrides, raw-vs-prepared analysis and independent reviews. External coefficient, executable, and source contents are not duplicated; their digests are retained in the preparation and execution records.

The `pre-run-plan-not-run-snapshot.json` and preflight v1/v2 are historical preparation records. The authoritative runtime records are the exact two-call execution receipt, strict authorization v2, preflight v3, root terminal receipt, and independent terminal review. An earlier v1 authorization was rejected before either call and remains a preserved zero-call history item; it is not a third solver call. The receipt's `model_invocations: 0` is correct: these were two standalone solver invocations and zero WRF forecasts.

Run the verifier and regenerate the derived tables from a repository checkout with Python 3 and NumPy:

```sh
python3 -B validation/rrtmgp37/exact-band-cloud-optics-attribution/analyze_two_calls.py --write
python3 -B validation/rrtmgp37/exact-band-cloud-optics-attribution/write_package_manifest.py
python3 -B validation/rrtmgp37/exact-band-cloud-optics-attribution/analyze_two_calls.py
```

The analyzer uses the repository-relative result parser and reuses the packaged PR captures, baseline and prepared overrides. It refuses changed input pins, outputs, results, or section support. `package-manifest.json` pins the complete local file roster; the final analyzer command validates that manifest. The archived original raw-vs-prepared script contains historical absolute workspace paths and is preserved for provenance; use `analyze_two_calls.py` for portable reproduction.
