# Stratified one-column phase-path sensitivity (32 paired seeds)

This evidence-only bundle records a bounded offline sensitivity experiment at six actual captured WRF columns. It does not change production code, and it does not establish forecast accuracy, a domain-wide bound, or the physical correctness of the experimental hydrometeor optics/precipitation choices.

## Scope and execution

The captured states are `cf0_rain_136_48`, `material_cf0_snow_103_156`, `ice_clip_low_132_35`, `ice_clip_high_170_72`, `clear_control_126_87`, and `daylight_liquid_268_27`. Each state has an unchanged captured LW and SW input/raw record. The seed-override reference executable was first checked against the ordinary captured replay for all 12 phase/state anchors (20 LW and 46 SW sections, exact MCICA mask). The matrix then used 32 deterministic positive 31-bit seeds, paired by seed between each baseline and eligible variant.

There were 1,152 unique engine calls: 384 baseline and 768 variant calls across 24 eligible state/phase/variant arms. The final v4 run reused 388 already successful calls after offline revalidation of their complete inputs, logs, outputs, and corrected source-derived validators, and executed 764 new calls. Successful jobs were not re-run. Total charged execution time was 220.465871 seconds under the 1,800 second cumulative cap and 180 second per-call timeout. The execution receipt records each call’s arguments, input/sidecar paths and hashes, stdout/result paths and hashes, return code, active sample seed, and status. The full per-call outputs remain in the external scratch run directory; this package retains the complete per-call digest ledger, not the gigabyte-scale output payloads.

Differences are variant minus the same-seed baseline. Reported fields are surface-down flux, TOA-up flux, and maximum absolute layer heating-rate difference. The table below gives sample mean ± sample standard deviation for each 32-seed arm. The accompanying JSON retains MCSE and approximate Student-t(31) intervals. Those intervals describe the finite deterministic seed list conditional on one captured column; they do not prove seed independence and are not physical-accuracy or observational confidence intervals.

| State | Phase | Variant | Surface down Δ (mean ± SD) W m⁻² | TOA up Δ (mean ± SD) W m⁻² | Max abs HR Δ (mean ± SD) K day⁻¹ |
|---|---|---|---:|---:|---:|
| cf0_rain_136_48 | LW | cf0_uniform | 0.331953 ± 0.339642 | -1.24134 ± 0.00571174 | 2.16019 ± 0.208405 |
| cf0_rain_136_48 | LW | grid_uniform | 0.338977 ± 0.352996 | -1.24149 ± 0.00597968 | 2.15594 ± 0.216684 |
| cf0_rain_136_48 | SW | cf0_uniform | -2.24395 ± 1.1881 | -1.3484 ± 1.04026 | 0.34451 ± 0.00991882 |
| cf0_rain_136_48 | SW | grid_uniform | -2.25428 ± 1.2091 | -1.34267 ± 1.04857 | 0.342955 ± 0.0051778 |
| ice_clip_high_170_72 | LW | cf0_uniform | 0.0412854 ± 0.00745241 | -4.35978e-06 ± 8.05191e-08 | 0.0805173 ± 0.00445146 |
| ice_clip_high_170_72 | LW | grid_uniform | 0.120787 ± 0.0478094 | -5.57054e-06 ± 1.72289e-06 | 0.404012 ± 0.165503 |
| ice_clip_high_170_72 | LW | ice140 | 0.00245079 ± 0.00106332 | -0.360087 ± 0.00320478 | 0.624054 ± 0.00366147 |
| ice_clip_high_170_72 | LW | ice160 | 0.00108982 ± 0.000472093 | -0.169088 ± 0.00149911 | 0.289994 ± 0.00171614 |
| ice_clip_high_170_72 | SW | cf0_uniform | -0.107909 ± 0.0167095 | 0.020616 ± 0.00225204 | 0.0134315 ± 0.00226304 |
| ice_clip_high_170_72 | SW | grid_uniform | -0.115726 ± 0.111387 | 0.052991 ± 0.0124121 | 0.0178024 ± 0.00425996 |
| ice_clip_high_170_72 | SW | ice140 | -0.752426 ± 0.0894911 | 1.20923 ± 0.0709736 | 0.0411366 ± 0.000267022 |
| ice_clip_high_170_72 | SW | ice160 | -0.33604 ± 0.0403039 | 0.543633 ± 0.032056 | 0.018694 ± 0.000129796 |
| ice_clip_low_132_35 | LW | cf0_uniform | 0.14564 ± 0.019832 | -0.0263359 ± 0.00648613 | 0.0641402 ± 0.00787376 |
| ice_clip_low_132_35 | LW | grid_uniform | 1.35512 ± 0.965788 | -0.736289 ± 0.463976 | 1.93266 ± 0.675221 |
| ice_clip_low_132_35 | LW | ice140 | 0.499288 ± 0.130662 | -1.72997 ± 0.189423 | 1.46623 ± 0.0307191 |
| ice_clip_low_132_35 | LW | ice160 | 0.242775 ± 0.0635557 | -0.831884 ± 0.0929921 | 0.675891 ± 0.0130737 |
| ice_clip_low_132_35 | SW | cf0_uniform | -0.0165209 ± 0.00100026 | 0.0082653 ± 0.000384396 | 0.00140597 ± 0.000232902 |
| ice_clip_low_132_35 | SW | grid_uniform | -0.173575 ± 0.149947 | 0.0735394 ± 0.115416 | 0.0162107 ± 0.00680075 |
| ice_clip_low_132_35 | SW | ice140 | -0.939906 ± 0.0146905 | 1.19963 ± 0.0127035 | 0.0815719 ± 5.81618e-05 |
| ice_clip_low_132_35 | SW | ice160 | -0.423147 ± 0.00683783 | 0.547442 ± 0.00592227 | 0.0390459 ± 2.45074e-05 |
| material_cf0_snow_103_156 | LW | cf0_uniform | 0.0833103 ± 0.0477194 | -3.00124e-05 ± 1.0323e-05 | 1.1479 ± 0.0991361 |
| material_cf0_snow_103_156 | LW | grid_uniform | 0.146951 ± 0.104661 | -0.000249175 ± 0.000199626 | 1.96309 ± 0.720924 |
| material_cf0_snow_103_156 | SW | cf0_uniform | -0.0419632 ± 0.000806713 | 0.0251293 ± 0.000527545 | 0.00121398 ± 0.000114706 |
| material_cf0_snow_103_156 | SW | grid_uniform | -0.0622332 ± 0.0847402 | 0.0376246 ± 0.0530507 | 0.00852069 ± 0.00452042 |

