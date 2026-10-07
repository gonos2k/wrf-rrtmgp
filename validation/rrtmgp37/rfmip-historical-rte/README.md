# Historical RTE fixed-optics replay

This evidence compares saved broadband shortwave fluxes from a four-arm, fixed-optics replay on the same 20 selected RFMIP profiles. The current-runtime 40-call replay is retained in the adjacent `rfmip-fixed-rte/` package. A separate 40-call replay uses the retained historical RRTMGP build. Both arms inject the same saved optics/source arrays and bypass gas optics.

| Runtime | Current optics | Historical optics |
|---|---|---|
| Current retained runtime | `F(current,current)` | `F(current,historical)` |
| Historical retained runtime | `F(historical,current)` | `F(historical,historical)` |

The historical diagonal reproduces the saved historical solver and written flux records bitwise for all 20 profiles. The current diagonal continues to reproduce its saved current-runtime records bitwise. All four solver and written outputs match within each replay. `two_by_two_analysis.json` gives the per-direction decomposition over 1,220 values per arm (20 profiles × 61 levels): optics effects, runtime-stack effects, their interaction, and the diagonal difference. The component identity closes exactly in the saved arithmetic.

Across this selected sample, changing optics changes flux by at most `2.162e-7 W m-2` downward and `5.593e-8 W m-2` upward; changing the retained runtime stack changes it by at most `6.063e-7 W m-2` downward and `5.032e-7 W m-2` upward. The interaction is at most `5.277e-10 W m-2` downward and `2.743e-10 W m-2` upward. These are descriptive results for this 20-profile replay. The runtime comparison changes the retained source/build/runtime stack, so it does not isolate a pure algorithm change.

The historical candidate source is `ed5b0113109fcd23a010a90c61f21bad551146ef`; the current fixed-RTE build plan records source `41c5fcd950fed09b8afe186dede266824eca7fd3`. Both builds used the pinned GNU Fortran 13.3.0 compiler binary and `-O0 -ffree-line-length-none`, while using different RTE source/module/static-library builds. The run reused current and historical coefficient descriptors and captured optics. The harness requires matching band/g-point descriptor limits, but matching indices do not establish physical g-point equivalence between coefficient generations.

The report also lists the 21 previously selected strict-failure cells as subset diagnostics. They are not the global strict-failure census. The original strict gate, tolerance, and failures remain unchanged. This result verifies replay against retained saved outputs; it does not authenticate the original published CMIP6 executable/compiler, establish physical accuracy, or close the global strict RFMIP gate.

To reproduce the saved-only arithmetic from any working directory, run:

```sh
python3 -B /path/to/validation/rrtmgp37/rfmip-historical-rte/analyze_historical_rte.py
```

The analyzer reads only the packaged execution receipt/flux outputs and the adjacent fixed-RTE package’s references and profile roster. It pins the adjacent fixed-RTE package manifest SHA-256 `7b1b66f9c0bc77a8086a53159b4dc72bf5602c4f3279b4521e440868af0dfe1b`. It launches no compiler, solver, or forecast.
