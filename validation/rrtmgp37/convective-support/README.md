# Same-support convection and a fixed real-data evaluation

This package completes the PR191 precipitation-support comparison and evaluates
the fixed Matthew configuration over the period declared in [plan.json](plan.json).
It preserves the completed specified-boundary and original 05:59 restart work.
There are no production-source, default-policy, coefficient, guard, number,
radius, or time-step changes. This is one real-data case, not multiple independent
meteorological cases.

**The preregistered 24 hours completed:** 1,440 steps, 25 initial/hourly/final
history records, and 144 actual LW calls. All 225 arrays at the available
original 06:00 overlap remain byte identical. There are no nonfinite numeric
elements in the hourly history inventory. **The water comparison residual and
negative vapor samples remain; this is not a physical-acceptance PASS.**

| Whole-period water term | kg/m² |
|---|---:|
| Atmospheric stock change | −0.1352341123 |
| Full-domain RAINC + RAINNC increase | +8.6048898278 |
| QFX on the actual interior source support | +5.0336721871 |
| Applied advection operator | +2.3218588215 |
| Relaxation contribution | +0.7580892615 |
| Specified tendency | −0.0805370234 |
| **Stock/surface/boundary comparison residual** | **+0.4365723682** |
| PBL − actual-support QFX | −0.0786189331 |
| CU + full-domain RAINC | +0.5157145824 |
| CU + interior RAINC | +0.4931971795 |
| Outer RAINC retained separately | +0.0225174029 |
| Active paired CU contribution | +0.0776234769 |
| Inactive positive-rain contribution | +0.4109073877 |
| CU tendency without positive rain | +0.0046654862 |
| Microphysics + its RAINNC | +0.0014394094 |

Native arithmetic, mixing, final MU/q assignments and the small rate/counter
differences are retained in the full result. Reconstruction residual magnitude
is at most `1.43e-19 kg/m²/step`; that is the measured-operator identity, not a
conservation error bound. There is no rainfall-counter change outside the
corresponding observed CU/microphysics calls. All 1,151 off-schedule CU checks
retain exactly the prior post-expiry inactive-rain rate.

The 25 hourly states contain **193 negative QVAPOR time–cell samples**, all in
the interior support. The minimum is `−3.5453544456e−7 kg/kg` at **12:00,
(i,j,k)=(88,98,22)** (one-based native physical indices). Its negative water
magnitude over that hourly state is `9.56905e−9 kg/m²`; this is not a time
integral. All seven moisture species are summed with their actual signed
values; none is clipped for the budget. Condensate/number hourly samples are
nonnegative. Small negative vapor also exists at the original byte-identical
06:00 overlap. The new 12:00 witness is preserved for targeted investigation;
its originating operation is not identified or assigned to RRTMGP here.

Actual interior radiation-equivalent source integrated over the day is
`−9.9447943577 MJ/m²`; the separately integrated raw interior source is
`−9.9447943577 MJ/m²` (unrounded difference `3.38e−5 J/m²`). This is not
whole-energy closure. LW native flux is observed for 86,400 seconds. SW has
48,600 observed-phase seconds, including 13,800 seconds with incomplete
sunlit-column coverage, and 37,800 seconds without a current-phase flux
observation; these missing/partial contributions are not silently filled.

Hold-weighted supplied LW frozen paths put **15.8586% of graupel and 55.6733%
of hail** in ambient layers warmer than 273.15 K. Endpoint-20,000 fractions are
0.192015% and 0.0161685%, respectively. Supplied outside-table path is zero;
this says nothing about the pre-limit PSD. Largest path calls are source 7,800 s
(graupel) and 3,000 s (hail). These actual large/warm-path states are useful
targets for independent melting/optical applicability work, without regenerating
the entire table. Their optical accuracy remains unapproved.

The terminal outcome, hourly water/source ledgers, frozen input exposure and
decisions are in [result.json](result.json). The saved verifier replays reductions;
`new_model_runs=0` describes that replay, not the actual development execution.

## What the existing fields establish

The original corrected continuous history is pinned by its full-file SHA256.
`extract_spatial.py` decodes its actual 05:59–06:02 RAINC, RAINNC and RAINSH
fields and map areas into a small portable binary. These are not reconstructed
from scalar means. The three 06:00–06:02 precipitation arrays are also bound to
PR189's per-array inventory; 05:59 is covered by the original whole-file pin.
Saved CI reads this extraction, not the large original NetCDF again.

