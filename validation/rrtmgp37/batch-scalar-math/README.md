# PR32 LW scalar-versus-batch numerical diagnosis

This evidence package records one reproducible first-call case and its two math-library counterfactuals. It does not change the WRF production code or compiler math flags. The instrumented probe and math shims are scratch-only. No production default was changed: the diagnostic module's absent `WRF_RRTMGP_BATCH_SIZE` uses batch size 1; size 32 is selected explicitly for this test.

## Finding

The original first-call WRF comparison found a one-float32-ULP LW heating difference at the target cell `(i,j,k)=(205,53,39)` between the scalar and 32-column paths. The 12:01 saved history differs only in heating arrays, with maximum `RTHRATLW`/`RTHRATEN` delta `7.275957614183426e-12` in host heating units at the target. A corrected 11-time, 211-variable exact readback found that the first non-heating field difference appears at 12:06; differences at later times are coupled-feedback confounded. Preserve that distinction: the forecast did not remain bitwise-identical for the full 11 minutes.

To identify the first numerical stage, the standalone diagnostic driver consumed the exact 32 scalar and 32 batch column captures from the original queue. The included Fortran-order binary fixture is 164,004 bytes (SHA256 `644ddb36f5f883b8e9a5ed75d53f426ec47176c83a5c24d7e49a40b6f62620da`); expected float32 output oracles are included at 36,608 bytes each. The root's independent decoder reports 1,856 input field/column checks across all 64 original captures, with headers, seeds, pressure ordering, native mass, and both baseline output oracles verified. The 64 original per-column source captures are not duplicated; their original absolute paths and hashes remain in `fixtures/manifest.json` and the independent readback receipt.

The default-math replay first differed at `GAS_TAU`: 42,310 of 192,512 values, maximum relative difference `2.807419165632381e-15`; `GAS_COL_DRY` was bitwise equal. The default replay's output oracle bytes matched the original WRF captures in both modes.

A local `_ZGVbN2v_log` shim called scalar libc `log` per lane. Its ABI test passed bitwise for 1,504 positive pressure arguments derived from captured `PLAY`. In the two bounded shim runs, gas optical depth, all source functions, and total optical depth became bitwise equal. The first remaining divergence was clear-sky up flux (`CLEAR_FU`), and clear/all-sky RTE fluxes and heating still differed. Both float32 output streams nevertheless remained byte-identical to their original WRF oracles.

A second shim overrode both `_ZGVbN2v_log` and `_ZGVbN2v_exp`; ABI checks passed for 192,516 finite nonpositive arguments (the exact negative `GAS_TAU` values plus explicit underflow cases) and the retained pressure-log fixture. In its two bounded runs, all 12 captured WP sections became bitwise equal, including clear and all-sky fluxes/heating. The scalar-mode float32 output matched the scalar original byte-for-byte. Joint batch output differed from its original batch output in only two float32 words, `HR` and `HRC` at `(column 0, layer 38)`, each one ULP; those values became the original scalar outputs. This strongly attributes this fixture's scalar/batch divergence to process-wide vector log/exp implementations. Because both symbols are replaced for every call in the process, the experiment does not identify the individual operation/call responsible or establish a production defect.

## Scope and limitations

- One 32-column LW fixture, one GNU 13.3/Linux/libm build, one pinned coefficient/table set. No claim for other compilers, architectures, configurations, bands, or production forecasts.
- The joint shim replaces vector log and exp process-wide, including any coefficient-initialization calls. It is a causal counterfactual, not a production math implementation recommendation.
- The full scalar/B32 trajectory diverges by minute 6 and later differences include atmospheric feedback; those later differences are not same-state radiation attribution.
- No tolerance was relaxed; all stage comparisons are exact IEEE bit comparisons. The one-ULP result is an observed output difference, not an accuracy score.
- No executable, full NetCDF coefficient/table, raw WP capture, full history, or production source overlay is included. Their exact identities are recorded by SHA256 in receipts/manifests. The fixed 164 KB input fixture and two small float32 oracle streams are included.

## Reproduction and offline verification

`verify_evidence.py` verifies artifact hashes and receipt invariants without invoking Fortran, a radiation engine, or WRF. To rerun the standalone experiments, follow `receipts/build-receipt.json` and the two runner scripts under `source/`; supply the external coefficient and frozen-table assets with the recorded hashes. The external source identity was commit `de312b7a53cefc2f69024e8b96de4bd586f00816`; generated baseline adapter SHA256 is in the build receipt. No full model build or forecast is needed to check the included evidence.

The fixture-v1 ordering failure, v2 scalar-section-parser failure (subsequently handled by offline parsing without rerun), log-only runtime-library preflight path mismatch, and joint-runner initial executable-path error are retained separately in `receipts/`. These were test-harness issues at distinct stages; they are not presented as radiation results.
