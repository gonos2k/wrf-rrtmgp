# Independent readback: CF0 precipitation campaign v5

This package contains an offline review of the completed eight-call campaign. It does not launch or rebuild the reference program. The campaign uses the frozen v5 plan and authorization; the result files remain in `build/udm37-cf0-precip-campaign-v5` and were not copied here.

`recompute.py` is a small standard-library parser and verifier. Run it from the repository root with:

```sh
python3 -I -S build/udm37-cf0-precip-campaign-v5-independent-result-review-v1/recompute.py \
  build/udm37-cf0-precip-campaign-v5 --output /tmp/cf0-campaign-readback.json
```

It independently hashes the 281 frozen input/source/data/runtime paths and eight generated outputs, checks each child PID/return code and terminal state, and parses the result section headers and values. It verifies each of the four zero-sidecar outputs byte-for-byte against its saved exact double-reference oracle (20 LW sections and 46 SW sections). For each positive case it checks the ordered section set, exact shape and text-token equality of all undeclared sections, and finite/range constraints for the added audit sections. It separately checks the `(1,41,1)` SW `AUDIT_DIRECT_PREDELTA` interface-array shape.

The unchanged baseline sections cover gas columns/depth optical properties, accepted precipitation and cloud optics, frozen optics, prepared optics, MCICA masks, clear-sky flux/heating, used radii, and the ordinary pre-delta direct diagnostics. The only changed original fields are the explicitly declared all-sky optical fields, fluxes, and heating. The separate audit direct diagnostic adds raw extra-precipitation extinction; it does not replace the ordinary pre-delta direct field.

The reported flux and heating changes are conditional, single-column occurrence-one sensitivities against the saved double-reference baseline. Fluxes are W m⁻²; `HR` is K day⁻¹. Surface net shortwave is calculated as down minus up at the first (surface) interface; TOA is the last interface. Heating maxima report the largest absolute layerwise difference separately across the native 39-layer prefix and the full engine depth (47 LW, 40 SW). These results are not an occurrence oracle, independent optical truth, validation of the current private-scalar backend, forecast accuracy, or a domain mean.

## Recomputed conditional sensitivities

| Added path | LW GLW Δ (W m⁻²) | LW OLR Δ (W m⁻²) | SW surface down Δ (W m⁻²) | SW surface net Δ (W m⁻²) | SW TOA up Δ (W m⁻²) | Max |ΔHR| native / engine (K day⁻¹) |
|---|---:|---:|---:|---:|---:|---:|
| Rain | +0.1496815613 | −1.2375571167 | −1.5385145817 | −1.2524692966 | −1.9463441889 | LW 2.2719224759 / 2.2719224759; SW 0.3418474502 / 0.3418474502 |
| Snow | +0.1588255203 | −0.0000190317 | −0.0415699858 | −0.0339884237 | +0.0251663205 | LW 0.9969685983 / 0.9969685983; SW 0.0011186069 / 0.0011186069 |

## Frozen source and result pins

- Runner: `1f2a09c0922f243abe242a92d1acda293fef84ec46af0960d969d68eac668ed2`
- Plan: `01286b3702a47359e1d55c6259169b99356dc9490f2b2cc5e18d2476a80d76bc`
- Stage manifest: `0b5b8c99847d77f5580fac594f669b26dad9182cd5bb0f4db1c8413709b3cf00`
- Integrity attestation: `69c971f67710a37fa57f0dcc41e1dbe3159387526a57299970615b4c2f1b7a21`
- Root authorization: `8c5d1132df1aa3e56fa69ba9952a74b3cc8846aa2a6c86bd89cb70651843fb78`
- Execution receipt: `9285816e2d1203b7c6ce0642cca91356f9e0ca3b42fa30761c87efc36064fdf5`
- Recomputed summary: `deade0f0383ec011c09b621ca1754b04cb3136829a6af33dbee03dd6a2076557`

The campaign receipt reports eight successful children, eight return codes of zero, 281/281 protected paths unchanged, 47/47 runtime libraries unchanged, and all eight generated-output pins unchanged at postflight. This independent review made no solver, build, or model calls.
