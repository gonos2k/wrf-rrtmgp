# Bounded Intel WRF compatibility validation

The fresh Intel serial `em_real` build and both one-minute restart compatibility smokes passed. This verifies the pinned workspace source with ifx/icx2025.3.3 and matching Intel NetCDF; it does not establish cross-compiler bitwise parity, Intel MPI/OpenMP full-model behavior, longer forecast behavior, or a universal stack-size recommendation.

Source is exactly detached `6f0f3ea3e73fbd43325fdad1050b000eecd70138` at `build/udm-workspace-intel-serial/source`; no production/vendor/compiler flags were changed. Configure serial76/nesting0 uses ifx/icx, real-size32/i4, O3, fp-model precise, big-endian unformatted I/O, and NetCDF4/HDF5. Command `csh -f ./compile -j 12 em_real` returned0 and built all four executables in183seconds. The source6639-entry manifest, configure bytes, and all870 shared compiler/runtime/NetCDF headers/modules/libraries remained unchanged. Make's25-object vendor list matches actual objects. Executable ldd paths resolve under the recorded controlled environment. Generated build files remain isolated and uncommitted; the postbuild full artifact manifest covers9157 entries.

| Artifact | SHA256 |
|---|---|
| configure.wrf | `55a0813e82e0f572c820430feea58d29b1c2eb6c29a6d4586cad644a6e6bd440` |
| wrf.exe | `f8bbb80f6745bcc02efc12a8be16f32db8a3e547d5ad933c24f8dc99b8ec7cae` |
| real.exe | `86f95287166b01f15f3202b74b9c5788e7c62975acc5a655f3716e290d4a4ed5` |
| ndown.exe | `3d186dac0eec9f25cea9714030f4fa7b3563ec4b4bd7eadbf546bde3eb4c7874` |
| tc.exe | `52832df82546489ace393df0f25d9665792f6f97c27911980f953196f0842b43` |

Build source/config/dependency/executable manifests and exact original/corrected launcher scripts are retained under `build/udm-workspace-intel-serial/` and `build/udm-intel-feasibility/`. The originally approved environment and tool probes are in `build/udm-cmake-intel-review-current.md` and the inventory receipt.

Both runtime cases use materialized own copies of the approved12:00 checkpoint, wrfinput, wrfbdy, selected I/O field list, all static runtime files, coefficient files and frozen table. Only fresh Intel executable copies, bounded end minute1, and own immutable optics paths are substituted. Audit/trace environment is empty. RA37 has LW/SW37, mp27/use_mp_re1, frozen1. RA4 has LW/SW4, frozen0/table empty. Source, config, executable copies, namelist, all input/runtime assets, coefficients and frozen table hashes are unchanged pre/post. All870 shared dependencies were also rehashed unchanged after the runs.

| Case | Result | History variables | Numeric arrays | Attributes |
|---|---|---:|---:|---:|
| RA37 frozen1,12:00→12:01 | return0, SUCCESS COMPLETE WRF | 211 | 210, all raw values finite | 1342 |
| RA4 legacy,12:00→12:01 | return0, SUCCESS COMPLETE WRF | 208 | 207, all raw values finite | 1324 |

Each case produced exactly one12:01 history. Every variable's dtype/dimensions/shape, complete attributes, raw byte count and raw-array SHA256 are retained, including character Times and integer seed arrays. Physical history geometry matches the approved289×189×39 case. Selected RTHRATEN/RTHRATLW/RTHRATSW/SWDDIR/SWDDIF/GSW/SWUPB/ALBEDO fields are present. Intel writes NETCDF4 here; the earlier GNU reference used NETCDF3_64BIT_OFFSET. Native `RANDOM_SEED(SIZE=...)` is2 for Intel and8 for GNU, so seed_dim_stag and six ISEED* shapes differ; the complete native metadata is preserved. Registry/registry.stoch explicitly defines that dimension via RANDOM_SEED, and separate intrinsic probes confirm2/8. No data bit comparison or forecast-quality conclusion is claimed between compilers.

