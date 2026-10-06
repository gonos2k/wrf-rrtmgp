# UDM ice-radius fit and size-definition audit

This evidence separates two questions: how the implemented UDM cubic compares with
the recovered reference integral, and whether two radius definitions are identical
for the same particle population. It changes no WRF, microphysics, optics or
radius policy. A numerical verification PASS applies to this calculation only.

## Recovered recipe and authority

[Wyser (1998)](https://journals.ametsoc.org/view/journals/clim/11/7/1520-0442_1998_011_1793_teriic_2.0.co_2.xml)
describes a mixed small-particle gamma/large-particle power-law spectrum, joined
continuously at 20 micrometres. The small branch uses exponent 3 and slope
0.3 per micrometre. The paper uses 10–1000 micrometre integration limits unless
otherwise stated; applying those defaults to its cubic derivation is an explicit
cross-section inference. The stated fit range is `-6 <= B <= -2`.

The calculation uses hexagonal columns with `x=L/D=1` through 30 micrometres and
`x=1+0.003*(L-30)` above that size. Normalization cancels between moment integrals.
The reference proxy and volume/projected-area definitions are evaluated separately:

```
n(L) = L**3 * exp(-0.3*L)                      L <= 20
     = 20**3 * exp(-6) * (L/20)**B             L > 20

rW  = 0.5 * integral(D**2*L*n) / integral((D**2*L)**(2/3)*n)
rVA = (3*sqrt(3)/8) * integral(D**2*L*n)
                    / integral((sqrt(3)*D**2/4 + D*L)*n)
```

Lengths and radii in this calculation are in micrometres. `rVA` is `3V/(4C)`
for the same orientation-averaged hexagonal-column population, not a claim about
the generator of the pinned RRTMGP table. The native coefficients and limits are
authenticated from the implemented UDM source. The literal numerical coefficients
of the paper's equation (35) were not recovered from the retained primary equation
resource; this audit does not verify their transcription against that equation.
See [provenance.json](provenance.json).

## Numerical checks

The portable calculator uses positive Gauss–Legendre quadrature on intervals
split at the spectrum and shape transitions. Two orders check convergence.
For an independent analytic oracle it also evaluates a fixed `D=L` population:
integer gamma moments and power-law moments are integrated analytically, including
the logarithmic special case. There the exact `rW/rVA` ratio is
`(sqrt(3)+4)/(3*sqrt(3))`, approximately 1.1031336923.

The saved sweep includes the reference fit domain and separately labelled
out-of-domain cold extrapolation inputs. Cubic values before and after the native
5.01–125 micrometre bounds are distinct. The cubic calculation is ideal binary64
math. Inputs here begin at a specified B; the temperature/IWC-to-B expression
and its freezing-reference convention are not evaluated. It does not execute the default-REAL Fortran routine or reproduce its rounding.

## Selected controlled inputs

| B | Recipe rW (µm) | Same-population rVA (µm) | Native ideal cubic (µm) | Native bounded value (µm) |
|---:|---:|---:|---:|---:|
| −6 | 10.37396 | 9.40236 | 10.5264 | 10.5264 |
| −2 | 99.54705 | 84.34845 | 103.4832 | 103.4832 |
| −6.873515885 (outside fit) | 9.58291 | 8.68633 | 1.57480 | 5.01000 |

These are specified numerical arguments, not independent observations or a
Fortran replay. The out-of-domain row illustrates extrapolation and a bound;
it does not establish which physical policy should replace that extrapolation.

## Interpretation

A cubic approximation error and a size-definition difference are different
quantities. Neither is automatically a WRF-to-RRTMGP transfer error. In particular,
extrapolation beyond the published fit range is an inherited parameterization
question, separate from PR #102's confirmed warm-ice invalid square root.

The same-population definitions differ even with exact integration. Their ratio
is not a universal ice-radius correction, a pinned-LUT error percentage, a flux
error, or an accuracy assessment. This package does not establish the pinned LUT's
PSD/habit generation, validate Nc units, or prove that large 4/37 flux differences
are normal. It introduces no B clamp, density factor or moment multiplier.

## Reproduce

From the repository root, using only the Python standard library:

```sh
python3 -I -S validation/rrtmgp37/ice-radius-fit-contract/audit.py
```

The verifier authenticates the pinned source and compares recomputed numerical
values to the saved results. CI runs only these mathematical checks; it invokes
no compiler, WRF forecast or RTE solver. The separate PR #102 supplies the native
warm-ice regression and model-preservation evidence.
