# Clear-state reference and first real-input boundary

The PR186 comparison implementation remains complete. This package executes a
pinned **direct upstream** reference and an **independent numerical LW angular
reference** on that same 121-layer clear state, evaluated at native layer 59 /
interface 60. It also implements an exact-zero real-input number producer and
executes a bounded real-data path. Production sources, guards, coefficients and
defaults are unchanged. `production_accepted=false`; the existing seven closure
conditions and RFMIP/LBLRTM FAILs remain unchanged.

## Executed result and decision

| Comparison with public WRF adapter | LW | SW |
|---|---:|---:|
| Direct upstream maximum UP/DN difference, W/m² | 0 | 4.2633e-14 |
| Actual dry molecule columns | identical | identical |
| Direct vendor-library control vs upstream | numerical agreement | numerical agreement |

The direct client links only upstream libraries at commit
`41c5fcd950fed09b8afe186dede266824eca7fd3`, using the pinned g128/g112 data,
WRF constants, **the same available gases in each phase**, boundary conditions
and the actual PR186 molecule bridge. It independently loads coefficients and
constructs optics/source; it does not call the WRF adapter. Thus no current
input/port defect is demonstrated by the PR186 clear difference. This is an
execution/port reference, not independent gas-spectroscopy truth.

The Python reference reuses the existing independent no-scattering recurrence,
then integrates 2μ dμ using Gauss–Jacobi quadrature. It preserves the exact pinned
37 optical depths, layer/level Planck source, surface and vertical-source closure.
One-angle reconstruction is within 1.21e-11 W/m². Successive 512→1024 angle
changes are 9.81e-11 / 2.11e-10 W/m² for UP/DN and 3.98e-10 K/day for pressure
heating. These are **observed refinement changes, not certified true-error
bounds**. Real-cloud representativeness and molecular/source accuracy are outside
this conditional numerical reference.

Signed LW differences at the same locations:

| Quantity | 37 one-angle − angular reference | Angular reference − 4 | 37 − 4 |
|---|---:|---:|---:|
| Surface net down, W/m² | +2.701954 | −0.276681 | +2.425273 |
| Native-top down, W/m² | +0.251244 | −8.440282 | −8.189038 |
| Native-top net down, W/m² | +0.291587 | −6.721443 | −6.429857 |
| Native column convergence, W/m² | −2.410367 | −6.444762 | −8.855130 |

The default angular approximation matters for the surface and column; it does
**not explain the large native-top downward discrepancy**. No change to the
production angle is proposed. Native common-capacity heating profiles are kept
signed in `result.json`; their maxima are not added as if they occurred together.
The angular reference inherits 37 spectroscopy/source, so proximity to it cannot
rank 4 and 37 for physical atmospheric accuracy.

The unchanged legacy caller was rerun with its existing LW-source export enabled.
Its original native output remained byte-identical. Spectral attribution groups
**unions with identical physical bounds**, never g-point or band indices alone.
For native-top downward flux, common 1180–1390 cm⁻¹ contributes −4.712492 W/m²
and 1080–1180 cm⁻¹ contributes −2.354629 W/m² to 37−4. These identify the next
molecular/source investigation, not an isolated absorber or source error. All
121 layers, including the upper extension, were retained. Legacy lookup/source,
actual band diffusivities and flux-conversion metadata are preserved. No Planck
native-unit record is silently relabelled SI or compared to a different spectral
interval.

**Disposition:** retain the current engineering baseline. No demonstrated port
fix or tuning is justified. Conditional transport has been tested; physical
spectral/source accuracy in the dominant interval still needs an appropriate
independent reference. That limitation does not reopen PR186 implementation.
SW retains its original low-Sun geometry; no noon/day-average claim is made.

## Actual input and boundary progress

`zero_number_input.py` processes the existing real.exe-produced Matthew initial
and eight-time specified-boundary dataset (90×99×44 interior). It requires exact
zero for all six condensate masses, available UDM numbers, every lateral side
and every lateral tendency. Nonzero/nonfinite values or missing required fields
are rejected before output. It copies the files, declares `eta=n/rho_d=0` and
population0, and verifies **every original variable array is unchanged**. It
never guesses a nonzero Nc, overwrites density, or deletes condensate.

