# Saved candidate-decision reader — unexecuted preparation

Source-v3 writes formatted ASCII: UDM37CAND1 plus23 integers and14 real values,38 tokens total. No record markers apply to this file. The inherited R3 and OD files instead use little-endian4-byte markers and INTEGER8/REAL8 payloads. Negative HUGE marks uncomputed operands, not physical values.

Invoke read_saved_candidate.py --authorization <absolute file> only after root static review and actual candidate terminal RC0. Authorization fields and the97 exact artifact pins are specified in plan.json; root additionally binds the candidate build/source/executable/input closure and reviewer receipt in its launcher. The reader checks terminal status before raw hashes/parse, claims a fresh report directory and writes exclusive fsynced success/failure output. Root persists actual reader PID/RC before report inspection. No executable is launched here.

Full identities are (pass,block,slot,LNCOR batch). Reason9 is before SPEAK/FREJ filtering; phase3 records actual CNVFNV entry; reason11 is later-panel handoff, not a drop. Repeated events for an invocation are retained. Target R3 updates join uniquely to full identities and exact operands; geometric overlap alone does not guarantee a write.

Inherited R3/PANEL trace digests must match. The prior pinned executed report supplies arithmetic/carry proof and its analyzer is not rerun. All45 spectra/panel headers are compared directly; only HTIME header word168 may differ, joined to each TAPE6. This reads saved data once, preserves negatives and does not accept spectroscopic truth, remaining negative OD or WRF residual. Original coefficient vectors are excluded from the report.

No reader, compiler, solver, model or numerical raw-data inspection has occurred during this preparation.
