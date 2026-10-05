# RFMIP reference lineage archive

This package preserves a read-only audit of the historical lineage behind the retained RFMIP `RTE-RRTMGP-181204` files. The report and receipts distinguish authenticated reference bytes and coefficient ancestry from the still-unknown exact source/coefficient pair that generated the historical outputs. No NetCDF payloads, failed retrieval routes, solver results, builds, or model runs are included here.

Read [the historical provenance report](report.md) for the findings and limits. In brief, SW reference files match the June 2023 repository replacement and the pinned snapshot; LW reference files match later May 2024 updates. The RSD reference bytes were retrieved from an ESGF replica at version `20191007`, while the raw FILE PID checksum in this archive identifies RSU. The official RTE+RRTMGP v1.0.0 SW coefficient bytes are authenticated to their Git blob, but neither that release nor the date-adjacent `181204` code candidate is proven to have generated the retained outputs. The exact historical generator remains unauthenticated.

The package retains an earlier local inventory and residual report as predecessor receipts, plus the later causal inventory that records the strict-gate counts: 104,071 current-reference failures (52,972 RSD and 51,099 RSU) and 155 old-solar sensitivity failures (116 RSD and 39 RSU). These are inherited historical counts; this package does not rerun or recount them. The independent provenance-review receipt is a scoped independent review of the current joins; direct file identity is recorded in the linked PID/Git receipts. The common 29 non-solar coefficient variables compare exactly, but this does not authenticate the full historical input or all loader paths.

## Integrity check

The standard-library verifier validates the sealed package roster and hashes, parses the raw PID responses, and checks joins among the PID, replica receipt, reference-byte inventory, Git trees/commits, solar-vector receipt, and coefficient retrieval. It needs no network, NetCDF package, or numerical library:

```sh
python3 -I -S validation/rrtmgp37/rfmip-reference-lineage/verify.py
```

## Optional local file check

If the three SW coefficient files and retained reference directory are already available locally, the optional checker accepts explicit paths, validates their recorded hashes, verifies exact historical/current non-solar variable intersections and the 224-element old-solar to counterfactual-quiet vector, and checks all four reference-file hashes. It does not fetch files or run a solver:

```sh
python3 validation/rrtmgp37/rfmip-reference-lineage/check_local_files.py \
  --historical-coefficient /path/to/rrtmgp-data-sw-g224-2018-12-04.nc \
  --current-coefficient /path/to/rrtmgp-gas-sw-g224.nc \
  --counterfactual-coefficient /path/to/rrtmgp-gas-sw-g224-old-solar-counterfactual.nc \
  --reference-dir /path/to/rfmip-clear-sky/reference
```

The checker requires Python NumPy and `netCDF4`. It only performs local array/hash comparisons. Exact historical source-plus-coefficient generation provenance, the 155 strict SW reference failures, and physical/observational accuracy remain unresolved.
