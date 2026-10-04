# Native ice-layer contribution replay review

Reviewed execution receipt SHA256: `b37c274ba3619afcae124fdc4804fc65859be38e7fedf3403a537764ef7ea423`.

No material correctness issue found.

- The receipt records exactly six reference invocations: two SW override identity controls, two SW ice-removal cases, and two LW IWP-zero cases. It records zero new builds/models and verifies its pinned source/data/executable/runtime files before and after.
- Both anchors are native-only for the tested inputs/results: no CU sections are present, each selected layer has LWP=0, IWP>0, CF>0, and requested ice diameter >180 µm while `DI_USED` is exactly 180 µm. The low anchor selects k15–18 (125.855381 g/m² grid IWP); the high anchor selects k17–19 (189.403839 g/m²). The high-anchor mixed k16 negative control is rejected without a solver invocation.
- Both SW controls compare all 46 result sections bitwise to their baseline outputs. The SW variants replace selected post-delta prepared optics with `PRECIP_TAU/SSA/G`; the runner verifies selected arrays equal precipitation-only optics, unselected prepared layers stay exact, and gas, mask, precipitation, frozen, clear-sky, direct-clear and pre-delta diagnostic sections remain exact. The retained pre-delta/raw direct diagnostics are explicitly excluded from the counterfactual interpretation.
- LW inputs are changed only in selected IWP entries; all other parsed fields compare exactly. CF, seed, gases, radii, surface/atmosphere and the listed gas/precip/frozen/mask/clear-sky outputs remain fixed. Metrics are variant-minus-baseline with stated W/m² and K/day units. I independently recomputed the table deltas from the pinned baseline and variant result arrays; values agree.
- The README limits interpretation to a finite contribution of selected clipped ice, not a clipping-error oracle, physical accuracy result, domain mean, or forecast approval.

Minor wording option: call the SW override “prepared solver optics” or “prepared cloud-plus-precip optics” to avoid implying the `PREPARED_*` array is cloud-only; in this reference path precipitation has already been incremented before the prepared arrays are captured. The code and the stated precip-only replacement are consistent.

Read-only only; no solver, build, or model was run.
