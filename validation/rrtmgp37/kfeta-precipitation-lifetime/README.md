# KF Eta precipitation lifetime

This is a common WRF KFETASCHEME correction, not an RRTMGP adapter, UDM number,
coefficient or policy change. The production change is confined to
`module_physics_addtendc.F:advance_ppt`.

For KF Eta only, each completed interval explicitly refreshes `RAINCV=DT*PRATEC`.
The same interval is accumulated in RAINC/RAINSH/CUPPT as before. At the existing
NCA expiry event, PRATEC is then zeroed along with the already-expiring thermal
and five moisture tendencies. RAINCV is deliberately retained: the next
`first_rk_step_part1` calls surface physics before the CU driver, and
`module_surface_driver.F` consumes that previous interval into RAINBL. The next
completed inactive interval refreshes RAINCV to zero. Clearing both variables
at expiry would discard the final valid surface delivery.

The expiry criterion remains the existing NCA rule; a vertically summed moisture
tendency is never used to decide activity. A normal CU call can initialize a new
rate and interval. MSKF and KFCUP retain their previous behavior despite sharing
the CASE branch. No accumulated rainfall is retrospectively corrected.

## Actual checks

`native.f90` calls the public `advance_ppt` through original and corrected public
libraries. Five intervals cover activity, the last valid interval, inactivity,
reactivation input and the following inactive interval. All source/array state
is retained in the binary outputs. KF Eta accumulates 30 mm for the first two
intervals in both arms; the corrected third interval adds zero. The reactivated
interval adds 30 mm and the next adds zero. RAINCV delivers the last valid 15 mm
and the reactivated 30 mm on their subsequent surface steps. The fixture starts
with a declared 15 mm previous interval, included in its surface total. MSKF and
KFCUP whole fixture byte streams are identical before/after.

The native fixture's surface accumulator reproduces the source ordering; it is
not a standalone call of the full surface driver. Actual host evidence adds a
bounded 05:59–06:06 integration from the original checkpoint and real forcing.
The read-only probe checks exact per-cell native accumulation, interval refresh,
expired-rate clearing and unchanged nonexpired rates. Its next-physics input is
exactly the previous completed interval. Positive expirations and the scheduled
06:04 reactivation are recorded. This input is the unchanged INTENT(IN) RAINCV
argument passed to the actual surface driver before the CU driver executes.

Observer OFF/ON histories are byte identical for 225 arrays at seven times:
**1,575 pairs**. This is observer noninterference on the candidate, not a new
cold-versus-restart proof. Restarting two copies of the same checkpoint is not
used as a replacement for that proof. Earlier MU-halo restart evidence remains
scoped and completed.

## Evidence and limits

`result.json` is reproduced from native raw output, binary state, actual host
probe and decoded history inventory by `verify_saved.py`. The deterministic
archive includes commands, receipts, generated observer and namelists. Build
and runtime executable hashes are bound; the diagnostic retains all numerical
solve statements. The large host histories were read locally and are represented
by file/array hashes, not replayed as raw NetCDF in CI.

The correction changes a common production source. PR191/PR192 evidence is
therefore verified against its exact retained source snapshot and explicitly
reports `current_runtime_source_matches=false`, rather than being retagged as a
corrected forecast. Their numerical results and historical residuals do not
change. Existing seven closure conditions and independent reference failures
remain. No old incorrect cold trajectory is required to match the corrected one.

This first correction does not fix negative vapor or approve physical water
conservation, frozen optical accuracy or forecast skill. A corrected full-day
comparison is deferred until the separate vapor operation has been assessed;
the old +0.4365723682 residual is not replaced by scalar subtraction. Old
checkpoints that already contain stale NCA<=0 rates are not silently rewritten;
normal driver recomputation establishes new activity. No new policy or guard
bypass is introduced.

Reproduce locally with `build.py`, `build_probe.py`, `run_host.py`,
`read_host.py`, `deposit.py`, then `verify_saved.py --write`. These builders
require the existing pinned public library/input artifacts and refuse overwrite.
Portable replay needs only Python's standard library:

```
python3 -I -S validation/rrtmgp37/kfeta-precipitation-lifetime/verify_saved.py
python3 -I -S validation/rrtmgp37/kfeta-precipitation-lifetime/test_saved.py
```

Local validation passed all **35 acceptance tests and five new semantic
counterexamples**, plus acceptance-index integrity. Actual execution was one
public incremental compilation/link, two native fixture arms (30 routine calls),
one private observer build and two 420-second host arms. Saved CI executes zero
models; these are not independent weather cases or a new full-day forecast.