The existing input has actual temperatures approximately 192.175–303.678 K.
It is not an all-warm research input. Two qualified current-executable processes
were executed:

* **number0/population0, LW37/SW37:** actual specified-boundary input read and
  20 model seconds completed (two 10-second steps). Research capacity and size
  options remain OFF. This is a short path smoke, not a forecast/accuracy or
  mixed-phase scientific approval. Terminal history was not requested; success
  is established by the recorded step and completion logs, not a terminal-array
  comparison.
* **number1/population0, produced zero input:** matching file/namelist number
  metadata passes to the next boundary, where the existing specified/nested
  guard rejects before history. **Number1 specified-boundary support is still
  not implemented.** The producer resolves only the previously ambiguous zero
  representation; it does not bypass that guard or support nonzero inflow.

The next real research-path implementation therefore needs a validated
specified-boundary number contract, not a density/radius scaling. The exact-zero
producer and legacy real smoke are reusable evidence; generic mixed-phase,
nonzero inflow, nested/MPI and warm population2 support are not claimed.

## Evidence, execution counts, and replay

Qualified new diagnostic work: **5 radiation processes / 6 engine calls**
(two direct upstream, two direct vendor control, one paired source-export process),
plus the numerical Python integration. These counts exclude internal radiation
calls in the separate WRF smoke. Qualified WRF processes: **one 20-second success
and one intentional pre-history refusal**. They are not independent weather
cases. No Mie, new 24-hour run or new reference dataset campaign was performed.

The full development command archive is retained, including the initial client
compile failure, intermediate extra-gas SW client, and two failed real staging
attempts. The latter used an empty iofields filename and failed in
`modify_io_masks`; restoring the original valid iofields file resolved staging.
A stack-limit retry did not resolve that problem. Neither those attempts nor
the extra-gas SW client are accepted scientific evidence. Two debugger attempts
(one loader failure, one reproduced staging failure) are noted separately.
The final SW client uses exactly the six available adapter gases and its raw
TAU/SSA/G match the saved adapter exactly. This corrects the diagnostic setup,
not production physics.

The original large real NetCDF files remain in build storage, content-pinned in
`identity.json`. The package publishes complete variable-array hashes, checked
zero-field shapes/hashes, namelists, actual logs and process records. Saved CI
replay does not reread those external NetCDF files or launch WRF. The local
producer tests actually use NetCDF and reject nonzero initial mass, nonzero
boundary number tendency, and nonfinite number.

From this worktree, with the pinned build directories available:

```sh
python validation/rrtmgp37/clear-reference/execute.py
python validation/rrtmgp37/clear-reference/vendor_control.py
python validation/rrtmgp37/clear-reference/angular.py
python validation/rrtmgp37/clear-reference/bands.py
python validation/rrtmgp37/clear-reference/real_path.py
```

Execution scripts require fresh output directories; the versioned names refer to
this recorded campaign and must be changed for a deliberate future campaign.
Their Runner records actual PID/return code/timeouts; serial fatal success is
judged using messages and artifacts. `deposit.py` freezes those bounded outputs.

Stored replay (stdlib only, no new model execution):

```sh
python -I -S validation/rrtmgp37/clear-reference/verify_saved.py
python -I -S validation/rrtmgp37/clear-reference/test_saved.py
```

The verifier checks source/evidence hashes, actual direct fluxes and molecules,
SW raw optics, independent one-angle recurrence, coarse/fine signed quadrature
arrays, native targets, physical spectral groups and the scoped real decision.
Five semantic tests reject physical approval promotion, extended-TOA substitution,
index-only spectral matching, boundary-support promotion and failed refinement.
The existing acceptance runner adds this replay without making another top-level
gate. Physical tolerances remain unspecified and were not invented from results.

After the specified-number implementation changes input/boundary sources, this
PR187 package remains a historical replay. The central historical-source binding
checks the original bytes/digests and reports `current_runtime_source_matches=false`;
it does not certify the new specified-boundary implementation.
