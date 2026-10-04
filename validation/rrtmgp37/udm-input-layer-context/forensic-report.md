# Matthew extended-Planck failure: read-only forensic audit

The new run failed with launcher RC 1, unchanged assets/executable, and an explicit rank-0 `RRTMGP_INPUT_DP_HPA_NOT_FINITE` message after the main-step timing reached **2016-10-06 00:50:00**. This authenticates a nonfinite radiation pressure-thickness input, not its producer. The earlier 00:40 frozen-temperature range failure was passed; this is not a completed 48 h run. No forecast, compiler, solver or production edit was performed here. The run is root-accounted forecast **78**, not an additional invocation by this audit.

## Logs and available state

All nine retained logs match the original execution receipt SHA/size pins. Rank 0 `rsl.error.0000:140` contains the direct fatal and line 141 the MPI abort. `rsl.out.0000:138` and `rsl.error.0000:139` contain the last main timing, 00:50. The main-step timing is written after the preceding advance; the fatal occurs while preparing the next radiation call at that clock time. No rank has a completion marker.

The four error/out diagnostic sequences are duplicated exactly (58, 56, 54, 54 records by rank). Do not sum the two streams. Their LW aggregate records reach source time 2400 s / radiation step 17. No SW path records are emitted. This is not proof that the SW solver never ran; these diagnostics are gated. There are no reported CFL exceedances, NaN/Inf values, flux extrema, heating extrema or frozen optical-depth maxima. The broad scanner records only an informational `W-DAMPING BEGINS AT W-COURANT NUMBER` startup line on rank 3, in both streams. This is not a measured CFL exceedance. Comparisons with NaN can also miss a CFL alarm; absence of an alarm is not stability evidence.

The sole partial history has **225 variables and one time, 00:00**, written before the first radiation call. Selected raw pressure, thermodynamic, moisture and velocity arrays are finite there. All six hydrometeor mass fields and requested radiation flux/heating/accumulated fields are zero. These initial values cannot reconstruct the previous 00:40 radiation output or the failing 00:50 input. There is no retained radiation-call capture or checkpoint for the failing state.

## Source chain and the dropped diagnostic context

All 11 audited source files match the copied-build source manifest and the corresponding PR65 `d3088f1ea0a532f286ea3d42415ecba5d4411aea` Git blobs. The executable is `17e37d7461d90bf4eac4110879ecf4716e515fd155aca9754ff74d573ca01725`. The build was a copied incremental build; its original `BUILD_FAIL` and corrected `BUILD_PASS_SCOPED` receipt remain distinct. This audit does not turn it into a pristine build.

Paths below are relative to `build/udm37-pr65-fatal-reporter-wrf-build-v1/source-copy`:

| Evidence | Actual source anchor | Consequence |
|---|---|---|
| Pressure preparation | `WRF/dyn_em/module_first_rk_step_part1.F:219–229` calls tile-local `phy_prep`; `:309` passes `grid%p_hyd_w` as radiation `P8W` | Trace the native hydrostatic interfaces, not the separately interpolated `p8w` scratch |
| Moist-loaded interface pressure | `WRF/dyn_em/module_big_step_utilities_em.F:4944–4958` starts from finite configured `p_top`, sums `moist(:,:,,:,PARAM_FIRST_SCALAR:n_moist)`, then integrates `(1+qtot)*(c1*MUT+c2)*dnw` top-down | A nonfinite native moisture total, nonfinite/overflowing arithmetic or corrupted pressure state can propagate downward; temperature is not directly in this recurrence |
| Native dry mass | `WRF/dyn_em/module_first_rk_step_part1.F:280–289`: explicit allocation/zero, then `-dnw*(c1h*MUT+c2h)/g` over owned mass cells | This is a separate dry denominator, not proof that moisture or all thermodynamics are finite |
| Actual moisture species | `WRF/Registry/Registry.EM_COMMON:3095`: UDM27 moist `qv,qc,qr,qi,qs,qg,qh`; scalar `qnn,qnc,qnr` | No number-concentration-as-moist-mass defect found in this pressure sum |
| Wrapper pressure assignment | `WRF/phys/module_ra_rrtmg_lw.F:12208–12212` copies `P8W/100` into `pw1d`; `:12493–12500` sets interfaces and `pdel=plev(k)-plev(k+1)` | Current native layers are explicitly assigned before builder use |
| Dry-mass checks precede dp | `WRF/phys/module_ra_rrtmgp_input.F:315–334`, then `:392` | In this executed builder path all supplied dry masses passed finite/positive checks before dp failed; this says nothing about finite moisture/T/previous RTE results |
| Index/context loss | `:392` passes `RESHAPE(dp_hpa,[n,1])` into generic positive/finite checks; `:820–847` constructs only generic 2-D column/layer labels | Reported `column=1 layer=1` means native vector element 1 in this case. A failure at native element k would report `column=k layer=1`. The provided wrapper `LW i=… j=…` context is discarded |
| Per-column context exists | `WRF/phys/module_ra_rrtmg_lw.F:12921`, builder calls `:13001–13018` | Missing global i/j is a concrete diagnostic defect, not absent caller knowledge |
| Failure before batch append | Builder `:13001–13018`; batch append `:13320–13359`; flush `:13361–13363` | The failing column has not entered this call's batch or backend. Earlier batches/calls can still be a precursor; this does not exonerate the backend |

