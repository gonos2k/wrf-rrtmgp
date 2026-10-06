# Curated one-step MPI decomposition evidence

This scratch bundle links the official pristine WRF v4.8.0 one-step MPI1/MPI4 comparison, the PR21 x-only MPI2 comparison, owner-bounded PRE/POST captures, local amplification replay, and the corrected stored-field visualization. It contains compact receipts and a narrow selected stencil; large model histories and executables remain at their original paths and are SHA-256 indexed in `evidence-index.json`.

## What the bounded comparisons establish

The official WRF source is commit `06d4240ae989cc3e50af412bb472df3d9048783c` (configure SHA `5f06ce4a…`). The GNU/MPICH pristine binary SHA is `865a687d…`; the archived executable and build output are byte-identical. From one common 12:00 checkpoint (SHA `943a53db…`), with one 60-second MP27/RA4/4 step to 12:01, official MPI1 and MPI4 outputs have 202 common same-shape/type variables: 139 compare exactly and 63 differ. The complete per-variable records are retained in `receipts/pristine-full-history-comparison.json` and summarized in `receipts/pristine-mpi1-mpi4-summary.json`. Thus decomposition-dependent differences occur in the official WRF/UDM/RA4 setup itself; this does not identify their first source or cause.

The PR21 MPI2 x-only run changes only the decomposition fields to `nproc_x=2,nproc_y=1`; it uses binary SHA `6c0c1e3e…`, source commit `e73b353f…`, and the same 12:00 checkpoint, wrfinput, and wrfbdy hashes as recorded in the index and run receipt. Its one-step numeric history arrays equal the MPI4 2×2 result exactly, while the comparison records expected processor-layout metadata differences (`NTASKS_TOTAL`, `NTASKS_X`, or `NTASKS_Y`). Comparisons to MPI1 and the MPI2 y-only layout have numeric differences and are preserved with full metrics and metadata in `receipts/xsplit-vs-mpi1.json` and `receipts/xsplit-vs-mpi2-ysplit.json`. These are bounded comparison outcomes, not a claim that MPI passes or a source-level explanation.

## Owner-bounded captures and local amplification

The final v3 diagnostic capture run is retained by reference and receipt. It records one owned PRE/POST stencil per selected global cell and rank, with pointer bounds checked; the instrumented history outputs match their uninstrumented MPI1 and MPI4 histories byte-for-byte across all 204 compared variables. The usable instrumented binary is the final v3 executable (SHA `e95cdf69…`). No v1 instrumented executable is claimed as retained.

`stencils/owner-neighbor-k2.json` extracts the current owner cell `(i=147,j=99,k=2)` and adjacent locations from raw v3 files. At target `(147,99,2)`, PRE NC is `-0.013483073562383652` in MPI1 and `+0.01819402538239956` in MPI4. The neighboring `(146,98,2)` values are about `1102.6`; they are a different cell and are included only to prevent accidental substitution. POST target NC is zero in both captures. These are raw scalar values with no unit conversion.

The separate local `adjust_number_concent` replay shows that the captured sign/magnitude change can be strongly amplified by the helper's thresholds and nonlinear number adjustment. Its receipt and CSV are included, with their own input/source hashes. It only demonstrates local amplification; it does not identify the upstream origin or cause of the MPI divergence.

## Plot and interpretation limits

`plots/mpi4-minus-mpi1-first-step.png` and PDF show the first-step MPI4−MPI1 spatial differences at 12:01, with all grid cells included and x/y decomposition seams marked. The script and receipt are included. QNCLOUD and QNCCN are plotted as stored-field differences in Registry-declared units; Registry metadata says `# kg(-1)`, but the UDM producer/consumer number-concentration convention is unresolved. No density conversion or particle-number-density claim is made.

All runs here cover one 60-second step only. The histories are separate coupled trajectories after decomposition-specific arithmetic, not same-state radiation perturbations, observational comparisons, or evidence of forecast readiness. The first divergent operation/source has not been isolated.

## Separate SR port issue

The pristine-versus-PR21 one-step comparison has 201/202 common fields equal, with only `SR` unequal; the full result is in the official comparison receipt. This is a separate UDM surface-rain row indexing issue, not evidence about the source of MPI decomposition sensitivity. The separate erratum and targeted row test are linked under `receipts/`; do not merge their interpretation with the MPI stencil or local-amplification evidence.

## Reproduction/provenance map

- Official pristine run commands and successful rank logs: `build/pristine-wrf-dm-sm/runtime-preflight/run_case.sh` and `restart12-mpi{1,4}-receipt.json` (compact copies under `receipts/`). Both ran with `OMP_NUM_THREADS=1`, MPICH 4.2, and the same checkpoint, input and boundary files.
- MPI2 x-only run details and complete comparison outputs: `receipts/mpi2-xsplit-run-receipt.json`, `receipts/xsplit-vs-*.json`.
- Final instrumented v3 source patch/binary/capture hashes and history comparisons: `receipts/capture-v3-run-receipt.json`, `receipts/mpi*-vs-uninstrumented.json`.
- Large executable, history, checkpoint, wrfinput, wrfbdy, and namelist path/hash/byte counts: `evidence-index.json`.
