# Specified-boundary restart: first arithmetic cause and minimal repair

The original PR188 05:59 restart now passes **all 675 time–variable pairs** at
06:00, 06:01 and 06:02, byte for byte. The checkpoint time, dt=60 s, forcing,
600 s radiation schedule, output precision, 225-variable inventory and frozen1
configuration are unchanged. The original 23/675 failure remains archived under
`specified-number-boundary`; it has not been rewritten as a pass.

## Actual first cause

The first newly computed divergence is in `rk_step_prep -> calc_ww_cp`, before
the first physics/radiation tendencies. In the continuous run, `set_phys_bc_dry_2`
fills the physical MU halo, then the final `spec_bdy_final` overwrites the
physical edge. The halo still contains the earlier value. Restart initialization
fills it from the final physical edge instead. Equal visible checkpoint arrays
therefore did not imply equal inputs to the next WW calculation.

The retained actual northern stencil gives these REAL32 witnesses (Fortran
indices; hexadecimal values are IEEE binary32 words):

| Operand/result | Continuous | Restart |
|---|---:|---:|
| MU(23,99), physical | 2048.972900390625 Pa | same |
| MU(23,100), halo | 2048.97265625 (`45000f90`) | 2048.972900390625 (`45000f91`) |
| MUB at both rows | 91994.109375 Pa | same |
| first `MU+MUB` sum | 94043.078125 (`47b7ad8a`) | 94043.0859375 (`47b7ad8b`) |
| local MUV used by WW | `47b7ad8a` | `47b7ad8b` |
| WW(23,2,99) | `bb5128a4` | `bb512892` |

All initialized physical U/V/W/T/PH/MU/MUB/P/AL/ALB/QV/NC/NR/CCN inputs in the
bounded entry stencil agree. Entry scratch/tendency buffers are recomputed and
are not promoted to causal first operations. The mass sum above is evaluated in
the native order `0.5*(MU(j)+MUB(j)+MU(j-1)+MUB(j-1))`.

`replay_first_ww.py` links the retained public native library and feeds it these
actual inputs. It reproduces the original continuous and restart WW profiles,
all 45 levels, exactly. A third arm calls the existing `set_physical_bc2d` on MU
before the same native WW calculation: all 45 levels then equal the restart
profile, while every physical MU cell in the fixture is unchanged. This causal
result comes from number1 itself; it is not inferred from the earlier confounded
number0 control.

## Production change

`WRF/dyn_em/solve_em.F` refreshes MU's physical halo with the existing native
boundary routine after the final specified-boundary tile loop has completed.
It uses the existing following `set_w_surface` tile pass, after the earlier
OpenMP barrier. No new state, arithmetic formula, policy or coefficient is
introduced. The guard is `config_flags%specified`: this is a common host halo
ordering correction, independent of the number option. Periodic paths skip it.
The scoped number1 boundary guards still reject MPI/OpenMP, nests and unsupported
policies. The scoped runtime evidence below is serial/one tile; it is not new
certification of all common-host parallel configurations.

The physical MU edge is not changed by the extra call. The corrected cold
trajectory can differ from the older stale-halo trajectory. Old/new cold-history
equality is consequently not claimed, and the older PR188 default-output
regression remains historical evidence. Policy defaults themselves are unchanged.

## Actual executions and results

| Check | Actual result |
|---|---|
| Private bounded observer vs original continuous run | 225 arrays × 5 times byte identical |
| Private observer vs original restart run | 225 arrays × 3 times byte identical |
| Original continuous/restart | 23 differing pairs of 675, preserved |
| Public corrected continuous/restart, original times | **0 differing pairs of 675** |
| Next six-hour forcing record | record 1 actually used; exact south MU reconstruction at retained outputs |
| Recomputed LW source after restart | 21,600 s in both runs; no SW LIQ event in this retained nighttime window |
| Prescribed original NC/NR edge | zero; positive interior number remains |

