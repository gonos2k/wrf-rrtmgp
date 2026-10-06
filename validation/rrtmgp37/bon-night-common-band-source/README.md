# BON common-band source and flux comparison

This packet preserves a Python-only, band-resolved comparison for one nighttime BON LW column. It evaluates saved RRTMGP optical/source profiles with an angular transport recurrence and compares the resulting profiles with the saved RRTMG4 selected-column packet. It does not call either radiation engine. The saved same-engine GP broadband result is reproduced to a maximum absolute difference of 2.899×10⁻¹² W m⁻² (up) and 4.198×10⁻¹² W m⁻² (down).

The two schemes have different spectral discretizations: 140 RRTMG4 g-points versus 128 RRTMGP g-points. Only bands 3–13 have identical physical edges. No g-point index pairing, source swapping, or unweighted g-point averaging is used. Bands outside that set are reported as engine-native totals, not as matched-band comparisons. The diagnostic column has 45 solver layers (32 native layers plus 13 upper extensions); it is a matched dry-mass carrier for this analysis, not a claim that WRF had 45 native layers. In band 12, both engines have zero optical depth in layers 29–45. Legacy also sets its Planck fractions to zero there; GP retains nonzero source values. The apparently large upper-layer source difference is inactive and was not renormalized. This does not mean the entire band has zero absorption or zero flux difference.

For the exact-edge common bands 3–13, the recorded totals are:

- Surface downwelling: legacy 99.863019 W m⁻²; GP fixed policy 100.458916 W m⁻²; GP angular integral 100.415714 W m⁻².
- TOA upwelling: legacy 132.277385 W m⁻²; GP fixed policy 132.073689 W m⁻²; GP angular integral 131.924232 W m⁻².

Across all engine-native bands, the stored band-value sums give surface downwelling of 187.837623 W m⁻² (legacy), 189.111524 W m⁻² (GP policy), and 188.561022 W m⁻² (GP integral). The original legacy broadband REAL32 value was 187.837631 W m⁻²; the 8.45×10⁻⁶ W m⁻² reporting-sum difference is the disclosed effect of promoting native REAL32 band values before summation. The exact original broadband and promoted-band total are distinct quantities.

The GP interior-level source uses a geometric mean of adjacent fractions; the GP layer source uses the layer’s own fraction. The legacy source is reduced at separate layer faces. The common-band residual therefore combines source interpolation, angular closure, k-discretization, and optical coefficients. It does not isolate one cause and is not a physical accuracy or “normal physics” verdict. The legacy surface Planck export already includes emissivity; legacy layer and level Planck exports do not. The GP raw surface source is multiplied by each band emissivity once. No source renormalization or second emissivity multiplication is applied.

The frozen `legacy_lw_replay.py` header says the actual packet was unavailable; that text dates from its earlier preparation and is superseded for this case by the pinned `legacy-actual-replay.json` receipt, which records the actual 12-field bitwise replay. The bundled helper is preserved byte-for-byte.

Plan, analysis, helpers, input, packet, output, and reviews are hash-pinned in `manifest.json`. The original absolute-path plan and execution are retained as archival provenance; they do not pin a compiled executable or attest a full external runtime closure. `reproduce.py` stages a copy in a new isolated output directory and refuses to overwrite it. The optional replay requires NumPy and SciPy, compares substantive result fields with absolute tolerance 1e-9, and ignores only the redirected plan hash. It is not a solver call.

From the repository root:

```sh
python3 -I -S validation/rrtmgp37/bon-night-common-band-source/verify.py --output build/bon-common-band-source-verification.json
python3 -I -S validation/rrtmgp37/bon-night-common-band-source/test_verify.py
# Optional numerical replay; the output directory must not exist:
python3 -B validation/rrtmgp37/bon-night-common-band-source/reproduce.py --run --output-dir build/bon-common-band-source-reproduction
```

The portable verifier checks the closed package roster and origin hashes, band labels/edges, stored profile dimensions/totals, the emissivity-to-GP-surface-source relation, 13 matched thermodynamic/state fields, and four trace-gas VMR pairs. Those state matches do not establish gas-optics coefficient equivalence. The trace-gas addendum records the four VMR comparisons; the band-12 zero-fraction addendum records the inactive upper-layer scope. Verification does not rerun transport or validate a radiation engine.
