# UDM ice size and the cloud-optics lookup coordinate

The adapter passes a diameter coordinate to the RRTMGP ice lookup. UDM supplies
an empirical ice **radius**; the conversion `D = 2 re` is explicit in the
adapter. This confirms a radius-to-diameter coordinate conversion, but it does
not by itself prove that the UDM radius and the lookup-table diameter describe
the same physical size metric.

UDM's ice polynomial matches the form and coefficients of Wyser Eq. (35).
This attribution is an inference from the equations: the local source credits
Soo Ya Bae (2015) and does not cite Wyser explicitly.

Wyser (1998) defines a spherical effective radius as a cross-section-weighted
mean. For nonspherical ice, the paper discusses several possible definitions.
Its Eqs. (19)–(20) use a single-particle geometric proxy for randomly oriented
hexagonal columns and a cross-section-weighted population average. Eq. (35) is
a third-order fit to that Eq. (20) value using the paper's assumed size
distribution and column geometry. The paper does not establish that this fit
equals a generic volume/projected-area radius for another habit or PSD.

There is a conditional factor-two identity: if both size variables use the
same PSD, habit weights, volume, and orientation-averaged projected area, then
`r_VA = 3 V_total / (4 A_total)` and the volume/projected-area effective
diameter `D_VA = 3 V_total / (2 A_total)` satisfy `D_VA = 2 r_VA`. This
identity must not be conflated with Fu's generalized effective size `Dge`, or
treated as proof that the UDM Eq. (35) radius is the metric used to generate
the pinned RRTMGP table.

The pinned table metadata and loader identify diameter-named ice bounds and
the frontend attributes ice optics to Yang et al. (2013). The pinned public
materials inspected here do not identify the table's PSD, habit mixture,
volume/projected-area convention, or integration recipe. Thus the physical
metric match remains unresolved: no factor-two defect is proven, and no
additional multiplier is justified by these sources. See
[`ICE_SIZE_METRIC_SOURCES.json`](ICE_SIZE_METRIC_SOURCES.json) for source
pins, references, and the bounded provenance finding.

## Primary references

- [Wyser (1998), *The Effective Radius in Ice Clouds*](https://doi.org/10.1175/1520-0442(1998)011%3C1793:TERIIC%3E2.0.CO;2), [AMS publisher text](https://journals.ametsoc.org/view/journals/clim/11/7/1520-0442_1998_011_1793_teriic_2.0.co_2.xml).
- [Wyser and Yang (1998), *Average ice crystal size and bulk short-wave single-scattering properties of cirrus clouds*](https://doi.org/10.1016/S0169-8095(98)00083-0).
- [Yang et al. (2013), *Spectrally Consistent Scattering, Absorption, and Polarization Properties of Atmospheric Ice Crystals*](https://doi.org/10.1175/JAS-D-12-039.1). The DOI is also listed in the [NASA author record](https://www.giss.nasa.gov/pubs/abs/ya07100h.html).

The AMS indexed primary text was available during this review, but direct page/PDF
access returned HTTP 403; no local Wyser PDF was acquired or hashed. The
equation discussion above is a concise structural summary, not a transcription
of image-rendered equation normalization.
