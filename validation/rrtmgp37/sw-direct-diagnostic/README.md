# SW direct-flux diagnostic validation receipt

The runtime experiment used a source overlay on `e73b353f2b76f323809f99bed19a29eaaf25af02`. The review branch also includes PR #22 (`361c05ad36c149dc7e9d700fa80fc47ea8843d60`), which adds documentation and evidence without changing production physics.

The change routes WRF `SWDDIR` through the independently reconstructed, pre-delta direct beam and computes `SWDDIF` as the unchanged solver total minus that beam. RRTMGP solver fluxes, heating, legacy adapter outputs, and the radiation-4 path remain unchanged. Optional direct outputs are all-or-none. SW captures using them are V9; transformed CF/seed counterfactuals discard V9-derived attenuation records and project strictly to the applicable legacy input schema.

## Build and standalone tests

The authoritative fresh GNU serial SCM build used 13 staged source files. A fresh `-j12` attempt failed because `module_bl_shinhong` was compiled before `ccpp_kind_types.mod` was available; subsequent missing-module and link errors were consequences of that dependency ordering. A same-tree `-j1` recovery completed successfully with unchanged staged source hashes. `build/wrf-build-receipt.json` records compiler, source hashes, compile-log hash, and executable hashes. `build/j12-launch-receipt.json` and `build/j1-launch-receipt.json` retain the launch outcomes. The failure and recovery logs remain in the scratch build tree; their paths, sizes, and SHA256 hashes are recorded by the manifest.

The standalone suite passes **95/95** with GNU Fortran 13.3 and the configured NetCDF library path. Its focused SW tests cover clear, cloudy, overlap-zero, night (zero-initialized optional outputs), both adversarial partial-output groups, and a wrong output shape. The two-column fixture checks cloudy/clear column independence. The V9 replay fixture checks cloud, precipitation, frozen G/H with overlap zero, independent replay, and VIS/NIR direct closure. V9 projection probes passed for both non-frozen V9→V5 and frozen V9→V7 inputs while preserving non-derived sections.

Reproduce the standalone suite from this worktree with:

```bash
LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/lib \
  ctest --test-dir build/sw-direct --output-on-failure
```

See `ctest/ctest-receipt.json` and `ctest/ctest-output.log` for the recorded run.

## Actual SCM runtime checks

`frozen-scm-result.json` is the one-minute, finite-initial-state SCM receipt. It records binary/input/source/table hashes before and after execution. Mode-one positive G/H control and mixed-cloud cases separately captured and replayed calls 1 and 2: LW V8 and SW V9. `native/` contains version-aware native-gas and native-mass receipts for mode-zero control/mixed and frozen mode-one control/mixed calls 1/2. The later call uses history record 1 and an explicit evolved-history option; raw q and native coordinates must still match that selected record exactly. Corrupted native mass and mismatched source-q probes were rejected.

For the current implementation against the hash-pinned PR21 parent, both control and mixed mode-zero RA37 runs were bitwise equal across all recorded numeric arrays except the explicitly changed `SWDDIR` and `SWDDIF`. This includes `SWDOWN`, `GSW`, `RTHRATLW`, and `RTHRATSW`. Both RA4 control/mixed runs were bitwise equal across all 207 numeric variables. The direct fields changed in both RA37 control and mixed comparisons; this receipt does not attribute that difference to positive G/H.

For every captured mode-one case, V9 `DIRECT_PREDELTA` at the surface equals the corresponding WRF history `SWDDIR` exactly (0 W m⁻² residual). The history validation checks `SWDOWN=SWDDIR+SWDDIF` and `GSW=SWDNB-SWUPB`; V9 replay checks `VISDIR_PREDELTA+NIRDIR_PREDELTA` against the broadband pre-delta beam. `direct-delta-replay-metrics.json` quantifies the pre-delta versus delta-scaled solver direct difference and independent replay errors for a current mode-zero mixed capture and a positive frozen mode-one mixed capture.

This evidence covers one-minute startup behavior and injected finite initial states only. It makes no long-forecast readiness or scientific-accuracy claim. It is not an observational DNI validation.

The SCM runtime uses one radiation column; multi-column independence is covered by the standalone two-column adapter/reference fixture, not a full WRF multi-column runtime.

## Selected captures

`captures/mode0-mixed-control/` contains one actual mode-zero mixed-cloud SW V9 capture; `captures/mode1-frozen-mixed-call1/` contains one actual positive G/H SW V9 capture. Each directory includes paired `.raw`, `.input`, `.result`, and `.reference.result` files. No large model history or restart NetCDF files are included.

`artifact-manifest.json` records SHA256 and byte size for the curated evidence files and selected source/binary/log provenance.
