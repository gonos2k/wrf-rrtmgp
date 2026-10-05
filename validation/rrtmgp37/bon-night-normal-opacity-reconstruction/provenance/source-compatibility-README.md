# Normal-carrier source compatibility addendum

The normal-replay inventory contains a narrow provenance mismatch: the selected driver file is SHA `6e82…b1ff0`, while the nested build receipt’s source-pin manifest records driver SHA `932…580e6f`. This addendum preserves that distinction rather than treating the receipt as proof that every compiled source byte came from the selected file.

The source diff has one hunk, inside the optional precipitation audit-sidecar guard. The normal replay command passed an empty final sidecar argument, so that branch was not entered. After replacing only that gate block with a marker, the source files are byte-identical. The LW gas roster, V10 constants initialization, 32-value native mass parse, `get_col_dry` call, and native-prefix override expressions also match exactly. The pinned executable contains the selected-generation sidecar diagnostic string; that static string check corroborates the selected generation but does not prove complete source-to-object provenance.

The appropriate characterization is therefore an authenticated direct-library output with a disclosed, narrowly scoped source-generation inconsistency. No opacity calculation or numerical target comparison was performed.
