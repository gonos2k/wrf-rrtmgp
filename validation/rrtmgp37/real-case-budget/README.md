# Actual Matthew water operators and radiation-source evaluation

This package evaluates the **unchanged PR190/PR189 real-data baseline**, rather
than adding another boundary/restart feature. It reads the available six-hour
state/surface inventory, then measures missing operators during **2016-10-06
05:59--06:02**. Production WRF/UDM/RTE sources, defaults, coefficients and the
seven original closure conditions are unchanged. PR189's original restart PASS
remains complete; this package does not repeat its six-hour restart campaign.

The result is `BOUNDED_REAL_CASE_BUDGET_EVALUATED`. **Water conservation, whole
energy conservation, frozen optical accuracy and forecast skill are not
approved.** A zero operator-reconstruction residual below is an accounting
identity using actual transitions, not an independent physical conservation test.

## Fixed input and measurement boundary

- One domain, serial, one tile; UDM27/LW37/SW37, number1/population0,
  scalar_adv_opt0, capacity0/liquid-size0, dt60 s, radiation interval600 s.
- Existing experimental frozen1 and the pinned expanded table
  (`ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a`).
- Original corrected 05:59 checkpoint, **original real boundary file**, original
  namelist. This is **not** PR189/190's manufactured nonzero forcing branch.
- Native physical mass domain 90x99x44, area 6.706117114499239e12 m2;
  no halo or duplicated staggered points.
- QVAPOR, QCLOUD, QRAIN, QICE, QSNOW, QGRAUP and QHAIL are all included.
  Number variables are not water mass.
- Diagnostic dry layer mass is
  `-(double(C1H)*double(fl32(MU+MUB))+double(C2H))*double(DNW)/double(g)`;
  horizontal area is double `DX*DY/(MSFTX*MSFTY)`. The actual native REAL32 sum
  is retained, with double reductions/products. This mass evaluation is stated
  explicitly; native division/product rounding remains visible separately.

`inventory.json` retains the actual initial stock and five late states. Total
water is 46.7841901410 kg/m2 at 00:00 and 46.5207939245 kg/m2 at 06:02. Initial
surface cumulative counters and six-hour boundary source history are unavailable
in those retained files. **No closed six-hour water residual is manufactured.**
The earlier `ACLHF/2501000` history diagnostic is preserved as a proxy, not an
exact evaporation source. Native WRF declares XLV=2500000, while actual QFX is
available for the bounded steps. Both ACLHF normalizations remain visible.

## Actual bounded water result

Every row is a 60 s physical interval; units are domain-mean kg/m2. Source label
21540 is 05:59, and its committed output is 06:00. NC/NR source values from PR190
are not reused as water sources.

| Interval | delta W | P | QFX on native PBL support | Advective operator | Relaxation | Specified tendency |
|---|---:|---:|---:|---:|---:|---:|
| 05:59--06:00 | -0.001607261 | 0.005931722 | 0.003244551 | +0.000708070 | +0.000392129 | -0.000035157 |
| 06:00--06:01 | -0.001468824 | 0.005934991 | 0.003244190 | +0.000708314 | +0.000402388 | -0.000044032 |
| 06:01--06:02 | -0.001319988 | 0.005937466 | 0.003243881 | +0.000709280 | +0.000411944 | -0.000044032 |

`Advective operator` integrates the **actual final-RK advection tendency on its
actual update region**. It is not a separately reconstructed velocity-times-water
lateral face flux. A physical face-flux audit, if needed, remains distinct from
this applied-operator ledger. Specified tendency is its change to the tendency
**after relaxation**, so the two do not double count each other. Actual final
MU and moisture overwrites are also recorded separately. The largest final
moisture overwrite is about -1.26e-8 kg/m2; the largest final-MU stock increment
is about +6.65e-10 kg/m2.

