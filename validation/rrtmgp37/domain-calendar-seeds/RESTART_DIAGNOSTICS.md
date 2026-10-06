# UDM37 diagnostic restart contract

`UDM_CLDFRA`, `UDM_CF_STEP`, and `UDM_CF_TOP` describe the last UDM
microphysics call. New checkpoints store these fields as well as history
output. Restart input initializes them to the unavailable sentinel `-1`
before reading the file, restores the sentinel after any failed diagnostic
read, and physics initialization resets them only on a cold start. The
post-read restoration is needed because MPI input can scatter a zero buffer
even when the underlying NetCDF read reports a missing variable. A checkpoint containing the fields therefore preserves them
in the initial restarted history record, before another microphysics call.

An older checkpoint without these fields leaves the sentinels and the
existing WRF missing-variable warnings. Its last-call diagnostics cannot be
recovered from the prognostic state: recomputing the current cloud fraction
would describe a different event. Microphysics refreshes the diagnostics on
its next call. Exact diagnostic restart equivalence requires checkpoints
written with this change. These changes apply only to UDM27 with paired
37/37 radiation; the RRTMG4 initialization path is unchanged.

The SCM restart runner compares the donor checkpoint directly with the
initial split-2 history, requiring all three fields, matching physical time,
finite unmasked values, and exact raw and decoded arrays. This occurs before
history merging. The merge retains the split-1 record at a duplicate
timestamp, so the merged history alone could hide an initial restart reset.
The boundary checker failure controls include that reset even when a later
record recovers, a missing checkpoint field, a wrong time, NaN, and a
decoding mismatch.

The original January MPI4/OpenMP2 two-hour probe exposed the defect: at the
one-hour restart boundary only these three diagnostics differed; all other
history fields matched, and the diagnostics matched again after the next
call. That failed probe remains evidence of the pre-fix defect, not proof
that the corrected implementation passes. Fresh executable and checkpoint
validation is reported separately.
