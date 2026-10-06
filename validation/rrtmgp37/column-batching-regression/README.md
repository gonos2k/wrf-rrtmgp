# UDM27 CPU column batching: scoped regression evidence

The RTE-only CPU scalar-math boundary in PR #52 removes the observed batch-size-dependent rounding under the pinned GNU toolchain. The default batch size remains 1; 32, 64 and 128 are opt-in. No process-wide preload was used in these runs.

## Completed 40-minute tests

The same fresh GNU executable ran UDM27 + radiation37/37 with MPI4 and two OpenMP threads per rank. B32, B64 and B128 match B1 exactly across five history times and the final checkpoint, including raw bytes, decoded arrays, shapes, dtypes and full metadata. The additional B64/B128 comparisons contain 3,390 variable comparisons, including character fields. Read-only audits rechecked executable, source, input, runtime-library and output pins, and actual rank identities/environments.

The B1 arm also matches the earlier scalar/pre-batching reference. A separate legacy RRTMG4 arm at MPI4/OMP1 matches its existing reference; this does not establish pristine WRF equivalence under every decomposition.

Logged radiation row widths 144/145 and the source packing rules give expected full and tail batches, with day and night samples. These are source-derived coverage estimates, not runtime call counts.

The compact [result.json](result.json) pins the full local execution/audit records. At the wide-regression snapshot it records 45 local model invocations inherited across this investigation, not 45 runs of this change or a current cumulative total. A subsequent short long-run gate invoked one additional model, which exited successfully but stopped at a validator schema error; that separate recovery remains pending. Exactly two new model invocations supplied the B64/B128 extension. Remote CI runs are excluded from that ledger.

## Independent backend checks

PR #52 also corrects the reference-client build to use the vendored Fortran modules when linking the vendored library. Its remote RFMIP and synthetic all-sky checks pass. Downloaded outputs and source manifests have been independently audited; the published RFMIP reference comparison remains NOT_RUN. The all-sky check validates paired gas/cloud/RTE backend outputs, not the WRF input mapping, McICA or forecast accuracy; its aerosol amount is zero.

## Scope

This is a fixed-toolchain numerical regression. Diagnostic elapsed times are not a benchmark. Long-run/restart and repeated performance gates remain separate. The original failed batch comparison and process-wide scalar-math counterfactual are retained in PR #51 rather than overwritten. No universal forecast accuracy, nested-domain acceptance or NOAA hail-optics parity is claimed.
