# Negative water-vapor correction — work in progress

This change follows the separate KF Eta precipitation lifetime correction in PR193.
It changes common WRF source/transport handling, not RRTMGP optics, UDM number,
radius, cloud fraction, policies, time step, input forcing, or coefficient tables.

The original cold 00:00–12:01 observer reproduces 2,925 hourly arrays byte for
byte. A separate original 05:59–12:01 source observer reproduces 1,575 arrays.
They establish two different first negative-producing operations:

* At source 60 s, native (7,49,20), saturated PD antidiffusive flux scaling and
  native REAL32 divergence/RK arithmetic leave numerator −3.725290298461914e−9.
  All six outgoing limited face fluxes reproduce the actual final negative.
* At source 42,180 s, native (88,98,22), boundary relaxation changes coupled
  tendency +6.9779721343365964e−6 to −7.1935355663299561e−6. PBL is positive,
  CU does not change this source, and the later specified tendency preserves it.
  The PD source pre-update changes positive QV to −4.492543670409077e−9.

The PD face limiter retains a finite-arithmetic donor reserve proportional to
operand norms and machine epsilon. It scales shared antidiffusive face fluxes
before divergence; it does not clip updated scalar values or add scalar mass.
The numerical reserve is not a purpose-specific physical tolerance, a mixing
ratio floor, or a certified global error bound.

For QV with positive-definite transport and specified boundaries, only a
negative external relaxation exchange that overdraws an admissible incoming
source is limited. The budget uses the full source interval and native old
pressure coupling consumed by `rk_update_scalar_pd`, not boundary interpolation
elapsed time or the first RK predictor interval. Earlier invalid sources and
negative inputs remain visible. The actual applied exchange stays in B_relax.
The optional budget is disabled for other existing callers. Work arrays read
only their own tile, not concurrent neighboring tile tendencies.

Public-library tests cover six external-source cases and six periodic native
PD transport cases. Original invalid-input behavior, zero/constant fields,
shared-flux conservation at roundoff scale, and fractional source dt are
checked. The final corrected cold real-data 24-hour evaluation, output
inventories, same-checkpoint restart, and retained-operand replay are being
assembled in this PR. No completed-day, full-water/energy, frozen-optics,
observation-skill, parallel, or adjoint approval is claimed at this stage.
