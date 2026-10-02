# Bounded negative UDM radiation-input evidence

See the [input contract](../../../WRF/doc/rrtmgp/NEGATIVE_INPUT_CONTRACT.md) for policy, units and limitations. Native UDM process thresholds are an explicit operational ceiling, not a proof of floating-point roundoff. Positive values and RRTMG4 are unchanged; positive hail remains unsupported and graupel remains explicitly omitted.

- `hourly-limit-coverage.json`: all 25 hourly files from the successful prior RRTMG4 24-hour case. Negative QC/QI magnitudes are below 1e-12, and QR/QS/QG/QH below 1e-9 kg/kg. No pressure-interface thickness is present in these history files, so this report does not invent water-path corrections. These are hourly samples, not every radiation activation or the evolving 37 state.
- `validation-summary.json`: actual-source negative-policy tests, whole standalone library coverage and GNU serial paired SCM. The first OpenMP standalone suite ran with an 8 MiB stack: 56/57 tests passed and the existing large transparent-overlap fixture segfaulted. The unchanged failed executable passed with a 64 MiB stack. Both outcomes are recorded; no numerical tolerance or code was changed to obtain that recheck.
- `positive-scm-comparison.json`: frozen pre-policy binary versus the new binary, byte-identical wrfinput/namelist per control and mixed case; all 210 RRTMGP37 history arrays match bitwise. The historical RRTMG4 comparison in `validation-summary.json` separately matches 208 arrays per case. These are one-minute SCM cases, not a real-data accuracy evaluation. All eight captured LW/SW call-1/call-2 raw records are reconstructed with the current six-phase validator.
- `compare_positive_scm.py`: reproducible frozen-binary comparison and raw reconstruction; it refuses an existing output directory.

```sh
python WRF/test/rrtmgp/test_udm_negative_policy.py
cmake -S WRF/test/rrtmgp -B build/udm-negative-columns
cmake --build build/udm-negative-columns -j 12
ctest --test-dir build/udm-negative-columns --output-on-failure
# For a CMake build with RRTMGP_TEST_OPENMP=ON, allow the existing ensemble
# fixture's large automatic mask arrays before running the whole suite:
ulimit -s 65536

# After building serial em_scm_xy, supply the actual pre-change 4/4 cases:
python WRF/test/rrtmgp/test_udm_scm.py NEW_SCM_DIRECTORY \
  --reference-executable build/udm-negative-columns/reference_column \
  --baseline-control PRE_CHANGE_CONTROL4 --baseline-mixed PRE_CHANGE_MIXED4
python validation/rrtmgp37/negative-input/compare_positive_scm.py \
  FROZEN_PRE_POLICY_WRF_BINARY NEW_SCM_DIRECTORY NEW_COMPARISON_DIRECTORY
```

Independent real-data MPI execution is separate from the unit/SCM results. Neither passing these tests nor correcting a tiny negative establishes hail/graupel optics, cloud/precipitation fraction validity, a completed 24-hour 37 forecast or observational accuracy.

The rebuilt MPI4/OMP1 real-data attempt passed the formerly rejected 600-second radiation activation, then stopped at 1200 seconds on positive hail. `runtime-result.json` records the expected unsupported-state exit, not a completed one-hour forecast. `same-time-hydro-history.json` shows that both matching RRTMG4 control histories also contain hail at this sampled time. `overlay-receipt.json` plus `mpi-runtime-source-parity.json` identify the compiled source rather than relying on the isolated checkout's historical git head. Raw rank diagnostic events have file/line order but no inferred timestamps. `publication-manifest.json` records unchanged JSON and any CSV newline normalization; original hashes in the run receipt refer to the original scratch files.
