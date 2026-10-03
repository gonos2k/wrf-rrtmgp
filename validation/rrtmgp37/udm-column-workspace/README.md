# Column workspace reuse validation

This directory retains small text receipts and the exact validators used for the optional tile-owned workspace change. It contains no executables, compiler outputs, model input/restart data or history NetCDF files. Full immutable source manifests and original logs remain in the isolated workspace paths named by the receipts; their SHA-256 values authenticate them. `manifest.json` records the tested source/configuration/executable identities, and `file-manifest.json` authenticates every retained artifact. Run `python verify_receipts.py` from this directory to verify artifact hashes and complete expected gates.

The production source is based on selected-column commit `fdafa534d5641fa2251ad5b02d294d57167b81fb`. The original column oracle independently compiles the adapter from `792f36b6bbc442f0db37b5cb9fdf19dd33600082`. The integrated source retains the exact SR-row fix and selector feature; full model candidates differ from their references only in the three radiation source files. WRF `ncol` remains one, and workspace lifetime is one tile invocation, ending before the wrapper returns.

## Artifact map

- `receipts/standalone/`: original-base output/raw-capture oracle, allocation counters, all five benchmark pairs and their checksums, raw measurement CSVs, source identity and CTest outcome.
- `receipts/serial/`: authenticated fresh GNU32/nesting0 build and candidate/reference runtime receipts for RA37 frozen1 and RA4 legacy; strict comparisons cover twelve history files.
- `receipts/dm-sm/`: matching GNU35/nesting1 builds and corresponding MPI1/OMP1, MPI1/OMP2, MPI4/OMP1 RA37 and MPI4/OMP1 RA4 runtime receipts; strict comparisons cover 34 histories. All rank logs succeeded. OMP2 baseline/candidate proofs identify the actual LW/SW callback and both active workers.
- `scripts/oracle/`: exact scratch CMake, fixture generator, allocation interposer and oracle/profile/benchmark runners.
- `scripts/serial/`, `scripts/dm-sm/`: exact frozen source staging, build and bounded run/comparison scripts.
- `scripts/omp/`: diagnostic GOMP callback probe, smoke source and symbol/CPU-time proof validator. The shared object is rebuilt from source and hashed in each OMP2 receipt.
- `scripts/shared/`: exact selected-column runner imported by the bounded candidate scripts.
- `failures/`: preserved environment/configuration/staging/namelist failures and their corrections. None required a production physics change.

The exact archived scripts retain the absolute paths used for these measurements. They document and reproduce the authenticated local experiment; a different installation must materialize the named scratch layout and dependencies or deliberately adapt the paths. Model restarts/inputs are required separately, and all input identities are recorded. The source paths under `build/` name isolated trees, not the live or running model source.

## Reproducing the column oracle

Materialize the original adapter with `git show 792f36b6bbc442f0db37b5cb9fdf19dd33600082:WRF/phys/module_ra_rrtmgp.F` into scratch `base_module.F`. The archived CMake links this independently compiled module against the same vendor/support objects as the candidate and uses the baseline-interface preprocessor branch of `WRF/test/rrtmgp/test_workspace.F90`. Build separate Debug and Release directories. `run_oracle.py` must have both binaries present, and the complete receipt must contain all four Debug/Release × frozen0/1 cases; `verify_receipts.py` rejects missing cases.

For instrumentation, configure a separate build with `WORKSPACE_INSTRUMENT=ON`. Before relinking the profiled candidate executable, apply `objcopy --globalize-symbol=__module_ra_rrtmgp_MOD_ensure_sw_diagnostics` to its scratch `candidate/libtest_rrtmgp_adapter.a`. This exposes only the diagnostic helper to the scratch `dladdr` counter; production/vendor source is unchanged. The archived `profile.c` counts actual vendor init/allocator entries and malloc/realloc within adapter calls. `run_profile.py` records cold/fresh and warmed calls; call four of the initial 1×3 shape is the warmed changing-state comparison.

`make_bench.py` derives the separate benchmark fixture from the checked-in test source. The fixture makes 1,500 changing daylight calls per phase at 1×60, always requests all four SW predelta outputs and includes native dry mass/rain/CFC inputs. `run_benchmark.py` runs five interleaved original/candidate pairs in each frozen mode, timing only column calls. The retained medians/ranges and checksums support modest column-level changes, not a full WRF speedup claim.

## Full-model guardrails and corrected attempts

Fresh source/build/output trees preserve the tested and running baseline sources. GNU serial configuration is byte-identical between reference/candidate (choice32/nesting0); GNU MPI/OpenMP likewise uses choice35/nesting1, MPICH4.2 ch3:sock, the same NetCDF/compiler/dependencies and flags. Each case authenticates its source/executable/configuration and hashes inputs, checkpoint, runtime assets and externally selected coefficients/table before and after execution. Every history variable, including character data and NaN payloads, and every global/variable attribute is independently compared by raw bytes; whole-file SHA-256 also matches all 46 files.

RA37 runs the same 12:00 checkpoint through 12:11 with frozen1/audit OFF. RA4 runs through 12:01 with frozen0/table empty. MPI1/OMP1 and MPI4/OMP1 use `numtiles=1`; MPI1/OMP2 uses `numtiles=2`. Candidate comparisons use the corresponding reference layout, so inherited MPI1-versus-MPI4 differences are outside the noninterference verdict. The diagnostic-only GOMP wrapper preserves the original function/data/team/flags and records worker IDs plus thread CPU time; disassembly identifies the callback that calls both LW and SW wrappers.

The first CTest invocation passed95/103 and failed eight for missing trace-thread environment, a large fixture exceeding the inherited stack, and an absent ignored worktree `build/` directory. With the existing fixture prerequisites supplied (`OMP_NUM_THREADS=1`, `OMP_STACKSIZE=64M`, process stack64MiB, worktree `build/` created), all eight reruns passed. The first baseline MPI build failed before compilation because MPICH wrappers were absent from PATH; its retry passed with the correct dependency prefix. Candidate configuration was stopped before compilation when generated `DM_CC=mpicc -cc=$(SCC)` differed from reference `mpicc`; mirroring that exact line restored complete configure byte equality. Initial serial staging omitted unused `ndown.exe`/`tc.exe` assets; the immutable-input guard stopped it before execution, and corrected staging included them.

The first MPI namelist used `num_tiles`, confusing a driver argument with the Registry namelist key. WRF rejected it before integration. The failed namelist/log are retained; fresh v2 cases use verified `numtiles` and their corrected hashes. RA4 frozen1 would violate the existing paired-RA37 guard, so both actual RA4 references/candidates correctly use frozen0/table empty.

No 24-hour rerun or forecast-accuracy metric is claimed here. Intel was not tested. No commit or publication was performed when these receipts were captured.

During curation, a rebuild was found to have restored local visibility for the private SW diagnostic helper, making its profiler subcounter unobservable. The scratch symbol was globalized again, its dynamic export verified, and all four profiler cases rerun. Corrected receipts show eight cold SW diagnostic allocations (8,400 requested bytes) and zero warmed allocations; total/vendor counters are unchanged, and both instrumented original/candidate output snapshots still match byte for byte. `verify_receipts.py` requires the nonzero cold count, preventing an unobservable zero from passing. No production source or timing benchmark was changed.
