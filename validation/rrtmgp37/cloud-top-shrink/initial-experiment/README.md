# Cold-freezing cloud-top shrink experiment

This separate standalone experiment leaves the sealed PR worktree and fixture unchanged. The driver adds a cold profile only in this experiment directory. Production UDM code is pinned and unmodified; the corrected instrumentation adds read-only snapshots to a temporary compile copy.

The seven-level profile initializes liquid cloud over k=2..5, at `qc=1e-4 kg kg-1` and `nc=1e8 m-3`. It sets k=2..4 to about 255 K and k=5 to 232 K, with `pii=1`, consistent pressure, and `dt=1 s`. At k=5, the source's homogeneous-freezing branch (`tcelci < -40 C`) should transfer liquid to ice between the two `slope_cloud` calls. This is a proposed mechanism, not an observed result.

Two candidate builds, O0 and O2, each execute the profile across three forwarding branches and three density modes under bounds checks, signaling-NaN initialization, floating-point traps, and no fast math. Passing requires every record to show a smaller positive second top and finite slopes above it that differ from the pre-call initializer and remain exactly unchanged across the second call. A failure remains unmodified and unretired; the same profile is not tuned or retried.

No rain is present, so the experiment cannot claim downstream `qrcon` use. It is a synthetic mechanism test, not evidence of meteorological occurrence. The precise source, runner, driver, v3 result, and corrected-marker review pins are in `plan.json`.
