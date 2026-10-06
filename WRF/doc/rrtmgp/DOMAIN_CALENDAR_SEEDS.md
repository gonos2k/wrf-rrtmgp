# UDM27 daily-fixed McICA seed contract

Option 37 now uses a pure function of `(domain_id, global_i, global_j, current_year, current_day_of_year, phase)`. Phase is 1 for LW and 2 for SW. `module_first_rk_step_part1` supplies year and day from the current WRF domain clock, rather than the run's initial year or `INT(julian)`. The radiation driver forwards the same identity to the production and diagnostic wrapper calls.

The policy remains fixed during each calendar day. No radiation-call counter, elapsed step, MPI rank, tile number, packing order, or restart counter participates. Domain and year now participate, so selected nested-domain and repeated-year keys have different streams. A finite 31-bit seed cannot guarantee globally unique keys or independent Monte Carlo samples. Adding these identity fields changes option-37 stochastic realizations; it does not establish lower sampling variance or forecast accuracy.

## Arithmetic and input contract

For each of the six integer fields in the stated order, starting from `state=1`, use signed int64 arithmetic:

```text
state = 1 + ((state * 48271 + field) modulo 2147483646)
```

The result is a default INTEGER in `[1, 2147483646]`. Products are safely within signed int64 even for maximum default-INTEGER input fields. Invalid nonpositive domain/grid/year, a day outside 1–366, or a phase other than 1/2 returns -1; the actual 37 wrapper rejects that result. Calendar validity is supplied by WRF's clock. The independent capture validator checks Gregorian dates for the documented SCM fixtures.

Required identity arguments are checked at 37 wrapper entry. Legacy RRTMG4 seeds and its original computation remain unchanged. An explicit diagnostic `mcica_seed_override` continues to replace the operational seed; this supports paired-seed audits and does not modify the daily policy.

## Capture and independent checks

The raw capture records `MCICA_DOMAIN_ID`, `MCICA_YEAR`, `MCICA_DAY`, `MCICA_POLICY_ID=1`, and `MCICA_SEED_OVERRIDE=0/1`. The sibling replay input header retains the exact INTEGER seed. Metadata scalars use the existing default-REAL trace API and are intended for normal WRF domain/calendar values, not arbitrary maximum integers.

`test_domain_seed.f90` compiles the actual helper and checks independently computed fixed vectors, traversal/partition invariance, selected key changes, invalid inputs, and maximum default-INTEGER inputs. These partition fixtures establish the pure function's contract, not an actual MPI/nested forecast result.

`test_domain_seed_capture.py` reconstructs the hash in Python without calling the Fortran helper. It checks the captured global indices and phase against an externally supplied domain ID and first-call history time. Custom overrides are reported separately, not falsely asserted to satisfy the operational hash. CI applies it to actual control and mixed UDM SCM captures.

```bash
python3 WRF/test/rrtmgp/test_domain_seed_capture.py build/udm-scm/mixed/ra37-call1/capture \
  --expected-domain-id 1 --expected-time 1999-10-22_19:00:00 \
  --output build/udm-scm/mixed/domain-calendar-seeds.json
```

Runtime results and binary/source provenance are recorded in [validation evidence](../../../validation/rrtmgp37/domain-calendar-seeds/README.md). The current GNU serial 37/37 executable passed control, mixed and calendar-boundary restart tests: 13 history times × 210 variables were bitwise equal in each case. A supplemental capture from the 37-generated midnight checkpoint independently confirmed LW year=2000/day=1; SW was inactive at that midnight. The daytime control confirmed both phase keys for year=1999/day=295. These short fixtures do not validate real-weather accuracy.

## Remaining temporal and physical questions

A calendar-day boundary still changes the sample abruptly. Daily-fixed, per-call and time-correlated samples require separate variance/autocorrelation experiments before choosing a different temporal policy. This change preserves the current fixed-day choice. It does not change cloud fraction, condensate paths, optical models, coefficient files, or supported hydrometeor categories. Actual MPI/OpenMP/nest and date-boundary runtime claims require their own tested executable; prior runtime receipts remain tied to their original binaries.
