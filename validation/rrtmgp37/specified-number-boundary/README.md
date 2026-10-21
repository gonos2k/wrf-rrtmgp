# Limited number1 specified-boundary implementation

The public general WRF path now accepts explicitly encoded dry cloud/rain
number at a single serial specified boundary. It consumes native mass-coupled
values and tendencies, treats the free CCN reservoir separately, and persists
the boundary contract through history/checkpoint I/O. The four production changes
are confined to `input_wrf.F`, `output_wrf.F`, `module_bc.F`, and `solve_em.F`.
Namelist defaults, UDM microphysics, radiation source, optical coefficients and
the existing seven closure conditions are unchanged.

**Full host bitwise restart remains unpassed.** All 225 visible arrays restored
exactly at the checkpoint, and the next boundary/radiation phases were retained,
but 23 of 675 subsequent time-variable array pairs differed. A number0 control
also had host restart differences. This does not identify their common arithmetic
cause or establish exact restart support. The original full validation criterion
is retained as false; no acceptance tolerance was fitted to the differences.

## Representation and supported path

The [user-facing contract](../../../WRF/test/rrtmgp/UDM_SPECIFIED_NUMBER.md) describes
the explicit producer and configuration. Cloud/rain boundary values are
`S=(C1H*(MU+MUB)+C2H)*eta`, where `eta=n/rho_d`; the file tendency is the
difference of stored coupled endpoints. The factor is native pressure coupling,
not layer mass in kg/m². Runtime interpolation is in stored S and then uncouples
with the current native factor. Volume number is not assumed linear in time.

The new route requires serial, one nonperiodic domain/tile,
number1/population0, moisture/scalar boundary fields, LW37/SW37 and
`scalar_adv_opt=0`; capacity/size research policies remain OFF. MPI/OpenMP,
nesting, specified population1/2 and specified research-radiation combinations
remain rejected. Every initial/boundary/restart file requires typed integer
`UDM_SPECIFIED_NUMBER_CONTRACT=1`. `real.exe` does not silently infer this contract.

NC/NR use native scalar relaxation, prescribed tendencies and final specified
values. File QNCCN is excluded from that operation: CCN inflow converts the
constant volume background using current inverse dry density, while outflow
retains zero-gradient eta. Interior generated number is not zeroed. This is a
distinct declared reservoir condition, not a conversion of zero file CCN.

## Actual calculations

| Check | Actual result |
|---|---|
| Exact-zero real producer | Original Matthew initial/boundary arrays preserved; all eight time records checked before tagging |
| Nonzero manufactured NetCDF | Explicit constant volume number, changing dry density and hybrid native mass factor; nonzero stored tendency |
| Public native kernels | Actual `relax_bdy_scalar`, `spec_bdy_scalar`, `spec_bdy_final`, `rk_update_scalar` and CCN inflow/outflow routines consumed the file payload |
| Current general executable | Four changed source objects rebuilt, library updated and executable linked; remaining objects inherited from the pinned serial general build |
| Real integration | 2016-10-06 00:00–06:02, dt=60 s, radiation interval=600 s, number1/population0 |
| Next forcing record | Correct second 6-hour record at and after 06:00; south MU residual exactly zero in saved samples |
| Stale-record counterexample | First-record extrapolation differs by 0.46258545 Pa at 06:01 and 0.92510986 Pa at 06:02 |
| Interior number | Final positive interior counts: NC 27,546; NR 42,692; CCN 313,280; outer prescribed NC/NR exactly zero |
| Default regression | Previous/current number0 executables: 225 arrays × 0/10/20 s byte-identical |
| Actual refusals | Six file/configuration cases rejected before success: missing/string initial contract, missing boundary/restart contract, missing scalar BCs and specified population2 |
| Scope probes | Current extracted input guard tested at O0/O2 and MPI/OpenMP preprocessor branches; these stubs are not NetCDF I/O tests |

The selected real input reaches about 192 K. The first mode0 attempt stopped on
the existing positive-hail optical refusal after model 1,200 s. That failure and
its logs remain saved. No hail was deleted and no guard disabled. Before the
replacement run, the plan addendum selected **existing experimental frozen
optics mode1** with the already available expanded table
`frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc`, SHA256
`ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a`.
The successful 6-hour trajectory therefore does not approve mode0 for this input,
or certify the experimental homogeneous-sphere ice optics or mixed-phase physics.

