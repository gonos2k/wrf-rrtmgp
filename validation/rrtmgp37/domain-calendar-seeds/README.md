# UDM27 domain/calendar seed validation

Tested on parent `0b01547cc36e4b604c16e73839ec728a0a1c8586` plus the PR16 sources listed in [provenance.json](provenance.json). GNU serial `em_scm_xy` WRF executable SHA256: `c52e08b0d88ab7bb267bbf9846b0654c27fc76607e5a44bf9132cc6029aa594a`. The fresh standalone build passed 67/67 CTest tests. The seed key and bounded int64 recurrence are specified in [the contract](../../../WRF/doc/rrtmgp/DOMAIN_CALENDAR_SEEDS.md).

## Actual SCM and independent seed oracle

The first-call control and mixed captures use domain 1, current year 1999 and day 295. Both actual headers match the independent Python oracle: LW 679102813 and SW 679102814. Call2 confirms the same daily key. Four mutations of actual captures (domain, year, day and header seed) were rejected. All 24 production captures from the eight-seed diagnostic audit also passed the key oracle; their override flag is 0. The separate synthetic override receipt exercises validator behavior only and is not a captured runtime override.

Frozen pre-seed RRTMG4 control/mixed histories and the new executable's RRTMG4 histories each matched across 208 arrays bitwise, with identical initial input hashes. Repeated RRTMGP37 histories matched across 210 arrays in each case. Audit OFF/ON also matched all 210 arrays; independent replay passed for all 24 captured columns. [SCM summary](scm-summary.json), [audit summary](physics-audit-summary.json), [audit seed validation](physics-audit-seed-validation.json), and [corruption probes](rejection-probes.json) preserve those scopes.

The old/new first-call replay text is exactly equal after removing only its INTEGER seed. All 77 pre-existing raw fields are exactly equal. Clear-sky output sections are unchanged. In mixed-cloud output, the changed samples alter LW flux by up to 8.9793 W/m² and SW flux by up to 2.4433 W/m² across the tested interfaces; these are single-realization differences, not accuracy or ensemble-mean changes. [The comparison](first-call-seed-only-comparison.json) records each output section and units. Its [runner](compare_seed_change.py) accepts explicit before/after SCM roots.

## Actual 37/37 restart and calendar boundary

The final runner explicitly selects `mp_physics=27`, `ra_lw_physics=37`, `ra_sw_physics=37`, `use_mp_re=1` and verifies the actual NetCDF physics attributes for every history and checkpoint. Control, mixed and a date-retimed clear fixture run for 120 seconds at 10-second steps with `radt=0.5` minutes. Continuous and 60+60-second split runs match bitwise over all 13 common timestamps × 210 variables per case; 201 checkpoint variables also match. L-infinity and L2 differences are zero. Every invocation recorded the same executable hash before and after execution.

The calendar fixture crosses 1999-12-31 23:59 through 2000-01-01 00:01, resuming from an actual 37-generated midnight checkpoint. It retimes only date metadata and forcing timestamps while checking the unchanged state payload. This is a calendar/restart test, not a meteorologically valid new case. A supplemental resumed LW capture independently confirms year=2000/day=1 and seed=847516934. SW is inactive at midnight and has no captured midnight seed. Daytime LW/SW captures confirm year=1999/day=295. [Restart receipt](restart-receipt.json), [comparison summary](restart-comparison-summary.json) and [calendar capture receipt](calendar-capture-receipt.json) retain the exact run and source hashes. The runner also rejects a manufactured wrong-mode test using an actual 4/4 history ([probe](wrong-mode-rejection.json)).

## Fresh restart diagnostic preservation

A separate January 2000 real-data campaign validates persistence of the three
last-call cloud diagnostics across short and long UDM37 restarts. The six-arm
primary run passes its scoped raw/decoded array checks, with strict invocation
metadata failures retained; an old-checkpoint compatibility run separately
validates the unavailable sentinel. See the [campaign report](fresh-restart/README.md)
and its [pinned summary](fresh-restart/summary.json). The previous PR54 CI run
had a serial-SCM restart timestamp failure; the validation-only fix has been
committed and its CI rerun is pending. This is separate from the local real-data
campaign and is not reported as green here.

Reproduce from a built checkout with fresh paired SCM initial states:

```bash
python3 validation/rrtmgp37/domain-calendar-seeds/run_restart_determinism.py \
  --repo . --baseline-root build/udm-scm \
  --output-root build/domain-seed-restart --calendar-boundary
python3 validation/rrtmgp37/domain-calendar-seeds/capture_calendar_seed.py \
  --repo . --restart-root build/domain-seed-restart \
  --output-root build/domain-seed-year-capture
```

Both commands refuse existing output roots. CI runs these against its newly built executable and actual UDM SCM states. Full local history, restart and comparison files remain under the provenance artifact root; receipt hashes identify them. The publication manifest hashes the shipped evidence and reusable runners.

## Limits

Daily-fixed sampling is retained; the change adds domain/year/current-day identity and changes 37's stochastic realization. It does not prove sample independence, reduce temporal variance, validate MPI/nest decomposition, or change cloud fraction/optical models. Prior MPI/OpenMP receipts remain tied to their original binaries. Graupel/hail optics, effective-size conventions, occurrence fractions, long forecasts and observation validation remain separate work.
