Retain scoped UDM37 CCN runtime and restart evidence

The UDM37 CCN startup/shared-CF repair removes the tested multi-tile thread differences. This evidence-only package retains the pre-change failures,official-pristine RA4 discriminator,early QNCCN observations and corresponding fixed runtime comparisons. It is stacked on PR49 (`199d0d9`; runtime-tested source `4673f9d`),with no source or configuration changes.

- Three-hour RA37 OMP1/2 and probe/plain outputs match all225 history and664 checkpoint raw variables,metadata and whole files. Four MPI PIDs each prove workers0/1/team2 callback activity.
- Same-thread RA4 behavior,including its legacy startup defect,is preserved exactly. New24h OMP2 history matches the earlier one-tile history; histories/checkpoints pass strict finite,mask and default-fill checks.
- Own-restart state is accepted: initial15:00 history222/225 matches with three documented history-only diagnostic resets; final16:00 history225/225 and checkpoint664/664 raw fields match. Metadata differences are explicitly START_DATE,Time extent and disabled alarm55. Original strict comparison FAIL is preserved; continuous/restart whole-file parity is not claimed.
- Original build-verifier failure and separate posthoc attestation,stale unrun stages and old raw-parity failures remain auditable. The standard-library verifier checks complete retained hash tables and per-PID worker evidence without model execution or external arrays.

The ledger contains17 primary processes,including8 candidate processes; the root's broader count21 includes4 prior references. The combined two-source-change effect is not isolated into individual causes. Evidence applies to the stated GNU/MPI4/two-tile case,not general nested/decomposition invariance or forecast accuracy. Latest PR49 CI was pending at preparation; previous tested head passed all eight checks. No model/build/reference calls or remote actions were performed by the packager.
