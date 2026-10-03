# Selected-column radiation diagnostics

The selected-column diagnostic option narrows the existing same-state radiation audit and serial RRTMGP input/output capture to one WRF mass column. It is opt-in and does not change the physical radiation or microphysics calculations. With both selection variables unset, existing trace selection remains column `(1,1)` and the audit retains its full-current-tile scope.

## Select a column

Set `WRF_RRTMGP_COLUMN_I` and `WRF_RRTMGP_COLUMN_J` together to positive decimal WRF indices. A partial pair, non-decimal value, zero, negative value, or integer overflow is rejected. The point must be in the global physical mass-column domain `IDS:IDE-1` by `JDS:JDE-1`; the staggered `IDE` and `JDE` edge points are not mass columns. If the selected point is outside a particular tile but inside the domain, that tile skips the diagnostic. A point outside the global domain is fatal.

When selected, audit rows use `scope=selected_column`: one row carries the selected positive `i,j`, and the `(0,0)` aggregate row is also scoped to that single point. It is not a domain mean or a multi-column average.

## Run the audit and capture

The same-state audit and trace capture use process-global diagnostic state and are serial-only. Use a serial WRF executable and one OpenMP thread. The audit rejects MPI-enabled builds and OpenMP runs with more than one thread; capture has the same serial restriction. Create both output directories before starting WRF.

From a prepared WRF run directory containing the namelist, inputs, and executable:

```sh
mkdir -p audit capture
export OMP_NUM_THREADS=1
export WRF_RRTMGP_COLUMN_I=169
export WRF_RRTMGP_COLUMN_J=80
export WRF_RRTMGP_AUDIT_DIR="$PWD/audit"
export WRF_RRTMGP_AUDIT_SEEDS=32
export WRF_RRTMGP_CAPTURE_DIR="$PWD/capture"
export WRF_RRTMGP_CAPTURE_CALL=2
./wrf.exe
```

This enables the selected-column paired audit with 32 deterministic McICA seeds and captures the second selected-column radiation call separately for LW and SW. The raw capture records `RADIATION_STEP`, `SOURCE_TIME_SECONDS`, domain/calendar seed identity, hydrometeors, cloud fraction, host `PI`, pressure, layer mass, gas inputs, and prepared cloud optics. The capture also writes replay input and WRF result files for each phase. Inspect the captured step/time metadata before correlating a call with a history record; the call number alone does not define a wall-clock time.

For an audit-off control, use a separate copy of the same restart and inputs, and clear the audit and capture variables. Keep the namelist and every input byte-identical between the OFF and ON cases. The audit is observational: paired shadow calls write audit output and do not feed values back into the forecast.

## Check the implementation

From the repository root, run the focused selector contract test and Make dependency check:

```sh
python3 WRF/test/rrtmgp/test_column_selection.py WRF
python3 WRF/test/rrtmgp/test_wrf_udm_dependencies.py WRF/main/depend.common
```

The test exercises legacy defaults, paired selection, global-bound validation, outside-tile filtering, and malformed selectors. It also rejects duplicate cell rows and invalid selected-scope aggregates. CTest registers the same contract as `rrtmgp_column_selection_contract` for GNU builds.

## Bounded real-data result

The completed serial `em_real` OFF/ON pair used the same 12:00 restart, initial and boundary data, namelist, immutable static assets, source snapshot, and executable. Both runs wrote histories from 12:01 through 12:11. The independent whole-file comparison passes: all 11 history files are byte-identical, including all 210 numeric variables and all file metadata. This shows that these enabled diagnostics did not change this run's forecast outputs; it is not a forecast-accuracy or physics-equivalence result.

The actual selected mass column is WRF one-based `(169,80)` (NetCDF zero-based `[79,168]`), with positive QG and QH at the chosen checkpoint level. Runtime audit events map to `source_seconds=43200`, step 721, and `source_seconds=43800`, step 731. The history file time is one minute after the audit source time because radiation diagnostics are advanced by the actual 60-second timestep; absolute `Times` and `XTIME` agree. At the captured second activation, the raw host column has 39 native physical layers; the replay engine inputs contain 47 LW and 40 SW layers. Those are distinct layer domains and should not be reported as a mismatch.

The corrected offline validator passes the selected audit/history and capture contracts. Independent reference replay passes 20 LW and 46 SW result sections for the captured call, and the paired OFF/ON history comparison passes whole-file byte equality. The original ON launch receipt is retained unchanged with status `FAIL`: the forecast completed, but that launcher's parser rejected lowercase phase tags. The corrected offline validator is a separate later artifact and did not rerun WRF. The selected ensemble analysis describes one opaque selected G/H column only; it does not support domain-wide generalization or a forecast-feedback claim.

Root-run native validation also passes for this column: coordinate-derived dry-layer mass against the 12:10 history state, all six species water paths, clear-cloud and upper-extension handling, and native/extended gas-column formulas. The native mass checker rejected corrupted mass and mismatched source-q probes; the gas checker rejected a missing-CFC V8 probe. The curated, hash-indexed receipts, captures, scripts, and independent replay outputs are in `validation/rrtmgp37/udm-selected-column-runtime/`; full histories, executable/build trees, and source manifest are represented by recorded hashes rather than copied into this package. Review the preserved original failure receipt as well as the later passing validator receipts.
