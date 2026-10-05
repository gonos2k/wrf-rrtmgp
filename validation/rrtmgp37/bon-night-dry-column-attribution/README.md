# BON night dry-column attribution

One additional standalone LW reference call changed only the first BON call's `NATIVE_DRY_LAYER_MASS_KG_M2` input section, from 32 native values to a 45-layer diagnostic mass carrier. The carrier imposes the actual same-call legacy molecular dry columns through `COLDry × M_dry × 10000 / avogad`. All other input bytes remain identical. This is not a new WRF native state or a production physics change.

The baseline and original export are reused from [the six-call reference replay](../bon-night-independent-replay/README.md) and [the night audit](../bon-night-same-state/README.md). No extra forecast, REAL run or build was made. The archived execution records one successful standalone call, PID 149609, RC 0, and unchanged pre/post identities for 120 files and 47 runtime paths. Together with the sibling replay, this evidence contains seven standalone calls and the original three forecasts.

| First-call surface down LW, direct binary64 | W m⁻² |
| --- | ---: |
| Reference with original native dry construction | 189.08001140829873 |
| Reference with legacy molecular dry columns | 189.08751473673385 |
| Actual legacy export | 187.83763122558594 |
| Original reference − legacy | +1.2423801827127932 |
| Original − matched dry construction | −0.007503328435120693 |
| Matched reference − legacy residual | +1.2498835111479139 |

The decomposition closes exactly in the retained binary64 calculations. Injecting the legacy molecular amount slightly increases the reference flux; this dry-column substitution does not explain the positive contrast. The remaining residual combines spectral, engine and other cross-implementation construction differences. It is not a pure spectral attribution, physical truth, observational accuracy result or resolution of the BON observed LW bias.

The achieved `GAS_COL_DRY` matches all 45 exported legacy columns within 2.220446049250313e−16 relative error. Fourteen cloud, CU, precipitation, frozen, mask and size fields are held exactly. Pressure, temperature, VMRs, gravity, heat capacity, seed and all 49 other input sections are unchanged. The diagnostic includes 13 upper extension layers; the 45-value carrier must not be described as 45 WRF native layers.

The direct binary64 decomposition differs from the actual WRF REAL32 boundary contrast, +1.2423858642578125 W m⁻². The original CSV's decimal encoding yields +1.2423858642578978 W m⁻². These are reported separately, without rewriting archived bytes.

Run from the repository checkout:

```sh
python3 -I -S validation/rrtmgp37/bon-night-dry-column-attribution/verify.py --output build/bon-dry-verification.json
python3 -I -S validation/rrtmgp37/bon-night-dry-column-attribution/test_verify.py
```

The stdlib verifier checks the closed payload roster, verbatim/decompressed origin hashes, sibling source/parser identities, archived authorization and execution joins, exact mass-only byte edit, conversion, achieved molecular columns, fourteen held result fields, finiteness and flux algebra. It reads retained arrays and invokes no radiation engine. It uses the existing tracked trace parser and the sibling export reader; the three evidence directories and repository parser dependencies are required. It does not reopen unbundled NetCDF histories or independently revalidate every external source/library file. External file stability is an archived execution and [independent terminal review](receipts/independent-terminal-review.json) attestation. The frozen runner is a workspace snapshot with original absolute paths, not a portable launch recipe.
