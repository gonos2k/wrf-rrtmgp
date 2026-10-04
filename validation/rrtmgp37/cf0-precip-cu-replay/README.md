# CF0 precipitation sensitivity with retained convective cloud

This package records an eight-call, test-only replay of one captured RRTMGP column. It asks how adding an occurrence-one rain or snow optical object at a native layer with cloud fraction zero changes the existing calculation when the sampled cloud, retained CU bundle, gas, frozen hydrometeors, masks, inputs, and seeds are held fixed. It is a local counterfactual, not a production occurrence rule, forecast test, or accuracy bound.

The source capture is the selected domain-1 column `(i=24, j=55)` in the retained PR75 evidence: LW V10 and SW V11. It has 44 native layers, high positive CU optical depth (maximum 22.2837 LW and 42.1856 SW), and low sun. The rain omitted-path sum is 579.00984 g m⁻² over four eligible native layers. The positive snow path is retained without a cutoff: 4.59486×10⁻⁹ g m⁻² over seven layers, so its response is very low signal and does not establish a material snow effect.

The eight actual solver calls were: baseline LW/SW without a sidecar; all-zero LW/SW sidecars; and positive rain and snow sidecars in both phases. All eight child processes returned 0. Each zero-sidecar result is byte-identical to the corresponding no-sidecar result. The independent terminal review also found zero heating residuals for all eight calls, zero total-extinction residual, and SW scattering-optical-depth composition residual (τ·SSA, zeroth angular moment) and scattering-weighted asymmetry composition residual (τ·SSA·g, first angular moment) no larger than 1.39×10⁻¹⁷. No second angular moment was validated.

| Positive case | Surface all-sky down-flux change (W m⁻²) | Maximum absolute layer-heating change (K day⁻¹) | Maximum absolute interface down-flux change (W m⁻²) |
|---|---:|---:|---:|
| Rain LW | +1.5036325 | 0.3765398 | 1.5036325 |
| Rain SW | −0.0012329 | 0.00001738 | 0.0489776 |
| Snow LW | 0 | 1.91×10⁻⁸ | 3.43×10⁻⁸ |
| Snow SW | −6.43×10⁻¹² | 3.02×10⁻⁸ | 6.46×10⁻⁸ |

The review measured positive retained CU optical depth in the baseline and positive cases. The positive sidecar changes total optical moments as intended; its precipitation object is added after sampled-cloud overlap with occurrence fixed to one. The four ordinary pre-delta diagnostics remain exact because they use the original optical state, while `AUDIT_DIRECT_PREDELTA` separately includes the audit extinction. All surface direct values are zero in this shielded fixture, but snow changes ordinary RTE `DIRECT` at upper interfaces (maximum absolute change 1.0771686×10⁻⁷ W m⁻²). Clear-sky fields remain exact because the audit is inserted after the clear solve; this does not establish physical clear-sky precipitation insensitivity.

The independent review is scoped to this captured column and the sidecar/control contracts. Snow is too small here to support a meaningful snow-impact conclusion. Nothing here selects a global cloud-fraction threshold, changes the production default, establishes behavior across other columns or stochastic cloud samples, or measures forecast accuracy.

## Reproduce and verify

From this directory, with Python 3 and NumPy available for the derived-profile script:

```sh
python3 -B summarize_eight_calls.py
python3 -B verify_package.py
```

The summary script reopens the eight compressed result and log files, verifies their raw hashes against the execution receipt, checks the shared PR75 input/raw identities and all six sidecars, enforces baseline/zero whole-file identity, checks held-section equality and reports independently reviewed optical-moment residuals, and rewrites `results/summary.json` plus `results/allsky-profile-deltas.csv`. It also runs sidecar rejection controls without invoking the solver. `verify_package.py` verifies the closed package roster and hashes; regenerate `package-manifest.json` only after an intentional evidence-package change.

The reused input/raw captures are linked by relative path to `../rrtmg4-same-call-attribution/traces/NEW_ON`. The package includes the exact sidecars, compressed outputs/logs, execution/build/source receipts, terminal review, and the portable parser. The executed source snapshot was based on `245b1a83`; this publication worktree is based on `ed902258`. The four non-CMake change files (driver, helper, test, and documentation) match the executed snapshot; CMake registration differs because this publication base retains later unrelated tests. The complete publication CMake tree was not rebuilt for this evidence package. The exact executable and build receipt are pinned in `receipts/source-build-lineage.json` and `receipts/build-execution.json`.