The corrected continuous run starts from the original 00:00 initial file. Its
05:59 checkpoint feeds the restart. Two restarts from one checkpoint were not
used as a substitute for a continuous reference. The observer also starts from
00:00 on the continuous arm, and reproduces the old failed trajectory without
changing its history. Large NetCDF files are kept in build storage and pinned by
byte length and SHA-256; `analyze_runtime.py` read their full arrays, without
masking, rounding, tolerance, variable exclusion or subnormal removal.

There are five qualified WRF processes: two observer runs, two corrected runs,
and the nonzero branch below. An earlier correction candidate was deliberately
stopped during its continuous run when the refresh was moved after the existing
tile barrier. Its commands and exact source are retained as excluded development
evidence. A first native fixture attempt used a tile bound that did not select
the physical north boundary; its failed repair assertion is also retained. The
qualified fixture corrects that bound and allocates the required ghost rows.
Neither excluded attempt is counted as a qualified model success or an
independent meteorological case.

The actual build reuses the retained general serial library and compile/link
flags, recompiles the changed solve object, replaces that object and links. It
is an incremental build, not a fresh whole-WRF build. Diagnostic observer and
native fixture compile/link command journals are also preserved. The subsequent
engineering CI performs its own ordinary build/SCM/column checks.

## One nonzero actual-host branch

After the restart fix, `run_nonzero.py` branches from its 05:59 checkpoint, keeps
the 00h/06h NC/NR endpoints zero, and supplies declared nonzero 12h endpoints to
a small warm southern patch (Python x=22:25, first two layers, five boundary
widths). The endpoint definitions are eta_NC=1e6 and eta_NR=1e3 kg_dry^-1 with
matching qc=1e-5 and qr=1e-6 kg/kg_dry. The existing public writer converts
explicit `n=eta*rho_donor` endpoints using the checkpoint ALT density donor;
this donor is not asserted to be the actual future density. It encodes REAL32
eta and native pressure mass factors, then differences stored S endpoints.
All other boundary variables are byte preserved. This is a manufactured forcing
branch, not an exact-restart comparison or an unmodified real forecast.

At the representative southern point, actual NC/NR are:

| Output | NC, kg_dry^-1 | NR, kg_dry^-1 |
|---|---:|---:|
| 06:00 | 0 | 0 |
| 06:01 | 2777.947509765625 | 2.777947425842285 |
| 06:02 | 5555.89404296875 | 5.555893898010254 |

Saved slices contain the stored-S interpolation, current history-based mass
factor, actual bits and uncoupling evaluation difference. The observed boundary values and a separate history-based `S/a` calculation
differ in the last bits. The exact evaluation boundary responsible for those
last bits was not separately instrumented in this branch; no fitted tolerance
is used to promote it into an exact conversion proof. Interior number remains positive. The selected relaxation
strip is zero at these three outputs, so a positive host relaxation-source test
is **not** claimed. Existing PR188 native relaxation evidence is retained. This
branch adds actual host nonzero outer-value/record-consumption evidence only.

## Saved replay and limits

Run without NumPy, NetCDF or compilers:

```sh
python3 -I -S validation/rrtmgp37/restart-first-step/verify_saved.py
python3 -I -S validation/rrtmgp37/restart-first-step/test_saved.py
```

The verifier checks the exact public compiled source against the current source,
the isolated diff against the frozen PR188 source, initialized raw stencil
operands, binary32 first sums, all native WW profile words, 675 full-array hash
pairs, observer noninterference inventories, actual forcing record/phase and
the nonzero branch slices. Six semantic counterexamples reject a false bitwise
flag, excluded arrays, rewritten original failure, stale kernel repair, stale
forcing record and zeroed nonzero tendency. CI replays saved evidence:
`new_model_runs=0`; it does not rerun the six-hour experiment or reread every
large NetCDF element.

The original experiment still needs existing **experimental frozen mode1** and
the unchanged expanded ice table (SHA-256
`ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a`).
Mode0's earlier positive-hail refusal is not erased. This PR does not approve
the spherical frozen-particle optics, PSD/occurrence assumptions, mixed-phase
accuracy, full water/energy closure, spectral accuracy, RFMIP/LBLRTM reference
conditions or final forecast skill. The original seven closure conditions and
reference FAILs are unchanged. No new Mie, angular, 24-hour manufactured-column
or full optical-reference campaign is added.
