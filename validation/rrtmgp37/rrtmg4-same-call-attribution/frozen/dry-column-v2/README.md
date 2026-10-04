# Dry-column reconstruction: observer capture, including legacy exports

Offline arithmetic only. No build, solver, REAL, or forecast was run. The capture is domain 1, i=24/j=55, step 2161 at source time 129600 s. LW/SW RRTMGP inputs contain 57/45 levels respectively; each has 44 native model layers, leaving 13 LW and 1 SW upper-extension levels.

Both legacy exports include the actual dry-column arrays: LW spells the field `COLDry` (57 levels), while SW uses `COLDRY` (45 levels). The case-insensitive parser in `reconstruct.py` reads both. For all exported levels in both phases, the reconstructed pressure/H2O formula differs from the actual export by at most 2.44e-07 relative. An explicit default-REAL32 arithmetic emulation (rounding each operation in source grouping) matches all actual exported values bit-for-bit (0 ULP difference in all 57 LW and 45 SW layers). The text exports encode the actual legacy values at higher decimal precision than the underlying REAL32 values.

For the native 44-layer overlap, `GAS_COL_DRY` is reconstructed from captured `NATIVE_DRY_LAYER_MASS_KG_M2` using `mass_kg_m2 * Avogadro / (M_dry_kg_mol * 10000)`. All 44 recorded native values match exactly for LW and SW (max relative difference 0). The native mass is read from its REAL32 trace value and promoted to REAL64, consistent with the wrapper’s call. The extension values are kept as a separate table in the JSON; this report does not apply the native-mass formula to those levels.

On the 44 shared native layers, legacy `COLDRY` exceeds the RRTMGP mass-derived column in all layers. Mean difference normalized by the native column is 0.165180%; maximum is 0.289159% at bottom-first layer 19. The same maximum absolute difference normalized by legacy is 0.288325%, explaining the earlier ~0.2883% figure by its denominator; these are not different computed columns. The mean is not 0.2883%.

Constants follow the pinned source: legacy `amd=28.9660 g/mol`, `amw=18.0160 g/mol`, `grav=9.8066 m/s2`, `Avogadro=6.02214199e23 mol-1`; the native helper uses captured initialized dry molar mass/gravity and RRTMGP `Avogadro=6.02214076e23 mol-1`. The JSON records source, input, output and export hashes, every native-layer comparison and the extension-layer comparisons, with matching pre/post hashes for the captured files.

Formula anchors: `module_ra_rrtmgp.F:574-586`; legacy LW `module_ra_rrtmg_lw.F:11394-11476` and export at `11101`; legacy SW `module_ra_rrtmg_sw.F:9894-9998` and export; RRTMGP constants `mo_gas_optics_constants.F90:37,48,51,58-67`.
