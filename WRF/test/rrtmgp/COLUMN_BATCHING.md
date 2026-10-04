# WRF RRTMGP column batching

The WRF RRTMGP37 wrappers can pack columns before calling the multi-column
adapter. `WRF_RRTMGP_BATCH_SIZE` accepts exactly `1`, `32`, `64`, or `128`;
unset means `1`, which retains the scalar path. The value is read by each
radiation call, so all ranks and threads in a run must use the same setting.

Batch buffers are call-local and hold at most the requested number of columns.
For 60 model layers, their declared REAL profile storage is about 2,365 values
per LW column and 2,602 per SW column (about 1.16 MiB and 1.27 MiB at size
128, respectively), excluding the adapter's RRTMGP workspaces. SW only packs
daylight columns. It flushes at capacity, at each row boundary, and before
processing a night column. The final partial batch is flushed at the end of
each row. Each column retains its own global `i,j` seed and solar normalization;
SW normalization is passed as a per-column vector.

The wrapper keeps the scalar route when capture or audit is requested, and for
an explicit nonnegative MCICA seed override. The default negative seed
sentinel remains eligible for batching. These fallbacks preserve the existing
single-column trace/audit formats and deterministic seed override behavior.
Legacy RRTMG4 calls remain on their existing path.

The opt-in check is adapter-level: `multi_column_equivalence` compares a
heterogeneous 64-column request with concatenated single-column calls, including
per-column solar and clear/eclipsed columns. CU/frozen and workspace reuse
contracts are separately covered by `cu_population_optics_*`,
`frozen_adapter_*`, and `workspace_reuse_states_*` tests. Full WRF numerical
equivalence and performance validation remain necessary before changing the
default batch size from one.
