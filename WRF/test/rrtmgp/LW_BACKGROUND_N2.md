# Longwave dry-background N2

The LW adapter now declares a fixed dry-background nitrogen VMR of
`0.7808_wp`, following the pinned CCPP embedded all-sky example (commit
`3e6660c6`, RTE revision `41c5`). This is a declared model background input;
it is not a BON measurement and was not selected to match RRTMG4.

New replay formats make the input explicit: V12 is LW without the CU input
group, and V13 is LW with the CU group. Both include `VMR_N2` and a scalar
`TRACE_GASES_PRESENT` flag. The four CFC VMR records are present only when
that flag is one; when it is zero the reference initializes those profiles to
zero. The wrapper also records `GAS_TAU_RAW` for both new formats. Existing
V1–V11 records keep their original gas closure and must not contain either new
N2 metadata field. SW and legacy RRTMG4 inputs are unchanged.

The fixed dry-air N2 assumption does not add CO, which remains outside this
change. Tests cover new-format round trips, absent versus explicit-zero CFC
inputs, malformed N2/CFC metadata, CU/no-CU format selection, and legacy
V10 parsing. Local validation also replayed the archived BON V10 input with
the new executable: its full output matched the retained output byte for byte.
Under V13, explicit zero N2 preserved all historical fields exactly; 0.7808
changed surface downward LW by +0.02400244 W/m2. This uses the original
32 native layers and 13 pressure-derived extensions and is separate from the
full-45-layer matched-dry diagnostic in PR #87. It is one column, not a
general bitwise guarantee across toolchains or a physical accuracy result.

Retained evidence that pins old reader, adapter, or comparator sources can be
checked with the [historical archive v2](../../../validation/rrtmgp37/reference-source-archive/README-v2.md).
Its wrapper resolves only recorded SHA-addressed historical dependencies;
it does not validate the current numerical implementation.