The actual native `add_a2a` physics support excludes the outer specified row.
The recorded full-domain QFX would additionally count about **9.87e-5 kg/m2 per
step on that unused row**. Both full and matched-support residuals are retained;
this domain choice is not a residual-fitted correction. Saved history QFX fields
are byte-bound to the observer inventory and their full reductions match the
actual call-time QFX reductions. P is RAINC+RAINNC; diagnostic frozen-precipitation
subsets are not added a second time.

Define R = deltaW - E + P - applied advection - relaxation - specified tendency
- final MU stock increment - final moisture overwrite. Its remaining terms are:

| Interval | R, matched QFX support | PBL return minus matched QFX | Cumulus plus its P | Microphysics plus its P |
|---|---:|---:|---:|---:|
| 05:59--06:00 | +1.48685e-5 | -5.16050e-5 | +6.73495e-5 | +1.89691e-7 |
| 06:00--06:01 | +1.55319e-4 | -5.16138e-5 | +2.07793e-4 | +1.84093e-7 |
| 06:01--06:02 | +2.96411e-4 | -5.15875e-5 | +3.48834e-4 | +1.83750e-7 |

Other physics/mixing is about -1.03 to -1.05e-6 kg/m2 per step. Actual PD/RK
arithmetic differences are of order 1e-8 kg/m2 or smaller. Independently observed
mass/state evaluation bridges are zero in this window. All these terms reproduce
the actual stock change at the saved domain reduction precision. The internal
arithmetic check uses64 ulps of the domain stock, not a physical mass tolerance. **They are not
new source corrections and are not defined by the final unexplained residual.**

The PBL and cumulus terms were measured around their actual host tendency-add
calls. Pre/post microphysics stocks and separate precipitation-counter intervals
were measured. These conditional source/sink mismatches need physical interpretation;
this result does not identify a new UDM or radiation production defect, justify
an empirical multiplier, or extrapolate a three-minute fraction to six hours.

Only the final RK update enters the physical-time ledger. The RK1 relaxation and
specified tendencies enter its actual final PD update once. Predictor snapshots
are not summed as independent 60 s changes. `pd_tendency`, actual PD pre/post,
RK base/after, actual advective tendency, split-physics, final MU and final q
are separate raw reductions. Native moisture IDs 2--8 correspond to the seven
listed species; all-species snapshots and PBL/CU groups use IDs1--7.

## Radiation result and its limit

The private wrapper records actual UP/DN and heating on the fresh LW call at
**21600 s**, all 8910 columns. It records native boundary45 separately from the
extended TOA. This is a nighttime window: no SW call occurs. Missing native
fluxes at the initial held step remain `null`, rather than being replaced by
history TOA fluxes or assumed zero.

| 06:00 fresh LW, W/m2 | Value |
|---|---:|
| Surface net downward | -47.889524272 |
| Native-top net downward | -242.840175097 |
| Extended-TOA net downward | -252.408575966 |
| Native full-column flux convergence | **-194.950650825** |
| Pressure-mass reconstructed heating | -194.950650602 |
| Native dry-mass weighted wrapper heating | -193.958326864 |
| Dry-mass host raw source, full domain | -193.958326652 |
| Native flux convergence, physics interior support | -186.018752359 |
| Actual host radiation addition, same interior support | **-185.073775688** |

The fresh wrapper's pressure-mass relation agrees at 2.22e-7 W/m2 in the domain
mean (maximum column residual4.51e-5 W/m2 with REAL32 wrapper outputs). The dry-mass
wrapper and raw host source agree to about2.12e-7 W/m2. **Capacity0's pressure-mass
heating and host dry-mass weighting are different contracts**; their difference
is not automatically a lost energy term. Neither the outer specified row nor the
upper extension is silently included in the applied interior source comparison.

Actual `phy_ra_ten` thermal-array additions are measured before/after; their
native mass coupling matches the raw interior source. Actual total thermal RHS
additions are also measured during each `rk_addtend_dry` call. The isolated
radiation component through the documented linear theta_m/map-factor conversion
is **inferred from the measured radiation addition**, not a separate radiation-only
forecast. The 06:00 component is -185.073775688 W/m2; the next held-step component
is -185.073748694 W/m2 using its actual state/Exner/mass. The 60 s RHS equivalents
are -11104.42654 and -11104.42492 J/m2, counted once, not three times.

