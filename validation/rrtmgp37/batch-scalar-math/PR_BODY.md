## Summary

This evidence-only PR isolates a one-ULP scalar-versus-batch LW heating difference using the exact captured 32-column WRF inputs. The default-math standalone replay first diverges at gas optical depth (`GAS_TAU`, maximum relative delta 2.81e-15). A local scalar-libc `log` ABI override makes gas optical depth, source functions, and total optical depth bitwise equal, but leaves clear-sky RTE differences. Adding a scalar-libc `exp` override makes all 12 captured WP stages bitwise equal; the batch float32 heating values then move one ULP to the original scalar outputs.

The package includes the exact fixed input and float32 oracle payloads, hashes/provenance, ABI tests, the two bounded run receipts, independent root readbacks, a no-engine integrity verifier, and the corrected 11-record history comparison. The full scalar/B32 history diverges in additional variables starting at minute 6; those later differences include coupled feedback and are not same-state solver attribution.

## Scope

This records a process-wide math-library counterfactual for one GNU 13.3/Linux LW fixture. It does not identify the individual vector-exp call, recommend production math changes, or prove forecast accuracy. No production source, math flags, coefficients, or tolerances were modified. Raw WP streams, complete NetCDF assets, executables, and history files are not included; their hashes are recorded.

## Validation

Run `python3 validation/rrtmgp37/batch-scalar-math/verify_evidence.py` from the repository root. It verifies artifact hashes, fixture/oracle bytes, selected exact comparison invariants, and that bulky engine outputs are absent; it does not build or execute the radiation model.
