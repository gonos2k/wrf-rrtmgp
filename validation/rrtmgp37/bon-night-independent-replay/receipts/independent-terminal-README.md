# BON night replay terminal review

Independent read-only review of the six-call standalone replay in `../run-v1/execution.json`. The retained direct `reference_column` executable completed six unique LW columns with RC 0 and no timeout; all six existing wrapper result files passed the pinned comparator on 24 common sections. The exact MASK section matched in every case. Production-only sections were `WRF_GLW`, `WRF_OLR`, and `WRF_THETA_HR`; there were no reference-only sections.

Across the compared output sections, the maximum absolute flux difference was 1.51260737e-05 (UP, `lw_000004`) and the maximum absolute heating difference was 2.2908852e-07 (HR, `lw_000005`). The maximum relative optical difference over nonzero reference entries was 1.22104165e-15 (GAS_TAU_RAW, `lw_000003`). The pinned comparator applies its existing tolerances (optics: 2e-13 absolute + 2e-12 relative; flux/heating: 4 float32 ULP + 1e-6); this review did not loosen them.

The execution receipt records 120 file pins before and after, unchanged, and a 47-path resolved runtime closure. The compiled `reference_column.f90` SHA matches the current source file SHA. This demonstrates same-code cross-driver replay consistency for these six retained columns; it is not an independent physical-accuracy or original-LUT oracle. No additional solver calls were made for this review.