Final runs and receipts:

- `build/udm-workspace-intel-runtime/ra37-stack1g-v3/receipt.json` and `history-inspection.json`; history SHA `446eef53443fdb8246d229671d1235850918d509986971c5c02b9f3ac070cbff`.
- `build/udm-workspace-intel-runtime/ra4-stack1g-v2/receipt.json` and `history-inspection.json`; history SHA `8565537e38a4359d7043b753ceb55b2555f84f150fca40b13de3f7f69cb8ffb7`.
- Both `live-process-evidence.json` files verify actual inferior `/proc/<pid>/limits` stack1073741824bytes, exact executable hash/cwd, and process status. Worker OMP stack remains64MiB; these are serial binaries.

## Preserved failures and evidence-based resource adjustment

The first RA37 run at64MiB and RA37/RA4 controls at512MiB failed with Fortran SIGSEGV174 in `solve_em_`, before any radiation call. They failed at the same address0xf2d65b, a PUSH instruction after automatic stack allocations. Their failed receipts, full logs and unchanged hashes are retained at `ra37/`, `ra37-stack512-v2/`, and `ra4-stack512-v1/`; they are not overwritten by passing cases.

A separately approved GDB entry-only probe (`gdb-solve-entry/`) used the exact same failed executable/input and512MiB limit. It stopped at solve_em entry, recorded actual child /proc limits, then stopped immediately before the faulting PUSH and killed only that inferior before integration. Actual halo memory bounds were i=-3:294 (298), k=1:40, j=-3:194 (198), with moist8/scalar4 and chem/tracer/dfi_moist/dfi_scalar1. Entry-to-before-fault stack allocation was exactly568806032bytes (542.4557MiB), already31935120bytes above the actual512MiB limit. Initial caller stack mapping was about14.84MiB.

The full assembly identifies50 dynamic RSP assignments before the fault. With S=298×40×198×4=9440640bytes and T=298×198×4=236016bytes, the compiled frame equals60S+10T+7472 alignment/fixed/push bytes, exactly matching GDB. Generated i1_decl.inc and solve_em.F contain the corresponding automatic arrays; solve_em's source explicitly notes their potential stack cost. All RSP-change instructions, the preceding40 fault-context lines, raw full disassembly, actual counts/bounds, source hashes and formula are retained in `gdb-solve-entry/stack-frame-analysis.json` and associated text/JSON artifacts.

Kernel dmesg access is denied; no independent kernel OOM-log claim is made. The runtime reports SIGSEGV174 rather than an OOM SIGKILL, and there is no core in the case directories or /var/crash (kernel core pattern routes to apport). The larger measured frame explains why512MiB was insufficient. Root authorized a single evidence-based1GiB limit for this case; both unchanged-binary smokes passed. No heap-array flag, source edit or rebuild was used. This is a resource requirement observed for this particular compiled case, not a recommended universal WRF setting or a radiation-port failure.

Two orchestration mistakes are also preserved transparently. The first build validator expected a configcheck success phrase that this WRF target never emits; the actual compile succeeded, all checks passed, and a separate actual configcheck returned0. `build-receipt-v1-validator-fail.json` and its exact launcher are preserved; correcting that validator did not rebuild. The first successful-run inspector required GNU and Intel seed-array metadata equal; both WRF runs had already succeeded with finite arrays. Their `receipt-v1-inspector-fail.json` and exact launcher are retained. Only the inspection was corrected to record the intrinsic seed-size difference while checking physical layouts and all raw numeric arrays; neither WRF run was repeated.

Earlier Intel standalone11-test probes also preserve the initial8MiB stack failures and unchanged-binary64MiB pass. All evidence remains in isolated build directories. No commit or publication was performed by this task; root review is next.
