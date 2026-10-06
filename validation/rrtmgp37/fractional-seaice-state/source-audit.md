# Winter QZ0 and USTM restart-field source audit

This is a source and restart-field audit, not a forecast rerun or a claim that either field is harmless. It explains two narrowly identified undefined reads in the fractional-sea-ice surface wrappers and records the scoped correction tested in the isolated PR46 worktree.

## QZ0

`module_surface_driver.F:1961-1962` sets `myj` only for `MYJSFCSCHEME` and `QNSESFCSCHEME`. Those are the paths that provide `QZ0_SEA`: the MYJ surface wrapper copies `QZ0_HOLD` into it at line 4925 and the QNSE wrapper does so at line 5291. The active `SFCLAY_SEAICE_WRAPPER` does not take or produce `QZ0_SEA`. Before the patch, all four fractional-sea-ice mixing blocks at the four blocks now at lines 3053, 3417, 4029, and 4248 read `QZ0_SEA` unconditionally. For SFCLAY configurations, the read therefore used an uninitialized local. The fix guards each existing weighted QZ0 blend with `IF (myj)`, retaining the original MYJ/QNSE weighting and skipping the undefined input for other schemes.

## USTM

The active `SFCLAY_SEAICE_WRAPPER` has optional USTM declared optional `INTENT(INOUT)` at line 6515. It calls the ice/land surface calculation first and the open-water calculation second. The second call receives local automatic `USTM_SEA`, which had no assignment before the call. The actual `module_sf_sfclay.F:802-803` update reads its old USTM value (`0.5*USTM + ...`) before writing the new value. `SFCLAYREV` has the same wrapper pattern; its actual implementation copies USTM into `USTM_HV` at line 203 and later writes it back at line 279, so it also consumes the incoming value. The isolated correction saves the incoming wrapper USTM before the first call and initializes each second-call USTM scratch from that saved state. If optional USTM is absent, the wrapper initializes its otherwise-unused scratch to zero; the test does not claim that the full EM_CORE SFCLAY entry supports an absent USTM argument, since its outer routine forwards `USTM(ims,j)` without a `PRESENT` guard.

The winter run used SFCLAY, so the SFCLAYREV correction prevents the same source defect for that wrapper but is not credited as a fix demonstrated by this case. No SFCLAY `PSIX` calculation, clipping, or surface physics was changed.

## Evidence and limits

The prior RA37 24-hour run completed its forecast history but failed strict checkpoint finiteness checks: USTM and QZ0 contained nonfinite or extreme values. Same-binary RA4 preservation showed finite checkpoint fields and byte-identical history against its recorded baseline. Those cross-run observations are consistent with the source audit but do not independently establish the cause of every bad checkpoint value. The correction does not sanitize prior checkpoint data; a fresh initialization and a new restart validation are required to establish corrected runtime behavior.

`test_fractional_seaice_state.py` compiles the actual SFCLAY source with `-DEM_CORE=1` and `-finit-real=snan`, exercises the production SFCLAY1D USTM recurrence, and compiles wrapper statements extracted from the production source. Its source-derived negative control removes only the new snapshot/restore and MYJ guard and demonstrates NaN propagation for partial/full ice USTM and non-MYJ QZ0; the patched sequence is finite for no/partial/full ice and a repeated timestep. This sentinel test demonstrates propagation of an undefined value, not the exact arbitrary bit pattern of an uninitialized local in the forecast.

Frozen production source hash: `fc99b8e6837573ed2335b6dd7bf62071c2da91348e4c5bf8668d780933f7c6cd` (`WRF/phys/module_surface_driver.F`). The test receipt is at `build/udm-winter-qz0-ustm-audit/test/source-test-receipt.json`.
