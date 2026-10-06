# UDM snow radius at the first radiation call

Before the first UDM microphysics update, a positive snow mixing ratio can
coexist with the initialization radius `RE_QS_BG`. The previous scheme-37
fallback selected 10 micrometres. The precipitation optics require a snow
radius strictly greater than 10 micrometres, so that fallback did not activate
the physical snow optical contribution.

Scheme 37 now diagnoses this background-radius case with the existing native
UDM effective-radius routine. The snow-only helper takes temperature and snow
mixing ratio from the current radiation input state, together with dry density
computed as `1./(AL+ALB)` in `first_rk_step_part1`. This is not a post-microphysics
radius sample. The radiation-stage moist density is not divided by an inferred
humidity factor to obtain this input. The caller passes the same native
`epsilon` and `svpt0` constants used by the microphysics driver.

The helper calls the native radius calculation without taking a microphysics
step or updating hydrometeor mass, number concentration, or the source
`re_snow` array. Its output is a local radius in metres; the wrapper converts
it to micrometres for the optical calculation. Native initialization of the
snow coefficient must already have completed. Finite input, initialization,
exponent and product guards reject invalid calculations rather than selecting
a replacement optical policy.

The bootstrap applies only in the RRTMGP branch when the source snow radius
equals the exact host-kind `RE_QS_BG`, snow mixing ratio is positive, cloud
fraction is positive, and `ICLOUD` is nonzero. Already diagnosed snow radii and
the liquid and ice fallback paths retain their existing selection. The strict
greater-than-10 optical activation threshold is unchanged. Ordinary radiation
scheme 4 retains its original calculation.

The shortwave precipitation module also returns a numerical optical-depth
floor for zero precipitation path. That floor is not a physical snow optical
contribution. The focused test compares the old 10-micrometre shortwave result
exactly with a zero-rain/zero-snow-path call to the actual module, then requires
the native-radius result at a fixed positive snow path to exceed that control
floor. Longwave checks require old zero and new positive snow optical depth.
These assertions introduce no optical-depth tolerance or threshold change.

## Capture and replay contract

New captures provide a four-field bundle:

- `SOURCE_DRY_RHO`: the passed dry-density column.
- `STARTUP_SNOW_BOOTSTRAP`: a binary mask of the selected background cases.
- `STARTUP_SNOW_RADIUS_M`: the local native diagnosis in metres, zero outside
  that mask.
- `HOST_REAL_BITS`: the host default-real storage size, 32 or 64 bits.

The replay checker requires all four fields together, verifies the exact
activation mask, positive dry density and native radius bounds, and checks the
metre-to-micrometre mapping in the declared host kind. This verifies selection
and unit mapping; the separate compiled native fixture checks the diagnosis.
Historical captures with none of these fields retain their previous fallback
contract. Their results are not relabelled as bootstrap runs.

## Validation scope

The standalone native fixture extracts the production initializer, helper and
radius routine and compiles the actual precipitation optics and wrapper snow
selection blocks. It covers tiny positive snow, native bounds, invalid inputs,
diagnosed-radius preservation and source-state immutability. The replay unit
tests cover both host kinds and malformed diagnostic bundles. The initial
fixture attempt compiled and produced 12 matching native-radius tuples, then
failed an incorrect assertion that the old shortwave optical depth was zero.
That failure is preserved. The corrected fixture passed at O0 and O2 with
invalid, zero and overflow trapping enabled: two compiler processes and two
fixture processes returned zero. The 12 replay mapping tests also passed.
These are source-extracted and manufactured-input checks, not a full-model
physical-accuracy result.

The first candidate full build subsequently failed to produce `wrf.exe`:
the wrapper's `HOST_REAL_BITS` array constructor caused a compiler error,
although the top-level build command returned zero. The diagnostic now uses
an explicitly declared default-real array with the same host-bit value.
The extended fixture includes that source declaration and assignment;
it passed in two fresh O0/O2 compiler and fixture processes, and the 12
mapping tests passed again. The repaired candidate also completed a fresh
serial `em_scm_xy` build with both required executables present.

The three-arm SCM run used one shared ideal seed and completed three
one-minute forecasts with actual return codes zero: retained main38 scheme 4,
candidate scheme 4, and candidate scheme 37. Its original postprocessor failed
because it assumed the precipitation optical-depth array had the native layer
count. That failure is preserved. Saved-output revalidation accounts for the
adapter's upper extension and its spectral-band axis, without rerunning WRF.
It found all 208 scheme-4 history arrays bitwise equal and the two complete
history-file hashes identical.

At the selected first-call snow layer, the source radius remained the
9.99-micrometre initialization sentinel. Both radiation phases selected the
native diagnosis of 134.778076 micrometres, with cloud fraction one, zero rain
path and positive snow path. The snow optical depth was positive in all 16
longwave bands and exceeded the numerical floor in all 14 shortwave bands.
This is a scoped local implementation check; exact-head CI is still pending.
The three arms do not include a capture-disabled/enabled pair and therefore
do not establish observer passivity. Their scheme-4 baseline is the retained
project main38 UDM executable, rather than pristine upstream WRF.

This change supplies a native snow diagnosis at a previously undiagnosed
first-call state. It does not establish the radiation LUT's particle-size
definition, validate a radiation PSD or cloud-fraction convention, resolve
number-concentration units, or close the remaining roughly 54 W/m² shortwave
physical-accuracy question. Those physical gates remain open.