## Validator history

The three stopped receipts are intentionally retained; each run stopped at the first validator error while the reference process returned success. Offline inspection established validator contract mistakes, not engine failures, and corrected each before reusing its successful outputs:

- v1’s GRID-uniform validator incorrectly required the combined `CLOUD_TAU` output to remain unchanged. Source semantics show `CLOUD_TAU` is cloud plus sampled precipitation; the exact forward reconstruction is baseline combined tau = GRID variant cloud-only tau + baseline precipitation tau, with the variant precipitation tau zero.
- v2 treated the source-defined SW zero-path tau floor (hex `0x1.2725dd1d48ae7p-60`) as leakage. The corrected check enforces the floor at source-defined zero-path support, independent of CF, with exact CF0-variant masking in cloudy layers and positive-path support checked separately.
- v3 required the baseline to emit `ICE_DIAMETER_RAW`, which it does not. For the ice variants, raw diameter is checked against the input-derived `2*REI`; applied/used diameter and inactive levels are checked separately.

Each original failure receipt and its erratum/readback are preserved unchanged. The `.gitattributes` file disables text conversion only for byte-sensitive captured traces, sidecars, and the archived source patches; their exact bytes are checked by the index verifier. The final receipt records offline revalidation of the 388 reused job outputs and successful execution of the remaining 764 jobs. Root’s independent v4 readback performed 6,136 checks over all 1,152 job outputs/logs, recomputed all 768 variant metric rows and 24 arms, verified raw-ice diameter from input, and found maximum summary roundoff of `4.440892098500626e-16`.

## Reproduction and verification

`run/plan-v4.json` pins the approved plan digest `2cddcde18b70a3400ce0ef9bbb11c8eb308a7b1ac64497240b8865e89947108c`. The runner, sidecar generator, diagnostic source, mechanical patch, compiler script, command helper, comparator, exact captured inputs/raw records, and sidecars are included. Original captured production/reference result files remain external, with hashes in the plan. The compiled executable, coefficient libraries/tables, and full per-call result files also remain external; their expected byte counts and SHA256 values are recorded in the plan, receipt, and `run/provenance.json`.

Run `python3 verify_index.py` from this directory to validate archived-file hashes and the receipt/plan/readback identities and counts. That standard-library verifier is relocatable. The execution and compile scripts retain the original workspace-specific paths, so a full recomputation requires the pinned RRTMGP/NetCDF build assets and those paths to be restored or carefully adapted; place any new output directory outside this archive. Do not overwrite the retained receipts.
