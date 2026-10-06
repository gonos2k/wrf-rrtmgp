# Preserved Matthew native-Courant timeline — corrected thermodynamic mapping

This v2 read-only analysis corrects v1's interpretation of history `T`. **v1 remains unchanged** and is pinned in this artifact. The model history, Courant analyzer, failure logs, and model execution are the same; no model, REAL, or radiation calls were repeated.

The preserved 4-rank RA37/frozen-optics diagnostic run was invoked once and failed (`FAIL_PRESERVED`, launcher return code 1, not timed out) after writing the `2016-10-06_00:50:00` record. The fatal was `RRTMGP_INPUT_DP_HPA_NOT_FINITE at column=1 layer=1`.

The history has 21 samples at 150-second intervals from 00:00 through 00:50 UTC. The endpoint metric is `abs(WW*dt/DNW/(C1F*(MU+MUB)+C2F))` at interior vertical interfaces: a sampled-history quantity, not an internal RK/acoustic-stage maximum. Its largest complete-record finite value is **2.9533128647 at 00:42:30 UTC**, Fortran indices `i=42, j=30, interface=30`. At 00:50, **18,103 endpoints are invalid**, so the maximum is unavailable for that record. The graph breaks the valid-record curve there and marks the invalid count; the finite-subset number 0.2438005339 is retained in JSON only and is not presented as recovery.

The Registry distinguishes two history variables. `T` maps to `th_phy_m_t0`, assigned as `th_phy-T0`, the **dry perturbation potential temperature**. `THM` maps to prognostic `t`, which is moist potential temperature when `USE_THETA_M=1`. Thus the physical temperature from history `T` is

```text
Tphysical = (T + 300) * ((P + PB) / 100000) ** (287 / 1004.5)
```

The independent `THM` reconstruction is `theta_dry=(THM+300)/(1+(461.6/287)*QVAPOR)`, followed by the same Exner factor. The source mapping is checked against `WRF/Registry/Registry.EM_COMMON` (DataName declarations), `WRF/dyn_em/module_big_step_utilities_em.F` (`th_phy_m_t0=th_phy-T0`, `t_phy=th_phy*pi_phy`), and `WRF/dyn_em/module_initialize_real.F` (moist-theta conversion). Across finite common cells, the `THM` reconstruction agrees with dry `T` to max absolute difference **5.78e-5 K** in theta and **4.65e-5 K** after Exner conversion, consistent with stored single-precision output rounding.

At the selected column `i=42, j=30`, physical temperature from `T` spans 178.83–299.70 K at the Courant peak sample (00:42:30). At 00:47:30, 43 finite levels span 106.01–446.36 K; at 00:50 all 44 levels are nonfinite. Across the full 00:50 record, T, P, and QVAPOR each have 21,164 nonfinite/fill cells. `RTHRATLW` has no nonfinite/fill cells in any sample; its full-domain finite extrema across the timeline are -0.0011083606 to 0.0003379784 K s-1. Selected-cell `GLW` ranges from 0 to 464.9427 W m-2.

Finite sampled `RTHRATLW` and `GLW` do not rule out an indirect tendency/thermodynamic trigger and do not establish a radiation-port cause. This is a partial failed-run diagnostic, not a stable forecast or accuracy evaluation. The history's `T` and `THM` raw records, metadata, source files, executable/build receipt, run logs, Courant analyzer, v1 package, script, report, and figures are hashed in `timeline.json` and `artifact-manifest.json`.

Recreate v2 with `python3 -B analyze_timeline.py` from this directory; it reads the preserved history only and writes the local JSON/PNG/PDF artifacts.
