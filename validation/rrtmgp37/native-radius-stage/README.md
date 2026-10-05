# Actual UDM radius generation and consumption evidence

This archive preserves a manufactured warm, saturated UDM27 SCM column captured
with PR #99's generation/consumption instrumentation. Its pinned production
sources match `d3d8fa7dcc9246ebd739f96a21daa8739c955c54`; later registration and
workflow-only fixes are not new model runs. It makes the saved
producer/consumer comparison reproducible without compiling or running WRF.
It does not change radiation, microphysics, number concentration, or particle size.

## Saved transfer

The eight original raw packets contain six successive UDM-return states and one
LW plus one SW radiation call. The radiation calls at step 2 consume all three
radius arrays from the latest earlier UDM producer, step 1, exactly as promoted
binary64 values. The producer time is 0 seconds and consumer time is 10 seconds.
At consumption, temperature differs in 38 layers and density in 59 layers;
recomputing a radius from that newer state would compare different generation
stages. The retained radii themselves are unchanged.

There are 198 wet liquid **layer rows across six packets of one manufactured
column**, with 33 active rows per packet. These are not 198 independent cases.
Neither the conditional liquid formula nor its alternative unit interpretation
activates the 2.51–50 micrometre bounds in these saved rows.

The original local SCM result is retained as context. Archive verification checks
stored evidence and source identity; it does not rerun that forecast, independent
RTE replay, or observer-invariance experiment. Earlier PR #99 contains those
runtime checks. The model was serial and this archive does not validate a
parallel capture, initialization/restart radius origin, or a real-data forecast.

## Conditional number-concentration calculation

For the same numeric tuple, using SI numeric values for density and water density,
the two explicitly conditional formulas are

```
Nc interpreted as #/m3: r_v = [3 rho qc / (4 pi rho_water Nc)]**(1/3)
Nc interpreted as #/kg: r_m = [3     qc / (4 pi rho_water Nc)]**(1/3)
```

Their numeric ratio is `r_v/r_m = (rho expressed in kg/m3)**(1/3)`. Keeping the
same numeric Nc while changing its unit interpretation describes different
populations; this ratio is not a measured physical error or a unit conversion
between the same population.

For these saved rows:

| Quantity | Result |
|---|---:|
| Density | 0.8528885841–1.1869719028 kg/m3 |
| Conditional radius ratio | 0.9483400687–1.0587988955 |
| Maximum native minus volume-style ideal formula | 4.3529983e-12 m |
| Maximum native minus mass-style conditional formula | 5.4692818e-7 m |

Agreement with the volume-style formula checks the native implementation on its
actual generation tuple. Default-REAL rounding is present; exact agreement with
an ideal binary64 formula is not asserted. It does not establish Nc's physical
units, a radiation PSD, its required radius moment, or radiative accuracy.

The [source audit](evidence/nc-source-review.json) and its
[qualifying supplement](evidence/nc-source-supplement.json) retain the unresolved
convention: native slope/radius
expressions require volume concentration for dimensional closure, while the
Registry labels QNCLOUD as mass-specific. Existing in-range numbers pass without
a systematic density conversion. A generic real.exe number-synthesis block
returns mass-specific values but excludes UDM, so it is not authority for this
UDM fixture's initial number convention. The native `nc*rho` small-number guard
is also distinct from the slope expression; the audit does not establish an
independent physical-unit definition for that guard threshold. The supplement
qualifies the original audit's stronger wording; the guard is not evidence of
an operational error, and the source conflict does not establish the units of
every imported positive Nc value.

No density multiplier, gamma-moment correction, or radius default is introduced.
The physical unit and radius-moment contracts remain open. These results do not
classify all RRTMG4/RRTMGP37 differences as expected or accurate.

## Reproduce

From the repository root:

```sh
python3 -I -S validation/rrtmgp37/native-radius-stage/verify.py
```

The default source root is the current checkout. After changes to a pinned
source, this command deliberately fails its original hash check. To verify
these historical packets, provide a checkout of PR #100 commit
`845d4ba72619539920a15d64bc90c5ca56da8971`:

```sh
python3 -I -S validation/rrtmgp37/native-radius-stage/verify.py \
  --source-root build/native-radius-stage-historical-source
```

CI checks out that fixed commit separately for source verification and parser
imports. The package, raw packets, saved results and all original source pins
stay unchanged; this does not label the archived outputs as results from newer
native-radius code.

The verifier authenticates the payload roster, raw packets and pinned source
files; re-runs the saved stage join; and independently evaluates both conditional
unit formulas on all 198 wet rows. The optional `--output FILE` writes a new
receipt and refuses overwriting an existing file. Original evidence is retained.
The CI job performs these saved-data checks and invokes no model or solver.
