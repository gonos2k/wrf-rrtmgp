# Native UDM and diagnosed cumulus cloud populations

Option 37 uses native UDM27 condensate and effective radii as one cloud population. When supported Kain–Fritsch radiation feedback is active, diagnosed cumulus liquid and ice form a second population. They have separate mass accounting, size assumptions, and cloud optical properties. The existing combined WRF radiation cloud fraction and one shared McICA mask are retained. This is an explicit occurrence approximation, not independent sampling of resolved and cumulus clouds.

The winter diagnosis in [PR #45](https://github.com/gonos2k/wrf-rrtmgp/pull/45) establishes why the populations must be distinguished. At the failing layer, saved native ice was zero. Diagnosed cumulus ice of `-2.811777051192621e-7 kg/kg` times cloud fraction `0.20000000298023224` produced the temporary radiation input `-5.623554244493789e-8 kg/kg` exactly in host single precision. In the adjacent layer, positive cumulus ice inherited the UDM zero-native-ice minimum radius of about 5.01 μm. The observations identify the immediate input and radius association; they do not quantify a radiative error or identify the earlier internal KF equation producing the negative diagnostic.

## Mass and input contract

The driver passes the saved native liquid and ice arrays, rather than recovering them by subtracting cumulus condensate from an augmented value. Native UDM input validation, existing small-negative limits, and native radius handling remain in the native builder. Positive cumulus condensate must never hide an invalid native input.

The diagnosed cumulus policy has a zero bound:

\[
q_{x,\mathrm{accepted}}=\max(0,q_{x,\mathrm{CU}}),\qquad
q_{x,\mathrm{rejected}}=\max(0,-q_{x,\mathrm{CU}}),
\]

for liquid and ice independently. This is an explicit radiation policy for a diagnosed CU field. It does not change prognostic UDM or KF storage, widen a native numerical tolerance, or repair the upstream KF producer. It also differs intentionally from the legacy RRTMG clipping of the combined input: positive native ice is preserved when the CU diagnostic is negative.

For native dry-layer mass \(m_d\), CU fraction \(f_{\mathrm{CU}}\), and combined radiation fraction \(f\), the accepted and rejected grid paths are

\[
W_{x,\mathrm{CU}}=1000m_df_{\mathrm{CU}}q_{x,\mathrm{accepted}},\qquad
W_{x,\mathrm{rejected}}=1000m_df_{\mathrm{CU}}q_{x,\mathrm{rejected}}.
\]

Paths are in g m⁻². The in-cloud input is \(W_{x,\mathrm{CU}}/f\) for positive \(f\), using the exact fraction without a floor. The input helper checks finite signed condensate, finite positive dry mass, individual DP/SH and combined fractions in [0,1], the host-precision identity \(f_{\mathrm{CU}}=f_{\mathrm{DP}}+f_{\mathrm{SH}}\), and \(f\ge f_{\mathrm{CU}}\). Nonfinite inputs and inconsistent fractions are errors.

Rejected CU grid paths and source-negative counts are reported separately from native negative corrections and native clear-cloud omissions. A negative source value with zero CU fraction has zero participating rejected mass. Sums of layer-grid paths across columns are diagnostics in g m⁻²; they are not area-integrated kilograms. Aggregated phase/tile/call summaries avoid a message for every layer.

## Separate sizes and optical properties

| Population | Liquid size | Ice size |
|---|---|---|
| Native UDM | UDM effective radius | Twice UDM effective radius for the ice LUT diameter |
| Diagnosed CU | Existing WRF `relcalc` analytic radius | Existing WRF `reicalc` temperature-table radius, then twice that radius |

The CU formulas are WRF fallback assumptions. They are not UDM diagnoses or KF particle-size-distribution diagnoses. Their separate arrays must not be overwritten by native microphysics radii. Existing LUT bounds apply to each population; clipping diagnostics must retain the population and water-path weight.

LW absorption from the two cloud populations is added before the shared cloud sampling. SW cloud optics are evaluated separately and combined through extinction and scattering moments, \(\tau\), \(\tau\omega\), and \(\tau\omega g\), before the cloud's single delta scaling. Existing already-scaled precipitation optics are then included in their original place. The unscaled-direct calculation uses aggregate raw native-plus-CU cloud extinction. Radius averaging or a second cloud delta scaling would define a different model.

An absent or all-zero prepared CU population skips the added optical increment. Existing precipitation, frozen G/H, gas optics, overlap, seed, and solver policies remain separate. Other active hydrometeor augmenters require an explicit supported mapping; they must not silently become native UDM input.

## Replay and validation scope

CU-aware LW V10 and SW V11 extend the existing LW V8 and SW V9 capture contracts. They carry complete native/CU provenance, signed source fields, fraction identities, accepted/rejected paths, radius and occurrence policies, separate native/CU optics, and aggregate outputs. The old V1–V9 meanings and validation requirements remain unchanged. A new-format capture must not relax an old-format identity check.

Validation must cover invalid native ice masked by positive CU, negative CU with zero and positive native mass, positive CU with zero native mass, malformed fractions and partial bundles, absent/zero CU equivalence, scattering-moment addition and one delta scaling, raw direct extinction, workspace reuse, and strict replay. Existing RRTMG4 and no-CU37 behavior require their own preservation comparisons.

The winter diagnosis reproduces an existing failure; it is not a corrected-forecast pass. A successful corrected column replay, a run crossing the former failure time, a complete winter forecast, and observational accuracy are distinct gates. No completed operational or physical-accuracy gate is implied by this contract document.
