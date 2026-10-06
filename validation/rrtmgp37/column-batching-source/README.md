# CPU column-batching source change

This change addresses a candidate cause of the observed batch-size sensitivity:
GNU may select vector `exp`, `log`, or `cos` library entry points when RRTMGP
evaluates those operations on arrays. The CPU RTE/RRTMGP units now call the
same scalar elemental wrappers across batch shapes. The helper is a separate
translation unit and is compiled without LTO/IPO; other kernel arithmetic
remains eligible for vectorization. This is scoped to CPU code and is not a
claim about accelerator builds.

`WRF_RRTMGP_BATCH_SIZE` remains opt-in: unset means `1`; allowed values are
`1`, `32`, `64`, and `128`. Capture/audit and explicit nonnegative MCICA seed
override requests keep the existing scalar route. Column packing preserves
per-column global seeds and solar inputs, flushes SW batches at row/night
boundaries, and scatters results back to the original columns. The wrappers
use call-local buffers; RRTMGP optical workspaces are separate from the
buffer-size estimate in `WRF/test/rrtmgp/COLUMN_BATCHING.md`.

## Evidence and limits

The earlier full-run comparison reported a B1/B32 numerical mismatch; that
failure is retained in its original receipt. A process-wide scalar-libm
counterfactual later restored equality, motivating this narrower source
boundary. The fresh GNU build and focused RTE-only B32 two-minute check passed.
The completed 40-minute regression used MPI4/OMP2 for B1 and B32 and
MPI4/OMP1 for the legacy RRTMG4 control. All five history files and the
40-minute checkpoint matched their pinned references in raw and decoded
values, types, shapes, and metadata. New B32 also matched new B1. The default
B1 matched the earlier B1 and pre-batching scalar trajectory; RRTMG4 matched
its earlier OMP1 control. No performance benchmark has been completed.
Coupled B64/B128, longer batched runs, and general forecast accuracy remain
unvalidated by these results. The compact `result.json` pins the run receipts.

The standalone compiler probe also checked the scalar helper boundary with
vectorization enabled and caller LTO enabled. Full model results, the preserved
failure receipts, and any completed longer comparison should be interpreted
from their own pinned run records rather than inferred from this source-level
change.

The initial independent CI client linked upstream-built objects to the vendored
library and failed in the LW loader. A local exact-source counterfactual
confirmed a type/vtable module mismatch. The corrected validation runners
compile the same pinned clients separately against each library's own modules.
Fresh RFMIP (four flux arrays) and synthetic all-sky (13 SW/12 LW arrays) then
matched bitwise. The original CI failure remains recorded; this harness repair
does not change WRF production sources or claim published-reference accuracy.
