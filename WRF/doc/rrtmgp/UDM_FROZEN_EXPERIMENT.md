# Explicit experimental graupel/hail optics

This opt-in research path consumes UDM27 graupel and hail separately; it does
not declare the ice sphere model accurate for atmospheric graupel or hail.
Neither NOAA internal UDM coupling nor observation agreement is claimed.
The default mode remains the validated prior path: graupel diagnostic omission
and fail-closed positive hail. RRTMG option 4 keeps its existing path.

## Selection and identity

```fortran
ra_lw_physics = 37
ra_sw_physics = 37
mp_physics = 27
use_mp_re = 1
rrtmgp_udm_frozen_optics = 1
rrtmgp_udm_frozen_table = '/absolute/path/frozen-ice-psd-moments.nc'
```

Every configured domain must use the same paired UDM37 configuration. Mode and
path are process-global and immutable after initialization. Each process loads
and validates a table once before radiation threads run. SHA256 is computed
from the raw bytes before and after loading; a changed file is rejected.
The immutable data in memory are the computation source thereafter. A file
replaced after successful initialization cannot change those loaded data.

A usable example table is tracked under
`validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/`.
It covers 300–20000 m-1 PSD slope and 180–300 K LW source weighting.
Its generation uses fixed material ice-Ih optical constants, homogeneous spheres,
exponential size distributions, order 128 quadrature and 50 cm-1 band steps.
Numerical controls and held-out interpolation differences are reported separately
in that validation directory; they do not establish global convergence or
forecast accuracy. Temperature interpolation changes Planck weighting only,
not the material index. Warm hail, melting, porosity, nonsphericity, habits and
coatings remain model limitations requiring independent evaluation.

## State, mass and occurrence

Native WRF dry layer mass defines grid paths in g m-2:

`GWP = qg * native_dry_layer_mass_kg_m2 * 1000`

and identically for hail. Existing documented host numerical-residue sanitation
is applied locally before optical conversion and size reconstruction; it does
not change prognostic UDM variables. Positive mass below UDM's 1e-9 process cutoff
is retained. The cutoff selects a size sentinel, never an omission threshold.

The diagnostic PSD slope is reconstructed from returned grid-mean mixing ratio
and the actual moist air density passed to UDM:

`lambda = min(20000, (pi * rho_bulk * N0 / (rho_air * q))**0.25)`.

Graupel uses N0=4e6 m-4 and bulk density 500 kg m-3; hail uses 4e4 and 912.
At q<=1e-9 the slope sentinel is 20000 m-1. The reconstruction is a diagnostic
of the returned post-process state, not a claim to reproduce every intermediate
in-cloud/process slope in UDM. Cloud/precipitation fractions and process-time
state can differ from returned grid state.

**Occurrence fraction is explicitly 1 for G/H in this experiment.** Paths are
never divided by cloud fraction and are never sampled with the cloud McICA mask.
They remain present when radiation CF is zero or overlap=0. This is an
experimental uniform precipitation assumption, not an inferred UDM precipitation
fraction. qc/qi/qr/qs retain their prior cloud-fraction path and sampling contracts.
No hail-to-snow or graupel-to-cloud-ice size proxy is used.

## Optical and clear-sky contracts

The lookup interpolates kappa*rho_bulk/lambda in log(lambda), and LW values
linearly in source temperature, then restores lambda. Divide the resulting
moments by species bulk density and multiply grid path in kg m-2 exactly once.
For every positive path, slope and LW temperature must be inside the table axes;
out-of-range queries fail with species, column/layer, input and axis context.
There is no clipping or extrapolation. Zero-path layers skip bounds queries,
while finite/positive size and temperature validation remains active.

LW uses absorption optical depth only. SW combines separate G/H values in
`tau`, `tau*ssa`, `tau*ssa*g` space, derives ratios, and delta scales the combined
G/H optical properties once. It adds G/H to all-sky atmospheric optics after
cloud sampling. This separate delta treatment is explicit; it is not the
combined cloud-plus-precipitation delta transform or pinned CCPP parity.

Gas-only clear-sky RTE runs first, so UPC/DNC/HRC remain free of cloud and all
precipitation including G/H. All-sky direct flux keeps the existing delta-scaled
solver meaning; it is not claimed to be true unscattered DNI.

## Capture and independent replay

Mode 1 emits `RRTMGP_REPLAY_V7`, preserving host constants, optional native dry
mass, explicit mode/occurrence, 64 lowercase-hex table hash bytes, GWP/HWP and
both slopes. Results retain per-species raw optical moments before combination,
combined scaled G/H optics, total optics, fluxes and heating.

The independent reference executable requires `WRF_RRTMGP_FROZEN_TABLE` for V7,
verifies the recorded raw-byte SHA256 and recomputes optics from recorded paths
and slopes. It does not substitute recorded optical output. Missing/changed
model metadata or a different table must be rejected. V1–V6 remain backward
compatible and cannot silently downgrade a V7 input.

## Completion boundary

Lookup parity, input mass closure, independent replay, compiler/build checks and
parallel read reproducibility address implementation correctness. Actual UDM
hail-producing long runs, restart/decomposition equivalence and independent
optical/observation comparisons are separate gates. Enabling this mode to finish
a hail-producing run does not by itself validate the chosen optical model.

The [actual-domain runtime record](../../../validation/rrtmgp37/realdata-parallel/README.md)
contains the completed PR20 four-rank 24-hour mode-1 trial and its separate
12-to-13-hour restart comparison. All numeric history fields agree exactly
at 13 hours, while global `START_DATE` differs. Hourly positive G/H paths
confirm that this was not a zero-particle bypass; substantial warm-air
positive-path shares also keep melting-particle fidelity outside the validated
scope. These receipts identify the older PR20 executable explicitly.
