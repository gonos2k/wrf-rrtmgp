# Deterministic Registry subgrid metadata

Registry array nodes must define `subgrid_x` and `subgrid_y` even when
their dimensions do not contain a horizontal coordinate. The I/O layer
reads both flags when deciding whether to write a two-dimensional field.

The original generator assigned each flag only when it encountered that
coordinate axis. For example, `ISEEDARR_MULT3D` has `ZZ` memory order
(`bottom_top` by `num_pert_3d`), and neither assignment was emitted.
The `fieldlist` declaration does not provide defaults. Reading these flags
therefore depended on undefined allocated-node contents.

The generator now emits false for both flags immediately after creating
an array node. Existing dimension-specific assignments follow these defaults,
so genuine X/Y subgrid fields retain their Registry settings. Scalar nodes
and their separate output path are unchanged. No field is removed from
restart, and the output predicate is unchanged.

## Evidence scope

A current GNU REAL32 CMake MPI4/OpenMP2 Matthew control run stalled at
its first 12-hour restart write. With field-level debug output, all ranks
had the same preceding writer sequence, then rank 0 omitted
`iseedarr_mult3d` while ranks 1–3 wrote it. Later scalar/status collectives
no longer aligned. The timeout and launcher return code 15 are preserved;
this is an I/O execution failure, not evidence of nonfinite radiation.

Source inspection establishes the uninitialized metadata defect. The
observed sequence is consistent with it, but the original runtime flag
values were not captured. A generated-code regression and a new restart
execution are required to establish the fix's behavior and its effect on
that observed stall. Neither implies physical accuracy or Nc/PSD approval.

The focused comparison uses the actual parent and fixed Registry executables:
the parent fails stale-TRUE sentinels for the seed array, Z-only, X-only,
and Y-only controls; the fixed output passes all six controls. Regular XY
and actual X/Y subgrid controls retain their extents and dataset dimensions.
The CI test builds the working Registry tools from an isolated copy, selects
the real seed declaration and dimensions, and checks generated assignments
by compiling/running a Fortran sentinel. A manufactured omission of the
seed-array defaults must fail. This negative control is not labelled an
upstream execution.

Run the focused current-source check with GCC, make and GNU Fortran:

```sh
python3 WRF/test/rrtmgp/test_registry_subgrid_metadata.py WRF \
  --workdir build/registry-subgrid-metadata \
  --output build/registry-subgrid-metadata/receipt.json
```

Use a fresh work directory; failed attempts and their process results are
preserved. This check does not launch WRF or approve the restart runtime gate.
