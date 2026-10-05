# BON dry-column intervention terminal review

Read-only independent review of the single-call diagnostic. The runner receipt records one unique solver PID (149609), RC 0, no timeout, and zero WRF/REAL/build invocations. Its 120 before/after file pins and 47 resolved runtime paths are unchanged.

The original BON replay input has a 32-level native dry-mass prefix in a 45-level LW V10 solver column. The diagnostic input changed only that record: its count is 45 and its 45 values are converted from the same-call legacy `COLDry` observer export. Every byte before and after the mass record is identical. Reconstructed counterfactual mass and result `GAS_COL_DRY` match the export within a maximum relative difference of 2.22e-16. Fourteen cloud/CU/precip/frozen/radius/mask sections are exactly unchanged; remaining changed sections are DN, DNC, GAS_COL_DRY, GAS_TAU, GAS_TAU_RAW, HR, HRC, TOTAL_TAU, UP, UPC.

Recomputed surface downward fluxes are GP native dry 189.08001140830, GP legacy-column matched 189.08751473673, and RRTMG4 observer 187.83763122559 W/m². The original direct GP-minus-legacy difference is +1.24238018271 W/m², decomposed into dry-column response -0.00750332844 W/m² plus matched-column residual +1.24988351115 W/m² (algebra residual 0). The WRF REAL32 boundary comparison is +1.24238586426 W/m² and is reported separately. The residual combines engine/spectral and other implementation differences; it does not isolate spectral effects or establish accuracy.

No additional solver calls were made during review.
