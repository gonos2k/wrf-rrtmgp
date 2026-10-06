# Localize the pre-PANEL LBLRTM negative R3 term

This extends PR116's additive PANEL diagnostic with saved per-write R3 accounting. In the captured layer-21 window, the **CO2 SPPSP/YI-controlled coupling branch drives a positive intermediate R3 value negative**. Baseline line contributions, carried R3 and the later continuum addition are nonnegative at the four selected target R3 points. The local GI line-strength multiplier is exactly 1. This establishes the local arithmetic path; it does not establish that the line-coupling data or approximation is valid, explain every negative, attribute the held WRF4/37 flux residual, or validate UDM physics.

## Execution and noninterference

The additive source starts from PR116's PANEL-instrumented tree, not directly from unchanged stock. Only `src/oprop.f90` changes among 446 copied regular files. The source baseline is AER-RC/LBLRTM v12.17 commit `a85ac73447c1e62401a57a34bbcb040683345dca`. Existing physical assignments and their arithmetic order remain unchanged; observational copies and after-hooks serialize separate diagnostic state. Newunit/shape guards can stop this diagnostic on an invariant failure, so it is not universally passive control flow. The measured noninterference is specific to this successful execution.

One GNU-double incremental make returned RC0; only `oprop.o` changed among 21 inherited objects before relinking. This is **not a fresh full-library build**. One new instrumented CPL/SAMPLE4/full-continuum case retained all 38 staged inputs and the exact TAPE5/TAPE3 of the saved baseline. Its actual child RC0 was saved before numerical inspection. No WRF, REAL, RTE, LNFL, or new unchanged-stock solve was run.

The corrected saved reader reconstructed **45,569 individual R3 writes bitwise**, including original multiplication association, before/after chains, SP/SPPSP metadata, snapshot joins and the PANEL carry shift. All **45 layers / 63,838,065 spectral samples**, panel headers and EOF records match the saved uninstrumented CPL baseline exactly. The sole file-header exception is zero-based word168, the TAPE6-confirmed runtime HTIME clock identified in PR116. The inherited PANEL trace is also byte exact. This proves scoped instrumentation noninterference, not physical-reference acceptance.

## Local result

The output target is 666.3964444444449 cm-1 in layer21 (348.36124 mbar, 228.3152 K). The internal R3 grid has different coordinates. At the four R3 stencil points for its pre-PANEL interpolation:

| R3 index | Internal wavenumber (cm-1) | Carry | Baseline sum | Coupling sum | Continuum addition | Pre-PANEL R3 |
|---:|---:|---:|---:|---:|---:|---:|
|61|666.313528889|0.000658456|0.004509224|-0.012963058|0.000259346|-0.007536032|
|62|666.373831111|0.000594570|0.005548779|-0.014122199|0.000259457|-0.007719393|
|63|666.434133333|0.000518143|0.006799025|-0.015348817|0.000259566|-0.007772083|
|64|666.494435556|0.000446208|0.008326314|-0.016769635|0.000259672|-0.007737442|

Component sums are descriptive `fsum` totals; tiny residuals are rounding, not an independent acceptance tolerance. The actual pass criterion is the ordered bitwise reconstruction of each write. Optional XSECTM and LBLF4 additions are zero at these points. All selected-point GI multipliers have min=max1, and baseline operands are nonnegative.

At record35615 (R3 index63), CO2 isotope1, shifted line center667.385965634841 cm-1, the saved GI=0, YI=3.034229991142273, SP=0.05631378974057237 and SPPSP=1.0431859088670232. The positive scaled STRF3 and F3 multiply a negative signed ZF3L, producing the coupling operand -0.013911364162291164. It changes R3 from +0.0010453855710148992 to -0.012865978591276264 in the original order, bitwise. An independent reviewer spot-decoded this and four neighboring raw records without rerunning the model or the full reader. Sixteen positive-to-negative crossings were captured in the bounded window. No universal GI/YI conclusion follows beyond these saved writes.

**The physical negative-OD gate remains FAIL.** The inherited final coupled minimum stays -4.884429085432753. There is no clipping, relaxed tolerance, promotion of NOCPL to truth, or flux residual attribution. The next task is to audit original main/companion coupling records and the applicable approximation/support before considering any spectroscopic reference acceptable.

## Reader failure retained

The first saved reader actually returned RC1: it assumed every captured post-PANEL stage127 had a captured predecessor126. At the first entrance into the target window, PANEL's origin advance exposes a newly zeroed tail while the prior window did not intersect the capture band. This is a reader boundary failure, not a model failure. Its source, execution, stderr and static preflight PASS are retained. The additive runtime review states that the static review did not cover this boundary.

The separate v2 reader accepts this first case only for seq1/no predecessor/nonfinal panel, when every selected slot maps beyond the previous MAX3 and is bitwise +0. Subsequent127 records still require preceding126, exact VFT advance and full bitwise carry/zero-tail. The v2 actual reader RC0 is separately archived. No model or build retry was needed.

## Archive and reproduction

Sources, executed source/patch/executable pins, authorization, actual RCs, review receipts, saved results and a byte manifest are archived. Executed scripts retain private absolute paths and parent dependencies; these packaged copies are **historical sources, not directly runnable reproducers**. Reproduction needs the original pinned assets and a reviewed fresh-directory path adaptation. The initial preparation script describes the pre-guard version; `source-preparation.json` records the diagnostic positive-index amendment made before compilation. The final patch, source pin and build plan identify the executed bytes. An initial preparation-only Python slice check failed before any build/model and is retained in that receipt.

The outer routine containing the CNVFNV/PANEL calls is **HIRAC1**. Earlier source-flow review prose calls it OPDPTH; this naming error does not change the hook locations or arithmetic. The terminal independent report's final index63 subsection accidentally copied three index61 identifiers/operands; its additive erratum gives the correct index63 sequences35615/35885/36165 and operands. Its raw record35615 decode and principal conclusion were already correct. The executed case runner's inherited postflight `scope` string also says stock LBLRTM; the explicit instrumented plan and executable pin are authoritative. Original archived records are not silently rewritten.

Raw term/PANEL traces, spectral OD files, AER line lists, TAPE3, coefficient data, complete vendor source, binaries and objects remain private. Atmospheric and Environmental Research, Inc. (AER) copyright and research-use redistribution notice are preserved in [LICENSE_AER.md](LICENSE_AER.md); this is not a BSD license. The source-only patch is additive to the parent PANEL patch. Numerical excerpts are derived diagnostics, not a redistributed spectral dataset. No production WRF source or CI workflow changes are included.
