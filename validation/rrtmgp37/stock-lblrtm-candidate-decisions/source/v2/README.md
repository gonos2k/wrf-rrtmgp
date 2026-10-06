# Candidate-decision diagnostics — private v2 source copy, uncompiled

This is an additive correction to the unexecuted v1 diagnostic patch. It preserves v1 byte-for-byte and corrects the identity fields in the new candidate copy: the encoded MOL value is retained verbatim, and isotope is decoded as `MOD(encoded_MOL,1000)/100`, matching the pinned source’s LNCOR1 expression. The earlier nested `MOD(...,100)` isotope expression always produced zero; v1 remains preserved as the historical draft.

The correction applies to RDLIN offered, below-VBOT, and deferred rows, and to the corresponding CNVFNV decision rows. RDLIN reason 1 now passes `udm37_rdlin_id(4,I)` as the encoded MOL field rather than reducing it to `MOD(...,100)`. The original IFLAG remains passed unchanged. This preserves source identity while LNCOR1 later reduces MOL for its own internal molecule/isotope operations.

No physical assignment, branch condition, coefficient, line-support operation, or R3 update is changed. The existing diagnostic hooks and equivalent branch wrappers are otherwise copied from v1. The candidate has only static source checks; it has not been compiled or run, and no model/solver was invoked.

See `plan.json` for the pinned base, v1 provenance, exact identity correction, static checks, and limits.
