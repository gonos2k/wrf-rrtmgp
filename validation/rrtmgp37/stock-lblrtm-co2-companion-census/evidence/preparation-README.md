# Bounded CO2 target-record companion census

This is a prepared, not-yet-executed reader for the 801 CO2 flag-1 identities already present in the saved target-contributor report. That prior report has already joined all 6,072 R3 updates for bins 61–64 to 837 phase-3 reason-12 identities; this reader does not repeat those raw CAND/R3 passes.

The proposed pass seeks directly to TAPE3 panels 484–496 and checks each expected main's block/slot, encoded MOL, and IFLAG. For each main it counts the complete run of immediately following negative-IFLG slots, including across panel boundaries in the selected range. A flag-1 identity is expected to have exactly one adjacent companion; missing, duplicate, mismatched, or still-open groups are explicit failures. It stores only identity summaries, companion slot/flag summaries, per-panel metadata, and hashes for the selected byte ranges.

The reader does not recompute YI/GI/SPPSP or R3 arithmetic. A pass would establish record association only for the already-observed target CO2 contributors. It would not establish a complete set of all candidate lines, a named physical coupling group, or physical cancellation closure. The TAPE3 whole-file digest is inherited from prior postflight provenance; this reader hashes no more than the file header and 13 selected panels.

`audit.py --run` is intentionally gated. Root review of the frozen plan and code is required before a one-use invocation. No model, build, or solver invocation is part of this audit.
