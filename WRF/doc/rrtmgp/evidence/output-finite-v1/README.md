# Output finite-check component evidence

This bundle records a focused component build and CTest run for the RRTMGP adapter output-finiteness guards. The candidate is based on `33632eafff3fa06a164c7c56f258fac6fb545205`; exact source hashes, commands, return codes, and log hashes are in `component-receipt.json`.

The selected CTest expression passed **11/11 tests**: the standard columns, multicolumn, workspace reuse mode 0/1, SW pre-delta clear/cloud/overlap-zero/night cases, and three injected guard faults. The tests/build used the component CMake project, not a full WRF build. The receipt records zero model invocations. The SW night case checks the initialized zero-return path; it is not a nighttime radiation validation.

The fault harness generates isolated adapter source copies from uniquely counted call-site anchors. It injects a clear-sky LW NaN, an all-sky SW heating NaN, and a finite working-precision LW flux that overflows when converted to default REAL. The overflow case is skipped when `HUGE(default REAL) >= HUGE(wp)`; that is the predicate in the pinned test driver. This fixture skip rule is distinct from the production checks, which test finiteness and do not change finite output values.

The independent V1/V2 reviews are included verbatim. V2 is a scoped follow-up on fault provenance, the precision-dependent overflow skip, and documentation; it did not repeat the full adapter review. The evidence package keeps the original component receipt and logs unchanged. `verify.py` checks the bundle's payload hashes against `manifest.json`; it does not rerun CMake or CTest.

This contract fails fast on nonfinite values. It does not explain or fix the separately observed thermodynamic/Courant failure, and it provides no forecast-accuracy or full-WRF validation claim. The output-finite guard does not resolve the still-open instability cause.

## Reproduction scope

`run_component_checks.py` preserves the exact recorded commands and original workspace paths. Reproduction requires the same source checkout, NetCDF installation, and RRTMGP data directory recorded in `component-receipt.json`; the script is evidence of the executed commands, not a relocatable build driver.
