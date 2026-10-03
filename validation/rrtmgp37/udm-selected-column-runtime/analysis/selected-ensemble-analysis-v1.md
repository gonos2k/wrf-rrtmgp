# Selected-column paired ensemble summary (v1)

This read-only analysis uses `on-only-20261003-v1/audit-on/run/audit/same_state.csv` (SHA-256 `f5d06ab9befa3ac115f2848f3319b62536e1da5c1ab88b4ff121e67090bb2b96`, 79,213 bytes). It selects only domain 1, physical point `(i,j)=(169,80)` and excludes the `(0,0)` aggregate rows. The CSV contains 32 paired samples per metric at each of two LW/SW source times: step 721 / 43,200 s and step 731 / 43,800 s. Radius mode is 0.

For each metric, the paired ensemble difference is `mean37 - mean4`; the descriptive MCSE is `sd_delta / sqrt(32)`. `sd_delta` is checked against the standard-deviation covariance bounds, and implied correlations are finite/in range whenever both marginal SDs are nonzero. The operational difference is the CSV's actual `value37 - value4`; residual is operational difference minus paired ensemble mean difference. These residuals are not feedback estimates. JSON retains every `HEAT_1` through `HEAT_39` layer, its paired mean difference, MCSE, operational difference, and residual.

| Phase / source time | Surface mean 37−4 | Approx. MCSE | Operational 37−4 | Operational residual | Largest absolute heating mean difference |
|---|---:|---:|---:|---:|---|
| SW / 43,200 s | 0.382864 | 0.015628 | 0.524424 | 0.141560 | HEAT_28: +13.203837 |
| SW / 43,800 s | 0.524537 | 0.020777 | 0.698264 | 0.173727 | HEAT_28: +14.275530 |
| LW / 43,200 s | 0.967348 | 0.116349 | 1.117828 | 0.150480 | HEAT_28: −4.191319 |
| LW / 43,800 s | 1.298762 | 0.122196 | 0.638611 | −0.660151 | HEAT_28: −4.304968 |

Flux/heating units follow the audit metric definitions; this receipt does not reinterpret units. Radius mode 0 compares operational RA4 generic radii with RRTMGP37 native radii, and composition/optics also differ, so this is not solver-only attribution. The selected column is ice-positive and optically opaque; do not extrapolate its magnitudes to a domain-wide mean or coupled forecast. Unbiasedness is not established for this selected case; MCSE is descriptive for these 32 paired samples, not a confidence guarantee. This evidence does not establish a reference pass.

The machine-readable details and 39-layer profiles are in `selected-ensemble-analysis-v1.json`.
