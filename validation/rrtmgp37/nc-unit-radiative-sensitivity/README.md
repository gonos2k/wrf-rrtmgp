# Conditional UDM number-unit radiative sensitivity

UDM's liquid-radius slope uses the stored number directly with condensate mass
per volume. The Registry labels transported number fields as `#/kg`, while the
CCN activation water increment divides embryo mass production by `DEN` and adds
the unscaled number increment. The default CCN initializer also copies a
volumetric concentration directly. These source-backed conventions conflict,
and other native expressions use density again. This package measures the
radiative consequence of two conditional interpretations; it changes no
production microphysics, transport, radius, or radiation policy.

The [source review](source-review.json) distinguishes a dry-pressure-coordinate
RK weight from physical parcel compression. It does not establish the units of
every initial, boundary, or restart number field, or a universal density basis.
A uniform density multiplier is not supported by this evidence. Option 37 uses
UDM's native radius, so an inherited native-number convention can affect this
coupling even when the radius is transferred faithfully. This is not evidence
that all remaining differences are radiation-engine discretization differences.

## Held calculation

The saved manufactured warm UDM27 column joins the step-1 producer at 0 seconds
to the step-2 LW/SW consumer at 10 seconds. The producer's temperature and density
are not the later consumer's state. All radii in this experiment are derived
from the earlier producer tuple and applied to the same fixed later radiation
state. There are 33 active liquid layers of one column, not 33 independent cases.

The completed matrix has three liquid-radius arms in each phase:

* **A — native:** original captured `REL`, including host REAL rounding.
* **B — volume interpretation:** binary64
  `r_v = [3 qc rho / (4 pi rho_water Nc)]^(1/3)`.
* **C — mass-specific interpretation:** binary64
  `r_m = [3 qc / (4 pi rho_water Nc)]^(1/3)`.

The native wet-layer guards and 2.51–50 micrometre bounds are retained. Only
`REL` record values are changed relative to each phase's physical-input base. Inactive layers and
upper extensions are untouched. Seeds, cloud fraction, paths, pressure,
temperature, gases, surface inputs, ice, and precipitation remain fixed.
The derived inputs are counterfactuals, not observed WRF captures; source-radius
records are not rewritten to claim otherwise.

Keeping the same numeric `Nc` while changing its unit interpretation describes
different particle populations. `C-B` is therefore a conditional sensitivity,
not a physical unit conversion or measured error. `B-A` controls ideal-math and
default-REAL rounding. The exact same executable reproduced the saved native
baseline bytes locally before the alternatives were evaluated.

Within each three-arm calculation, gas optics, dry columns, clear-sky output,
McICA masks, ice diameter, snow size, and precipitation optics must remain exact.
All active liquid alternatives lie within the pinned 2.5–21.5 micrometre liquid
LUT. The warm ice diameter still clips to 180 micrometres in every arm; a native
ice **radius** around 103 micrometres does not prove that its doubled diameter
lies inside the LUT. This experiment does not test an ice policy.

For **C minus B**, the held-state results are:

| Metric | LW | SW |
|---|---:|---:|
| Surface downward flux (W/m²) | +0.01235077 | −0.10144265 |
| TOA upward flux (W/m²) | +0.00002933 | −0.51818779 |
| Surface net downward flux (W/m²) | +0.01216551 | −0.08419740 |
| Maximum absolute native heating difference (K/day) | 0.05354567 | 0.09352867 |

The exact signed values and profiles are preserved in `evidence/local-result.json`.
The maximum B-minus-A heating changes are below 6e-7 K/day in both phases;
those are rounding controls, not the unit-interpretation effect. Small flux
effects in this optically thick manufactured column do not bound other states.

## Reproduce

Authenticate the saved files and exact source/coefficient pins without running
a compiler, model, or solver:

```sh
python3 -I -S validation/rrtmgp37/nc-unit-radiative-sensitivity/verify.py
```

For six fresh standalone RTE calls, build the existing independent reference
target, then invoke `replay.py` with the archived capture, coefficient directory,
and a new output directory. The replay script's `--help` gives its exact CLI.

```sh
cmake -S WRF/test/rrtmgp -B build/nc-unit-reference \
  -DRRTMGP_DATA_DIR="$PWD/WRF/run"
cmake --build build/nc-unit-reference --target reference_column --parallel 2
python3 -B validation/rrtmgp37/nc-unit-radiative-sensitivity/replay.py \
  --capture-dir validation/rrtmgp37/nc-unit-radiative-sensitivity/capture \
  --reference-exe build/nc-unit-reference/reference_column \
  --data-dir WRF/run \
  --expected-result-dir validation/rrtmgp37/nc-unit-radiative-sensitivity/expected \
  --baseline-mode numeric --output-dir build/nc-unit-replay
```

The CI job checks saved evidence and runs the six-column replay with a newly
built reference executable. Across toolchains, numeric comparison of stored
outputs is separate from exact within-run control checks and the original
local byte-identical baseline. A numerical match does not retroactively claim
bitwise identity across compilers.

### Original SW oracle and counterfactual protocol

The first attempt kept the full SW V9 recorded-optics input and changed only
`REL`. Its raw-cloud-optical-depth oracle correctly rejected the volume arm:
the old recorded optical depth no longer described the new radius. Five solver
attempts had occurred at that point; four produced outputs, and the SW mass arm
was not launched. That stopped experiment, log, and its accounting are retained.
The original guard and failed result are not weakened or promoted to a pass.

For a separate SW sensitivity, the physical input is projected to the existing
V6 protocol: the magic is changed and the trailing pre-delta diagnostic/oracle
records are removed. Every physical field, native dry layer mass, constant,
surface setting, seed and header value is retained. In the original same-executable
local experiment, the projected native arm had to exactly reproduce all common
output sections of the original V9 replay before either counterfactual arm was
launched. Four pre-delta diagnostic outputs
are absent under V6; this test makes no claim about their counterfactual values.
Only `REL` differs among the three V6 arms. This explicit projection is not a
rewritten observed capture or a new optical oracle manufactured to pass.

The successful matrix reuses the three completed LW outputs and adds three SW
V6 calls. Including the earlier original-SW baseline and rejected SW variant,
the local execution ledger records **eight attempts: seven outputs and one
rejection**. A fresh CI reproduction runs six matrix arms; those are separate
executions, not additional WRF forecasts.

The portable script was also validated locally in six further calls using the
same retained reference executable, with **exact baseline mode**. Those six
passed; the complete local ledger for this work is therefore **14 attempts,
13 output-producing calls, one original V9 rejection, and zero WRF forecasts
or builds**. The preserved v2 shape-check error and v3 preflight NameError are
Python harness failures; the latter launched no solver. They are not additional
physical solver failures. CI's new build and six calls are counted separately.

## Remaining contract

This single operational-seed test is neither an ensemble nor a coupled forecast.
It does not select the physically intended Nc convention, determine the liquid
radiation PSD/moment, or validate optical accuracy. The inherited mixed unit
contract needs a consistent producer, storage, transport, process, and radius
definition before any correction is justified. RRTMG4 is unchanged. Large
RRTMG4/RRTMGP37 differences cannot all be classified as normal from this result.
