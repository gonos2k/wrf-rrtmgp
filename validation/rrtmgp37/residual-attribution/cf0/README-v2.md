# CF0 audit README correction

This additive correction preserves the original `README.md` unchanged (SHA-256 `0838d7c665d99d92b1921cf6f4e9ee7b644a62e6fa7b4ca0d2f650f580088cd4`). It narrows one statement about where per-record context is stored.

`audit-final-v2.json` (SHA-256 `10420a87623d968ccfb55a8a5c9587108a24c8988236e08386d16bf601e103ef`) contains aggregate totals, per-rank breakdowns, and record counts. It does **not** contain per-record source-time or overlap-context rows. The per-record context remains in the four pinned rank-unique `rsl.error.0000`–`0003` source logs; the analyzer reads those rows and cross-matches the compact CF0 summaries with contextual PHASE_PATH records while calculating the aggregates. The source-log hashes and record counts are in `audit-final-v2.json` under `run.unique_rank_logs`.

All omission totals, ratios, source/executable/log pins, and interpretation limits in the original README and audit JSON are unchanged. This correction changes documentation only; no model, parser, or numerical analysis was rerun.
