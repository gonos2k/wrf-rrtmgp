# Actual UDM27 call-entry density and observer passivity

The opt-in, serial RRTMGP37 observer records simultaneous arguments immediately
before the native UDM call. The native UDM implementation and all existing UDM
call arguments remain unchanged. `DEND_REEVALUATED_PRECALL_KG_M3` is explicitly
an observer reevaluation of the source expression, not direct observation of
UDM's private internal state. Capture is off by default.

One fresh GNU 13.3 serial `em_scm_xy` build used a clean `efd7b45` checkout plus
only the reviewed driver/trace overlays. All 7,853 tracked source entries were
verified before/after; no objects were reused. Six new one-minute SCM forecasts
used the immutable cold/warm manufactured UDM inputs: 37 off/on and ordinary 4
for each input. All model return codes were zero. No ideal initialization or
standalone radiation replay was invoked in this checkpoint.

Both 37 off/on pairs preserve all 211 history arrays, dimensions, attributes
and whole-file bytes. Current 37 also preserves the archived source-equivalent
37 histories; ordinary 4 preserves all 208 arrays and whole-file bytes against
the archived UDM4 histories. These are scoped SCM regressions against the saved
source-equivalent build, not new pristine-official or real-data forecast tests.

Each input yields six pre-call packets (59 native levels, clocks 0–50 seconds)
and six exact same-call post-radius joins. Across 708 level/call samples:

| Input | Passed DEN vs conditional dry-air EOS: max relative residual | Re-evaluated DEND vs that EOS: most negative relative difference |
|---|---:|---:|
| Cold | 2.24974e-7 | -0.791798% |
| Warm | 2.48180e-7 | -2.141690% |

The EOS comparison uses `P/[T*(RD+RV*QV)]`; the separate gas-total hypothesis
multiplies that value by `(1+QV)`. The passed DEN agrees with the dry hypothesis
at default-REAL roundoff in these states. Substituting dry DEN into UDM's
inherited `(P/T-DEN*RV)/(RD-RV)` expression instead gives
`DEND/rho_d = 1 + QV*RV/(RD-RV)` when the EOS is consistent. This explains the
measured deficit. It identifies a host/UDM density-contract question; it does
not establish an RRTMGP-introduced defect or attribute every 4/37 difference to
this issue. No physical density, activation, size or optical policy is changed.
The pressure identity derived from the same DEND expression is not an
independent check.

The closed V1 parser accepts the reviewed default-REAL32 target and checks
identity, field roster, sizes, finite values, clocks, source arithmetic and
same-call joins. Negative raw moisture/number/DEND values are retained for
inspection. It keeps pre-call temperature separate from updated post-call
radius state. Twenty manufactured protocol/failure controls pass. The actual
trace module passes standalone `-O0/-O2` tests including default-off passivity,
selection, malformed shapes, TH/raw NaN, clock, gate, directory, duplicate-file
and OpenMP guards. Final v7 uses six compiler/link children and 28 fixture
children (six successful, 22 expected fatal). Earlier development generations
and failures remain in the text archive; cumulative counts are 33 compiler/link
children and 93 fixture children. Those are separate from the six WRF runs.

Verify saved packets and reports without running WRF or a solver:

```sh
python3 -I -S validation/rrtmgp37/entry-density/verify.py
```

CI authenticates this saved evidence and freshly compiles/tests the current
writer. The normal port workflow also compiles and runs the current WRF tree.
The saved NetCDF comparison is authenticated as a receipt; its binary histories
and executable remain in the hash-pinned local experiment directories.

`scm-receipt.json` retains process/input/executable/source pins and comparison
results. `build-receipt.json` retains the build return code, executable/dependency
closure and canonical complete-source manifest hashes; the full receipt is
locally pinned. `execution-text.json.gz` retains logs, namelists, fixture results
and the build runner/compile log with per-file hashes. The manifest closes the
payload and source rosters. Original absolute paths in saved reports are
provenance only; verification compares all identities, values, hashes and sizes
while relocating packet paths to the current checkout.

Next: review every native UDM density use and test a narrowly scoped correction
before changing production policy. Nc unit/PSD authority, LUT size-generator
provenance and overall physical accuracy remain separate open requirements.
