# Explicit dry-number specified boundaries

`udm_number_policy=1` now has a limited specified-boundary path in addition to
the existing periodic research path. This is a representation/transport feature,
not approval of general mixed-phase UDM forecasts.

Required configuration: serial build, one nonperiodic specified domain, one tile,
UDM27/LW37/SW37, `scalar_adv_opt=0`, `udm_population_policy=0`,
`have_bcs_scalar=.true.`, `have_bcs_moist=.true.`, and
`rrtmgp_capacity_policy=0`, `rrtmgp_liquid_size_policy=0`. Nested domains,
MPI/OpenMP, and other specified research-policy combinations remain rejected.

Every input, boundary and restart file must carry integer global attributes
`UDM_NUMBER_POLICY=1` and `UDM_SPECIFIED_NUMBER_CONTRACT=1`, in addition to the
existing population metadata. History and checkpoint output persist the contract.
Adding attributes to legacy nonzero arrays is not a conversion.

For cloud/rain number, initial and transported values are
`eta=n/rho_d` [kg_dry^-1]. The native boundary file contains

```
a = C1H * (MU + MUB) + C2H       [Pa]
S = a * eta                    [Pa kg_dry^-1]
BT = (S_next - S) / dt          [Pa kg_dry^-1 s^-1]
```

Time interpolation is linear in stored `S`, followed by current native mass
uncoupling. It is not linear interpolation in volume number. Neither density
changes nor changes in `a` may be omitted when constructing tendencies.
`write_volume_series` in [convert_udm_specified.py](convert_udm_specified.py)
accepts explicit N+1 endpoint volume numbers, dry densities, full native mass
factors and timestamps for a complete side series. It rounds eta and the factor
to REAL32, couples endpoints, then differences the stored endpoints. Matching
condensate endpoints must be positive wherever number is positive. This API does
not infer dry density or the full mass factor from variable names, and does not
initialize nonzero interior fields for the caller.

For the independently verified exact-zero input only:

```bash
python WRF/test/rrtmgp/convert_udm_specified.py wrfinput_d01 wrfbdy_d01 encoded
```

This CLI reuses the PR187 exact-zero producer, rejects nonzero/nonfinite/missing
hydrometeor fields, and preserves all original arrays. It does not remove
condensate to satisfy the contract.

Free CCN is separate from cloud/rain number. File QNCCN is not relaxed into the
number1 reservoir. At inflow, `ccn_conc` remains a constant volume background and
is converted with current `ALT=1/rho_d`; at outflow, eta has a zero gradient.
Interior generated number is not reset. The cloud/rain outer specified zone
uses the prescribed file state, including at outflow, as in the native scalar
specified-boundary contract. CCN may subsequently change through microphysics.

See the [executed evidence and limitations](../../../validation/rrtmgp37/specified-number-boundary/README.md).
The real next-record test and checkpoint restoration succeeded; full host
continuous/restarted bitwise equality did not. Defaults remain unchanged.
