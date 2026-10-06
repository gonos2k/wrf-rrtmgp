# UDM cloud slopes above the liquid-cloud top

This correction concerns the shared UDM microphysics implementation. It is
separate from the option-37 dry-density selection in PR #107 and does not change
that selection, particle-size equations, or optical coefficients.

## Inherited read and correction

UDM finds liquid-cloud and rain tops separately. Both `slope_cloud` calls write
only through the liquid-cloud top, but the warm-rain `qrcon` calculation reads
`rslopec2` through the larger of the cloud and rain tops. Rain accretion also
reads `rslopec3` through the rain top. Thus a rain-only column, or rain extending
above the liquid cloud, can read values not prepared for the current column.
Zero cloud mass or a zero rate cap does not prevent evaluation of the slope
expression.

Original PR #106 sources and the PR #107 density candidate both trapped at this
read under signaling-NaN initialization and floating-point exception checking.
That result establishes an inherited source defect under the manufactured
inputs. It does not establish a failure in a particular WRF forecast or explain
the earlier large radiation differences.

The correction initializes `rslopec`, `rslopec2`, and `rslopec3` once per active
column and microphysics substep, before the first `slope_cloud` call, using the
same finite fallback constants already used by that routine. Both calls retain
their original ranges and arithmetic. There is no second reset: when phase
changes lower the cloud top, values computed by the first call must remain
available to subsequent rain processes.

## Compatibility and validation scope

Where either original call prepared a slope for the current column, the same
call still overwrites the initializer with the same arithmetic. These defined
paths are the appropriate bitwise compatibility controls. A never-written
value is uninitialized; a value retained from another column or substep may
instead be finite but stale. Neither is a valid current-state reference.

The correction changes shared UDM code used by radiation options 4 and 37.
Native compatibility tests and actual archived scheme-4 comparisons must be
reported separately. Undefined historical cases cannot be presented as a
bitwise regression reference, and a changed forecast cannot be called
unchanged merely because its schema is preserved.

Native execution passed at O0 and O2 with signaling-NaN/FPE traps. The original
rain-only and rain-above-cloud cases trapped at the `qrcon` continuation reading
`rslopec2`; the candidate returned finite state across all three forwarding
branches and all three density-option arms. Cloud-only, full-overlap, and a
finite warm trace control retained identical binary32 physical state and
optional diagnostic tags. The selected trace control did not observe a
within-substep cloud-top decrease, so dynamic shrink-retention validation
remains open; the unchanged two-call source structure is separately reviewed.

The initial fixture attempt compared candidate-only probe metadata as if it
were physical state. Its failure receipt and logs are preserved. The successor
compares physical words and tags separately. Final inspection also found that
its two trace labels surrounded the first call, leaving the second call
unobserved. Those old traces cannot establish shrink or no-shrink. A separate
corrected injector instruments the two original occurrences independently and
checks marker order before compilation; the earlier runner and results remain
preserved. The corrected third run passed O0/O2 with the two distinct trace
sites; its trace-control cloud top stayed at level 5 at both calls. Dynamic
shrink retention therefore remains untested.

A fresh GNU serial full-WRF SCM build completed in 468.07 seconds from the
pinned PR #107 runtime source with this sole UDM overlay. Six cold/warm SCM
runs completed successfully. Ordinary option 4 matched its archived parent in
all 208 variables, metadata, masks, and whole-file bytes. Option 37 capture
OFF/ON matched across all 211 variables and whole-file bytes; both new option
37 histories also matched their parent files exactly. An independent saved-data
review reopened all six outputs and checked 708 entry/radius joins. These
short fixtures did not activate a forecast difference; they do not replace the
manufactured native hazard tests or prove domain accuracy.

The initial SCM runner attempt completed two forecasts but failed its capture
contract because the supposed ON arm did not set the actual entry gate. Its
failure receipt and outputs remain preserved. The corrected six-arm execution
and its source pins are recorded separately. Neither initial forecast is
counted as a successful capture-passivity test.

Any no-artificial-cloud assertion is restricted to a controlled subsaturated state:
later physical activation or rain-to-cloud conversion can legitimately create
cloud water and droplet number.

The existing Nc unit, particle-size moment, LUT provenance, and physical
accuracy questions remain separate. Finite execution alone does not resolve
them.
