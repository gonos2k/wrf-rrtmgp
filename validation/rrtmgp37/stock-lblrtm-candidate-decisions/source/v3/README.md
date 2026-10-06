# Candidate-decision diagnostics — private v3 source copy, uncompiled

This additive metadata correction preserves v1 and v2 unchanged. The candidate source and patch are byte-identical to v2; this version corrects the interpretation of one event label.

`LNCOR1_9` is emitted immediately after corrected SP/SPPSP strength calculation and before the later SPEAK/FREJ filters. It records that the line reached that point and provides computed operands; it does not prove the line survived all LNCOR1 filters or entered CNVFNV. A phase-3 CNVFNV record with the same invocation identity is the evidence of CNVFNV entry. No source hook is moved.

The v2 identity fixes remain: encoded MOL is retained verbatim, isotope is decoded with `MOD(encoded_MOL,1000)/100` to match the pinned LNCOR1 expression, and the original IFLAG is preserved. No physics assignments or control-flow predicates are changed. No compilation or model/solver run has occurred.

See `plan.json` for v1/v2 provenance, exact identity and stage-interpretation corrections, static-check results, and limitations.
