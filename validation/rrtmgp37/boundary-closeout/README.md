# Specified-boundary closeout: actual source and final operands

The two remaining small boundary checks are complete in this scope. Actual
NC/NR host relaxation adds a positive tendency despite zero later history
samples in the selected relaxation strip. The final prescribed-value/history
last-bit difference is reproduced exactly using the different mass operands
actually consumed. Common native MU halo properties pass for number0/number1
and four sequential tile decompositions/orders. **Production source, policy
values and coefficients are unchanged.**

PR189's original 05:59 continuous/restart result remains **675/675 byte equal**.
This package does not repeat that six-hour restart or the 45-level WW replay.
The new 675-pair comparison below measures observer noninterference in the
existing nonzero branch, not another restart test or an independent weather case.

## Actual bounded host observation

`run_host.py` reuses PR189's exact nonzero forcing, 05:59 checkpoint and namelist.
One private observer executable integrates the same three 60-second steps to
06:02. The reference is the original public PR189 nonzero branch output, not a
second restart. Every variable/time array is decoded locally with masking off:
**225 arrays × 3 times = 675 pairs byte identical**. Checkpoint, forcing and
namelist SHA-256 values equal the preserved PR189 receipts.

The private module and solve copies add context setters and read-only records
around the actual NC/NR `relax_bdy_scalar` calls and within its native
`relax_bdytend_core`. Native numerical assignments remain verbatim. The exact
private sources are reconstructed from current public sources by `instrument.py`
and checked against compiled copies. No source setter, array replacement, new
physical option or coefficient is added to production.

The selected source point is Fortran **i=24, k=1, j=2** (southern relaxation row).
At source time 21,600 s, actual boundary interpolation uses `dtbc=60 s`:
The source label is the solver step-start clock; `dtbc` is captured from the
actual call rather than inferred from that label. The finalization trace has
`rk=4` because the three-step RK loop has exited; this is not a fourth RK step.


| Actual call | S target | S model | Tend before | Tend after/increment |
|---|---:|---:|---:|---:|
| NC | 265014592 | 0 | 0 | 441687.46875 |
| NR | 265014.625 | 0 | 0 | 441.6875915527344 |

S is the native pressure-coupled number (Pa kg_dry^-1); tendencies have the
additional s^-1. These are **not** volume concentrations or integrated number
amounts. The five actual `fls` operands, FCX/GCX, incoming/outgoing tendencies
and wrapper/core correspondence are preserved as IEEE binary32 words. Replaying
native REAL32 operation order reproduces all six relaxation outputs exactly
(two species at three times); four calls have positive increments. At source
21,660 s the incoming tendency is already nonzero, so only after-minus-before
is attributed to relaxation. The zero first endpoint produces zero source.

The later selected relaxation-strip history values remain zero, as in PR189.
That does not erase the observed positive source. This package does not trace
which subsequent transport/microphysics/limiting operation produces those zero
outputs, nor declare a new conservation defect from that observation.

## Exact explanation of the final last bits

The prescribed-value point is **i=24, k=1, j=1**, a different row from the source
point. `spec_bdy_final` actually evaluates:

```
bfield = boundary_value + dtbc * boundary_tendency
xmu    = C1H * MUTS + C2H
eta    = xmsf * bfield / xmu       (xmsf = 1 for NC/NR)
```

The actual caller still passes native `MUTS`; history reconstruction instead
uses its final `MU_2 + MUB`. The recorded physical MU and coefficients agree
between the final call and history, but `MUTS` and the reconstructed sum differ.
For output 06:01:

| Operand/result | Native call | History-based reconstruction |
|---|---:|---:|
| Total MU input, Pa | 95388.828125 (`47ba4e6a`) | 95388.8125 (`47ba4e68`) |
| C1H * total MU + C2H, Pa | 95394.0625 (`47ba5108`) | 95394.046875 (`47ba5106`) |
| Final NC word | `452d9f29` | `452d9f2b` |

Both results reproduce exactly from their own inputs, including interpolation
and division. All six native final outputs equal the actual history bits.
The code sequence finalizes MU separately and passes the native working total
`MUTS` to scalar finalization; it does not recompute that operand from history.
Thus the separate history formula was not using the actual native call inputs.
No fitted tolerance, rounding, mass adjustment or production change is needed
to explain these results. This does not approve complete number/water/energy
conservation or every thermodynamic interpretation of the host coupling.

## Common MU halo regression

`common_halo.f90` links the retained **public corrected PR189 library**, rather
than the private observer. It initializes a manufactured 12×10 physical field,
leaves stale halo sentinels, sets final nonuniform physical edge values and calls
current native `set_physical_bc2d(...,'t',...)` with `specified=true`.

For both number0 and number1 it checks:

- every physical MU cell remains byte unchanged;
- all three physical halo rows/columns, including corners, equal the newest
  nearest physical edge;
- a repeated whole-domain call is byte idempotent;
- four-tile forward/reverse, two x-tiles and two y-tiles agree byte for byte with
  one whole-domain call after all physical edge updates are complete.

All **8 policy/method combinations** pass. These are direct common-native
function/property tests with sequential tile calls. They are not a full-host
number0 integration, a threaded race test, MPI process-decomposition proof or
new number1 parallel support. Existing number1 serial/one-tile guards remain.
The PR189 solve call stays after the preceding tile loop's barrier; no new
synchronization or halo algorithm is introduced.

## Fixed baseline and next evaluation

Base main is `553df58f4f0cb8c48f9cdb68843094bb9433d0c4`, tree
`f6ffe201b3bd33479fa3a79155d2ef9d967d4d64`. The real research baseline remains
single-domain serial UDM27/LW37/SW37, number1/population0, scalar_adv_opt0,
capacity0/size0, dt60/radiation600, experimental frozen1 with unchanged table
SHA-256 `ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a`.
The nonzero branch is a declared manufactured forcing perturbation, distinct
from the baseline real forcing. Source, coefficient and original closure-file
hashes are pinned in `identity.json`.

These results close the bounded boundary checks. Subsequent real-case water
budgets must include lateral net inflow, and radiation budgets must distinguish
native top, extended TOA and actual source application. The existing six-hour
outputs can be inventoried before choosing additional duration/diagnostics.
This package adds no new long forecast, water/energy acceptance claim, frozen
optical validation, Mie campaign, seven-condition replacement or reference PASS.
All original scientific limitations and RFMIP/LBLRTM FAILs remain.

## Reproduction and saved CI

Actual new work: **one successful bounded WRF process**, one native halo process,
three private observer compiles plus archive replacement/link, and one native
fixture compile/link. The build is incremental from the retained general PR189
library and exact flags; it is not a fresh full-WRF build. Commands, source
copies, trace words, full history hash inventory and local raw-file pins are
preserved. No failed model attempts are excluded from these counts.

```sh
python3 -I -S validation/rrtmgp37/boundary-closeout/verify_saved.py
python3 -I -S validation/rrtmgp37/boundary-closeout/test_saved.py
```

The stdlib verifier checks bounded saved evidence and current source identity.
It does not decode the large raw NetCDF histories again or run a compiler/model:
`new_model_runs=0`. Six semantic counterexamples reject a zeroed source, stale
time interpolation, substituted history mass factor, changed observer array,
omitted number0 coverage and removed physical-preservation assertion. This is
one added regression package within the existing acceptance suite, not a new
scientific gate.
