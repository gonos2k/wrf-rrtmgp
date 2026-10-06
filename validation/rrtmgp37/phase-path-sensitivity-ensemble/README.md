# Paired-seed sensitivity replay for one selected column

This package records a 32-seed paired sensitivity experiment using the independent offline RRTMGP column replay. It replays one actual RA37 mode-1 selected state at WRF point `(i,j)=(169,80)`, corresponding to SW step 731 at source time 43,800 s (12:10 UTC) and its matching LW capture. The column has 39 native layers; replay inputs are padded to 40 SW and 47 LW engine levels. This is a sensitivity result for one opaque column, not a domain average, forecast-feedback experiment, or accuracy assessment.

Each phase first passed a strict captured-seed comparison: SW compared all 46 output sections and verified its V9 recorded MCICA mask; LW compared all 20 sections. V8 LW has no recorded mask, so the captured-mask check is explicitly unavailable. The subsequent 32 manufactured seeds are distinct from the captured seed in each phase. Each seed has one baseline and four paired variants under the same generated mask: `CF0_UNIFORM`, `GRID_UNIFORM`, `ICE160`, and `ICE140`. This is 64 seeded baselines plus 256 variants, in addition to two strict anchor calls: 322 calls total.

`CF0_UNIFORM` adds grid-mean rain/snow optical depth at zero-cloud-fraction layers while leaving current precipitation/cloud optics untouched at CF-positive layers. `GRID_UNIFORM` replaces the existing mask-conditioned precipitation occurrence with the grid-path contribution. Neither sets cloud fraction to one nor divides in-cloud path by cloud fraction. `ICE160` and `ICE140` change the applied cloud-ice diameter only at the four active positive-IWP levels whose original, unclamped diameter exceeds the LUT's 180 µm upper limit; both probes remain inside the supported LUT coordinate. These are bounded counterfactuals, not estimates of the true out-of-range optics.

The run receipt and independent verification check the actual `ACTIVE_SAMPLE_SEED` fields and logs for every sample, 32 unique active seeds per phase, equal baseline/variant masks for each seed, unchanged gas and frozen G/H optics, unchanged precipitation optics in ice-size probes, and unchanged cloud/precipitation optics in the CF0-only probe. All result fields are parsed and finite. The independent verifier also checks the 4-level ice-size edit and matching applied diameters. All inputs and sidecars are byte-identical to their recorded pre-run hashes after execution. Full per-call logs/results remain at the path recorded in `execution/OUTPUTS_RETAINED_AT.txt`; `execution/output-hashes.sha256` contains hashes for every seeded result and log.

## Paired differences

Values below are variant minus same-seed baseline. Surface downward flux uses the bottom `DN` boundary; TOA upward flux uses the top `UP` boundary. Heating is the maximum absolute per-level `HR` difference in K/day for each seed. Means and sample SDs summarize 32 paired outcomes. The machine-readable `independent-verification.json` contains the full per-level flux/heating means, SDs, MCSEs, and intervals, plus scalar boundary summaries and sample ranges.

| Phase | Variant | Surface DN Δ, W/m² (mean ± SD) | TOA UP Δ, W/m² (mean ± SD) | Max abs ΔHR, K/day (mean ± SD) |
|---|---|---:|---:|---:|
| LW | CF0_UNIFORM | +7.4672 ± 0.435 | −3.84e−10 ± 0 | 0.5656 ± 0.1208 |
| LW | GRID_UNIFORM | +7.5475 ± 0.479 | +1.29e−10 ± 0 | 0.6859 ± 0.1791 |
| LW | ICE160 | +8.21e−11 ± 9.80e−11 | 0 ± 0 | 2.2701e−5 ± 0 |
| LW | ICE140 | +1.86e−10 ± 2.22e−10 | 0 ± 0 | 5.1634e−5 ± 0 |
| SW | CF0_UNIFORM | −0.1521 ± 0.0322 | +0.05184 ± 0.00401 | 0.002932 ± 0.001416 |
| SW | GRID_UNIFORM | −0.1661 ± 0.0578 | +0.05557 ± 0.0142 | 0.002908 ± 0.001264 |
| SW | ICE160 | −4.771e−5 ± 5.06e−6 | +6.943e−5 ± 2.15e−6 | 1.2192e−5 ± 1.73e−8 |
| SW | ICE140 | −1.091e−4 ± 1.16e−5 | +1.5882e−4 ± 4.92e−6 | 2.7884e−5 ± 3.96e−8 |

