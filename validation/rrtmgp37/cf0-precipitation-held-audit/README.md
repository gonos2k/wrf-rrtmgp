# CF0 precipitation held-state audit and compiled reader

The standalone test reference accepts an optional sixth argument for a one-column V8/V9 CF0 precipitation sidecar. Existing calls without a sidecar retain their multi-column interface. Production physics, cloud fraction, microphysics, Registry and vendor code are unchanged. The audit is a declared occurrence-one contribution experiment, not a proposed production occurrence policy.

Two separately pinned results are retained:

- **Historical held captures:** exactly eight reference calls using frozen source `939981fd` and the historical focused-v2 library closure. Four all-zero sidecars reproduce their original `67261` exact double-reference result files byte for byte; four positive sidecars pass the declared output contract. The [execution](campaign/execution.json), [analysis](campaign/analysis.json) and [independent readback](review/campaign-result-review.json) retain exact pins and metrics. All 281 protected paths, 47 runtime libraries and eight output pins remained unchanged.
- **Current compiled reader:** source `93214328` was built separately with the current private-scalar backend. Its [synthetic test report](current-helper/compiled-reader-report-v4.json) records 14 reference processes: 10 successful and four rejected before output. Two fixture programs make three adapter RTE calls (LW one, SW two). These use a synthetic three-layer state, not an actual captured WRF radiation call. Units/native depth/positive-CF/NaN-CF rejection, zero/no-sidecar equality and positive optics are exercised. This does not turn the historical held-capture results into current-backend or forecast proof.

## Historical conditional response

All values below are positive-sidecar minus the saved exact double reference. Flux is W m⁻²; maximum absolute native-layer heating difference is K day⁻¹. `SW net` means surface down minus up.

| Added species / phase | Surface down Δ | TOA up Δ | Surface SW net Δ | Max native absolute ΔHR |
|---|---:|---:|---:|---:|
| Rain LW | +0.1496815613 | −1.2375571167 | — | 2.2719224759 |
| Rain SW | −1.5385145817 | −1.9463441889 | −1.2524692966 | 0.3418474502 |
| Snow LW | +0.1588255203 | −0.0000190317 | — | 0.9969685983 |
| Snow SW | −0.0415699858 | +0.0251663205 | −0.0339884237 | 0.0011186069 |

The raw captures contain 16 strictly positive rain layers (202.428637 g m⁻²) and 13 snow layers (5.622483 g m⁻²). All tiny positive snow paths are retained; six larger layers are a descriptive subset, not a threshold. Native depth is 39, with engine-only extensions to 47 LW/40 SW layers. Added optical arrays are zero in those extensions; extension-layer heating responses are separately reported. Optical sums across layers and bands are not vertically integrated optical depth or a physical-domain budget.

Paths exactly match captured omitted rain/snow mass at CF zero, with native-only shape, zero padding, one species and occurrence exactly one. Snow requires explicit source-radius capability and matching prepared radius; background snow radius is rejected. Extra precipitation is added **after cloud sampling** and before frozen optics/RTE. Original masks, gas/cloud/accepted-precipitation/frozen/prepared optics, clear-sky fields and ordinary pre-delta direct diagnostics stay exact. `PREPARED_*` means baseline cloud plus accepted precipitation, not audit-total optics. Ordinary all-sky totals/flux/heating may change. SW provides separate `AUDIT_DIRECT_PREDELTA` with the extra raw extinction; unchanged ordinary pre-delta records are not the intervention's direct flux.

## Source, failures and reproducibility

The integrated current reader adds finite CF in [0,1] and exact-zero placement checks relative to historical source `939981fd`; [the precise delta](forensic/current-test-helper-cf-guard.diff) and [four captured-input preconditions](validation/captured-cf-precondition.json) are retained. The historical source/executable is untouched. The original [then-uncompiled proposal status](forensic/proposal-status-v2.json), [NOT_EXECUTED preparation](history/preparation-summary.json) and its manifest/README remain original historical bytes. Later build/results do not reclassify them.

[Preserved current-helper failures](current-helper/preserved-failures.json) distinguish a wrong CMake path before any child, a fixture loader failure with zero reference calls, and two later parser/shape harness failures after successful LW fixture/reference children. Original receipts/logs remain externally pinned; no successful numerical receipt is fabricated by overwriting a failed one. The final runtime-v4 pass uses the corrected parser/group and interface-array shape contracts.

The checked-in Python parser has 23 portable controls, recorded separately from compiled Fortran controls. The shared result parser recognizes only complete optional audit groups. Copied forensic launcher/analysis/readback scripts remain nonportable workspace snapshots. The successful campaign used exact argv/data/policy/empty override/cwd/loader pins, fresh protected outputs, durable PID/return-code accounting, zero controls before positive calls and pre/post/finally immutability. The offline gate alone is not a general safe launcher.

`python3 -I -S verify_artifacts.py` checks retained hashes and compact receipt contracts using the standard library. It does not launch helpers or recompute external arrays. Large captures/results/logs, binaries, coefficients and inventories are external hash references; no bytecode is packaged. Package curation adds zero solver, model, REAL or build calls.

These held, seeded states do not establish correct precipitation occurrence, independent optical truth, physical accuracy, a domain mean, LUT clipping error or current forecast equivalence. The historical focused-v2 closure differs from the current private-scalar backend; the current synthetic reader test proves its own bounded contract only.
