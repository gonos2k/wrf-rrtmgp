# Intel serial UDM27 compatibility evidence

Intel ifx/icx 2025.3.3 built the workspace source as serial `em_real`, and RA37 frozen 1 plus RA4 legacy restart runs each completed 12:00→12:01 successfully. The two histories contain 210 and 207 numeric arrays respectively; every raw value is finite. Inputs, executable copies, source/configuration, optics assets, and 870 shared toolchain/dependency files remained unchanged. This evidence adds compiler coverage; it does not change model source or physical policy.

The full model used commit `6f0f3ea3e73fbd43325fdad1050b000eecd70138`. This evidence branch starts at `bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291`, whose only follow-up changes initialize a standalone test's default coefficient path earlier and refresh its registration receipt. The three workspace production files are byte-identical; their SHA256/Git blobs are in [source-pins.json](inventories/source-pins.json).

| Configuration | Recorded value |
|---|---|
| Compilers | ifx/icx 2025.3.3; ifx build 20260319 |
| Libraries | Intel-built NetCDF-Fortran 4.6.2 and NetCDF C 4.9.3 |
| Configure/build | Intel oneAPI LLVM serial 76, nesting 0; `csh -f ./compile -j 12 em_real` |
| Flags | Native real4/int4, O3, fp-model precise, big-endian unformatted I/O; exact [configure.wrf](config/configure.wrf) retained |
| Runtime case | Original 289×189×39 checkpoint, UDM27/use_mp_re 1, audit OFF, OMP 1 |
| RA37 | LW/SW 37, frozen 1, one 12:01 history, 211 variables/1342 attributes |
| RA4 | LW/SW 4, frozen 0/table empty, one 12:01 history, 208 variables/1324 attributes |

Eleven selected Intel standalone tests also pass: frozen SHA, workspace frozen 0/1/mode-lock, ordinary columns, four SW predelta cases including night, frozen queries, and column/workspace concurrent reentrancy. Those standalone targets compile the CPU-only vendor and adapter with Intel OpenMP; the full WRF binaries in this package are serial. This is not full-model Intel MPI/OpenMP validation.

Full-model 64 MiB and 512 MiB stack attempts failed before radiation in `solve_em`. A 512 MiB GDB entry-only probe measured an automatic frame of 568806032 bytes (542.4557 MiB) and confirmed the actual inferior limit via `/proc`. The unchanged executable/input then passed the two bounded smokes with an approved 1 GiB master-stack limit. This resource limit applies to the measured case; it is not a universal WRF minimum. No vendor edit, heap-array flag, source change, or rebuild was used for the retries. Initial failures remain in [failures/](failures/); the [GDB evidence](receipts/gdb/actual-inferior-evidence.json) and [frame analysis](receipts/gdb/stack-frame-analysis.json) explain the adjustment.

The Intel histories use NetCDF4, while the GNU reference histories use NetCDF3_64BIT_OFFSET. Intel's native RANDOM_SEED size is 2 and GNU's is 8, changing seed_dim_stag and six ISEED* array shapes. Registry defines that dimension from RANDOM_SEED(SIZE=...). [Intrinsic probes](receipts/random-seed-metadata-proof.json) and [format observations](receipts/format-seed-observation.json) record these differences; complete native candidate metadata is retained. Physical dimensions and other variable layouts match the approved case. Cross-compiler bitwise equality, longer forecasts, and forecast quality were not tested here.

Run the portable, standard-library-only artifact check from any checkout:

```sh
python3 validation/rrtmgp37/intel-serial-compatibility/verify_artifacts.py
```

It authenticates all packaged bytes and checks the recorded build/run/failure/stack/test contracts. The NetCDF histories, executables, objects, libraries, full generated tree, and shared dependency payloads are excluded. Consequently this portable check does not reopen model outputs or rerun physics. Exact live source/dependency/history validation was performed separately; [live-validator.json](receipts/live-validator.json) retains its result and [verify_intel_receipts.py](scripts/verify_intel_receipts.py) retains that host-bound validator. The original isolated trees are required to repeat the live check.

[summary.json](receipts/summary.json) indexes the passing cases. Each history inspection records every variable's dtype/dimensions/shape, raw byte count and SHA256, finiteness/range, and all attributes. [provenance.json](provenance.json) identifies byte-exact originals and the compact derived records. The full source 6639-entry and generated 9157-entry manifests are pinned by hash/count, and the 870 shared files have a [hash-only inventory](inventories/shared-dependency-sha256.json). Historical experiment scripts preserve their original absolute paths and are audit/replay references, not portable run commands.

The original build validator falsely required a configcheck phrase absent from this WRF; an actual configcheck returned 0. The original successful-run inspector falsely required equal GNU/Intel seed dimensions. Their failed receipts and exact executed validators are preserved alongside corrected versions. Neither correction rebuilt or repeated a successful WRF run. [REPORT.md](REPORT.md) retains the detailed contemporaneous validation report.

Root independently reopened both live histories and checked their full-file hashes, unmasked finite numeric arrays, time, geometry, and physics metadata. The compact [root-history-recheck.json](receipts/root-history-recheck.json) records that review. Its original inline command was not retained; it is a derived review receipt, not an original standalone validator.