The exported t(0.975,31) bands are **approximate Monte Carlo mean intervals conditional on this fixed state and deterministic seed list**. Deterministic seed keys do not demonstrate independent samples; these intervals are not distribution-free guarantees, empirical-observation confidence bounds, or forecast uncertainty. Reported zero variance for some LW diagnostics means the 32 sampled outputs were identical at the shown precision; it does not imply general invariance.

## Provenance and rerun

`execution/receipt.json` records all input, coefficient, sidecar, table, executable, and source hashes and the 322-call status. `execution/independent-verification.json` recomputes paired statistics directly from each per-seed result file and verifies the post-run immutable hashes. `execution/per-seed-paired-deltas.csv` is the compact per-seed projection. The exact seed-override source/patch and base reference source are included. The compiled executable is not bundled: it remains at the scratch path recorded in `execution/executable-provenance.json`, with SHA256 and byte count cross-checked against the run receipt. The run used GNU Fortran through `/usr/bin/f95`, the standalone CMake build settings are recorded in the original build cache at `build/udm-phase-path-sensitivity-work/ensemble-build/CMakeCache.txt`, and shared libraries were resolved with the root dependency bundle under `build/deps/root/usr/lib/x86_64-linux-gnu`.

From the workspace root, the original bounded execution command was:

```sh
export LD_LIBRARY_PATH="/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
python3 build/udm-phase-path-sensitivity-work/ensemble/run_seed_ensemble_bounded.py \
  --execute \
  --exe build/udm-phase-path-sensitivity-work/ensemble-build/reference_column \
  --data-dir build/pr-wrf-rrtmgp/WRF/run \
  --capture-dir build/udm-selected-real-audit/on-only-20261003-v1/audit-on/run/capture \
  --sw-sidecars build/udm-phase-path-sensitivity-work/prepared-v2 \
  --lw-sidecars build/udm-phase-path-sensitivity-work/prepared-lw \
  --table build/pr-wrf-rrtmgp/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc \
  --out build/udm-phase-path-sensitivity-work/ensemble/ensemble-32-final-retry1
```

The executed bounded script differs from the reviewed runner only by a 180-second timeout on each standalone subprocess; both exact scripts are included. The first attempt is retained as `preflight-failure-no-netcdf-*`: it stopped at the first anchor because `libnetcdf.so.19` was missing from the runtime path, before any radiation call. `execution/superseded-endpoint-check-v0-not-valid.json` documents a later diagnostic indexing error. Its first output had been overwritten during correction; the bundled JSON records `original_output_retained: false` and is reconstructed from preserved results, not the original executed receipt. The successful retry used the dependency path above. Earlier plan drafts are preserved under `not-executed/` and explicitly were not run.

The result supports only a conditional sensitivity statement for the captured column, state, and chosen policy variants. It does not validate whole-domain cloud or precipitation behavior, resolve the physical correctness of occurrence assumptions or out-of-range ice properties, or demonstrate forecast benefit or error.

The package's compact consistency check can be run with `PYTHONDONTWRITEBYTECODE=1 python3 validation/rrtmgp37/phase-path-sensitivity-ensemble/verify_index.py` from the source root. To verify the retained full run output tree while it remains at its recorded scratch path, run `sha256sum -c validation/rrtmgp37/phase-path-sensitivity-ensemble/execution/output-hashes.sha256` from the workspace root.

The root `.gitattributes` entries are scoped to this evidence package: capture and sidecar bytes, paired CSV, and output-hash manifest are stored without text conversion. The archived build cache and patch are byte-preserved; only their recorded blank-line/trailing-space diagnostics are excluded from `git diff --check`.
