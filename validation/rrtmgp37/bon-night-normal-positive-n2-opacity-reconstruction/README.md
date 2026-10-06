# Normal positive-N2 LW opacity reconstruction

This package records one saved source-order reconstruction for an actual one-column LW V13 `SOURCE_OFF` capture. The input has 45 engine layers, including 32 native dry-mass layers and 13 pressure-derived upper extensions. All 45 captured `VMR_N2` values equal the pinned adapter default, 0.7808; the V13 CFC trace marker and four complete profiles match the adapter's all-or-none interface contract.

The saved construction and independent terminal audit report exact array equality for all 45 dry-column values, all 5,760 cells of `GAS_TAU_RAW`, and all 5,760 cells of `GAS_TAU`; the audit separately reports native-32 and extension-13 scopes. It rechecks 11 input gas profiles and their dry-column products, 46,080 major-corner terms, and 61,564 minor-corner terms. The point process completed once with return code 0. No RTE, WRF, REAL, or compiler call occurred during that point process or terminal audit.

This is a descriptive same-table source-mechanics result for this captured positive-N2 state. It is not a tolerance acceptance test, coefficient-generation validation, spectroscopic or atmospheric accuracy result, global N2 policy, or explanation of the broader broadband residual. The reconstruction uses Python binary64 and does not claim bitwise emulation of the Fortran evaluation. The captured N2 field is treated as an input; this check does not establish that value's physical truth.

The terminal audit has a preserved v2 numeric report and a v3 metadata correction. V3 changes only a provenance limitation: the actual positive-N2 campaign's adapter, gas constants, gas frontend, kernel, loader, and LW table bytes match the current comparison worktree, while its separately instrumented trace module differs. This does not claim identity of the entire WRF source tree. The correction receipt links v2 and v3 without rerunning the numerical audit.

The package verifier uses only Python's standard library. It checks the closed payload roster, stored and inflated hashes, original-copy provenance, execution/authorization/construction ancestry, input/source preconditions, every per-gas 45-layer `VMR × dry column`, source-order 32+13 dry construction, both saved tau arrays, and recorded residual summaries. It reads saved artifacts only; it never reconstructs opacity or invokes RTE, WRF, REAL, or a compiler. The LW gas table is not duplicated in the package: its exact tracked repository path and hash are checked by the verifier.

Run from any working directory:

```sh
python3 -I -S /path/to/bon-night-normal-positive-n2-opacity-reconstruction/verify.py
```

The workflow runs this saved-evidence verifier only. It does not rebuild or execute a solver or model.
