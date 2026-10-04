# Erratum to frozen CF-zero precipitation design v2

`build/udm37-cf0-precip-audit-design-v2` remains unchanged. For its pinned raw files, a fresh direct count finds 16 strictly positive `RWP_OMITTED` layers at the rain anchor, not 17; the 13 snow layers have strictly positive `SWP_OMITTED` values, not six. Six snow paths exceed 1e-8 g m-2; seven are smaller positive traces, with minimum about 2.92e-18 g m-2. No cutoff is applied to the candidate sidecars. Phase-specific file hashes, every active layer and radius-source eligibility are in `captured-layer-audit.json` and `captured-layer-audit.md`.

The snow radius eligibility check found `HAS_REQS=1`, source values not equal to float32 `RE_QS_BG=9.99e-6 m`, `RES` mapped from `SOURCE_RE_SNOW` in metres to microns, and all 13 active `RES` values >10 µm. The WRF wrapper fallback for background radii is conditional on CF>0, so it does not replace these CF-zero-layer source values. This proves captured input eligibility for the proposed parameterized optics, not the physical provenance of each microphysics radius.

No build or solver call was made while preparing this erratum. The four-call unmodified original baseline remains the only executed standalone solver baseline for this design.
