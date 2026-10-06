# Bounded legacy LW source export

Set `WRF_RRTMGP_RRTMG4_EXPORT_LW_SOURCE=1` with the existing export directory
and all five selected-column keys to add LW source records. Unset or `0`
keeps the original four-stage packet. Invalid flags and `1` without an export
directory are rejected. SW exports do not add LW records. Serial execution
and one OpenMP thread remain required by the existing observer.

The additional records come from the actual selected first-column `rtrnmc`
call, after gas/cloud preparation and before broadband result mapping. This
observer copies values; it changes no radiation formula, coefficient or angle.
Optional chemistry clean-sky calls do not emit this source group.

`RTE_PLANCK_LAYER_NATIVE` and `RTE_PLANCK_LEVEL_NATIVE` have `(band,layer)`
and `(band,interface)` layouts. Interface slot 1 is original Fortran level 0
(surface). `RTE_PLANCK_FRACTIONS` has `(gpoint,layer)` layout.
`RTE_PLANCK_SURFACE_NATIVE` already contains the emissivity treatment from
`setcoef`; consumers must not apply emissivity a second time.

The four `RTE_BAND_*_NATIVE` arrays use `(band,interface)` and preserve
`uflux`, `dflux`, `uclfl`, `dclfl` exactly before band-width multiplication,
broadband accumulation, and final flux conversion. Multiply by the recorded
`RTE_DELWAVE`, accumulate in original band order and native precision, then
apply `RTE_FLUXFAC` to reconstruct the existing broadband result. They are
not separately rounded band fluxes in W/m2. Preserve the recorded
`RTE_WTDIFF` when independently reconstructing radiances.

`RTE_SECDIFF` contains the actual band diffusivity values; it is not inferred
from precipitable water by a separate formula. `RTE_TABLE_BOUNDS` gives the
Fortran lookup-table lower/upper indices. The stored tau, exponential and
transition tables retain native precision and first-index order. The recorded
`RTE_TBLINT`, `RTE_BPADE`, `RTE_REC_6`, and `RTE_HEATFAC` complete the
clear-sky recurrence and heating conversion inputs.

The native Planck/radiance units are deliberately kept with their actual
conversion factors. A field label alone must not be treated as SI radiance.
This observer provides source/transport attribution evidence; it does not
establish an independent physical truth, observational accuracy, or equality
between the different RRTMG and RRTMGP spectral discretizations.
