# Current-source RA4 regression and RFMIP solar attribution

These are two separate comparisons. The first checks preservation of the
existing WRF UDM27/RRTMG4 path. The second investigates a small clear-sky SW
residual already present in the pinned upstream RRTMGP executable. Neither
comparison approves UDM cloud optics or observational forecast accuracy.
The [publication manifest](publication-manifest.json) pins the verbatim
scratch evidence copies. Original receipts and older failed results remain
unchanged. The publication changes no production Fortran.

## Fresh current-source RA4 comparison

A clean, isolated serial `em_scm_xy` build used the frozen source compiled
from `d05c97b4f26be0ca21867051b50d6fca00261d51`. Its Fortran matches the
publication review base `7ad818ed7a9fd5fc25cd1ba015bbae03f8c4c88f`.
The source copy matched 5,835 WRF manifest entries before cleanup.
GNU Fortran 13.3, default REAL32, optimization and serial settings match
the retained official WRF v4.8.0 build. The only configure-file difference
is the required RRTMGP module include path, shown in
[configure.wrf.diff](serial-ra4/configure.wrf.diff); the configurations are
not byte-identical. No official-pristine rebuild or rerun was performed.

The new executable has SHA256
`7d6526f4c509aa93d2b28c73db6c782d72e68ef76fc1658ceb360250adf03caa`.
Exactly two fresh 60-second UDM27/RRTMG4 SCM runs completed successfully.
Each matches its retained official-pristine output in all 208 variables,
dtype, dimensions and attributes. More strongly, the complete NetCDF files
have the same SHA256:

| Case | Current and official history SHA256 |
|---|---|
| control | `cc34da6667b2569063f7b302985a9e9b44dac4f4b528989255404c1a5cf9da8f` |
| mixed | `e04dd6fbd89a3df30e9d65e518d022ba2086291b6443268b7a09e293d4f4f216` |

[Final receipt](serial-ra4/final-receipt.json),
[build receipt](serial-ra4/build-receipt.json), and the
[control](serial-ra4/control-receipt.json)/[mixed](serial-ra4/mixed-receipt.json)
receipts preserve executable, inputs, runtime assets and output checks.
The full compiler stdout was not saved to a disk log; the
[build summary](serial-ra4/build-summary.log) explicitly records that
capture limitation. This is a two-case serial regression, not a general
long-forecast or compiler/decomposition guarantee.
The [independent read-only review](serial-ra4/independent-review.json)
rechecked the source, configure and generated/reference file hashes.

## Solar-spectrum-only SW counterfactual

The published `RTE-RRTMGP-181204` label is a CMIP6 source ID, not an exact
Git SHA. No exact generating source/data snapshot was established.
[Provenance](rfmip-provenance/README.md) distinguishes the public v1.0.0
candidate release from authenticated historical output provenance.
Its shared LW and SW gas/lookup arrays equal the current pinned arrays,
but the SW solar-source representation changed. The current default solar
vector differs from the older stored vector. Those facts motivated the
counterfactual; they did not themselves prove a flux cause.

The successful [stage-v7 execution](solar/stage-v7/execution.json) holds
the executable, RFMIP inputs and gas/lookup arrays fixed. Only
`solar_source_quiet`, `solar_source_facular`, and `solar_source_sunspot`
change in an isolated coefficient clone. Quiet is the old stored vector
promoted to the current dtype, and the other two spectra are zero, making
the current loader reconstruct that vector exactly. Dimensions, attributes,
all other 32 variables and default parameters are unchanged. The clone is
an attribution experiment, not a replacement production coefficient file.

Two SW invocations used the same upstream executable
`fcebb76288fec0fceba4d720f61001f495819489a975769eec7de57ca8daa74f`,
source `41c5fcd950fed09b8afe186dede266824eca7fd3`, current data
`ea788bb39876948fa8d2c235665ccff19b4686b5`, 1,800 RFMIP profiles, g224,
and the published reference's float32 output representation.
The current-spectrum control reproduced both retained current upstream
flux arrays bitwise before the counterfactual was launched.

| Published-reference residual | Current spectrum | Old-spectrum clone |
|---|---:|---:|
| rsd maximum absolute difference, W/m² | 0.0006103515625 | 0.0001220703125 |
| rsd mean absolute difference, W/m² | 7.4672560e-5 | 5.0376239e-8 |
| rsd values exceeding 1e-5 | 52,972 | 116 |
| rsu maximum absolute difference, W/m² | 0.00018310546875 | 0.000030517578125 |
| rsu mean absolute difference, W/m² | 2.3464896e-5 | 2.2313200e-8 |
| rsu values exceeding 1e-5 | 51,099 | 39 |

Solar-spectrum choice explains most of the mean absolute residual in
this controlled upstream clear-sky experiment. **Both comparisons still
FAIL the unchanged published `atol=1e-5 W/m², rtol=0` criterion.**
Successful process completion does not change that scientific comparison
result. The remaining residual's exact historical code, rounding or
toolchain contributions are unresolved; they are not assigned to a cause
without evidence. This is not a test of g112 production cloud optics,
WRF host constants, UDM conversion, McICA, precipitation or coupled state
feedback. It cannot explain the much larger cloudy 4/37 differences.

The earlier [stage-v6 failure](solar/stage-v6/execution.json) remains
preserved. Its current-spectrum control passed, but its counterfactual
failed before flux computation because the upstream example declares
`kdist_file` as `CHARACTER(LEN=132)` and truncated the long absolute path.
The corrected runner uses checked relative paths, without rebuilding the
executable or changing coefficients/tolerances. Four SW process attempts
occurred across the two stages: three completed and one failed before
calculation. None is a WRF model run. No stage was overwritten or retried
in place.
The [independent solar review](solar/independent-review.json) rehashed
the actual outputs and recomputed the coefficient and residual comparisons.

## Reproduction limits

The copied Python helpers preserve their executed versions and original
workspace paths. They are nonportable evidence snapshots, not commands
to launch from this publication directory. Raw executables, coefficient
clones, official and generated NetCDF outputs remain under the original
manifest paths. The manifests record their hashes; they are not committed
here. Reuse requires obtaining those exact inputs and deliberately staging
a fresh output directory.

Physical occurrence, LUT-clipping impact and observational accuracy remain
open. Current-runtime evidence and this source preservation comparison
should be read alongside the [policy audit](../current-policy-audit/README.md).