Every term uses the same whole physical-domain area, including the interior and
outer contributions. Physical columns are 90 by 99; the applied CU tendency
excludes the outer row, leaving 88 by 97. Halo cells are excluded.

| Source second | Outer RAINC contribution | CU + interior RAINC |
|---:|---:|---:|
| 21,540 | 0.000005428943 | 0.000061925631 |
| 21,600 | 0.000005428943 | 0.000202362297 |
| 21,660 | 0.000005428943 | 0.000343405410 |

Units are kg/m² per 60 seconds, normalized by the whole area. Outer precipitation
is preserved separately, not removed from the whole-domain ledger. It explains
only part of PR191's CU comparison residual.

PR191's pre-microphysics counter used native REAL32 `RAINC+RAINNC` before a
double reduction. Subtracting separately reduced RAINC fields is slightly
different. The original pre/during-microphysics counters are reproduced from
the saved fields with that actual REAL32 sum. Its small signed evaluation
difference is retained separately from outer rainfall and physical residuals.
RAINSH is zero in these existing fields; it is measured throughout the new run
as well. RAINNC is the grid-scale precipitation counter; frozen subsets are not
added to it again.

## The narrowed time contract is measured in the sustained run

The active configuration is `cu_physics=1` (KFETASCHEME), `cudt=5` minutes,
`dt=60` seconds. The relevant current sources are:

* [`advance_ppt` and `add_a2a`](../../../WRF/phys/module_physics_addtendc.F):
  full-tile rainfall accumulation, interior tendency application, and NCA expiry.
* [Cumulus driver](../../../WRF/phys/module_cumulus_driver.F): scheduled calls
  and retained precipitation on intervening steps.
* [KF Eta scheme](../../../WRF/phys/module_cu_kfeta.F): active NCA selection and
  resetting precipitation when a column is recomputed.
* [Registry](../../../WRF/Registry/Registry.EM_COMMON): package-number mapping.

For the same pre-call expiry cohort, the observer records the five actual water
tendencies before/after `advance_ppt`, NCA and PRATEC. Native expiry zeros those
tendencies while leaving the selected positive PRATEC unchanged. The driver
does not recompute CU on every 60-second step. The next off-schedule step can
therefore accumulate precipitation with all five CU water tendencies zero.

| Source second | Active paired contribution | Inactive positive rain | Tendency without positive rain |
|---:|---:|---:|---:|
| 21,540 | 0.000059145545 | 0 | 0.000002779733 |
| 21,600 | 0.000057734886 | 0.000141847187 | 0.000002779734 |
| 21,660 | 0.000056235993 | 0.000284389176 | 0.000002779732 |

Units/support are identical to the first table. Counter accumulation and native
tendency-addition arithmetic are additional signed terms in the saved identity.
In particular, the third column is not relabeled as rounding. Expired-column
observations predict the next off-schedule inactive-rain contribution directly.

This resolves the support/time attribution question. It does not establish the
correctness of the common CU process or its mass normalization. Remaining active
paired and tendency-without-positive-rain terms stay visible. No PRATEC clearing,
empirical multiplier, CU/PBL change, or RRTMGP adapter correction is introduced.

## Fixed-period execution and accounting

The cold real-data evaluation is 2016-10-06 00:00 through 2016-10-07 00:00,
preregistered before execution. It uses the original real initial/boundary fields,
not the manufactured nonzero NC/NR branch:

```
single domain / serial / one tile
UDM27 / LW37 / SW37 / number1 / population0 / scalar_adv_opt0
capacity0 / liquid-size0 / existing experimental frozen1 and fixed table
dt60s / radiation600s / CU300s / SWINT_OPT0
```

Only the declared duration, hourly history schedule and restart-output interval
change from the original corrected continuous namelist. No new restart campaign
is run. At the common 06:00 output, all 225 arrays are compared with the original
corrected trajectory. That overlap is an observer/output-schedule check; the
earlier 675/675 restart result remains the PR189 result.

The water ledger uses seven species and the same native dry mass and map area as
PR191. Final applied PD/RK tendencies are counted once, with actual increments
and evaluation bridges reported separately. Advection is the applied final-RK
operator; it is not an independently reconstructed lateral face flux.