**An isolated radiation-only acoustic prognostic state increment is not measured.**
These are flux/source assembly and RHS-consumption results, not closure of full
model energy or the total temperature change. Pressure work, kinetic/geopotential
energy, latent/precipitation energy, PBL/surface exchange and acoustic splitting
are not approved by this ledger.

## Actual frozen1 input exposure

The same fresh LW call records host-supplied positive graupel/hail inputs at the
actual call boundary. No additional optics campaign or component-removal run occurs.

| Species | Area-mean path kg/m2 | Positive native layers | lambda m^-1 | Temperature K |
|---|---:|---:|---|---|
| Graupel | 0.00184999949 |112230|1733.1493--20000|190.9532--279.6671|
| Hail |0.00030672849|111496|739.9125--20000|190.9532--285.3884|

No positive path in these supplied inputs is outside the table's declared
lambda300--20000 or T150--330 axes. This is **one actual call's exposure**, not
all six hours or a claim of physical accuracy. Homogeneous ice-Ih spheres,
exponential PSD, fixed material properties and independent grid-mean precipitation
occurrence remain experimental. Component contribution and independent frozen
optical accuracy are not calculated here. Actual important states are now
identified for a bounded subsequent physical comparison. Input lambda endpoints
do not reveal pre-limit PSD values or endpoint-use path fractions; these remain
unmeasured.

## Evidence, reproduction and execution counts

Run the saved checks (standard library only; no model execution):

```sh
python3 -I -S validation/rrtmgp37/real-case-budget/verify_saved.py
python3 -I -S validation/rrtmgp37/real-case-budget/test_saved.py
```

`inventory.py` reads retained NetCDF files, `build.py` makes a private incremental
observer, `run.py` performs the bounded original-forcing replay, `surface_domains.py`
reads only the available QFX fields, and `analyze.py` calculates the result.
The retained build/library/include paths are explicit in their receipts. This
reproduction requires those original local assets; portable CI replays saved
reductions and hash inventories instead. The archive pins generated sources,
compiler/link commands, return codes, exact inputs, raw reductions, original
reference hashes and all675 decoded observer/reference history pairs.

The compiled helper is preserved byte-for-byte in the archive; the checked-in
helper only trims trailing whitespace, which the verifier explicitly permits.
The final private transformation consists only of inserted observer calls/USEs.
All original numerical lines remain verbatim; no insertion may interrupt a native
continued IF/CALL. The probe has no INOUT prognostic argument. **Final observed
225arrays x3times are byte identical to the original corrected real baseline.**
That is observer noninterference, not another restart approval.

Actual new execution: **two bounded WRF processes**, each three steps. The first
qualified observation established the budget and source partitions needing finer
PBL/CU and matched-support detail; the second provides the final evidence. Each
matched675 history pairs; these are one meteorological window, not independent
cases. Development had five incremental private build attempts (one SW observer
symbol compile failure, two unused intermediate builds), **27successful Fortran
compiles and1failed compile,4archive replacements and4links**. The final build
uses six successful compiles, one archive replacement and one link. No full WRF
build, six-hour/24-hour campaign, Mie/WW/kernel campaign, production source edit,
policy/coefficient change or guard relaxation occurred. Development journals are
retained separately and are not promoted into final results.

Next useful decision: interpret the measured PBL/cumulus support and precipitation
contracts and the capacity0 pressure/dry-mass conversion for the intended use.
A longer real-data campaign should carry just these required diagnostics (and,
if full applied energy is the target, the missing acoustic source application).
Existing RFMIP/LBLRTM failures and all original scientific closure conditions
remain unchanged; no new top-level gate or accuracy percentage is introduced.
