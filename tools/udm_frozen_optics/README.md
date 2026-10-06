# Experimental UDM frozen-particle optical reference

This offline package generates an inspectable numerical reference for the
unresolved UDM27 graupel/hail radiation path. It does **not** enable that path in
WRF, relax positive-hail rejection, change RRTMG4, or validate a forecast.
The material/geometry model is a homogeneous ice-Ih sphere with an exponential
diameter distribution. It is an explicit experimental approximation, not a
reproduction of NOAA's internal UDM radiation configuration.

## Reproduce

Requirements: GNU Fortran, Python 3, NumPy, SciPy and netCDF4. The optional
independent kernel check additionally requires `miepython==3.0.2`.

```bash
python3 tools/udm_frozen_optics/test_reference.py \
  --output-dir build/frozen-kernel-check

python3 -m venv --system-site-packages build/frozen-reference-venv
build/frozen-reference-venv/bin/pip install --require-hashes --no-deps \
  -r tools/udm_frozen_optics/requirements-independent.txt
build/frozen-reference-venv/bin/python tools/udm_frozen_optics/independent_mie_check.py \
  --output-dir build/frozen-independent-check

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 tools/udm_frozen_optics/generate.py \
  --input-dir build/frozen-input --fetch-inputs \
  --output-dir build/frozen-o64-s50 \
  --lambda-grid 300 2000 20000 --temperatures 180 233 250 300 \
  --order 64 --spectral-step 50 --workers 8

python3 tools/udm_frozen_optics/test_artifacts.py \
  --generation build/frozen-o64-s50 --output-dir build/frozen-artifact-check
```

Use a new output directory for each run. Failed/partial evidence is preserved;
only `result.json` with a complete status accompanies a final NetCDF table.
The pinned inputs are fetched only on request and verified by SHA256. Their raw
bytes are not redistributed here. Gas coefficients supply the exact 14 SW and
16 LW band bounds; coefficient, material, solar and source hashes are retained.
Changes during execution prevent final attribution to the starting sources.
The comparator also checks table/task identities against this checkout's exact
generator and pinned sources. Use the corresponding checkout for historical
receipts. A local compiled library and adaptation manifest are verified when
present; a portable table/receipt without them does not prove the binary's bytes.

Generate a second table with different numerical controls, keeping axes and
source choices identical, then compare:

```bash
python3 tools/udm_frozen_optics/compare.py \
  --candidate build/frozen-o64-s50 --reference build/frozen-o128-s50 \
  --output build/frozen-order-comparison.json
```

This reports differences without granting a scientific PASS. The optional
`--max-extinction-normalized-error` applies a caller-selected **numerical**
tolerance only. Validate spectral spacing, quadrature order, interpolation and
state coverage separately before using a table in a model.

## Mass and size contract

Let diameter `D` be in metres and `N(D)=N0 exp(-lambda D)`. For the chosen sphere
model, particle mass is `rho_bulk*pi*D^3/6` and optical cross section is
`Q*pi*D^2/4`. The analytic PSD mass integral is `pi*rho_bulk*N0/lambda^4`.
Consequently the table stores

```text
kappa * rho_bulk = (lambda/4) * integral exp(-u) u^2 Q(u) du
u = lambda D
```

The variables have units **m-1**. Recover a mass-specific coefficient in m2/kg
by dividing by the particle bulk density, then multiply the **actual** water
path in kg/m2 to get dimensionless optical depth. A water path in g/m2 needs a
factor of 1e-3. `N0` cancels from these normalized coefficients; it remains
relevant to reconstructing a slope from the host state.

The public UDM constants in this repository are:

| Category | N0 (m-4) | Bulk density (kg/m3) |
|---|---:|---:|
| Graupel | 4e6 | 500 |
| Hail | 4e4 | 912 |

For active mass, UDM's spherical PSD closure is
`lambda=(pi*rho_bulk*N0/(rho_air*q))^0.25`, capped at 20000 m-1. Its process
cutoff is `q=1e-9` kg/kg, with the capped slope as the small-mass sentinel.
`lambda` is **not an effective radius**: UDM's inverse slope `1/lambda` differs
from the separate geometric sphere volume/area metric `R_eff=3/(2*lambda)`.
No liquid/ice/snow radius from the host is substituted for a graupel/hail slope.

UDM's process slope uses moist-air density. Radiation mixing ratios are on the
dry-air basis and their grid water paths use native dry-layer mass. UDM also
updates its final slopes before sedimentation, whereas returned hydrometeors
are after sedimentation. A slope reconstructed from returned `q` and density
is therefore a **state diagnostic**, not an exact exported process slope.
At the cutoff/cap, the fixed-N0 PSD's analytic mass need not equal `rho_air*q`.
Using normalized coefficients and the actual host path is an explicit
mass-normalized model, not a claim to reproduce the host number moments.

