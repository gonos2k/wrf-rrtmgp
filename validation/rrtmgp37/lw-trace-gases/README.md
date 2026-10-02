# UDM27 LW trace-gas input correction

The pre-change coverage audit found that CFC11/CFC12/CFC22/CCl4 minor-absorber
intervals in the pinned LW data were filtered out by the six-gas initialization.
The current adapter loads ten LW gases and forwards the existing WRF wrapper
profiles. SW retains six gases. This repairs a port input omission; it does not
make the RRTMG and RRTMGP spectral or cloud models identical.

## Evidence and scope

- `prior-coverage-audit.*` describe the parent implementation, not current coverage.
- `fresh-wrf-build.json` records a fresh GNU serial `em_scm_xy` build and matching
  hashes of all thirteen staged production files before and after compilation.
- `synthetic-replay.json` exercises each gas, all four gases, zero/absent parity,
  invalid optional groups, and recorded gas optical depth against an independent
  replay executable. The fixture uses explicitly labeled synthetic fallback VMRs.
- `replay-formats-final.json` checks malformed V8 inputs, zero-CFC legacy parity,
  and the combined V8/frozen-table metadata contract.
- `frozen-scm-v8.json` checks the new LW V8 format together with opt-in frozen
  optics through actual WRF columns. Experimental ice spheres are not validated
  against atmospheric observations.
- `scm-fallback-cfc.json` records five actual LW captures, same-reference
  zero-CFC attribution and control/mixed parent RRTMG4 bitwise checks (207 arrays
  each). Maximum profile flux differences in these cases are about 0.394 W/m2.
- `real-cam-cfc.json` records a one-minute real-data UDM27/37 experiment. CAM
  file loading is logged, CFC11/12 match the first LW wrapper interpolation
  at its actual Julian date, native profiles pass exactly, and above-top values
  remain held at the native top. Independent V8 replay also passes with the
  experimental frozen table. Same-reference four-gas removal changes the LW
  profile flux by at most about 0.4403 W/m2 and heating by 0.00879 K/day. This is
  one captured boundary column; it is not a domain average or accuracy metric.
- `native-gas-v8.json` checks the unchanged independent native dry-mass and
  above-top gas-column formulas on actual V8 LW/V6 SW captures. The updated
  parser also rejects a V8 capture missing a trace-gas profile.
- `cf-replay-*.json` record the workflow-equivalent eight-seed control/mixed
  V8 LW/V6 SW CF/precipitation/delta-policy matrices, V4 compatibility and a
  combined frozen V8 smoke replay. Every non-updated record is checked exactly,
  including CFC profiles and any frozen metadata. These are counterfactual
  policy tests, not a new production cloud-fraction choice.
- `review.json` records a separate read-only source review and its limits.

The first full standalone test run passed 88 of 89 tests. The new CFC fixture
compared Python double literals to values encoded by the adapter's default REAL
inputs. The test was corrected to use their explicit float32 encoding; the
output tolerance was not relaxed. Its initial failure and focused passing retest
are preserved. The later replay-format test was also rerun after its executable
malformed-input probes were strengthened.

Ideal SCM initialization skips the CAM tracer-file load. Even with GHG_INPUT=1,
its observed CFC values are host fallback constants. A CAM-table hash alone is
not evidence of consumption. Real-data CAM input consumption is checked
separately. CFC attribution must compare the same reference engine on captured
input and an otherwise identical input with only the four VMR arrays zeroed;
production REAL32 versus reference precision is checked separately.

No forecast or observational accuracy claim follows from these input/replay tests.

The first real-case validator used the integer-Julian-day physics initialization
log as its equality oracle. Radiation calls the reader at its own Julian date.
The full WRF run completed, but this incorrect test oracle failed. The corrected
run enables diagnostic logging in a copied namelist and checks the first LW
wrapper interpolation record. It retains the numeric tolerances and exact raw
native-prefix checks. `attempts.json` preserves this and an earlier launch with
a missing shared-library path.
