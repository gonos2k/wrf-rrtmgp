# Frozen raw-column replay contract

A valid frozen-mode1 capture preserves graupel and hail grid mass as radiation and adapter input. The old general replay validator instead required all graupel mass to be omitted and rejected positive hail. This caused a valid first-point LW capture to fail before independent replay.

The validator now checks complete frozen metadata, mode1 and uniform occurrence1, supplied table SHA256, native dry mass, corrected G/H grid paths, exact GRID→RADIATION→adapter identity, exact zero omitted and padded paths, and raw/input slopes when available. No-frozen mode0 retains diagnostic-only graupel and positive-hail refusal. Existing numerical correction and mass tolerances remain unchanged. No production Fortran, coefficients, or physical policy changed.

The four source changes are `WRF/test/rrtmgp/test_column_replay.py`, the new Python-only `test_frozen_raw_replay_contract.py`, its CMake test registration, and their exact blobs in `config/registration37.json`. The clean branch starts from `de312b7a53cefc2f69024e8b96de4bd586f00816` (PR #32, including the PR #30 workspace implementation).

Thirteen Python test methods exercise LW/SW with material positive G/H, both modes, malformed or incomplete policy/hash markers, changed native paths, nonzero omitted/padded mass, slope/native-mass mismatches, table identity, and unchanged strict negative corrections. The original pinned validator fails the synthetic mode1 case in both phases. The existing Python negative-record validation also passes.

Actual validation uses only point (136,48), radiation step 721 at source time 43200 seconds, from the approved shared 12h checkpoint. Native geometry is 289×189×39. LW V8 extends this column to 47 layers; SW V9 to 40. The original one-minute capture produced the exact audit-OFF history SHA `7a76a430f1d37ba88ee2692c5cb076a271f3d525a1190b5cd824df3790225025`, including all variables and attributes; all 210 numeric history variables are finite and unmasked in raw and decoded reads.

Exactly two independent reference calls completed: LW compares 20 sections, SW 46. Masks match exactly; unchanged optical and float-output tolerances apply. An independent result parser checks production/reference 23/20 LW sections (29,091/29,050 values) and 50/46 SW sections (42,337/42,295 values). The root independently recomputed every 20+46 reported section maximum and exact masks. Production-only WRF records are validated separately, so section counts differ.

SW input `RAW_GAS_TAU` is explicitly serialized as default `REAL(work%raw_gas_tau)` while result `GAS_TAU` retains working precision. All 4,480 input values equal `GAS_TAU.astype(float32).astype(float64)` exactly, consistent with the pinned GNU build's four-byte default REAL. The maximum 0.0006210739302332513 conversion difference is serialization evidence; it is not an optical tolerance change. No other field uses this conversion check.

The preserved failures distinguish harness problems from the validator bug:

- Capture v2 omitted staging the restart checkpoint. Its failed receipt remains unchanged.
- Capture v3 ran WRF and passed whole-history parity, then failed importing sibling Python modules. Its overall receipt remains FAIL.
- Replay recovery v1 fixed imports, then exposed the real mode0-only validator bug before any reference call.
- Recovery v2 uses the reviewed validator and completes LW, then fails before SW on a harness lookup of absent SW `GAS_TAU_RAW`. Its receipt remains FAIL and its LW pass is inherited explicitly.
- Recovery v3 fixes that single SW lookup/serialization assertion and executes only the remaining SW call. Its success links the two receipts without rewriting earlier failures or repeating LW.
- The first Python proof wrapper used an incorrect plan key and failed before tests. Its receipt and script are retained; the corrected proof passes.
- The root readback initially assumed equal production/reference section sets, failed before writing, then records the production-only WRF-record erratum in its final receipt.

The executed scripts and receipts retain exact source/helper/executable/checkpoint/table/asset pins and before/after checks. Production sources and captures remained unchanged. Numerical capture and history payloads, binaries, objects, and NetCDF files are represented by hash-only inventories. The historical six-point plan SHA remains `4f9e642fad9b648f352805ac6f9d71363945df0388c1e0acc608b3740f374279`; the validator update is explicit in recovery receipts.

Run `python3 -I -S validation/rrtmgp37/frozen-raw-replay-contract/verify_artifacts.py` to verify this package and its four source files. This portable check authenticates retained evidence; rerunning the host-specific executed scripts requires the pinned external files. Run `python3 WRF/test/rrtmgp/test_frozen_raw_replay_contract.py` for the Python-only contract tests (NumPy and netCDF4 required).

This is one captured state with substantial CF0 rain. Native profile/path summaries are evidence for that state, not optical-depth proxies promoted to measured tau, a domain flux bound, climatology, or a resolution of precipitation occurrence or LUT clipping policies. The remaining five planned captures and sensitivity variants have not run in this package.