For positive atmospheric inputs, the stock/surface/boundary comparison is

```
ΔW − E + P − advection − relaxation − specified tendency − final MU − final q.
```

It retains all outer precipitation, boundary forcing and final assignments.
The operator reconstruction additionally includes PBL, CU, microphysics,
mixing, source changes and native arithmetic. A zero reconstruction residual is
an accounting identity, not an independent water-conservation PASS. Hourly
NetCDF stocks and the step-reduction stocks are compared separately.

### Radiation coverage

Actual `phy_ra_ten` increments are measured each step. Their radiation-only
linear component in the consumed moist-theta RK RHS is preserved using the
declared native conversion. This is an equivalent dry-mass heat source, not a
measured radiation-only acoustic state increment or a whole-energy budget.

Hourly summaries distinguish whole/native-interior areas, native top/extended
TOA, pressure-mass heating, dry-mass heating and the actual applied interior
source. With `SWINT_OPT=0`, call values are integrated over their held intervals.
This does not turn call-level fluxes into independently measured state energy.

LW observations cover all 8,910 columns. The SW column callback covers sunlit
columns only; dawn/dusk can have incomplete spatial coverage. These values are
observed-column contributions normalized by the whole domain, with column
counts and incomplete-spatial seconds retained. When no current-phase SW call
is observed, native SW flux is **unavailable**, not filled with zero or a stale
daytime value. The actual all-sky host source remains recorded. Thus the package
does not claim complete whole-domain native SW flux closure at every step.

### Frozen input scope

Actual supplied LW graupel/hail paths, lambda and ambient layer temperature are
recorded at every observed call. Summaries retain endpoint-20,000 path fractions,
above-273.15 K ambient-layer path fractions, outside-table paths and the largest
path calls. Hold-weighted path exposure is a numerical sampling diagnostic,
not actual particle residence time, pre-limit PSD recovery or an optical error.

The original experimental homogeneous ice-Ih sphere/exponential-PSD table,
static refractive index, graupel/hail densities and precipitation occurrence
assumptions remain. Warm ambient layers containing frozen species are not
automatically illegal; their melting/optical applicability needs independent
evidence. No whole-table Mie regeneration or scientific frozen approval is
implied by staying within the supplied table range.

## Evidence and reproduction

Development executed two private incremental builds: 12 Fortran compilations,
two archive replacements and two links. The first build was not executed; its
observer cohort/initial-exposure bookkeeping was corrected before the qualified
run. The final build executes one cold model process. No new RTE/Mie/column
campaign, guard bypass, time-step retry or production-source edit is involved.

The deterministic archive includes raw reductions, final stdout/stderr and
receipts, generated private sources, actual namelists, original precipitation
extraction, locally decoded hourly history inventory and coefficient pins.
Original numerical source statements and native continued IF/CALL constructs
must remain unchanged. Four optical files are hashed during and after the run;
these are not described as pre-run hashes. The actual frozen-table hash is
checked against the retained fixed table.

On an environment with the original local build/input artifacts, reproduce with
`extract_spatial.py`, `build.py`, `run.py`, `analyze_run.py`, `read_history.py`,
`capture_coefficients.py --stage during` while the model is running,
`capture_coefficients.py --stage after` at its terminal outcome, `deposit.py`,
then `verify_saved.py --write`. Build/run directories deliberately
refuse overwrite, and a stopped period is preserved rather than retried or
promoted to a completed day. Saved replay needs only Python's standard library:

```sh
python3 -I -S validation/rrtmgp37/convective-support/verify_saved.py
python3 -I -S validation/rrtmgp37/convective-support/test_saved.py
```

Local validation: **34 full acceptance tests and seven new semantic tests
passed**, including the portable terminal replay; acceptance-index integrity
also passed. These saved-evidence checks execute zero new models. The actual
cold run took 1,926.35 wall-clock seconds and completed without a fatal/guard
stop. That duration is recorded execution metadata, not a performance benchmark.

The seven existing closure conditions and historical RFMIP/LBL failures are
unchanged. Purpose-specific tolerances, observations, independent lateral face
fluxes, whole-energy closure and frozen optical accuracy are not supplied by
this package. Completed engineering work stays completed; these scientific
limits are preserved separately in the terminal result.
