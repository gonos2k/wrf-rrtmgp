# Single-execution engineering identity

The capsule verifier connects one installed CMake UDM27–RRTMGP37 startup-snow
SCM to its source, build receipts, executable bytes, offered inputs, actual child
results, capture and history output. It keeps physical acceptance `NOT_ACCEPTED`.
It does not approve Nc units, particle-size moments, RFMIP, LBLRTM, or forecast
accuracy.

`manifest.json` lists every regular file in a capsule except itself. Missing,
extra, duplicate, changed or unsafe paths fail. Supply a trusted manifest digest
with `--expected-manifest-sha256`: without an out-of-band digest, the check is
internal consistency, not independent authenticity of the author's manifest.

The selected Git worktree must match the declared clean HEAD/tree and complete
tracked-file inventory. Unused tracked symlinks are checked as literal Git
objects, including dangling vendor links; runtime byte references cannot escape
their explicit roots. Build receipts, tools, selected CMake cache values,
executables and shared libraries are pinned. Child records join their original
process receipts, prepared input plans and executable hashes. Saved runtime
validation, history and the summary must refer to that same invocation.

The verifier requires explicit roots for large files retained outside the
capsule. It works from a foreign working directory, but does not certify generic
installation-prefix relocation or regenerate the build. Prepared tables are an
inventory of files made available to the case, not an operating-system file-open
trace. Hash equality and recorded process success do not substitute for a
scientific benchmark.

```sh
python3 -I -S /path/to/repo/validation/rrtmgp37/execution-identity/verify_capsule.py \
  /path/to/capsule/manifest.json \
  --expected-manifest-sha256 TRUSTED_DIGEST \
  --root source=/path/to/exact-source \
  --root install=/path/to/exact-install --root system=/
python3 -I -S /path/to/repo/validation/rrtmgp37/execution-identity/tests/test_verify_capsule.py
```

The tests use manufactured files and temporary Git repositories. They run no
compiler, RTE calculation, ideal initialization or WRF forecast. The local
engineering report records the separate real execution and its tested scope.

For the actual evidence, source `fe8dfc6` was built with GNU 13.3, serial REAL32
and allocatable host arrays. One ideal initialization and one 60-second SCM
completed. The selected initial snow layer used 134.778076 μm and had positive
snow precipitation optics in all 16 LW bands and all 14 SW bands above the
numerical floor. Source, installed assets and resolved model libraries matched
before and after execution. This is a manufactured startup contract test.

PR #131's independent CMake workflow
[37443922808](https://github.com/gonos2k/wrf-rrtmgp/actions/runs/37443922808)
also passed build/install, package consumers and SCM at this exact head.
PR #131 and #132 are merged. The original 19 review findings, current 12 work
items, strict reference failures and incomplete scientific identity remain in
the [acceptance checklist](../acceptance/README.md).

The [local report](LOCAL_VALIDATION.json) retains the separate root verifier receipt
and independent static review. The capsule is a local retained artifact, not a
portable bundled scientific reference. Whole-port run
[37443922887](https://github.com/gonos2k/wrf-rrtmgp/actions/runs/37443922887)
failed at the traditional Make SCM build because Fortran and Registry selected
different storage kinds. Runtime steps were skipped. A separate production fix
is in progress; the CMake success does not close that failure.
