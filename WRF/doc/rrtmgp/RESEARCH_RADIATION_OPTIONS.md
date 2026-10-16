# Opt-in native radiation research definitions

Both physics namelist integers default to **0**. This implements the two PR179
private candidates as explicit, independently selected normal-build paths:

| Option | 0 | 1 |
|---|---|---|
| `rrtmgp_capacity_policy` | Existing pressure-mass heating | `native-constant-kappa-source-v1` |
| `rrtmgp_liquid_size_policy` | Existing host liquid radius | `final-liquid-gamma-veff-0p1-v1` optical radius |

These are conditional research definitions, not a correction claiming that all
WRF physics use one caloric potential or that Gamma8 is an observed cloud PSD.
The seven scientific closure conditions and `production_accepted=false` remain.

## Capacity source

Native layers use same-call host dry mass and water vapor:

```
C = md * cpd * (1 + (Rv/Rd) * qv)
Tdot = (net_down_upper - net_down_lower) / C
```

This is the fixed-composition constant-kappa caloric completion documented in
`validation/rrtmgp37/native-radiation-capacity/README_ko.md`. Condensate heat
capacities are neglected in this approximation. It is distinct from the physical
fixed-composition mixture heat capacity and from a dry-mass-times-cpd ledger.
The native prefix alone is changed, with the same definition in LW/SW and
clear/all-sky. Extension layers keep existing pressure heating. Fluxes and gas,
cloud and precipitation optics are unchanged by the capacity choice. No UDM
cpm, density, number, latent heat or surface source is adjusted.

Capacity is a caller-owned optional REAL(wp) column array. No environment setter
or mutable per-column module state controls these choices. An absent array takes
the existing calculation. The existing held-theta radiation interval is unchanged.

## Optical size

At the radiation boundary, same-call qc, dry-mass number eta, dry density and
population footprint define the Gamma number distribution with shape 8 and
veff=0.1. M0 and M3 set lambda, M2 sets reff=M3/M2. Only the liquid optical REL is
replaced. UDM RE_CLOUD and its subsequent microphysics consumption are unchanged.
Cloud CF/masks, rain optics, ice/snow radii, LUTs and coefficients are unchanged.
The common footprint cancels from the radius, but the declared population is
still required. This does not certify the original LUT generating PSD.

## Scope and file contract

Selected options require number policy1, population policy2, use_theta_m=1,
one tile and a serial build. The existing number policy guard also requires one
periodic domain with UDM27/LW37/SW37 and scalar_adv_opt=0. Radiation calls reject
cold/frozen columns and batched research columns. Population2's existing runtime
scope checks also apply. General real/ideal/boundary eta producers remain
unsupported. MPI/OpenMP and mixed phase are outside this integration.

Input, history and checkpoint attributes are independently named
`RRTMGP_CAPACITY_POLICY` and `RRTMGP_LIQUID_SIZE_POLICY`. Missing attributes mean
0, so old legacy files remain usable with both options OFF. A selected option
requires its matching explicit tag, and mismatched restart selections are
rejected before history production. A changed selection is a new branch
experiment, not an exact restart. Adding these two tags to an already explicitly
encoded eta/population2 research input changes metadata only; it does not certify
or convert raw number inputs.

Held LW/SW/total and clear tendencies and STEPRA already belong to the restart
state. No new prognostic moment or cached capacity is needed: capacity and REL
are rebuilt from current state at each actual radiation call. The integration
study tests a checkpoint at 20 seconds between calls at 0 and 30 seconds.

The capture bundle records same-call md/qv and the executed choices in `.raw`,
optical/gas inputs in `.input`, and optional native capacity plus REAL(wp)
flux/heating in `.result`. Existing pressure-only standalone replay of `.input`
alone does not exercise the research capacity. To reproduce research heating,
pass the separately recorded capacity to `rrtmgp_*_column`'s optional
`native_heat_capacity` argument. The retained integration checker verifies this
layer source explicitly; it does not claim a new standalone solver replay.
