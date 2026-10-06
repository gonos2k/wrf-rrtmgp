# Localize stock LBLRTM negatives with PANEL snapshots

This follows PR115's coupling×sampling controls. A private additive diagnostic copy of LBLRTM v12.17 captures R1/R2/R3 before and after the two PANEL interpolations and JRAD0 scaling, only in panels containing the saved layers 21 and 44 minima. Four calls and one intent-in helper are added; no original physical formula or array assignment is changed. This is **instrumented diagnostic source**, not the unchanged stock executable or WRF production source.

The same GNU-double target/flags and NetCDF libraries were used. The copied source readback covers 446 regular files, with only `src/oprop.f90` changed. One incremental make returned RC0; of 21 inherited objects only `oprop.o` changed before relinking. This is not a fresh full-library build. Two new one-use cases retain the exact 38 staged inputs and TAPE5/TAPE3 of the existing full-continuum SAMPLE4 coupled and NOCPL baselines. The executed source/executable, root authorization, input pins and actual child RCs are archived. The initial wrong `--run` CLI was rejected with parent RC 2 before any model launch; it is preserved, followed by the valid `--launch` call. No model retry occurred.

## Noninterference

Both instrumented cases returned actual child RC 0. Each new output was compared across all 45 layers and 63,838,065 spectral samples. Every panel header, spectral payload and EOF record is byte exact against its saved corresponding baseline. Every 177-word file header is exact except zero-based word 168. The original readers retained `HEADER_METADATA_REVIEW_PENDING`; a separate source check identifies that field as YID(2), equivalenced to HTIME and assigned by FTIME at initialization (`lblrtm.f90:531,661`). The old/new eight-character clocks also occur in the corresponding execution logs. The original reader reports remain unchanged; the supplemental proof closes only this timestamp/noninterference question.

There are two captured panels per case, with ordered stages 1, 2, 3, 4 for each. The inclusive target predicate could capture two adjacent panels at a shared boundary; the reader reports duplicates rather than assuming a fixed record count. No duplicate was observed here. Physical negative-OD failures remain unchanged. The independent review in [independent-local-review.json](independent-local-review.json) also decodes the small NOCPL layer-44 trace and reconstructs one R3→R2 step bitwise without rerunning a model. Its scoped causal conclusion does not close physical acceptance.

## Local result

| Point | Before PANEL | After first interpolation | Final OD |
|---|---|---|---:|
| layer 21, coupled, 666.3964444 cm⁻¹ | R3 already has negative entries | Target R2 stencil is negative | -4.884429085432753 |
| same point, NOCPL | R1/R2/R3 nonnegative | Target R2 stencil positive | +4.4625484239488955 |
| layer 44, NOCPL, 677.54904465 cm⁻¹ | All R1/R2/R3 nonnegative | R3→R2 stencil creates negatives | -0.0009924067060697163 |

At layer 44, positive R3 inputs include a sharp neighboring increase. The signed four-point weights (-7/128,105/128,35/128,-5/128), their reverse, and (-1/16,9/16,9/16,-1/16) introduce three negative R2 entries. The supplemental exact-order evaluation reconstructs these values bitwise from the saved input arrays. They propagate through R2→R1 and the positive RADFNI multiplier (~651.964). Thus the residual at this captured point is an interpolation overshoot, not an output-decoder sign error. This proves a **local mechanism**, not the cause of every negative in the full domain or a physically valid replacement interpolation.

For layer 21, pre-PANEL R3 negativity establishes that the large coupling-dependent problem is already upstream of PANEL. It does not isolate CNVFNV from preceding continuum/cross-section additions, GI from YI/SPPSP, or any individual molecular line. NOCPL suppresses both GI strength and YI dispersion paths. The saved raw R3 and target stencils support this limited statement; they do not establish a unique signed term.

## Acceptance and reproduction

**Independent physical-reference acceptance remains FAIL.** No value is clipped, no tolerance is relaxed, no NOCPL or instrumented result is promoted to the correct reference, and no held WRF 4/37 flux residual is attributed by this local diagnosis. No WRF/REAL/RTE run, full WRF build, production source or workflow changes here. The next discriminating work is line-term/continuum partition upstream of PANEL and a scientifically valid spectral reference.

Scripts/runners are historical archived executed sources. Their private workspace roots and relative parent-directory assumptions mean they are not directly runnable from these packaged locations. Reproduction needs the pinned original private assets and an explicitly reviewed path/output adaptation in a fresh directory. Actual executions and source provenance are preserved in receipts. The parent NOCPL plan contained stale descriptive cwd/authorization-scope strings copied from the earlier continuum plan; its actual runner/journal/input pins were authoritative. These new derived plans explicitly record their matching case cwd and instrumented scope. This is metadata correction, not a change to the parent calculations.

Original AER line lists, generated TAPE3, coefficient data, raw trace/spectral files, object files and executables remain private. The published source-only patch acknowledges Atmospheric and Environmental Research, Inc. (AER); its copyright and research-use redistribution notice are reproduced in [LICENSE_AER.md](LICENSE_AER.md). Source baseline: AER-RC/LBLRTM commit `a85ac73447c1e62401a57a34bbcb040683345dca`, v12.17. The numerical excerpts are derived diagnostic results, not a distributed line/optics dataset.
