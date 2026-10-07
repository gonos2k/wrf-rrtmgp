# Startup snow optics validation

The SCM validator checks all 16 LW and all 14 SW precipitation bands in the
selected first-call snow layer. Every LW band must be positive and every SW
band must exceed the native `1e-12` extinction floor. A single surviving band
cannot satisfy the check.

With zero rain, the independent LW expectation is
`1.5 * 1.05756 * SWP / RES`, where SWP is the consumed in-cloud path in g/m²
and RES is the consumed radius in micrometers. Its comparison budget is
`16 * epsilon(binary64) * expected_tau` for arithmetic roundoff.

The independent SW check uses delta-scaling conservation of absorption:
`tau_delta * (1 - ssa_delta) = tau_unscaled * max(1e-6, B0S + B1S*1.0315*RES)`.
The `1e-6` term retains the production module's SSA cap. The B0S and B1S array
literals first round to default REAL before promotion to the optical module's
binary64 kind; the capture's HOST_REAL_BITS distinguishes REAL32 and REAL64.
The comparison budget is `64 * epsilon(binary64) * tau_unscaled`, including
the cancellation in `1-ssa`. These budgets test the source contract and do not
relax any physical acceptance threshold or change production coefficients.

Saved-only controls run without WRF, compilation, or a reference solver:

```sh
python3 -B WRF/test/rrtmgp/test_udm_startup_optics_contract.py
```

An existing captured case can also be checked with `--saved-case CASE` and
`--execution EXECUTION_JSON`. Manufactured negative controls include a missing
band, wrong LW magnitude, wrong SW SSA or extinction, missing SSA, nonfinite
values, wrong default-literal kind and capture-pair identity mismatches.

The optional `--capture-pair` flag adds a candidate37 capture-OFF forecast
immediately before the capture-ON forecast. Both arms use the same executable,
shared initial input and namelist. Their entire NetCDF histories must be byte
identical; the validator also checks the complete variable roster and arrays.
This is observer passivity for that candidate and input. Runtime-only mode
does not compare engine4 or a pristine upstream WRF executable.

```sh
python3 -B WRF/test/rrtmgp/test_udm_startup_snow_scm.py NEW_OUTPUT \
  --candidate-wrf-root BUILT_WRF --runtime-only --capture-pair
```

This command requires already-built executables and performs one ideal
invocation and two forecasts. Without `--capture-pair`, the original invocation
counts remain unchanged. The checks establish optical-builder integration and
capture passivity; they do not establish Nc units, snow PSD/LUT compatibility,
RFMIP or LBLRTM acceptance, or forecast accuracy.
