# UDM cloud-top shrink and slope retention

The PR #108 rain-only fixture established the inherited read and the finite
initializer, but its warm trace control did not shrink. Its corrected v3 result
and archived package keep that limitation. This additional test uses a distinct
manufactured cold profile and leaves the old fixture and production equations
unchanged.

Liquid cloud initially extends through level 5. Levels 2–4 are at 255 K and
level 5 is at 232 K. The existing UDM homogeneous-freezing branch converts the
top liquid cloud to ice between the two `slope_cloud` calls. The recomputed
liquid-cloud top therefore decreases from 5 to 4 within one substep.

The test observes the actual `rslopec2` vectors immediately before and after each
of the two distinct calls. At the removed level it requires a finite value
computed by the first call that differs from the initializer; this value must
be exactly unchanged before and after the second call. It checks all three
UDM forwarding branches, with the optional density policy omitted, false, and
true, at GNU O0 and O2 with signaling-NaN and floating-point traps.

The initial isolated experiment passed all 18 branch/mode observations.
`rslopec2(5)` changed from the initializer `9.9999998245167004e-15` to
`2.2132137789121487e-10` at the first call and was retained by the second.
The repository wrapper and driver were then frozen and executed separately:
10 compile/link processes and two fixture executions again passed all 18
observations. Their actual logs and source pins are archived separately from
the initial experiment.

No rain is included. This proves this array-retention behavior for the
manufactured freezing profile; it does not establish downstream `qrcon` use,
atmospheric frequency, water-budget closure, particle-size accuracy, or a
forecast improvement. No WRF forecast, REAL, or radiation solver is invoked.
