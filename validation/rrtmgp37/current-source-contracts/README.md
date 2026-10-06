# Archived evidence and current-source checks

The three source-pin failures came from validators that authenticated saved
artifacts against their original producer source, `092b901bf40b5334c5497fbf75f630b255262fb2`.
Those saved manifests and results remain historical and unchanged. The workflow
checks their source pins using a side-by-side checkout at `092b901`. That commit
has the same four source blobs used by the archived activation/density contract
(`module_mp_udm.F`, `module_microphysics_driver.F`,
`module_big_step_utilities_em.F`, and `module_model_constants.F`); the archive's
older commit label is not rewritten.

The affected CI runs were 37424242648 (Nc sensitivity), 37424242659 (ice-radius
fit), and 37424242590 (activation/density). Each stopped at its saved-source
authentication gate before its intended fresh/current test; the Nc RTE replay
was skipped because its evidence prerequisite failed. The archived source pins
for UDM, the microphysics driver, host density preparation, and model constants
remain the original `092b901` blobs.

Separate fresh checks operate on the current checkout. Their receipts record
the exact working-file SHA-256 for each tested source file, along with checkout
HEAD/tree for provenance; receipts that also record a Git blob comparison use
it as supplementary context. If a source file is dirty, its working-file SHA
identifies the tested contents while HEAD/tree identify only the surrounding
checkout. The checks do not use a baked-in digest for the current UDM or
microphysics driver, so a later unrelated production edit does not invalidate
them. Changes to the tested formulas, driver policy call, constants, or
activation contract still fail the scoped checks. Activation and density
checks also compile small extracted fixtures.

The Nc workflow authenticates the saved producer evidence at the archived
source. Its fresh six-arm job is an RTE replay of those retained historical
inputs; it is not a new WRF producer capture or a current-source Nc sensitivity
result.

No source evidence, historical manifest, or historical numeric result is
rewritten by these checks. Current-source output is generated only beneath the
workflow's fresh `build/` directory. CI uploads the compact current-source
receipts and fixture logs with `if: always()`, so a failed check still leaves
its source identity and available diagnostics attached to the run. The Nc
workflow is also triggered by changes to this verifier package; its RTE job
uploads only the compact replay receipt and per-arm logs, not result arrays.
