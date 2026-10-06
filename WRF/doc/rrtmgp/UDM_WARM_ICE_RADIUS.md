# Finite UDM ice radius above freezing

The native UDM ice-radius fit uses `sqrt(T0C - T)`. Positive ice can remain
temporarily above freezing: the retained warm-block SCM producer at step 1
contained such ice at native levels 31–33 (274.463, 273.903 and 273.299 K).
Calling the unchanged native routine with those exact returned temperature,
density and ice-mixing-ratio tuples stops with an invalid-operation trap.
Without trapping, GNU Fortran 13.3 propagates NaN through the cubic, and the
intrinsic bounds happen to select 125 micrometres. That selection is not a
valid evaluation of the radius fit.

The routine now evaluates its supercooling coordinate as
`max(0., T0C - T)`. For warm ice this explicitly uses the freezing-point
endpoint, B = -2, while retaining the existing polynomial and radius bounds.
The endpoint is approximately 103.4832 micrometres. The subfreezing expression,
liquid and snow branches, hydrometeor masses and all optical-model choices
are unchanged.

This is a finite extension of a subfreezing parameterization, not validation
of warm-ice particle sizes or a correction to the radiation LUT size metric.
It does not clamp B to the published fit interval, resolve the UDM number
concentration units, or establish forecast accuracy. Those physical questions
remain separate. Ordinary UDM RRTMG4 does not enable this native-radius block;
the dedicated 37/37 initialization does.

The focused test compiles the production routine, exercises the three retained
warm tuples and the freezing endpoint with invalid-operation trapping, compares
cold outputs with the unguarded implementation, and requires the reverted warm
case to fail in the native routine. Run it from the repository root:

```sh
python3 WRF/test/rrtmgp/test_udm_warm_ice_radius.py --wrf-root WRF \
  --workdir build/udm-warm-ice-radius-test
```

The archived pre-fix packets in `validation/rrtmgp37/native-radius-stage/`
remain evidence from their original source. Their verifier authenticates the
original PR100 source checkout rather than relabelling old outputs as results
from the new native routine.

## Local integration result

A fresh GNU 13.3 serial `em_scm_xy` build was run on the same retained cold
mixed and contiguous warm-block initial states as the pre-fix executable.
Six one-minute forecasts and four independent LW/SW column replays passed.
Ordinary UDM4 preserved all 208 history arrays bitwise in each of the two
cases; cold UDM37 preserved all 211 arrays. In the warm case, the first
producer's temperature, density, condensates, Nc, liquid radius and snow radius
were exact before/after matches. Only the three warm ice radii changed from
125.000006 to 103.483188 micrometres, and both later radiation phases consumed
the returned radius arrays exactly.

The retained warm history showed zero change in SWDOWN, GLW, LWUPT, both
radiative heating rates, temperature and ice mass. This fixture therefore
establishes a repaired finite native calculation and preserved radiation
results, rather than attributing earlier large 4/37 flux differences to this
defect. It is a short manufactured SCM comparison, not an assessment of
real-domain accuracy or long warm-ice episodes.
