# Historical package verification, archive v2

The original v1 `artifact-manifest.json`, `historical-verification.json`, reader archive, adapter archive, v1 wrapper, and v1 test remain byte-for-byte unchanged. The v1 wrapper/test are historical snapshots; use the v2 wrapper and test against this checkout because the current comparator dependency has changed. This additive v2 archive preserves the comparator snapshot pinned by the retained independent-replay package and inherited by the dry-column package: `WRF/test/rrtmgp/compare_column_replay.py`, SHA-256 `6099a3819268d3ee17bbcbaf0610c03822c09247da6ac5bdfdef66c9190533a7` (12,800 bytes), from the PR86 checkout. The LW-transport package does not declare that comparator dependency.

Run the v2 offline checks from the nested worktree:

```sh
python3 validation/rrtmgp37/reference-source-archive/test_verify_historical_packages_v2.py
python3 validation/rrtmgp37/reference-source-archive/verify_historical_packages_v2.py --output build/udm37-bon-night-n2-reference-archive-comparator-v2.json
```

The v2 wrapper supplies archived reader, adapter, and comparator bytes only when a retained package roster pins that exact identity; it hash-checks every other dependency against the nested checkout. The v2 roster check ignores only generated `.pyc` files inside `__pycache__`; unexpected payloads such as `extra.py` are still rejected. It invokes the existing package verifiers unchanged and writes an optional receipt outside this archive. No package manifest or receipt is edited. The checks verify historical retained artifacts, not V12/V13 source behavior, current physics, or accuracy. No compiler or solver is invoked.