The `p_hyd_w` recurrence makes native moisture and the hydrostatic interface state high-value observations. If `qtot` becomes NaN above the bottom, both adjacent lower interfaces can be NaN. Finite dry mass is insufficient to distinguish this from pressure-buffer corruption or arithmetic overflow. No logged value chooses among them.

## Backend, batching and accumulation audit

The LW wrapper is `RECURSIVE` (`module_ra_rrtmg_lw.F:11570`), owns a local workspace (`:11633`), resets its local batch count (`:12051`), packs all used state arrays (`:13323–13359`), slices only `1:nbuf`, and scatters with saved i/j (`:13627–13636`). Native pressure is assigned directly from the host before packing. G/H paths are initially zero with slope sentinels (`:12118–12119`), CU bundles reset/assign per column (`:13062` onward), and padded native cloud paths/CF are explicitly zero (`:13206–13220`). No concrete stale/uninitialized batch slot or shared writable workspace defect was established in these inspected branches. This is a static finding, not a memory-safety proof or new runtime equivalence test.

The module's saved gas/cloud descriptors are initialized before parallel calls in `module_physics_init.F:2440`; writable optics/source scratch are supplied through the tile-owned workspace. Source/gas optics are recomputed before each LW solver invocation. A shape-reuse return is not by itself proof of stale numeric data; no observed stale-source value is available here.

There is a real **output-validation gap**. `module_ra_rrtmgp.F:758–761` and `:836–839` check returned RTE/heating error strings but do not check the returned flux arrays, heating array or subsequent default-REAL conversion for finiteness. `WRF/external/rte_rrtmgp/extensions/mo_heating_rates.F90:36–70` checks extents and computes flux divergence divided by `cp_dry*(p_lev(k+1)-p_lev(k))`; it does not reject nonfinite inputs/results. The adapter does require finite, strictly decreasing plev before earlier backend calls (`module_ra_rrtmgp_input.F:728–750`), so an exact zero layer pressure denominator is rejected on that path. There is no newly demonstrated zero denominator. Extremely thin layers, nonfinite RTE fluxes, overflow in conversion to host REAL, or wrapper division by nonfinite/zero `PI3D` remain observable risks rather than established causes. `scatter_lw_column:13671–13674` divides by host Exner without a new finite guard.

Radiation flux accumulators at `module_radiation_driver.F:3848–3867` are `old + held_flux*DT`, confined to each owned tile. No examined call reads those accumulated-energy fields into pressure or dynamics. Instantaneous heating does feed the physics tendency: the radiation driver passes `RTHRATEN` as the LW output (`:2148`), and `module_physics_addtendc.F:133`, `:229` adds that tendency. Accumulated flux corruption is not an identified producer; a nonfinite instantaneous tendency from an earlier call is a plausible unmeasured bridge.

The timestep diagnostic is **6.22594 s/km including map factor**, above the namelist's reported reasonable ratio 6; `w_damping=0`. This is a concrete configuration concern, not proof of CFL failure, and RA4's completed run does not establish stability under different radiative feedback.

## Frozen table observations and unresolved optical causality

The new table SHA `ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a` spans 150–330 K with 38 temperature nodes and retains nine lambda nodes. Every read raw moment is finite. SW moments/bands and lambda are exactly equal to the old table. LW absorption values at each old temperature knot (180, 233, 250, 300 K) also match exactly. New extrema are not orders-of-magnitude anomalous relative to old extrema: maximum LW absorption-times-density is 11952.7043 versus 11950.6298 in the old table. This is a table-level observation only, not a bound on actual optical depths or flux/heating feedback.

`module_ra_rrtmgp_frozen.F:240–286` checks finite/positive input, ranges and final queried real64 optical depth. `module_ra_rrtmgp.F:344–356` sums species, converts to `wp` and increments atmospheric optics. RTE checks optical properties by default, but no dedicated post-solver flux/heating finite guard is present. New temperature nodes also change LW interpolation between old knots; therefore this retry is not an unchanged-physics experiment that isolates range coverage from optical feedback. No actual G/H per-layer paths, tau maxima or preceding heating profiles are retained for this run. High CU/native path/clipping aggregates alone cannot determine extreme frozen optics or causal radiative heating.

## Bounded next evidence and recommendation

The already root-owned diagnostic should recover global i/j/k and native species/QV totals, `p_hyd_w`/pdel, dry mass, T/Exner, pressure/geopotential, and instantaneous radiation/physics tendencies immediately before the 00:50 call. Saving only hourly history or only T cannot identify this bridge. A few pre-failure timesteps and the previous radiation call are necessary to decide whether nonfinite moisture/thermodynamics preceded radiation, whether RTE first produced nonfinite output, or whether pressure changed without its recurrence inputs becoming invalid. No diagnostic run was launched here.

Separately, the minimal proposed diagnostic fix and meaningful controls are in [diagnostic-proposal.md](diagnostic-proposal.md). It preserves fail-closed behavior and identifies actual native layer/context; it adds no clipping, threshold, policy or numerical correction. The implementation cause remains **UNRESOLVED**. Do not label the failure normal physics, dynamical instability, frozen-optics error or port corruption until measured state establishes the first nonfinite bracket.

Exact pins, retained log rows, selected initial arrays and table statistics are in [audit.json](audit.json), generated by [audit.py](audit.py). This forensic report changes no existing receipt or failure status.
