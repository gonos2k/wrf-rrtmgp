# UDM rain-only cloud-slope initialization evidence

This archive covers one narrowly scoped source fix in `module_mp_udm.F`: initialize the liquid-cloud slope arrays once at the start of each column/substep so rain processing can read defined values above the current liquid-cloud top. The candidate is based on source head `e3b9e52c2a20811830a27d34420721ca89b62e59`, with only `WRF/phys/module_mp_udm.F` overlaid. The fresh-build receipt binds the driver and radiation trace source unchanged.

## SCM run

The successful candidate build is `receipts/fresh-build-execution.json.gz`. The successful SCM receipt is `receipts/scm-v2-execution.json.gz`: six forecasts returned zero, all reached the WRF success marker, and all six output files passed history validation. Each cold and warm 37/37 off/on pair is whole-file byte-identical. Both ordinary 4/4 cases are whole-file byte-identical to their archived 4 controls. The four new 37 histories also match their archived 37 histories byte for byte in these two short SCM seeds; the runner records these parent comparisons descriptively rather than using them as a required gate. An independent read-only review is preserved at `reviews/independent-runtime-review.json.gz`.

The first SCM attempt is preserved at `receipts/scm-v1-failed-execution.json.gz`. Its first two WRF processes returned zero, but the on arm produced no entry packets because that runner did not actually set the on-gate environment variable. This was a runner failure, not a model/source failure. The corrected runner and second attempt are separately pinned in the successful receipt.

The two 37-on arms contribute 12 V2 entry packets and 12 post-radius packets under `captures/`. `tools/WRF/test/rrtmgp/test_udm_entry_density.py` is the unchanged V2 parser, alongside its pinned radius parser and trace source. The reports in `analysis/` were recomputed from the archived packet bytes by the package verifier: 12 packet joins and 708 native-level checks across cold and warm. They establish exact call identity/time, binary32 DEN preservation across the UDM call, and the reported source-expression checks. Shared temperature and condensate fields may change during UDM and are reported rather than required to remain equal.

## Native fixture history

The native fixture receipts `receipts/native-run-v1-comparator-failure.json.gz` and `receipts/native-run-v2-pass.json.gz` are retained as historical attempts. A source review found their test-only slope markers did not identify the two cloud-slope call sites independently, so their marker-based retention observations are superseded. The corrected `receipts/native-run-v3.json.gz` uses distinct call-site markers and passes the scoped initialization fixture: 20 compile/link and 20 fixture invocations, zero WRF/REAL/RTE calls. Across O0/O2 the pre-fix rain-only and rain-above-cloud controls terminate on invalid arithmetic, while candidate executions are finite and initialized controls match. The corrected trace-cloud-top control did not observe a within-substep cloud-top shrink with a changed retained slope value; shrink retention therefore remains untested. The prior marker-placement runner and its independent static review are preserved separately under `native/history/` and `reviews/`. The inherited-control receipt is `receipts/native-rain-only-controls-v2.json.gz`.

## Limits

These are two short single-column-case families plus a source-level native fixture. They do not establish precipitation occurrence, rainfall magnitude accuracy, domain-wide conservation, coupled trajectory stability, a whole-water budget, or a general physical validation. They do not establish the unobserved within-substep shrinking-cloud-top retention condition. The archive contains no executable, build object, or NetCDF history file. Complete textual model/build/native logs are retained as lossless gzip streams and linked to their original hashes in `logs/log-index.json`.

The parent worktree head `9a83b9021d8f10a8aec8b5615f0c138ebbc48b85` includes metadata/test registration; the compiled production source base and overlay are recorded independently by the build receipt. No CI result is asserted here.
