# Fresh UDM37 diagnostic restart evidence

This evidence records a local real-data January 2000 restart campaign for the
three diagnostics written by the latest UDM microphysics call:
`UDM_CLDFRA`, `UDM_CF_STEP`, and `UDM_CF_TOP`. The primary run used one fresh
GNU/MPICH DM+SM executable with four MPI ranks and two OpenMP threads per rank
for six arms: batch-1 and batch-32 continuous runs,
short and long own-checkpoint restarts, and their comparisons. All 225 checked
history fields and 667 checkpoint fields are exact across the stated array
comparisons, including the three diagnostics. There are no numeric or raw-array
exemptions, and immutable-input postflight passed. The short continuous runs
cover two hours with a one-hour restart segment; the long runs cover 24 hours
with a 12-hour restart segment.

The strict comparator still reports `FAIL_PRESERVED` for invocation metadata.
`START_DATE` differs between continuous and restarted invocations; restart
checkpoint metadata also contains a different `WRF_ALARM_SECS_TIL_NEXT_RING_55`
countdown. These values are validated under the source-backed invocation
metadata contract, but the campaign does not call the NetCDF files wholly
identical. No state-array tolerance or exception was applied.

A separate run restarted from a pre-diagnostics checkpoint. At its initial
history time, the three diagnostic fields are the unavailable sentinel `-1`;
the other 222 checked fields match. From the next 10-minute history record,
all 225 fields match at each history time through 14:00. The final checkpoint fields match
under the same invocation-metadata policy. The receipt explicitly makes no
claim that all 225 fields match at the initial record. This documents legacy
checkpoint behavior rather than reconstructing a diagnostic value that the old
checkpoint did not contain.

The campaign ran seven model invocations total and no benchmark cases. The
compiled source and executable are pinned in `summary.json`; the large output
files remain in the local build artifact tree and are identified by the
execution receipts rather than copied into this repository.

The preceding PR54 CI run failed its serial-SCM restart check because the first
restarted record began at 19:01:10 instead of 19:01:00. A validation-only fix
was committed at `dbf03a9171b86cfc2f825a5ff2d7189ba572d4fa`; it enables the
initial restarted history write and tests that control. The updated-head CI run `37173604961` passed all eight jobs. Its serial-SCM
restart cases (control, mixed, and calendar boundary) match at 13 timestamps
across 211 history variables each; restart-boundary checks cover 204 variables.
All nine CI restart invocations succeeded. These SCM runs are separate from
the seven local real-data runs above. The earlier CI failure, fix, and new
success receipts are pinned in `summary.json`.
The follow-up changes only the validation runner and its tests; the compiled
Fortran sources used by the local campaign are unchanged.

The existing [diagnostic restart contract](../RESTART_DIAGNOSTICS.md) describes
the sentinel handling and the source change. This local report is scoped to the
pinned run and does not make broader meteorological accuracy claims.
