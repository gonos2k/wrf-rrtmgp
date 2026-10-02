# Experimental UDM graupel/hail runtime evidence

This change connects the PR #19 lookup table to UDM27 option 37 through an
explicit opt-in. It does not establish atmospheric graupel/hail accuracy,
NOAA internal coupling parity, or forecast readiness. Mode zero retains
graupel omission diagnostics and positive-hail refusal.

The physical contract is in
[`UDM_FROZEN_EXPERIMENT.md`](../../../WRF/doc/rrtmgp/UDM_FROZEN_EXPERIMENT.md).
The source base is `f8cbfeea7f4c59e5e0655bd2f23e3b424b8359b3`.

## Completed checks

- All 88 standalone CTest cases passed, including new SHA256, strict table
  validation, species optical responses, mass/PSD contracts, V7 replay,
  invalid-input rejection and two/four-thread immutable lookup tests.
- Fortran lookup agrees with the independent Python implementation for 1092
  values per SW moment and 8736 LW absorption values. Maximum differences are
  below 5e-16 in these fixtures. Both implementations consume the same table;
  this is interpolation/units verification, not an independent physical model.
- Seven two-column fixtures (graupel, hail, mixed, cloud plus frozen, tiny,
  overlap zero, zero) passed LW/SW independent executable replay. Raw frozen
  moments had zero maximum difference. Reference and production share the
  frozen lookup module; reference recomputes from inputs rather than recorded
  optics. Python parity provides the separate interpolation implementation.
- Full serial EM Registry regeneration, generated constant compilation, and
  original Registry comparison passed without new generator warnings.
- Fresh isolated GNU 13.3 serial `em_scm_xy` build passed. Its receipt binds all
  13 staged production files before/after compilation and both executable hashes.
- Actual one-minute clear-CF and mixed-cloud UDM SCM fixtures passed. First and
  second LW/SW calls (eight captured phases) matched independently replayed V7
  optics, fluxes and heating; native G/H paths and post-state slopes also matched
  separate Python calculations. Positive G/H at CF=0 remained represented.
- Current mode-zero histories were bitwise identical to the pre-change local
  executable for control/mixed option 37 (209 numeric arrays each) and option 4
  (207 arrays each), using byte-identical initial files. This parent executable
  is a recorded historical build, not a newly built pristine official WRF.
- Fresh isolated GNU MPI `em_real` build passed against workspace MPICH 4.2.0
  ch3:sock. This is build evidence; the 24-hour mode-one forecast is evaluated
  separately and is not included as a passing runtime claim here.

`artifact-index.json` records copied evidence hashes and scratch origins.
`serial-build.json` binds the exact production source bytes. The source tree
and build logs remain in their original scratch directories.

## Reproduction and retained failures

The column build enables OpenMP and links NetCDF from the recorded dependency
prefix. The final suite used `ulimit -s 65536` (KiB): the pre-existing 2048-column
transparent-overlap fixture exceeds an 8 MiB stack when GNU OpenMP makes its
automatic arrays recursive. Actual WRF wrappers still use one column per call.
No batching or forecast performance claim is made.

Earlier attempts are retained in scratch, including the first WRF compilation
that exposed an undeclared SW array extent, and initial replay/CTest driver
failures corrected before the final passing run. The final source uses the SW
wrapper's actual `kts:kte+1` extent. Earlier receipts are not passing evidence.

## Completion boundary

The frozen model uses homogeneous ice spheres, an exponential PSD, fixed
material constants, occurrence fraction one and LW absorption only. Melting,
wet hail, porosity, nonsphericity and atmospheric observations remain outside
this evidence. The table has strict finite slope/temperature axes and runtime
out-of-range rejection. Existing hourly RRTMG4 coverage is not evidence that
all calls of an RRTMGP37 forecast remain inside those axes.

Long MPI forecasts, restart, nests, physical accuracy and the remaining trace
gas/WRF batching work must be evaluated separately.