## Spectral and material contract

* Ice index: the static [Warren–Brandt ice-Ih compilation](https://atmos.uw.edu/ice_optical_constants/).
  Real index is linear in log wavelength; log imaginary index is linear in log
  wavelength. Some source measurements were adjusted to 266 K. The requested
  LW temperature changes Planck weighting, **not** the material index.
* SW source: NOAA's
  [NNLSSI1 reference spectra](https://www.ncei.noaa.gov/data/solar-spectral-irradiance/access/ancillary-data/),
  file `tsi-ssi_v03r00_reference-spectra_c20240830.txt`, `BaselineModel` column
  in W m-2 nm-1. This is distinct from RRTMGP gas-optics NRLSSI2. Conversion to
  wavenumber weighting includes `abs(d lambda_nm / d nu_cm)=1e7/nu_cm^2`.
* LW source: Planck wavenumber shape `nu^3/expm1(h*c*100*nu/(k*T))`, normalized
  separately within each band and temperature. Common radiance factors cancel.
* Moments retained: extinction, scattering, scattering times asymmetry, and
  absorption. For an absorption-only LW solver, use **absorption**, not
  extinction. LW scattering is not implemented by this tool's existence.
* Quadrature: Gauss–Laguerre integration in `u` constructed by the symmetric
  Jacobi eigenproblem (Golub–Welsch, fixed LAPACK STEV), checked against exact
  polynomial moments before spectral work. Uniform band wavenumber integration
  includes both endpoints; nonoverlapping worker chunks retain the full-band
  trapezoid weights and combine in a fixed node order. Nodes with `weight*u^2<=1e-16` are
  pruned; area- and mass-weight fractions are recorded. Those fractions alone
  are not a complete radiative error bound. A recurrence workspace limit
  never causes a particle node to be silently deleted: the run fails instead.

The same solid-ice index combined with different bulk densities changes mass
normalization only. It does not infer a porous effective-medium index, wet
coating, nonspherical habit or mixed phase. These remain physical model choices.
[Hill et al. (2018)](https://doi.org/10.1029/2018MS001415) provide precedent for
Mie-based precipitating frozen-particle optics, but use different densities,
material data and band parameterizations. This tool does not reproduce their
coefficients or establish observational accuracy.

## Kernel provenance and precision correction

The minimal kernel is from [Met Office SOCRATES](https://github.com/MetOffice/SOCRATES/tree/3709ddf63086731a9976f0f08ca571760dac15ac),
commit `3709ddf63086731a9976f0f08ca571760dac15ac`, BSD-3-Clause. `socrates/`
retains exact original bytes, `COPYRIGHT.txt` and `LICENCE`; `SOURCE.json` pins
each file. The compiled copy adds `KIND=RealK` to four `CMPLX` constructors.
The diff and both source hashes are written under each output's `kernel/`.
Three constructors otherwise lower the double-precision Riccati-Bessel values
to default single-precision complex values before widening them again.

An actual GL32/SW12 weak-absorption node (`n=1.3162090691501627`,
`k=6.647598667764746e-11`, `x=15.82866539592279`) made the original kernel
return `Qsca>Qext`. The corrected constructors restore positive absorption;
the zero-absorption limit also closes. `test_reference.py` builds both paths
and reproduces that counterfactual. It additionally checks three published
[Du (2004) MIEV0 benchmarks](https://doi.org/10.1364/AO.43.001951), large dynamic
recurrence workspaces, invalid inputs, analytic PSD normalization, and SW/LW
spectral transformations. This correction does not relax the physical bounds
or project Mie efficiencies onto them.

`independent_mie_check.py` compares 20 representative weak-absorption and general
fixtures with a pinned independent pure-Python Mie implementation, including
the negative/positive imaginary-index convention. Its receipt binds the
independent module tree, corrected source and compiled library. This isolates
kernel arithmetic; it does not establish band-table or model accuracy.

`test_quadrature.py` checks orders through 1024, agreement with the independent
SciPy special-function rule through 256, and rejection of nonfinite/invalid
weights. The generator limits requested order to 512. A preliminary 512-order
special-function run returned nonfinite weights on the tested SciPy version;
its zero-coefficient artifact is invalid and was excluded. Polynomial moment
agreement does not by itself imply convergence of an oscillatory Mie integrand.

## Remaining integration gates

The lambda/temperature fixtures above are a numerical test matrix, not a
production interpolation grid. Live WRF support still needs an explicit
experimental model selector, validated interpolation/range rejection, mass and
occurrence contracts, all nonzero qg/qh consumption, trace/replay extensions,
species limits, same-state RRTMG comparison, and full real-case restart/MPI/
OpenMP/24–48-hour checks. Default hail rejection remains in force until such a
path is implemented and reviewed. Material and forecast accuracy require
independent evidence in addition to numerical convergence.
