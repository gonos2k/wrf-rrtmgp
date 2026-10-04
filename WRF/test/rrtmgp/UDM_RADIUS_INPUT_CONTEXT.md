# UDM radius input diagnostics

`test_udm_negative_policy.py` compiles the current `module_ra_rrtmgp_input.F`
and checks that nonfinite cloud, ice, and snow radii report the native layer
and optional caller column context. It also checks the layer-only fallback
when no context is supplied. Valid-radius behavior and rejection scope are
unchanged.

The previously built PR68 executable predates this source change, so its
runtime evidence does not exercise these radius-diagnostic checks. The
focused fixture verifies the actual edited Fortran module; it is not a full
WRF build or forecast.
