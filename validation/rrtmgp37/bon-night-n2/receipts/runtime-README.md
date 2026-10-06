# N2 gas-composition sensitivity: prepared runner

This preparation defines three fixed-input LW calls at the same 1-column, 45-layer state and explicit LW transport policy 1: (1) absent N2 override, (2) explicit N2 VMR 0.0, and (3) N2 VMR 0.7808. It uses the already built private executable from `build-v2`, compiled from the corrected `preparation-v3/reference_column.f90`. No solver call has been made by this preparation.

The first run must match both the retained matched-legacy-dry result and the earlier angular policy-1 result byte for byte (24 main result sections). The explicit-zero run must match the new baseline file byte for byte, including all 24 sections; its sidecar adds only `N2_OVERRIDE=0`. The positive run holds all non-gas inputs and sidecar source fields unchanged, checks the N2 gas-depth support at gpoints 1–26 and 123–124 below the pinned tropopause pressure, and records the radiative response. This is a controlled gas-composition sensitivity, not an accuracy verdict.

`run_once.py` defaults to offline preflight. It requires a separate root authorization file for `--execute`, creates a retained one-use lock, stops on the first failure, and does not retry. It records child PID and return code before comparing outputs. A failure receipt is preserved as a failure. No production source, forecast, WRF, or REAL invocation is part of this runner.