Five late history times were checked for finite, nonnegative hydrometeor mass
and number. This is not a full six-hour water/energy budget or physical accuracy
assessment. Existing optical clipping/coverage limitations are not erased.

## Restart result and open limitation

Checkpoint: 05:59 (21,540 s), between radiation calls and before the 06:00 boundary
record. Restart: 180 s, next radiation source time 21,600 s. Existing
`override_restart_timers=.true.` is retained with a 60-second history interval.

- An observer run with `write_hist_at_0h_rst=.true.` shows all 225 arrays identical
  to continuous output at 05:59. Its subsequent 675 array pairs equal the original
  restart, so the observer did not change the subsequent restart trajectory.
- At the first integrated output, W and PH differ by at most
  `7.450580596923828e-9` in their own units; QNC also has a subnormal difference.
  By 06:02 the largest W difference is about `4.39228e-4 m/s` and PH about
  `0.0297852 m²/s²`. All differing variable/time witnesses and hashes are retained.
- The number0 counterfactual, with its legacy BC flags, restores the same 225
  arrays exactly but has 49 differing pairs over 900 comparisons. First-step PH
  differs at the same north-boundary/relaxation location. This establishes that
  this kind of mismatch also occurs without new number1 boundaries; it does not
  establish that both have the same arithmetic cause.

`T`/THM differences are perturbation thermodynamic-variable differences, not
direct actual-air-temperature errors. No whole-host exact-restart or forecast
accuracy claim follows from these small initial differences. The first arithmetic
cause remains unlocalized.

## Reproduction and evidence limits

```bash
python validation/rrtmgp37/specified-number-boundary/test_producer.py
python -I -S validation/rrtmgp37/specified-number-boundary/verify_saved.py
python -I -S validation/rrtmgp37/specified-number-boundary/test_saved.py
python validation/rrtmgp37/acceptance/test_verify.py
```

`build.py`, `run.py`, `kernel.py`, `legacy_regression.py`, `refusals.py`,
`restart_probe.py`, `host_restart_control.py`, and `analyze_runtime.py` preserve
the actual commands and analysis; they require the pinned local build/data
dependencies and create new output directories rather than overwrite results.
The retained executable SHA256 is
`6fe57ae72ab2bc87a551b0c680d59009df8aab9a692fef5c49e12c6288b4f89e`.
It is an incremental public-source build, not a new clean whole-WRF build.

`identity.json` pins source bytes, executable/library receipts and saved payloads.
The large real NetCDF history/checkpoint files remain in local build storage and
are content-pinned in saved analysis. The committed package contains array-hash
inventories, difference witnesses, selected boundary slices, actual manufactured
NetCDF and command logs. Stdlib CI verifies those saved records and six semantic
counterexamples; it neither independently rereads the large histories nor runs
new WRF science. A replay PASS means the retained findings are internally
consistent, **including the retained restart failure**, not that the failed model
criterion passed.

There were 15 WRF processes: eight successful runs (including observers/default
controls), six expected contract/scope refusals, and one preserved physical-range
refusal. These are one real case and controls, not 15 independent weather cases.
Only native-kernel v4 and scope-probe v3 qualify against the current code; earlier
development journals are retained separately. Local producer tests number five;
saved semantic counterexamples number six. Saved replay adds zero model runs.

The pre-existing source-extraction transport fixture also ran at O0/O2 against
the changed boundary routine. Its minimal adapter now imports `ieee_is_finite`
and declares `udm_number_policy=0`; its original legacy arithmetic and boundary
assertions are unchanged. This adapter update is not a production source change
or a new WRF forecast. Registration hashes cover the current boundary sources.

Older PR evidence remains bound to its exact PR187 source snapshot; it is not
silently retagged as current-source validation. Existing RFMIP/LBLRTM FAILs and
`production_accepted=false` are preserved. No new spectroscopy, Mie, 1024-angle,
24-hour warm-column or 4/37 tuning campaign was performed here.
