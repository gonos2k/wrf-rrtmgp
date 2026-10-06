# Selected-column OFF/ON runtime evidence

This package curates the completed bounded 2010-06-11 12:00 restart experiment for review. `curated-provenance.json` records SHA-256 digests for every copied file plus the large external source, executable, restart, initial/boundary, coefficient, and frozen-table assets. Large model histories, executables, and the complete source manifest are intentionally not duplicated; their digests are retained in the receipts and provenance index.

## Result scope

The OFF and ON serial `em_real` runs used an identical restart, namelist, initial/boundary files, static runtime assets, source snapshot, and executable. Each produced 11 history files from 12:01 through 12:11. `receipts/root-wholefile-comparison.json` reports PASS: all 11 complete history files are byte-identical, each containing 210 numeric variables and 211 total variables. This demonstrates diagnostic noninterference for this run. It does not show forecast accuracy, equivalence of radiation physics, or domain representativeness.

The selected WRF mass column is one-based `(169,80)` (NetCDF `[79,168]`) and has positive QG and QH. The paired audit records activations at source seconds 43,200 / step 721 and 43,800 / step 731. The history record is one actual 60-second timestep after each radiation source time: absolute `Times` and `XTIME*60` align. For the second activation, the captured raw host profile has 39 native physical layers; the replay input/output grids have 47 LW and 40 SW engine layers. Keep these layer counts separate.

The offline validation v5 bundle and its exact scripts are retained under `scripts/` and `receipts/`; it passed the audit/history and capture contracts without rerunning WRF. The independent selected-call reference replay passes 20 LW and 46 SW sections; its two generated outputs and provenance are retained under `independent-reference/` and `receipts/`. The capture is call 2 at the selected point and does not validate the frozen-particle optical model independently.

The original ON launch receipt is preserved losslessly as `receipts/on/original-launch-receipt-fail.json`. Its `FAIL` status reflects the frozen launcher parser rejecting lowercase audit phase tags after the forecast process completed; it is not a WRF runtime failure. The later offline validator corrected parser assumptions and consumed the retained run artifacts. Preparation-only receipts are retained separately under `receipts/preflight/`.

Root-run native validation also passes: the captured native dry-mass profile matches the same-time history-derived WRF coordinate formula within the stated REAL32 tolerance; all six species grid-mean water paths close against the 12:10 history state, with clear-cloud and upper-extension handling checked; and native plus upper-extension GAS_COL_DRY matches the respective native-mass and pressure/H2O formulas. Missing-CFC, corrupted-native-mass, and mismatched-source-q negative probes are rejected. These checks cover this one selected column and captured call only. The included 32-seed statistics and analysis apply only to this selected opaque G/H column; they cannot be generalized to a domain mean, the full 45 W grid, normal forecast behavior, or radiation feedback.

## Contents

- `captures/on/`: the six actual ON LW/SW `.input`, `.raw`, and `.result` capture files.
- `independent-reference/`: independent LW and SW replay result sections.
- `scripts/`: exact OFF launcher, frozen original ON launcher, corrected offline runner/validator, and independent capture validator snapshots.
- `receipts/`: OFF/ON launch receipts and progress/plan records; original ON failure; corrected v5 validation, the earlier v4 receipt, independent reference results/provenance, whole-file comparison, corrected build receipt v2, and root-run native gas/mass validation receipts.
- `scripts/native-gas-columns-validator.py` and `scripts/native-mass-history-validator.py`: exact validators used for the added native checks.
- `analysis/`: the exact `same_state.csv` (79,213 bytes, SHA-256 `f5d06ab9befa3ac115f2848f3319b62536e1da5c1ab88b4ff121e67090bb2b96`) underlying the selected-column 32-seed analysis, plus its scoped JSON/Markdown summary and a verifier for the archived summary statistics.

The original scratch analysis had no retained standalone generator script. `analysis/verify_selected_ensemble.py` is a posthoc consistency verifier, not claimed as the original generator; it recomputes differences/MCSE/covariance bounds/correlations from the exact CSV and checks them against the retained analysis JSON. Run from this package directory with `python3 analysis/verify_selected_ensemble.py analysis/same_state.csv analysis/selected-ensemble-analysis-v1.json`.
- `curated-provenance.json`: copied-file digests and hashes for uncopied large assets.

No model case is launched by the scripts in this package. Reproduction requires the retained source/build/input/table assets at the paths and with the hashes recorded in receipts; those large assets are not copied here.

## Native validation commands and dependencies

The exact commands used by root, including the explicit 12:10 history record and both output receipts, are preserved in `receipts/root-native-validator-provenance.json`. They invoked `test_native_gas_columns.py --capture-dir ... --output ...` and `test_udm_native_mass.py CAPTURE_DIR WRFINPUT --history HISTORY --history-state-may-differ-from-wrfinput --executable WRF_EXE --output ...`; the mass tool's `--time-index` defaults to `0`, the 12:10 record in this one-record history file. The receipt records hashes for the two validators and their `test_column_replay.py` / `compare_column_replay.py` dependencies, as well as both output JSON receipts and the source manifest.

Equivalent reruns should use new output paths and the exact copied scripts/dependencies in `scripts/`; do not overwrite the frozen root receipts. These are offline validation commands and do not launch WRF.
