# Independent SI Planck/source comparison — design only

Status: prepared design; no integration, solver, forecast, build, or production change was performed.

This note defines a future held-input comparison for one captured 45-layer BON longwave column. The machine-readable plan pins the legacy native Planck export, the current GP input/output and source sidecar, coefficient file, and relevant source files by SHA-256. A later run must recheck every pin before reading values.

Use exact SI constants from [NIST SP 330, Section 2](https://www.nist.gov/pml/special-publication-330/sp-330-section-2): `c=299792458 m s-1`, `h=6.62607015e-34 J s`, and `k=1.380649e-23 J K-1`. NIST's [spectroradiometry note](https://nvlpubs.nist.gov/nistpubs/Legacy/TN/nbstechnicalnote910-8.pdf) gives Planck's spectral-radiance law. For wavenumber `sigma` in m⁻¹, the transformed radiance density is

`B_sigma(T) = 2 h c^2 sigma^3 / expm1(h c sigma / (k T))`.

For band limits in cm⁻¹, multiply each limit by 100 before integrating over m⁻¹. The band radiance is the integral of `B_sigma` over those transformed limits; the blackbody hemispheric exitance check is `pi * B_band`. The full-spectrum check uses `sigma_SB = 2 pi^5 k^4 / (15 h^3 c^2)`. These equations specify future calculations only; no values were evaluated in this task.

Compare only physical bands 3–13, whose common intervals are 500–2250 cm⁻¹. Their edges match between the captured legacy and GP tables. Exclude bands 1–2 and 14–16 because their intervals differ; do not align or average the distinct 140- and 128-g-point grids. At each captured layer, interface, and surface temperature, compare the legacy raw native Planck ordinate and the SI band integral separately from its `DELWAVE`, `WTDIFF`, and `FLUXFAC` conversion. The legacy code's diffuse-flux product is retained intact: `WTDIFF=0.5`, `FLUXFAC=pi*2e4`. Its raw-table scaling must be established from the pinned generation/source convention, not inferred from flux output or tuned to fit.

The GP sidecar stores `SOURCE_LAYER`, `SOURCE_LEVEL`, and `SOURCE_SURFACE` after multiplying per-band Planck values by g-point Planck fractions. It does not store the raw interpolated per-band Planck array or the fractions. Therefore it cannot, by itself, distinguish a Planck normalization difference from fraction closure. The future comparison should either observe `planck_function` and `pfrac` immediately before mapping in the existing kernel, or reconstruct them with the exact pinned table, frontend interpolation constants, interpolation routines, and input state. Report each raw band Planck value, fraction sum, and mapped source separately; never normalize the saved fractions to one.

At GP interior interfaces, the kernel maps the level source with the square root of adjacent-layer fractions. Do not equate that quantity with either adjacent layer's fraction. The legacy surface Planck export already includes surface emissivity; the GP raw surface Planck source does not. Apply emissivity once only when comparing the physical emitted surface source. Legacy band-12 upper-layer fractions are zero in the existing audit even though raw band-12 Planck values remain defined; keep these two fields distinct.

`totplnk` and `plank_fraction` in the pinned GP NetCDF have no units attributes. The legacy source says its units are generally cgs and applies the recorded diffuse quadrature and flux conversion. The solver comments describe GP source arrays as W/m² while applying a later pi angular factor. Resolve those source conventions from the pinned generation and solver code before making a numerical equivalence claim. This design establishes no tolerance, accuracy verdict, or engine preference.

See `plan.json` for artifact hashes, field names, source line locations, exact common band edges, and proposed convergence checks.
