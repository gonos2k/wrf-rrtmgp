# Corrected PR26 24-hour and restart evidence

This compact evidence set preserves the corrected paired 24-hour RA4/RA37
run and same-executable own-arm 12Z→13Z restart check. This is an evidence-only
record pinned to the stated PR26 source build; it contains no production-code
changes and makes no claim about later source revisions.

The source build was reviewed against PR26/fix-udm-sr-row source head
`792f36b6bbc442f0db37b5cb9fdf19dd33600082` (local build commit
`e7c97ed661403b3922fcf752300c052611ef89cd`), with executable SHA256
`176f589d657ca87df670cef3429d7474e674f3e44445eb7886aed871e36bef8f`.
The evidence and executable provenance apply to that source revision only.

- `run/` contains the exact paired-run driver, preflight, execution and root
  review receipts, source provenance, plan notes, both namelists, and compact
  rank logs with SUCCESS markers.
- `analysis/` contains both unchanged V1 (active-model AREA2D-weighted) and V2
  (physical map-factor-weighted) analyzer scripts and results, root reviews,
  reports, and analyzer self-test receipts. `analysis/V1-ERRATUM.md` explains
  the AREA2D source nuance. V2 reports cell-center map-factor area estimates;
  neither nominal V1 model-area integrals nor V2 estimates are described as
  geodesic Earth-area integrals.
- `restart/` contains the same-executable own-arm restart runner, preflight,
  execution receipt, exact namelists/logs, raw-byte proof receipt, and a clearly
  labeled posthoc comparator plus its output.
- `netcdf-sha-index.json` records SHA256 and sizes for all 50 continuous
  histories, all four 12/24 h checkpoints, both restarted 13Z outputs, and
  their continuous 13Z references. Large NetCDF files are not copied.
- `completion-and-log-index.json` records exact rank-log hashes and terminal
  WRF completion markers. `verify_index.py` checks the package hashes and
  consistency of receipt/hash metadata without opening forecast NetCDF files;
  `artifact-index.json` hashes the curated package contents.

Scoped whitespace handling preserves byte evidence for only these archived
files: the two metrics CSVs retain their original CRLF line endings, and the
run/restart namelist copies retain trailing blanks. The package `.gitattributes`
uses `-text` plus `whitespace=cr-at-eol` for the CSVs and
`whitespace=-blank-at-eol` for namelists. Authored Markdown and Python files
remain subject to normal whitespace checks.

Run the package verifier from any directory:

```sh
python3 validation/rrtmgp37/realdata-parallel/current-pr26-corrected-24h/verify_index.py \
  validation/rrtmgp37/realdata-parallel/current-pr26-corrected-24h
```

The analyzer checks available identities: 125 pass, 100 are unavailable in
history output and skipped, and none fail. Overall field-math status remains
`INCOMPLETE_FIELD_MATH_CONTRACTS`. The paired fields are coupled trajectory
snapshots and accumulator totals, not a same-state solver benchmark or a
forecast-skill claim. See `analysis/V2-REPORT.md` and `restart/REPORT.md` for
scoped summaries.
