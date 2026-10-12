# Validation at parent main 36301782 (2026-10-12)

- Actual component configuration: 2 RC0 commands. Component builds: first RC2 from missing free-form mode; 3 corrected RC0 commands. GNU 13.3, O2/vectorize/unroll, bounds checking; no WRF/ideal build or run.
- Actual standalone Fortran processes: 393, 392 RC0. One input seed overflow failed before public-column entry, RC2. Bounded mapping fixed it; 66 completed supplemental pairs reused and 62 pairs completed afterward. No failed process is counted in final evidence.
- Final qualified public-column processes: 312, covering 4 retained columns; LW 3 paired seeds and SW 35 paired seeds per column, plus 8 original-seed A baseline controls. Earlier 80 prototype processes are preserved in accounting and excluded from final statistics.
- A versus retained PR168 common fields: bit equal for all 8 controls. Zero-extra Z versus A: all original result records bit equal. Z/B inputs and existing optical properties, radii, masks and clear fluxes equal.
- Extra-only single SW scaling, band/gpoint opacity and optical moments, flux/heating difference closure checked. All layer/interface/band signed outputs saved. Both scaled RTE flux and raw-direct WRF-convention surface flux are reported.
- Saved replay RC0. Five sensitivity boundary tests PASS normally and under Python -O.
- Existing acceptance integration: 12 tests PASS, including the new replay and controls. Existing identity boundaries: 16 tests PASS. Python compilation and source/doc whitespace check: RC0.
- Seven physical/final closure conditions unchanged byte-for-byte. Production code, coefficient files and initial/number/occurrence policies unchanged. No claim of independent physics or forecast approval.

Saved-data CI performs neither a new compiler/model execution nor independent coefficient/NetCDF interpretation. It reassembles exact original capture bytes from record blocks, then repeats the optical/flux/heating comparisons. Scientific uncertainty beyond the held model/finite seed experiment remains unquantified.
